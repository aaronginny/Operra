"""Reminder scheduler — checks pending/in-progress tasks and sends reminders.

Uses a plain asyncio background loop (no external scheduler dependency).

Follow-up tiers:
  60 min before deadline → friendly progress check
  30 min before deadline → urgency reminder
  Deadline reached       → overdue alert
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

_scheduler_task: asyncio.Task | None = None
_last_checkin_date = None


async def _check_and_remind() -> None:
    """Single tick: query active tasks and send tiered follow-ups."""
    now = datetime.now()

    async with async_session() as db:
        stmt = (
            select(Task)
            .where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]))
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

                # Tier 0: Overdue
                if due < now:
                    task.status = TaskStatus.overdue
                    msg = format_deadline_alert(task.title)
                    await send_whatsapp_message(assignee_phone, msg)
                    if assignee_email:
                        await send_email(assignee_email, msg)
                    logger.info("Marked task #%s as overdue.", task.id)
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
                        msg = format_progress_check(assignee_name, task.title, deadline_str)
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

        # FEATURE 5 -> Daily check-in bot
        global _last_checkin_date
        today = now.date()
        # let's say we send it at 9 AM or whenever, or just once a day if now.hour >= 9
        if getattr(settings, 'checkin_bot_enabled', True):
            if now.hour >= 9 and _last_checkin_date != today:
                # get all employees with active tasks
                stmt_emp = select(Task.assigned_employee_id).where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress])).distinct()
                emp_res = await db.execute(stmt_emp)
                emp_ids = emp_res.scalars().all()
                for eid in emp_ids:
                    if eid:
                        from app.models.employee import Employee
                        emp = await db.get(Employee, eid)
                        if emp and emp.phone_number:
                            await send_whatsapp_message(emp.phone_number, "Daily Update\n\nWhat progress did you make today?")
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
