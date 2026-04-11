"""CEO WhatsApp Command Center — handles natural-language commands from the CEO.

The CEO can manage tasks, check status, and message employees directly via
WhatsApp. Commands are parsed by OpenAI into structured intents and executed.
"""

import logging
from datetime import datetime

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai_service import parse_ceo_command
from app.services.employee_service import (
    get_all_employee_names,
    get_employee_by_phone,
    normalize_phone_number,
)
from app.services.messaging_service import send_whatsapp_message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CEO detection
# ---------------------------------------------------------------------------


async def get_ceo_user(db: AsyncSession, sender_phone: str) -> User | None:
    """Check if the sender phone matches any User's whatsapp_number.

    Returns the User row if found (CEO / founder), None otherwise.
    """
    normalized = normalize_phone_number(sender_phone)

    # Exact match
    stmt = select(User).where(User.whatsapp_number == normalized)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user:
        return user

    # Suffix fallback (last 10 digits)
    import re
    suffix = re.sub(r"\D", "", normalized)[-10:]
    if len(suffix) == 10:
        stmt2 = select(User).where(User.whatsapp_number.like(f"%{suffix}"))
        result2 = await db.execute(stmt2)
        user2 = result2.scalars().first()
        if user2:
            return user2

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

    # Prefer active tasks
    stmt = stmt.where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]))

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
        return f"Foreman AI: No active task found for {emp_name}."

    employee = await _get_employee_for_task(db, task)
    emp_name = employee.name if employee else (task.assigned_to or "Unassigned")

    status_label = task.status.value.replace("_", " ").title()
    progress = f"{task.progress_percent}%" if task.progress_percent else "0%"
    last_update = task.last_update_summary or "No updates yet"
    due = task.due_at.strftime("%b %d, %I:%M %p").lstrip("0") if task.due_at else "No deadline"

    return (
        f"Foreman AI — Status Report\n\n"
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
        return f"Foreman AI: No active task found for {emp_name}."

    changes = parsed.get("changes") or {}
    changes_made = []

    if changes.get("due_date"):
        try:
            new_due = datetime.fromisoformat(changes["due_date"])
            old_due = task.due_at
            task.due_at = new_due
            changes_made.append(f"Deadline → {new_due.strftime('%b %d, %I:%M %p').lstrip('0')}")
        except (ValueError, TypeError):
            pass

    if changes.get("description"):
        task.description = changes["description"]
        changes_made.append(f"Description updated")

    if changes.get("title"):
        task.title = changes["title"]
        changes_made.append(f"Title → {changes['title']}")

    if not changes_made:
        return "Foreman AI: I understood you want to update a task, but I couldn't determine what to change. Try: 'Change the deadline for [task] to [date]'"

    await db.flush()

    # Notify the assigned employee
    employee = await _get_employee_for_task(db, task)
    if employee and employee.phone_number:
        change_text = "\n".join(f"• {c}" for c in changes_made)
        notification = (
            f"CEO Update for {task.title}:\n"
            f"{change_text}\n"
            f"Please acknowledge."
        )
        await send_whatsapp_message(employee.phone_number, notification)
        emp_name = employee.name
    else:
        emp_name = task.assigned_to or "Unassigned"

    change_summary = ", ".join(changes_made)
    return f"Done. {emp_name} has been notified about: {change_summary}."


async def _handle_complete_task(
    db: AsyncSession, company_id: int, parsed: dict
) -> str:
    """Handle: 'Mark Ryan's bedroom task as complete'"""
    task = await _find_task(db, company_id, parsed["employee_name"], parsed["task_keyword"])
    if not task:
        emp_name = parsed["employee_name"] or "that employee"
        return f"Foreman AI: No active task found for {emp_name}."

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
        return "Foreman AI: I couldn't determine which employee to message. Try: 'Tell [name] ...'"

    # Find employee
    emp_stmt = select(Employee).where(
        sa_func.lower(Employee.name) == emp_name.strip().lower(),
        Employee.company_id == company_id,
    )
    emp_result = await db.execute(emp_stmt)
    employee = emp_result.scalars().first()

    if not employee or not employee.phone_number:
        return f"Foreman AI: Employee \"{emp_name}\" not found or has no phone number."

    relay_message = parsed.get("message") or parsed.get("summary") or "Message from CEO."
    notification = f"Message from CEO:\n{relay_message}"
    sent = await send_whatsapp_message(employee.phone_number, notification)

    if sent:
        return f"Done. Message sent to {employee.name}."
    else:
        return f"Foreman AI: Failed to send message to {employee.name}. Check Twilio config."


_FALLBACK_HELP = (
    "Foreman AI: Command not recognized.\n\n"
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


async def handle_ceo_command(
    db: AsyncSession,
    ceo_user: User,
    sender: str,
    text: str,
) -> dict:
    """Process a CEO WhatsApp command end-to-end.

    Returns a dict with 'status' and 'reply' keys for the TwiML response.
    """
    company_id = ceo_user.company_id
    logger.info(
        "=== CEO COMMAND === user_id=%s company=%s text=%r",
        ceo_user.id, company_id, text,
    )

    # Get known employee names for better AI parsing
    employee_names = await get_all_employee_names(db)

    # Parse intent via AI
    parsed = await parse_ceo_command(text, employee_names)
    intent = parsed.get("intent", "unknown")

    logger.info(
        "CEO intent parsed: intent=%s employee=%s keyword=%s",
        intent, parsed.get("employee_name"), parsed.get("task_keyword"),
    )

    # Execute the command
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

    return {"status": "ceo_command", "reply": reply}
