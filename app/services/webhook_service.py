"""Webhook service — shared processing logic for incoming WhatsApp messages.

Both the JSON webhook (Swagger testing) and the Twilio form-data webhook
call into this service so business logic is never duplicated.
"""

import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.employee import Employee
from app.models.message_log import MessageLog
from app.models.task import Task, TaskStatus, SourceType
from app.services.ai_service import extract_task_from_message
from app.services.employee_service import (
    find_employee_by_name,
    get_all_employee_names,
    get_employee_by_phone,
    normalize_phone_number,
)
from app.services.messaging_service import send_welcome_message, send_whatsapp_message

logger = logging.getLogger(__name__)

# Regex to detect ADD <name> <phone_number> command
_ADD_EMPLOYEE_PATTERN = re.compile(
    r"^ADD\s+([A-Za-z][A-Za-z\s]*)\s+(\+?\d[\d\s-]{8,})$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_due_date(value) -> datetime | None:
    """Convert a due_date value (str or datetime) to a datetime object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# ADD employee command
# ---------------------------------------------------------------------------

async def handle_add_employee(
    db: AsyncSession, sender: str, text: str, company_id: int = 1
) -> dict | None:
    """Check if the message is an ADD employee command.

    Format: ADD <name> <phone_number>
    Example: ADD Ravi +919150016161

    Returns a response dict if handled, None otherwise.
    """
    match = _ADD_EMPLOYEE_PATTERN.match(text.strip())
    if not match:
        return None

    name = " ".join(part.capitalize() for part in match.group(1).strip().split())
    phone = normalize_phone_number(match.group(2))

    # Check if employee already exists by phone
    existing = await get_employee_by_phone(db, phone)
    if existing:
        logger.info("Employee already exists: %s (%s)", existing.name, phone)
        await send_whatsapp_message(
            sender,
            "Employee already exists.",
        )
        return {
            "status": "employee_exists",
            "employee_id": existing.id,
            "employee_name": existing.name,
            "phone_number": phone,
        }

    # Create new employee
    employee = Employee(
        name=name,
        phone_number=phone,
        company_id=company_id,
        is_active=True,
    )
    db.add(employee)
    await db.flush()
    await db.refresh(employee)

    logger.info("Employee created: %s / %s", name, phone)

    await send_whatsapp_message(
        sender,
        f"Employee added successfully\n\nName: {name}\nPhone: {phone}",
    )

    # Send welcome message to the new employee
    await send_welcome_message(phone)

    return {
        "status": "employee_created",
        "employee_id": employee.id,
        "employee_name": name,
        "phone_number": phone,
    }


# ---------------------------------------------------------------------------
# Reply command handling
# ---------------------------------------------------------------------------

async def handle_reply(
    db: AsyncSession, sender: str, command: str
) -> dict | None:
    """Check if the message is a reply command (DONE / STARTED / HELP).

    Returns a response dict if handled, None otherwise.
    """
    text = command.strip().upper()

    # Determine action
    if text == "DONE":
        new_status = TaskStatus.completed
    elif text == "STARTED":
        new_status = TaskStatus.in_progress
    elif text == "HELP":
        new_status = TaskStatus.needs_help
    else:
        return None  # Not a command

    # Look up employee by phone number
    employee = await get_employee_by_phone(db, sender)
    if not employee:
        return {
            "status": "error",
            "detail": f"No employee found for phone number {sender}",
        }

    # Find most recent pending/in_progress task for this employee
    stmt = (
        select(Task)
        .where(
            Task.assigned_employee_id == employee.id,
            Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        await send_whatsapp_message(
            sender,
            f"You have no pending or in-progress tasks at the moment, {employee.name}.",
        )
        return {
            "status": "error",
            "detail": f"No pending/in-progress task found for {employee.name}",
        }

    # Apply the status change + intelligence tracking
    task.status = new_status
    if new_status == TaskStatus.completed:
        task.completed_at = datetime.now()
    elif new_status == TaskStatus.in_progress:
        task.started_at = datetime.now()
    elif new_status == TaskStatus.needs_help:
        task.help_requested = True

    await db.flush()

    # Log the action and send confirmations
    status_label = new_status.value
    if new_status == TaskStatus.completed:
        logger.info(
            'Employee %s marked task "%s" as completed.',
            employee.name, task.title,
        )
        await send_whatsapp_message(sender, "Task marked complete.")
    elif new_status == TaskStatus.needs_help:
        logger.info(
            'Employee %s requested help on task "%s".',
            employee.name, task.title,
        )
        deadline_str = (
            task.due_at.strftime("%I:%M %p").lstrip("0") if task.due_at else "No deadline"
        )
        help_alert = (
            f"⚠️ Employee Needs Help\n\n"
            f"Employee: {employee.name}\n"
            f"Task: {task.title}\n"
            f"Deadline: {deadline_str}\n\n"
            f"The employee requested assistance."
        )
        if settings.founder_phone:
            await send_whatsapp_message(settings.founder_phone, help_alert)
        else:
            logger.warning("FOUNDER_PHONE not set — help alert logged only.")
    else:
        logger.info(
            'Employee %s marked task "%s" as %s.',
            employee.name, task.title, status_label,
        )

    return {
        "status": "task_updated",
        "employee": employee.name,
        "task_id": task.id,
        "task_title": task.title,
        "new_status": status_label,
    }


# ---------------------------------------------------------------------------
# Full message processing pipeline
# ---------------------------------------------------------------------------

async def process_incoming_message(
    db: AsyncSession,
    sender: str,
    text: str,
    force_company_id: int = None,
) -> dict:
    """Process an incoming WhatsApp message end-to-end.

    1. Auto-register employee if new
    2. Log the raw message
    3. Handle reply commands (DONE / STARTED / DELAY / HELP)
    4. Extract & save task via AI
    5. Send confirmations

    Returns a result dict describing what happened.
    """
    if not text.strip():
        return {"status": "no_text"}
        
    # resolve company_id from sender
    # First, try to find an employee with this phone
    existing_emp = await get_employee_by_phone(db, sender)
    
    if existing_emp:
        company_id = existing_emp.company_id
    elif force_company_id is not None:
        company_id = force_company_id
    else:
        # Fallback to the first company (admin company) if unknown
        # In a real SaaS, we might reject the message or put in a 'ghost' company
        company_id = 1

    # ── Auto-register employee if first contact ──────────────────
    # Use a placeholder name — the real name will be set when AI extracts it
    existing = await get_employee_by_phone(db, sender)
    if existing is None and sender != "unknown":
        placeholder_name = f"Employee_{sender[-4:]}"  # e.g. "Employee_6161"
        new_emp = Employee(
            name=placeholder_name,
            phone_number=sender,
            company_id=company_id,
            is_active=True,
        )
        db.add(new_emp)
        await db.flush()
        await db.refresh(new_emp)
        logger.info("Auto-registered new employee: %s (id=%s)", placeholder_name, new_emp.id)
        await send_welcome_message(sender)

    # ── Log raw message ──────────────────────────────────────────
    log = MessageLog(
        company_id=company_id,
        sender=sender,
        channel="whatsapp",
        raw_text=text,
        direction="incoming",
    )
    db.add(log)
    await db.flush()

    # ── Check for ADD employee command ───────────────────────────
    add_result = await handle_add_employee(db, sender, text, company_id)
    if add_result is not None:
        add_result["message_log_id"] = log.id
        return add_result

    # ── Check for reply commands ─────────────────────────────────
    reply_result = await handle_reply(db, sender, text)
    if reply_result is not None:
        reply_result["message_log_id"] = log.id
        return reply_result

    # ── Extract task via AI ──────────────────────────────────────
    # Fetch real employee names (phone-number placeholders are filtered out)
    known_names = await get_all_employee_names(db)

    logger.info("Incoming message: %s", text)
    
    from app.services.ai_service import analyze_progress_update
    
    # Let's see if the employee has an active task and this is a progress update
    employee_for_update = None
    if sender != "unknown":
        employee_for_update = await get_employee_by_phone(db, sender)
        
    if employee_for_update:
        stmt = (
            select(Task)
            .where(
                Task.assigned_employee_id == employee_for_update.id,
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        task_res = await db.execute(stmt)
        active_task = task_res.scalars().first()
        
        if active_task:
            analysis = await analyze_progress_update(text, active_task.title)
            if analysis.get("type") in ["progress_update", "task_completion"]:
                is_completion = analysis.get("type") == "task_completion"
                pct = 100 if is_completion else analysis.get("progress_percent")
                summary = analysis.get("summary")

                if pct is not None:
                    active_task.progress_percent = pct
                if summary:
                    active_task.last_update_summary = summary

                active_task.last_update = datetime.now()
                active_task.status = TaskStatus.completed if is_completion else TaskStatus.in_progress
                if active_task.status == TaskStatus.completed:
                    active_task.completed_at = datetime.now()
                elif active_task.status == TaskStatus.in_progress and not active_task.started_at:
                    active_task.started_at = datetime.now()

                await db.flush()

                logger.info(
                    'Employee %s updated "%s": %s%% — %s',
                    employee_for_update.name, active_task.title, pct, summary,
                )
                confirm_msg = "Task marked complete!" if is_completion else f"Progress updated: {pct}%. Keep it up!"
                await send_whatsapp_message(sender, confirm_msg)
                
                return {
                    "status": "task_updated",
                    "employee": employee_for_update.name,
                    "task_id": active_task.id,
                    "task_title": active_task.title,
                    "new_status": active_task.status.value,
                    "message_log_id": log.id
                }

    extracted = await extract_task_from_message(text, known_employee_names=known_names)


    if not extracted.get("title"):
        logger.info("No task detected — message ignored.")
        return {"status": "no_task_detected", "message_log_id": log.id}

    # ── Resolve employee (lookup only — never auto-create) ───────
    owner_name = extracted.get("owner")
    employee = None
    employee_id = None

    if owner_name:
        employee = await find_employee_by_name(
            db, name=owner_name, company_id=company_id,
        )
        if not employee:
            logger.warning("Employee not found: %s", owner_name)
            await send_whatsapp_message(
                sender,
                f'Employee "{owner_name}" not found. Please add them first.',
            )
            return {
                "status": "employee_not_found",
                "message_log_id": log.id,
                "employee_name": owner_name,
            }
        employee_id = employee.id

    # ── Duplicate task check ─────────────────────────────────────
    dup_stmt = (
        select(Task)
        .where(
            Task.title == extracted["title"],
            Task.assigned_employee_id == employee_id,
            Task.status == TaskStatus.pending,
        )
        .limit(1)
    )
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalars().first():
        logger.info("Duplicate task detected — skipping: %s", extracted["title"])
        return {
            "status": "duplicate_task",
            "message_log_id": log.id,
            "task_title": extracted["title"],
        }

    # ── Save task ────────────────────────────────────────────────
    task = Task(
        company_id=company_id,
        title=extracted["title"],
        description=extracted.get("description"),
        assigned_to=extracted.get("owner"),
        assigned_employee_id=employee_id,
        owner_id=None,
        due_at=parse_due_date(extracted.get("due_date")),
        status=TaskStatus.pending,
        source_type=SourceType.whatsapp,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    due_str = (
        task.due_at.strftime("%I:%M %p").lstrip("0") if task.due_at else "No deadline"
    )
    assignee_str = task.assigned_to or "Unassigned"

    response = {
        "status": "task_created",
        "message_log_id": log.id,
        "task_id": task.id,
        "task_title": task.title,
    }
    if employee:
        response["employee_id"] = employee.id
        response["employee_name"] = employee.name

    logger.info("Task created: %s", task.title)
    logger.info("Task assigned to: %s", assignee_str)

    # ── Send confirmation WhatsApp to the manager (sender) ──────
    confirmation = (
        f"Task created:\n"
        f"{task.title}\n"
        f"Assigned to: {assignee_str}\n"
        f"Deadline: {due_str}"
    )
    if sender != "unknown":
        await send_whatsapp_message(sender, confirmation)

    # ── Notify the assigned employee ─────────────────────────────
    if employee and employee.phone_number:
        desc_str = task.description or "No description"
        task_notification = (
            f"Foreman AI - New Task Assigned\n\n"
            f"Task: {task.title}\n"
            f"Description: {desc_str}\n"
            f"Due: {due_str}\n\n"
            f"Reply with:\n"
            f"DONE - mark complete\n"
            f"HELP - request assistance\n"
            f"UPDATE <text> - send progress"
        )
        await send_whatsapp_message(employee.phone_number, task_notification)
        task.notification_sent = True
        await db.flush()
        logger.info("Notification sent to: %s", employee.phone_number)
    elif employee:
        logger.warning(
            "Employee %s has no phone number — cannot notify.", employee.name,
        )

    return response
