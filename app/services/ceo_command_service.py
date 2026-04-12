"""CEO WhatsApp Command Center — handles natural-language commands from the CEO.

The CEO can manage tasks, check status, and message employees directly via
WhatsApp. Commands are parsed by OpenAI into structured intents and executed.
"""

import logging
import re
from datetime import datetime

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai_service import parse_ceo_command, _MONTH_NAMES, _extract_date_from_text, _extract_task_keyword
from app.config import settings
from app.services.employee_service import (
    get_all_employee_names,
    get_employee_by_phone,
    normalize_phone_number,
)
from app.services.messaging_service import send_whatsapp_message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Post-parse sanitization — deterministic correction layer
# ---------------------------------------------------------------------------

# Captures the first word after Tell/Ask/Message/Notify/Inform
_TELL_NAME_RE = re.compile(
    r"(?:tell|ask|message|notify|inform)\s+([A-Za-z][A-Za-z'-]{1,30})",
    re.IGNORECASE,
)

# Keywords that mean a task field is being changed
_UPDATE_KEYWORDS = {"deadline", "due date", "is now", "extend", "move the deadline", "description", "change"}


def _sanitize_parsed(parsed: dict, raw_text: str, employee_names: list[str]) -> dict:
    """Deterministic post-processing layer applied after AI/rule-based parsing.

    Fixes two known failure modes:
    1. AI returns a month name ("April") as employee_name instead of the person.
    2. AI returns "send_message" intent when the message actually contains a
       deadline/date change ("Tell X the deadline is now April 25th").
    """
    text_lower = raw_text.lower()
    emp = parsed.get("employee_name") or ""

    # ── Fix 1: employee_name is a month name → extract from "Tell <name>" ──
    if emp.lower() in _MONTH_NAMES or not emp:
        logger.warning("CEO parse: employee_name=%r looks like a month — re-extracting from text", emp)

        # Try known DB names first (longest match wins, month names excluded)
        fixed_name = None
        for name in sorted(employee_names, key=len, reverse=True):
            if name.lower() in text_lower and name.lower() not in _MONTH_NAMES:
                fixed_name = name
                break

        # Fallback: first word after Tell/Ask/Message
        if not fixed_name:
            m = _TELL_NAME_RE.search(raw_text)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in _MONTH_NAMES:
                    fixed_name = candidate.capitalize()

        if fixed_name:
            logger.info("CEO parse: corrected employee_name %r → %r", emp, fixed_name)
            parsed = {**parsed, "employee_name": fixed_name}

    # ── Fix 2: intent is send_message but message has deadline/date → update_task ──
    if parsed.get("intent") == "send_message":
        has_update_kw = any(kw in text_lower for kw in _UPDATE_KEYWORDS)
        has_date = bool(_extract_date_from_text(raw_text))
        if has_update_kw or has_date:
            logger.info("CEO parse: overriding intent send_message → update_task (deadline/date detected)")
            date_iso = _extract_date_from_text(raw_text)
            changes = dict(parsed.get("changes") or {})
            if date_iso and not changes.get("due_date"):
                changes["due_date"] = date_iso
            parsed = {**parsed, "intent": "update_task", "changes": changes}

    # ── Fix 3: update_task but no due_date extracted yet → try from raw text ──
    if parsed.get("intent") == "update_task":
        changes = dict(parsed.get("changes") or {})
        if not changes.get("due_date"):
            date_iso = _extract_date_from_text(raw_text)
            if date_iso:
                changes["due_date"] = date_iso
                parsed = {**parsed, "changes": changes}

    # ── Fix 4: BLOCK create_task — CEO Control Tower never creates tasks ──
    if parsed.get("intent") == "create_task":
        logger.warning("CEO parse: blocking create_task intent — converting to update_task")
        date_iso = _extract_date_from_text(raw_text)
        changes = dict(parsed.get("changes") or {})
        if date_iso and not changes.get("due_date"):
            changes["due_date"] = date_iso
        parsed = {**parsed, "intent": "update_task", "changes": changes}

    # ── Fix 5: Extract task_keyword from raw text if missing ──
    if not parsed.get("task_keyword"):
        keyword = _extract_task_keyword(raw_text)
        if keyword:
            logger.info("CEO parse: extracted task_keyword=%r from raw text", keyword)
            parsed = {**parsed, "task_keyword": keyword}

    return parsed

# ---------------------------------------------------------------------------
# CEO detection
# ---------------------------------------------------------------------------


async def get_ceo_user(db: AsyncSession, sender_phone: str) -> User | None:
    """Check if the sender phone matches a User's whatsapp_number OR the
    FOUNDER_PHONE env var (fallback for accounts that haven't set their
    WhatsApp number in Settings yet).

    Returns the User row if found, None otherwise.
    """
    normalized = normalize_phone_number(sender_phone)
    logger.info("get_ceo_user: checking sender=%r normalized=%r", sender_phone, normalized)

    # 1. Exact match against users.whatsapp_number
    stmt = select(User).where(User.whatsapp_number == normalized)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user:
        logger.info("get_ceo_user: exact match user_id=%s", user.id)
        return user

    # 2. Suffix fallback (last 10 digits) — handles +91XXXXXXXXXX vs XXXXXXXXXX mismatches
    suffix = re.sub(r"\D", "", normalized)[-10:]
    if len(suffix) == 10:
        stmt2 = select(User).where(User.whatsapp_number.like(f"%{suffix}"))
        result2 = await db.execute(stmt2)
        user2 = result2.scalars().first()
        if user2:
            logger.info("get_ceo_user: suffix match user_id=%s", user2.id)
            return user2

    # 3. FOUNDER_PHONE env var fallback — if the CEO hasn't set whatsapp_number yet
    if settings.founder_phone:
        founder_normalized = normalize_phone_number(settings.founder_phone)
        founder_suffix = re.sub(r"\D", "", founder_normalized)[-10:]
        sender_suffix = re.sub(r"\D", "", normalized)[-10:]
        if founder_suffix and founder_suffix == sender_suffix:
            # Phone matches FOUNDER_PHONE — find the first User in the matching company
            stmt3 = select(User).order_by(User.id.asc()).limit(1)
            result3 = await db.execute(stmt3)
            user3 = result3.scalars().first()
            if user3:
                logger.info(
                    "get_ceo_user: FOUNDER_PHONE fallback matched, using user_id=%s", user3.id
                )
                return user3

    logger.info("get_ceo_user: no CEO match for sender=%r", sender_phone)
    return None


# ---------------------------------------------------------------------------
# Task search — fuzzy match by keyword + employee
# ---------------------------------------------------------------------------


async def _find_task(
    db: AsyncSession,
    company_id: int,
    employee_name: str | None,
    task_keyword: str | None,
) -> Task | None:
    """Find the best-matching task for a CEO command.

    Strategy: filter by employee if given, then by keyword in title/description,
    falling back to the most recent active task.
    """
    stmt = select(Task).where(Task.company_id == company_id)

    # Filter by employee
    employee = None
    if employee_name:
        emp_stmt = select(Employee).where(
            sa_func.lower(Employee.name) == employee_name.strip().lower(),
            Employee.company_id == company_id,
        )
        emp_result = await db.execute(emp_stmt)
        employee = emp_result.scalars().first()
        if employee:
            stmt = stmt.where(Task.assigned_employee_id == employee.id)

    # Exclude only fully closed tasks — include pending, in_progress, delayed, needs_help, overdue
    stmt = stmt.where(Task.status.not_in([TaskStatus.completed, TaskStatus.archived]))

    # If keyword given, try to match title first
    if task_keyword:
        keyword_stmt = stmt.where(
            sa_func.lower(Task.title).contains(task_keyword.lower())
        )
        keyword_result = await db.execute(keyword_stmt.order_by(Task.created_at.desc()).limit(1))
        task = keyword_result.scalars().first()
        if task:
            return task

        # Try description
        desc_stmt = stmt.where(
            sa_func.lower(Task.description).contains(task_keyword.lower())
        )
        desc_result = await db.execute(desc_stmt.order_by(Task.created_at.desc()).limit(1))
        task = desc_result.scalars().first()
        if task:
            return task

    # Fallback: most recent active task for that employee (or company)
    fallback_result = await db.execute(stmt.order_by(Task.created_at.desc()).limit(1))
    return fallback_result.scalars().first()


async def _get_employee_for_task(db: AsyncSession, task: Task) -> Employee | None:
    """Get the employee assigned to a task."""
    if task.assigned_employee_id:
        return await db.get(Employee, task.assigned_employee_id)
    return None


# ---------------------------------------------------------------------------
# Command executors
# ---------------------------------------------------------------------------


async def _handle_check_status(
    db: AsyncSession, company_id: int, parsed: dict
) -> str:
    """Handle: 'How is Ryan doing on the plumbing task?'"""
    task = await _find_task(db, company_id, parsed["employee_name"], parsed["task_keyword"])
    if not task:
        emp_name = parsed["employee_name"] or "that employee"
        return f"PhantomPilot: No active task found for {emp_name}."

    employee = await _get_employee_for_task(db, task)
    emp_name = employee.name if employee else (task.assigned_to or "Unassigned")

    status_label = task.status.value.replace("_", " ").title()
    progress = f"{task.progress_percent}%" if task.progress_percent else "0%"
    last_update = task.last_update_summary or "No updates yet"
    due = task.due_at.strftime("%b %d, %I:%M %p").lstrip("0") if task.due_at else "No deadline"

    return (
        f"PhantomPilot — Status Report\n\n"
        f"Task: {task.title}\n"
        f"Assigned to: {emp_name}\n"
        f"Status: {status_label}\n"
        f"Progress: {progress}\n"
        f"Last update: {last_update}\n"
        f"Due: {due}"
    )


async def _handle_update_task(
    db: AsyncSession, company_id: int, parsed: dict, ceo_phone: str
) -> str:
    """Handle: 'Tell Ryan the deadline for the plumbing job is now April 20th'"""
    task = await _find_task(db, company_id, parsed["employee_name"], parsed["task_keyword"])
    if not task:
        emp_name = parsed["employee_name"] or "that employee"
        return f"PhantomPilot: No active task found for {emp_name}."

    changes = parsed.get("changes") or {}
    changes_made = []
    deadline_str = ""

    if changes.get("due_date"):
        try:
            new_due = datetime.fromisoformat(changes["due_date"])
            task.due_at = new_due
            # Use explicit format e.g. "April 25th"
            day = new_due.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            deadline_str = f"{new_due.strftime('%B')} {day}{suffix}"
            
            # Show just date for EOD deadlines, full time otherwise
            if new_due.hour == 17 and new_due.minute == 0:
                due_display = new_due.strftime("%B %d").replace(" 0", " ")
            elif new_due.hour == 0 and new_due.minute == 0:
                due_display = new_due.strftime("%B %d").replace(" 0", " ")
            else:
                due_display = new_due.strftime("%b %d, %I:%M %p").lstrip("0")
            changes_made.append(f"Deadline → {due_display}")
        except (ValueError, TypeError):
            pass

    if changes.get("description"):
        task.description = changes["description"]
        changes_made.append(f"Description updated")

    if changes.get("title"):
        task.title = changes["title"]
        changes_made.append(f"Title → {changes['title']}")

    if not changes_made:
        return "PhantomPilot: I understood you want to update a task, but I couldn't determine what to change. Try: 'Change the deadline for [task] to [date]'"

    await db.flush()

    # Notify the assigned employee
    employee = await _get_employee_for_task(db, task)
    
    # Custom message format for deadline updates if that's the only/main change
    kw = parsed.get("task_keyword") or "task"
    if deadline_str and not changes.get("description") and not changes.get("title"):
        notification = f"CEO Update: Deadline for {kw} moved to {deadline_str}"
        ceo_reply = f"Done. {employee.name if employee else (task.assigned_to or 'Unassigned')} notified - {kw} deadline updated to {deadline_str}"
    else:
        # Fallback formatting for multiple changes
        change_text = "\n".join(f"• {c}" for c in changes_made)
        notification = (
            f"CEO Update: {change_text} for task:\n"
            f"{task.title}\n"
            f"Please acknowledge."
        )
        emp_name = employee.name if employee else (task.assigned_to or "Unassigned")
        change_summary = ", ".join(changes_made)
        ceo_reply = f"Done. {emp_name} notified about {task.title} — {change_summary}."

    if employee and employee.phone_number:
        await send_whatsapp_message(employee.phone_number, notification)

    return ceo_reply


async def _handle_complete_task(
    db: AsyncSession, company_id: int, parsed: dict
) -> str:
    """Handle: 'Mark Ryan's bedroom task as complete'"""
    task = await _find_task(db, company_id, parsed["employee_name"], parsed["task_keyword"])
    if not task:
        emp_name = parsed["employee_name"] or "that employee"
        return f"PhantomPilot: No active task found for {emp_name}."

    task.status = TaskStatus.completed
    task.completed_at = datetime.now()
    task.progress_percent = 100
    await db.flush()

    employee = await _get_employee_for_task(db, task)
    if employee and employee.phone_number:
        notification = (
            f"CEO Update for {task.title}:\n"
            f"• Task marked as COMPLETED by CEO.\n"
            f"Good work!"
        )
        await send_whatsapp_message(employee.phone_number, notification)
        emp_name = employee.name
    else:
        emp_name = task.assigned_to or "Unassigned"

    return f"Done. \"{task.title}\" marked as completed. {emp_name} has been notified."


async def _handle_send_message(
    db: AsyncSession, company_id: int, parsed: dict
) -> str:
    """Handle: 'Tell Ryan to call me'"""
    emp_name = parsed.get("employee_name")
    if not emp_name:
        return "PhantomPilot: I couldn't determine which employee to message. Try: 'Tell [name] ...'"

    # Find employee
    emp_stmt = select(Employee).where(
        sa_func.lower(Employee.name) == emp_name.strip().lower(),
        Employee.company_id == company_id,
    )
    emp_result = await db.execute(emp_stmt)
    employee = emp_result.scalars().first()

    if not employee or not employee.phone_number:
        return f"PhantomPilot: Employee \"{emp_name}\" not found or has no phone number."

    relay_message = parsed.get("message") or parsed.get("summary") or "Message from CEO."
    notification = f"Message from CEO:\n{relay_message}"
    sent = await send_whatsapp_message(employee.phone_number, notification)

    if sent:
        return f"Done. Message sent to {employee.name}."
    else:
        return f"PhantomPilot: Failed to send message to {employee.name}. Check Twilio config."


_FALLBACK_HELP = (
    "PhantomPilot: Command not recognized.\n\n"
    "Try:\n"
    "• \"Tell [employee] the deadline for [task] is [date]\"\n"
    "• \"How is [employee] doing on [task]?\"\n"
    "• \"Mark [employee]'s [task] as complete\"\n"
    "• \"Update [employee]'s task description to [text]\"\n"
    "• \"Tell [employee] to [message]\""
)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


# Hardcoded regex for the most common CEO deadline update pattern.
# Intercepts BEFORE AI parsing — immune to model hallucinations.
# Pattern: "Tell <Name> the deadline for <task> is now <date>"
_HARD_DEADLINE_RE = re.compile(
    r"tell\s+([A-Za-z][A-Za-z'-]{1,30})\s+the\s+deadline\s+for\s+(.+?)\s+is\s+now\s+(.+)",
    re.IGNORECASE,
)


async def handle_ceo_command(
    db: AsyncSession,
    ceo_user: User,
    sender: str,
    text: str,
) -> dict:
    """Process a CEO WhatsApp command end-to-end.

    Returns a dict with 'status' and 'reply' keys for the TwiML response.
    Always returns a reply — never silently fails.
    """
    company_id = ceo_user.company_id
    logger.info(
        "=== CEO COMMAND === sender=%r user_id=%s company=%s text=%r",
        sender, ceo_user.id, company_id, text,
    )

    try:
        # ── Hardcoded regex intercept (bypasses AI for deadline updates) ──
        hard_match = _HARD_DEADLINE_RE.match(text.strip())
        if hard_match:
            emp_name = hard_match.group(1).strip().capitalize()
            task_kw  = hard_match.group(2).strip()
            date_raw = hard_match.group(3).strip()
            date_iso = _extract_date_from_text(date_raw) or _extract_date_from_text(text)
            logger.info(
                "CEO hard-regex match: emp=%r kw=%r date_raw=%r → date_iso=%r",
                emp_name, task_kw, date_raw, date_iso,
            )
            if date_iso:
                parsed = {
                    "intent": "update_task",
                    "employee_name": emp_name,
                    "task_keyword": task_kw,
                    "changes": {"due_date": date_iso},
                    "message": None,
                    "summary": f"Update deadline for {emp_name}'s {task_kw} task to {date_raw}",
                }
                reply = await _handle_update_task(db, company_id, parsed, sender)
                return {"status": "ceo_command", "reply": reply}

        # ── AI / rule-based parsing path ──────────────────────────────────
        employee_names = await get_all_employee_names(db)

        parsed = await parse_ceo_command(text, employee_names)
        logger.info(
            "CEO raw parse: intent=%s employee=%r keyword=%r changes=%r",
            parsed.get("intent"), parsed.get("employee_name"),
            parsed.get("task_keyword"), parsed.get("changes"),
        )

        parsed = _sanitize_parsed(parsed, text, employee_names)
        intent = parsed.get("intent", "unknown")
        logger.info(
            "CEO final parse: intent=%s employee=%r keyword=%r changes=%r",
            intent, parsed.get("employee_name"),
            parsed.get("task_keyword"), parsed.get("changes"),
        )

        if intent == "check_status":
            reply = await _handle_check_status(db, company_id, parsed)
        elif intent == "update_task":
            reply = await _handle_update_task(db, company_id, parsed, sender)
        elif intent == "complete_task":
            reply = await _handle_complete_task(db, company_id, parsed)
        elif intent == "send_message":
            reply = await _handle_send_message(db, company_id, parsed)
        else:
            reply = _FALLBACK_HELP

    except Exception as exc:
        logger.exception("CEO command failed: %s", exc)
        reply = f"Command received but failed: {exc!r}\nPlease try again."

    return {"status": "ceo_command", "reply": reply}
