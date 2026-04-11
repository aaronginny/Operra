"""Reminder scheduler — checks pending/in-progress tasks and sends reminders.

Uses a plain asyncio background loop (no external scheduler dependency).

Follow-up tiers:
  60 min before deadline → friendly progress check
  30 min before deadline → urgency reminder
  Deadline reached       → overdue alert + escalation every 4h
  9 AM daily             → personalized morning pulse with checkpoint info
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings

from app.database import async_session
from app.models.task import Task, TaskStatus
from app.services.daily_report_service import check_and_send_daily_report
from app.services.messaging_service import (
    format_deadline_alert,
    format_progress_check,
    format_reminder,
    format_urgent_reminder,
    send_email,
    send_whatsapp_message,
)

logger = logging.getLogger(__name__)

# How often the scheduler runs (seconds)
CHECK_INTERVAL = 60

# Thresholds
FOLLOWUP_WINDOW = timedelta(minutes=60)
URGENT_WINDOW = timedelta(minutes=30)

# Minimum gap between repeated nudges of the same tier (avoid spam)
NUDGE_COOLDOWN = timedelta(minutes=25)

# Escalation nagging for overdue tasks
OVERDUE_NAG_INTERVAL = timedelta(hours=4)

_scheduler_task: asyncio.Task | None = None
_last_checkin_date = None
_last_morning_pulse_date = None


def _get_next_checkpoint(task) -> str | None:
    """Return the text of the first incomplete checkpoint, or None."""
    import json
    if not task.checkpoints:
        return None
    try:
        cps = json.loads(task.checkpoints)
        for cp in cps:
            if not cp.get("done", False):
                return cp.get("text")
    except (ValueError, TypeError, KeyError):
        pass
    return None


async def _send_morning_pulse(db) -> None:
    """Send a personalized 9 AM WhatsApp to every employee with active tasks.

    References the first incomplete checkpoint to make the message actionable.
    """
    from app.models.employee import Employee

    stmt = (
        select(Task)
        .where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue]))
        .options(selectinload(Task.assigned_employee))
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # Group tasks by employee
    emp_tasks: dict[int, list[Task]] = {}
    for task in tasks:
        if task.assigned_employee_id:
            emp_tasks.setdefault(task.assigned_employee_id, []).append(task)

    for emp_id, emp_task_list in emp_tasks.items():
        employee = emp_task_list[0].assigned_employee
        if not employee or not employee.phone_number:
            continue

        # Build message — pick the most important task (overdue first, then nearest deadline)
        priority_task = sorted(emp_task_list, key=lambda t: (
            0 if t.status == TaskStatus.overdue else 1,
            t.due_at or datetime(2099, 12, 31),
        ))[0]

        next_cp = _get_next_checkpoint(priority_task)
        checkpoint_line = ""
        if next_cp:
            checkpoint_line = f"\nThe CEO is looking for progress on: \"{next_cp}\".\n"

        task_count = len(emp_task_list)
        extra_tasks = ""
        if task_count > 1:
            extra_tasks = f"\n(You also have {task_count - 1} other active task{'s' if task_count > 2 else ''}.)"

        msg = (
            f"Good morning {employee.name}! 🌅\n\n"
            f"For the \"{priority_task.title}\":"
            f"{checkpoint_line}"
            f"\nHow is it coming along?"
            f"{extra_tasks}\n\n"
            f"Reply with an update or type DONE if completed!"
        )

        await send_whatsapp_message(employee.phone_number, msg)
        logger.info("Morning pulse sent to %s (%d tasks)", employee.name, task_count)


async def _check_and_remind() -> None:
    """Single tick: query active tasks and send tiered follow-ups."""
    now = datetime.now()

    async with async_session() as db:
        stmt = (
            select(Task)
            .where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue]))
            .options(selectinload(Task.assigned_employee))
        )
        result = await db.execute(stmt)
        tasks = list(result.scalars().all())

        for task in tasks:
            if task.due_at is None:
                pass
            else:
                due = task.due_at.replace(tzinfo=None) if task.due_at.tzinfo else task.due_at
                employee = task.assigned_employee
                assignee_name = employee.name if employee else (task.assigned_to or "Team")
                assignee_phone = (employee.phone_number if employee else None) or "unknown"
                assignee_email = employee.email if employee else None

                time_left = due - now
                deadline_str = due.strftime("%I:%M %p").lstrip("0")

                # Tier 0: Overdue — escalation nagging every 4 hours
                if due < now:
                    if task.status != TaskStatus.overdue:
                        task.status = TaskStatus.overdue
                        msg = format_deadline_alert(task.title)
                        await send_whatsapp_message(assignee_phone, msg)
                        if assignee_email:
                            await send_email(assignee_email, msg)
                        logger.info("Marked task #%s as overdue.", task.id)
                    else:
                        # Already overdue — nag every 4 hours
                        last_nag = task.last_urgent_reminder_sent or task.due_at
                        last_nag_naive = last_nag.replace(tzinfo=None) if last_nag.tzinfo else last_nag
                        if (now - last_nag_naive) >= OVERDUE_NAG_INTERVAL:
                            hours_late = int((now - due).total_seconds() / 3600)
                            next_cp = _get_next_checkpoint(task)
                            cp_line = f'\nNext checkpoint: "{next_cp}"' if next_cp else ""
                            nag_msg = (
                                f"⏰ Overdue Reminder ({hours_late}h late)\n\n"
                                f"Task: {task.title}"
                                f"{cp_line}\n\n"
                                f"Please send an UPDATE or reply DONE if completed."
                            )
                            await send_whatsapp_message(assignee_phone, nag_msg)
                            task.last_urgent_reminder_sent = now
                            logger.info("Overdue escalation nag sent for task #%s (%dh late)", task.id, hours_late)
                    continue

                if time_left <= URGENT_WINDOW:
                    if _cooldown_ok(task.last_urgent_reminder_sent, now):
                        msg = format_urgent_reminder(task.title)
                        await send_whatsapp_message(assignee_phone, msg)
                        if assignee_email:
                            await send_email(assignee_email, msg)
                        task.last_urgent_reminder_sent = now
                    continue

                if time_left <= FOLLOWUP_WINDOW:
                    if _cooldown_ok(task.last_followup_sent, now):
                        # Extract next incomplete checkpoint (if any)
                        next_cp = _get_next_checkpoint(task)
                        msg = format_progress_check(assignee_name, task.title, deadline_str, next_checkpoint=next_cp)
                        await send_whatsapp_message(assignee_phone, msg)
                        if assignee_email:
                            await send_email(assignee_email, msg)
                        task.last_followup_sent = now

            # FEATURE 3 -> interval reminders
            if task.reminder_interval_days:
                last_up = task.last_update or task.created_at
                last_up_naive = last_up.replace(tzinfo=None) if last_up.tzinfo else last_up
                if (now - last_up_naive).days >= task.reminder_interval_days:
                    # check if we already nudged them recently
                    if _cooldown_ok(task.last_followup_sent, now):
                        employee = task.assigned_employee
                        assignee_phone = (employee.phone_number if employee else None) or "unknown"
                        msg = f"Interval Reminder\n\nDon\'t forget your task: {task.title}"
                        await send_whatsapp_message(assignee_phone, msg)
                        task.last_update = now # reset interval
                        task.last_followup_sent = now

        # ── Morning Pulse (9 AM daily) ──────────────────────────
        global _last_morning_pulse_date
        today = now.date()
        if now.hour >= 9 and _last_morning_pulse_date != today:
            try:
                await _send_morning_pulse(db)
                _last_morning_pulse_date = today
                logger.info("Morning pulse completed for %s", today)
            except Exception:
                logger.exception("Morning pulse failed")

        # Legacy daily check-in (replaced by morning pulse above)
        global _last_checkin_date
        # Kept for backward compat but morning pulse handles it now
        _last_checkin_date = today

        await db.commit()


def _cooldown_ok(last_sent: datetime | None, now: datetime) -> bool:
    """Return True if enough time has passed since the last nudge."""
    if last_sent is None:
        return True
    last = last_sent.replace(tzinfo=None) if last_sent.tzinfo else last_sent
    return (now - last) >= NUDGE_COOLDOWN


async def _scheduler_loop() -> None:
    """Infinite loop that runs _check_and_remind every CHECK_INTERVAL seconds."""
    logger.info("Reminder scheduler started (interval=%ss).", CHECK_INTERVAL)
    while True:
        try:
            await _check_and_remind()
        except Exception:
            logger.exception("Error in reminder scheduler tick.")

        # Daily operations report (runs once per day at configured time)
        try:
            await check_and_send_daily_report()
        except Exception:
            logger.exception("Error in daily report check.")

        await asyncio.sleep(CHECK_INTERVAL)


def start_scheduler() -> None:
    """Launch the scheduler as a background asyncio task."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        loop = asyncio.get_event_loop()
        _scheduler_task = loop.create_task(_scheduler_loop())
        logger.info("Reminder scheduler background task created.")


async def stop_scheduler() -> None:
    """Cancel the scheduler background task."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("Reminder scheduler stopped.")
    _scheduler_task = None
