"""Daily Operations Report — generates and sends a summary to the founder."""

import logging
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.task import Task, TaskStatus
from app.services.analytics_service import get_employee_performance
from app.services.messaging_service import send_email, send_whatsapp_message

logger = logging.getLogger(__name__)

# Track whether we already sent today's report
_last_report_date: date | None = None


def _parse_report_time() -> tuple[int, int]:
    """Parse DAILY_REPORT_TIME env var into (hour, minute)."""
    parts = settings.daily_report_time.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


async def generate_daily_report(db: AsyncSession) -> str:
    """Build the daily operations summary text."""
    today = date.today().strftime("%B %d, %Y")

    # Task counts by status
    stmt = select(Task.status, func.count(Task.id)).group_by(Task.status)
    result = await db.execute(stmt)
    counts = {row[0]: row[1] for row in result.all()}

    total = sum(counts.values())
    completed = counts.get(TaskStatus.completed, 0)
    in_progress = counts.get(TaskStatus.in_progress, 0)
    pending = counts.get(TaskStatus.pending, 0)
    overdue = counts.get(TaskStatus.overdue, 0)
    delayed = counts.get(TaskStatus.delayed, 0)
    needs_help = counts.get(TaskStatus.needs_help, 0)

    # Employee performance
    perf = await get_employee_performance(db)

    # Employees needing help (help_requests > 0)
    help_list = [p for p in perf if p["help_requests"] > 0]
    help_section = ""
    if help_list:
        lines = [f"  • {p['employee_name']} ({p['help_requests']} requests)" for p in help_list]
        help_section = "\n".join(lines)
    else:
        help_section = "  None — all good!"

    # Top performers (completion_rate >= 80% with at least 1 completed task)
    stars = [p for p in perf if p["completion_rate"] >= 80 and p["tasks_completed"] >= 1]
    star_section = ""
    if stars:
        lines = [f"  ⭐ {p['employee_name']} — {p['completion_rate']}%" for p in stars]
        star_section = "\n".join(lines)
    else:
        star_section = "  No standout performers yet."

    report = (
        f"📊 Daily Operations Summary\n\n"
        f"Date: {today}\n\n"
        f"Total tasks: {total}\n"
        f"Completed: {completed}\n"
        f"In Progress: {in_progress}\n"
        f"Pending: {pending}\n"
        f"Overdue: {overdue}\n"
        f"Delayed: {delayed}\n"
        f"Needs Help: {needs_help}\n\n"
        f"Employees needing help:\n{help_section}\n\n"
        f"Top performers:\n{star_section}"
    )

    return report


async def send_daily_report() -> None:
    """Generate and send the daily report to the founder."""
    async with async_session() as db:
        report = await generate_daily_report(db)

    logger.info("Daily report generated:\n%s", report)

    if settings.founder_phone:
        await send_whatsapp_message(settings.founder_phone, report)
    else:
        logger.warning("FOUNDER_PHONE not set — daily report not sent via WhatsApp.")

    if settings.founder_email:
        await send_email(settings.founder_email, report, subject="📊 Daily Operations Summary")
    else:
        logger.warning("FOUNDER_EMAIL not set — daily report not sent via email.")


async def check_and_send_daily_report() -> None:
    """Called every scheduler tick. Sends the report once per day at the configured time."""
    global _last_report_date

    now = datetime.now()
    target_hour, target_minute = _parse_report_time()

    # Already sent today?
    if _last_report_date == now.date():
        return

    # Is it past the target time?
    if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
        _last_report_date = now.date()
        logger.info("Triggering daily report for %s", now.date())
        await send_daily_report()
