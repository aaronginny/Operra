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
from app.models.enquiry import Enquiry
from app.models.task import Task, TaskStatus, SourceType
from app.models.task_message import TaskMessage, MessageSender
from app.models.task_update import TaskUpdate
from app.services.ai_service import ask_employee_assistant, extract_enquiry_from_message, extract_task_from_message
from app.services.employee_service import (
    find_employee_by_name,
    get_all_employee_names,
    get_employee_by_phone,
    normalize_phone_number,
)
from app.services.ceo_command_service import get_ceo_user, handle_ceo_command
from app.services.messaging_service import send_welcome_message, send_whatsapp_message
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def _get_manager_phone(db: AsyncSession, company_id: int) -> str | None:
    """Return the WhatsApp number of the CEO/founder for the given company.

    Falls back to FOUNDER_PHONE env var only when no CEO user is found (e.g.
    during dev or for the platform owner's own company).
    """
    stmt = (
        select(User)
        .where(
            User.company_id == company_id,
            User.role.in_([UserRole.ceo, UserRole.founder]),
        )
        .order_by(User.id.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user and user.whatsapp_number:
        return user.whatsapp_number
    # Platform-owner fallback
    return settings.founder_phone


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
    """Check if the message is a reply command (DONE / STARTED / HELP / HELP <message> / UPDATE <text>).

    DONE  → status becomes pending_confirmation (CEO must CONFIRM/REJECT).
    HELP  → status becomes needs_help, CEO is notified with the employee's message.
    UPDATE <text> → saves a TaskUpdate row + notifies CEO + updates last_update_summary.

    Returns a response dict if handled, None otherwise.
    """
    stripped = command.strip()
    upper = stripped.upper()
    upper_words = upper.split()

    # Determine action
    is_update_cmd = bool(upper_words) and upper_words[0] == "UPDATE" and len(stripped) > len("UPDATE")
    if upper == "DONE":
        new_status = TaskStatus.pending_confirmation
    elif upper == "STARTED":
        new_status = TaskStatus.in_progress
    elif upper == "HELP" or upper_words[0] == "HELP":
        new_status = TaskStatus.needs_help
    elif is_update_cmd:
        new_status = None  # handled separately
    else:
        return None  # Not a command

    # Look up employee by phone number (no company_id needed — phone is globally unique per employee)
    logger.info("handle_reply: looking up employee for phone=%r command=%r", sender, upper)
    employee = await get_employee_by_phone(db, sender)
    if not employee:
        logger.warning("handle_reply: NO employee found for phone=%r", sender)
        return {
            "status": "error",
            "detail": f"No employee found for phone number {sender}",
        }
    logger.info("handle_reply: found employee id=%s name=%r company_id=%s", employee.id, employee.name, employee.company_id)

    # Find most recent open task for this employee — scoped to their company.
    # Include needs_help and pending_confirmation so subsequent commands can still target the same task.
    stmt = (
        select(Task)
        .where(
            Task.assigned_employee_id == employee.id,
            Task.company_id == employee.company_id,
            Task.status.in_([
                TaskStatus.pending,
                TaskStatus.in_progress,
                TaskStatus.needs_help,
                TaskStatus.pending_confirmation,
            ]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    task = result.scalars().first()

    if not task:
        logger.warning(
            "handle_reply: no open task for employee id=%s name=%r",
            employee.id, employee.name,
        )
        await send_whatsapp_message(
            sender,
            f"You have no pending or in-progress tasks at the moment, {employee.name}.",
        )
        return {
            "status": "error",
            "detail": f"No open task found for {employee.name}",
        }

    # ── UPDATE <text> command ────────────────────────────────────────
    if is_update_cmd:
        update_text = stripped[len("UPDATE"):].strip()
        logger.info("handle_reply: UPDATE for task id=%s text=%r", task.id, update_text[:120])

        # Persist to task_updates table
        tu = TaskUpdate(
            task_id=task.id,
            employee_id=employee.id,
            update_text=update_text,
        )
        db.add(tu)

        # Reflect on the task itself so the dashboard shows it under the task
        task.last_update = datetime.now()
        task.last_update_summary = update_text[:500]
        if task.status == TaskStatus.pending:
            task.status = TaskStatus.in_progress
            if not task.started_at:
                task.started_at = datetime.now()

        await db.flush()

        # Notify CEO
        manager_phone = await _get_manager_phone(db, employee.company_id)
        if manager_phone:
            ceo_msg = (
                f"📊 *Update from {employee.name}* on task: *{task.title}*\n"
                f"{update_text}"
            )
            await send_whatsapp_message(manager_phone, ceo_msg)
        else:
            logger.warning(
                "No manager phone found for company_id=%s — update logged only.",
                employee.company_id,
            )

        await send_whatsapp_message(
            sender,
            f"Got it! 👍 Your manager has been updated on \"{task.title}\".",
        )

        return {
            "status": "task_update_saved",
            "employee": employee.name,
            "task_id": task.id,
            "task_title": task.title,
            "update_text": update_text,
        }

    logger.info("handle_reply: updating task id=%s %r → %s", task.id, task.title, new_status)

    # Apply the status change + intelligence tracking
    task.status = new_status
    if new_status == TaskStatus.pending_confirmation:
        # Don't set completed_at yet — CEO must confirm first
        pass
    elif new_status == TaskStatus.in_progress:
        task.started_at = datetime.now()
    elif new_status == TaskStatus.needs_help:
        task.help_requested = True

    await db.flush()

    # Log the action and send confirmations
    status_label = new_status.value
    if new_status == TaskStatus.pending_confirmation:
        logger.info(
            'Employee %s marked task "%s" as DONE → pending CEO confirmation.',
            employee.name, task.title,
        )
        await send_whatsapp_message(
            sender,
            f"Got it! ✅ Your manager has been asked to confirm completion of \"{task.title}\".",
        )
        manager_phone = await _get_manager_phone(db, employee.company_id)
        if manager_phone:
            ceo_msg = (
                f"✅ *{employee.name}* says task *{task.title}* is done.\n"
                f"Reply CONFIRM {task.id} to mark complete\n"
                f"Reply REJECT {task.id} to send it back"
            )
            await send_whatsapp_message(manager_phone, ceo_msg)
        else:
            logger.warning(
                "No manager phone found for company_id=%s — DONE confirmation request logged only.",
                employee.company_id,
            )
    elif new_status == TaskStatus.in_progress:
        logger.info(
            'Employee %s marked task "%s" as in_progress.',
            employee.name, task.title,
        )
        await send_whatsapp_message(sender, f"Got it! 👍 \"{task.title}\" is now marked as in progress. Keep going!")
    elif new_status == TaskStatus.needs_help:
        logger.info(
            'Employee %s requested help on task "%s".',
            employee.name, task.title,
        )
        # Capture the message text after HELP (if any)
        question = stripped[4:].strip() if len(stripped) > 4 else ""

        await send_whatsapp_message(
            sender,
            f"Understood! I've informed your manager about your concern with \"{task.title}\". They'll get back to you soon. Hang tight! 💪",
        )

        manager_phone = await _get_manager_phone(db, employee.company_id)
        if manager_phone:
            employee_msg = question if question else "(no additional details)"
            help_alert = (
                f"🆘 *{employee.name}* needs help with task: *{task.title}*\n"
                f"They said: {employee_msg}\n\n"
                f"Reply OK to acknowledge"
            )
            await send_whatsapp_message(manager_phone, help_alert)
        else:
            logger.warning(
                "No manager phone found for company_id=%s — help alert logged only.",
                employee.company_id,
            )

        # Save the help message so it shows on the dashboard under the task
        if question:
            task.last_update = datetime.now()
            task.last_update_summary = f"HELP: {question[:480]}"
            await db.flush()

    return {
        "status": "task_updated",
        "employee": employee.name,
        "task_id": task.id,
        "task_title": task.title,
        "new_status": status_label,
    }


# ---------------------------------------------------------------------------
# Employee→manager message forwarding
# ---------------------------------------------------------------------------

# Regex: "OK" or "DELAY <reason>"
_OK_PATTERN = re.compile(r"^OK\s*$", re.IGNORECASE)
_DELAY_PATTERN = re.compile(r"^DELAY\s+(.+)$", re.IGNORECASE | re.DOTALL)
# CEO confirmation flow for DONE tasks: "CONFIRM 42" / "REJECT 42"
_CONFIRM_PATTERN = re.compile(r"^CONFIRM\s+(\d+)\s*$", re.IGNORECASE)
_REJECT_PATTERN = re.compile(r"^REJECT\s+(\d+)\s*$", re.IGNORECASE)


async def handle_ceo_confirm_reject(
    db: AsyncSession,
    sender: str,
    text: str,
    company_id: int,
) -> dict | None:
    """Handle CEO replies of the form `CONFIRM <task_id>` / `REJECT <task_id>`.

    Returns a result dict if handled, None otherwise.
    """
    stripped = text.strip()
    confirm_m = _CONFIRM_PATTERN.match(stripped)
    reject_m = _REJECT_PATTERN.match(stripped)
    if not confirm_m and not reject_m:
        return None

    task_id = int((confirm_m or reject_m).group(1))
    task = await db.get(Task, task_id)
    if not task or task.company_id != company_id:
        await send_whatsapp_message(
            sender,
            f"PhantomPilot: I couldn't find task #{task_id} in your company.",
        )
        return {"status": "ceo_confirm_unknown_task", "task_id": task_id}

    # Look up the assigned employee for notifications
    employee_phone = None
    employee_name = task.assigned_to or "the employee"
    if task.assigned_employee_id:
        emp = await db.get(Employee, task.assigned_employee_id)
        if emp:
            employee_phone = emp.phone_number
            employee_name = emp.name

    if confirm_m:
        task.status = TaskStatus.completed
        task.completed_at = datetime.now()
        task.progress_percent = 100
        await db.flush()
        if employee_phone:
            await send_whatsapp_message(
                employee_phone,
                "Great job! Your manager confirmed completion.",
            )
        await send_whatsapp_message(
            sender,
            f'Done. "{task.title}" marked as completed.',
        )
        return {
            "status": "task_confirmed_complete",
            "task_id": task.id,
            "employee": employee_name,
        }
    else:
        task.status = TaskStatus.in_progress
        task.completed_at = None
        await db.flush()
        if employee_phone:
            await send_whatsapp_message(
                employee_phone,
                "Your manager sent the task back. Please check and redo.",
            )
        await send_whatsapp_message(
            sender,
            f'Got it. "{task.title}" sent back to {employee_name}.',
        )
        return {
            "status": "task_rejected",
            "task_id": task.id,
            "employee": employee_name,
        }


async def forward_to_manager(
    db: AsyncSession,
    employee: "Employee",
    task: Task,
    raw_text: str,
) -> None:
    """Save the employee message and forward it to the manager via WhatsApp."""
    from app.services.ai_service import ask_employee_assistant

    # Let AI reformat the raw text into a clean, professional sentence
    tasks_ctx = [{"title": task.title, "description": task.description,
                   "due_at": task.due_at.strftime("%b %d, %I:%M %p") if task.due_at else None,
                   "status": task.status.value}]
    formatted = await ask_employee_assistant(
        f"Rewrite this employee message as a single clear, professional sentence for their manager "
        f"(keep it short, no extra commentary): {raw_text}",
        tasks_ctx,
    )

    # Save to DB
    msg = TaskMessage(
        task_id=task.id,
        sender=MessageSender.employee,
        message=formatted,
        acknowledged=False,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)

    manager_phone = await _get_manager_phone(db, task.company_id)
    if not manager_phone:
        logger.warning("No manager phone found for company_id=%s — employee message logged only (task_message id=%s)", task.company_id, msg.id)
        return

    notif = (
        f"📨 *Task Update from {employee.name}*\n"
        f"Task: {task.title}\n"
        f"Message: {formatted}\n\n"
        f"Reply *OK* to acknowledge\n"
        f"Reply *DELAY [reason]* to send them a message back"
    )
    await send_whatsapp_message(manager_phone, notif)
    logger.info("Employee message forwarded to manager (task_message id=%s)", msg.id)


async def handle_manager_reply(
    db: AsyncSession,
    sender: str,
    text: str,
    company_id: int,
) -> dict | None:
    """Handle OK / DELAY <reason> replies from the manager.

    Looks for the most recent unacknowledged TaskMessage for this company,
    marks it acknowledged, and notifies the employee.

    Returns a result dict if handled, None if not an OK/DELAY command.
    """
    ok_match = _OK_PATTERN.match(text.strip())
    delay_match = _DELAY_PATTERN.match(text.strip())

    if not ok_match and not delay_match:
        return None

    # Find the most recent unacknowledged employee message in this company
    stmt = (
        select(TaskMessage)
        .join(Task, Task.id == TaskMessage.task_id)
        .where(
            Task.company_id == company_id,
            TaskMessage.sender == MessageSender.employee,
            TaskMessage.acknowledged == False,  # noqa: E712
        )
        .order_by(TaskMessage.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    msg = result.scalars().first()

    if not msg:
        logger.info("Manager replied %r but no pending employee message found", text.strip())
        return None

    msg.acknowledged = True
    await db.flush()

    # Load the associated task and employee
    task_stmt = select(Task).where(Task.id == msg.task_id)
    task = (await db.execute(task_stmt)).scalars().first()
    emp_phone = None
    if task and task.assigned_employee_id:
        emp_stmt = select(Employee).where(Employee.id == task.assigned_employee_id)
        emp = (await db.execute(emp_stmt)).scalars().first()
        if emp:
            emp_phone = emp.phone_number

    if ok_match:
        if emp_phone:
            await send_whatsapp_message(
                emp_phone,
                "✅ Your manager has acknowledged your message. You're good to continue! 💪",
            )
        return {"status": "manager_ok", "task_message_id": msg.id}
    else:
        reason = delay_match.group(1).strip()
        # Save manager's reply as a message too
        mgr_msg = TaskMessage(
            task_id=msg.task_id,
            sender=MessageSender.manager,
            message=reason,
            acknowledged=True,
        )
        db.add(mgr_msg)
        await db.flush()

        if emp_phone:
            await send_whatsapp_message(
                emp_phone,
                f"⚠️ Message from your manager:\n{reason}",
            )
        return {"status": "manager_delay", "task_message_id": msg.id, "reason": reason}


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

    # ── TEST MODE: CEO can simulate employee messages ─────────────
    # Prefix "EMPLOYEE:" (any case) strips CEO detection and processes
    # the rest as if it came from a regular employee (same sender number).
    # Example: "EMPLOYEE: UPDATE finished the pipe inspection"
    _EMPLOYEE_TEST_PREFIX = "EMPLOYEE:"
    force_employee_path = False
    if text.strip().upper().startswith(_EMPLOYEE_TEST_PREFIX):
        original_text = text.strip()
        text = original_text[len(_EMPLOYEE_TEST_PREFIX):].strip()
        force_employee_path = True
        logger.info("=== TEST MODE === stripping prefix, remaining text: %r", text[:120])

    logger.info("=== INCOMING === sender=%r force_employee=%s text=%r", sender, force_employee_path, text[:120])

    # ── CEO lookup — skipped entirely when force_employee_path is True ──
    ceo_user = None
    if not force_employee_path:
        ceo_user = await get_ceo_user(db, sender)
    else:
        logger.info("=== TEST MODE === EMPLOYEE prefix detected — skipping CEO detection entirely")

    if ceo_user:
        # Resolve company_id from the CEO user record
        ceo_company_id = ceo_user.company_id

        # Log raw message for audit trail
        log = MessageLog(
            company_id=ceo_company_id,
            sender=sender,
            channel="whatsapp",
            raw_text=text,
            direction="incoming",
        )
        db.add(log)
        await db.flush()

        logger.info("=== CEO DETECTED === user_id=%s name=%r company=%s", ceo_user.id, ceo_user.name, ceo_company_id)

        # ── Tier check: Control Tower requires Basic or Premium ────────
        from app.services.billing_service import check_can_use_control_tower
        control_tower_ok = await check_can_use_control_tower(db, ceo_company_id, user_role=ceo_user.role.value)
        if not control_tower_ok:
            logger.info("Control Tower blocked (free tier) for company=%s", ceo_company_id)
            await send_whatsapp_message(
                sender,
                "PhantomPilot — Upgrade Required\n\n"
                "WhatsApp Control Tower is available on the Basic plan (₹2,000/project) "
                "or Premium plan (₹5,000/month).\n\n"
                "Visit your dashboard to upgrade.",
            )
            await db.commit()
            return {"status": "control_tower_blocked_free_tier"}

        # CEO can still use ADD command; everything else is Control Tower
        add_check = await handle_add_employee(db, sender, text, ceo_company_id)
        if add_check is not None:
            add_check["message_log_id"] = log.id
            return add_check

        # ── CEO CONFIRM / REJECT for DONE flow ───────────────────────
        confirm_result = await handle_ceo_confirm_reject(db, sender, text, ceo_company_id)
        if confirm_result is not None:
            confirm_result["message_log_id"] = log.id
            await db.commit()
            return confirm_result

        # ── Manager reply to employee message (OK / DELAY <reason>) ──
        mgr_reply = await handle_manager_reply(db, sender, text, ceo_company_id)
        if mgr_reply is not None:
            mgr_reply["message_log_id"] = log.id
            await db.commit()
            return mgr_reply

        # ── CEO HELP — usage guide (bare "HELP" or "HELP <anything>") ──────────
        stripped_text = text.strip()
        upper_stripped = stripped_text.upper()
        _is_help = upper_stripped == "HELP" or upper_stripped.startswith("HELP ")
        if _is_help:
            help_reply = (
                "Hi! Here's how to use PhantomPilot Control Tower:\n\n"
                "• \"Assign [task] to [name] by [date]\"\n"
                "• \"Tell [name] the deadline for [task] is now [date]\"\n"
                "• \"How is [name] doing on [task]?\"\n"
                "• \"Mark [name]'s [task] as complete\"\n"
                "• \"Tell [name] to [message]\"\n"
                "• \"Update [name]'s [task] description to [text]\"\n\n"
                "Need more help? Visit your dashboard."
            )
            await send_whatsapp_message(sender, help_reply)
            await db.commit()
            return {"status": "ceo_help_info", "message_log_id": log.id}

        ceo_result = await handle_ceo_command(db, ceo_user, sender, text)
        ceo_result["message_log_id"] = log.id
        # Send the reply back to the CEO via WhatsApp
        reply_text = ceo_result.get("reply")
        if reply_text:
            await send_whatsapp_message(sender, reply_text)
        return ceo_result

    # ── resolve company_id from sender (employee path) ───────────
    existing_emp = await get_employee_by_phone(db, sender)

    if existing_emp:
        company_id = existing_emp.company_id
    elif force_company_id is not None:
        company_id = force_company_id
    else:
        company_id = 1

    # ── Auto-register employee if first contact ──────────────────
    existing = await get_employee_by_phone(db, sender)
    if existing is None and sender != "unknown":
        placeholder_name = f"Employee_{sender[-4:]}"
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

    # ── Check for enquiry ──────────────────────────────────────
    enquiry_result = await extract_enquiry_from_message(text)
    if enquiry_result.get("is_enquiry"):
        enquiry = Enquiry(
            company_id=company_id,
            client_name=enquiry_result.get("client_name") or "Unknown Client",
            service_requested=enquiry_result.get("service_requested"),
            notes=enquiry_result.get("notes"),
        )
        db.add(enquiry)
        await db.flush()
        await db.refresh(enquiry)

        logger.info(
            "Enquiry saved: %s — %s",
            enquiry.client_name,
            enquiry.service_requested or "(no service)",
        )

        confirm_msg = (
            f"Enquiry saved for {enquiry.client_name}"
            + (f" - {enquiry.service_requested}" if enquiry.service_requested else "")
        )
        if sender != "unknown":
            await send_whatsapp_message(sender, confirm_msg)

        return {
            "status": "enquiry_created",
            "message_log_id": log.id,
            "enquiry_id": enquiry.id,
            "client_name": enquiry.client_name,
            "service_requested": enquiry.service_requested,
        }

    # ── Extract task via AI ──────────────────────────────────────
    # Fetch real employee names for this company only (phone-number placeholders are filtered out)
    known_names = await get_all_employee_names(db, company_id=company_id)

    logger.info("Incoming message: %s", text)
    
    from app.services.ai_service import analyze_progress_update

    # Let's see if the employee has an active task and this is a progress update
    employee_for_update = None
    active_task = None
    if sender != "unknown":
        employee_for_update = await get_employee_by_phone(db, sender)
        
    if employee_for_update:
        stmt = (
            select(Task)
            .where(
                Task.assigned_employee_id == employee_for_update.id,
                Task.company_id == employee_for_update.company_id,
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        task_res = await db.execute(stmt)
        active_task = task_res.scalars().first()
        
        if active_task:
            analysis = await analyze_progress_update(text, active_task.title, checkpoints_json=active_task.checkpoints)
            # If message starts with "UPDATE", always treat it as a progress update
            # even if AI couldn't classify it (e.g. "UPDATE i kinda did it...")
            if analysis.get("type") == "no_progress" and text.strip().upper().startswith("UPDATE"):
                from app.services.ai_service import _detect_blocker
                analysis = {
                    "type": "progress_update",
                    "progress_percent": analysis.get("progress_percent"),
                    "summary": text.strip()[6:].strip()[:120] or "Employee update",
                    "is_blocker": _detect_blocker(text),
                }
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

                # ── Smart Checkpoint completion ──────────────────
                checkpoint_msg = ""
                if active_task.checkpoints:
                    import json as _json
                    from app.services.ai_service import analyze_checkpoint_completion
                    try:
                        cps = _json.loads(active_task.checkpoints)
                        incomplete = [(i, cp) for i, cp in enumerate(cps) if not cp.get("done", False)]
                        if incomplete:
                            match_idx = analyze_checkpoint_completion(
                                text, [cp["text"] for _, cp in incomplete]
                            )
                            if match_idx is not None:
                                real_idx = incomplete[match_idx][0]
                                cps[real_idx]["done"] = True
                                active_task.checkpoints = _json.dumps(cps)
                                cp_text = cps[real_idx]["text"]
                                checkpoint_msg = f'\n✅ Checkpoint marked done: "{cp_text}"'
                                logger.info(
                                    'Checkpoint auto-completed: task=%s cp=%r',
                                    active_task.id, cp_text,
                                )
                    except (ValueError, TypeError, KeyError):
                        pass

                # ── Manager Blocker Alert ────────────────────────────
                if analysis.get("is_blocker") and not is_completion:
                    manager_phone = await _get_manager_phone(db, employee_for_update.company_id)
                    if manager_phone:
                        alert_msg = (
                            f"⚠️ PhantomPilot Alert: {employee_for_update.name} is stuck "
                            f"on \"{active_task.title}\".\n"
                            f"Detail: {summary or text[:100]}"
                        )
                        await send_whatsapp_message(manager_phone, alert_msg)
                        logger.info(
                            "Manager blocker alert sent for task #%s — %s",
                            active_task.id, employee_for_update.name,
                        )

                await db.flush()

                logger.info(
                    'Employee %s updated "%s": %s%% — %s',
                    employee_for_update.name, active_task.title, pct, summary,
                )
                confirm_msg = f"Great job! ✅ We'll notify your manager that \"{active_task.title}\" is done. Keep it up!" if is_completion else (f"Got it! 👍 Your manager will be updated — {pct}% progress on \"{active_task.title}\". Keep going!" if pct is not None else f"Got it! 👍 Your manager will be updated on \"{active_task.title}\". Keep going!")
                confirm_msg += checkpoint_msg
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
        # Forward unrecognized employee messages to the manager
        if employee_for_update and sender != "unknown" and active_task is not None:
            await forward_to_manager(db, employee_for_update, active_task, text)
            await send_whatsapp_message(
                sender,
                "📨 Your message has been forwarded to your manager. They'll get back to you shortly!",
            )
            logger.info("Employee message forwarded to manager from %s", employee_for_update.name)
            return {"status": "forwarded_to_manager", "message_log_id": log.id}
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

    # ── Duplicate task check — scoped to company ────────────────
    dup_stmt = (
        select(Task)
        .where(
            Task.title == extracted["title"],
            Task.assigned_employee_id == employee_id,
            Task.company_id == company_id,
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
        # Count prior tasks — only send reply guide on first assignment
        from sqlalchemy import func as _func
        prior_res = await db.execute(
            select(_func.count()).select_from(Task).where(
                Task.assigned_employee_id == employee.id,
                Task.company_id == company_id,
                Task.id != task.id,
            )
        )
        is_first_task = (prior_res.scalar() or 0) == 0

        task_notification = (
            f"PhantomPilot - New Task Assigned\n\n"
            f"Task: {task.title}\n"
            f"Description: {desc_str}\n"
            f"Due: {due_str}"
        )
        if is_first_task:
            task_notification += (
                "\n\nReply with:\n"
                "DONE - mark complete\n"
                "HELP - request assistance\n"
                "UPDATE <text> - send progress"
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
