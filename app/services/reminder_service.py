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
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings

from app.database import async_session
from app.models.task import Task, TaskStatus
from app.models.company_settings import CompanySettings
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
_last_archive_cleanup_date = None

# {company_id: date} — the last day this company's proactive-message slot
# (employee morning pulse OR a vertical's daily hook) was evaluated. Replaces
# a single global `_last_morning_pulse_date` — see _company_pulse_due for why
# that was a bug, not a simplification.
_last_pulse_date_by_company: dict[int, date] = {}

# Cache of {company_id: CompanySettings} refreshed each scheduler tick
_company_settings_cache: dict[int, CompanySettings] = {}


async def _load_company_settings(db) -> dict[int, CompanySettings]:
    result = await db.execute(select(CompanySettings))
    return {row.company_id: row for row in result.scalars().all()}


def _company_freq_hours(company_id: int) -> int:
    s = _company_settings_cache.get(company_id)
    if s and s.reminders_enabled:
        return s.reminder_frequency_hours
    return 4  # default


def _company_reminders_enabled(company_id: int) -> bool:
    s = _company_settings_cache.get(company_id)
    return s.reminders_enabled if s is not None else True


def _company_pulse_enabled(company_id: int) -> bool:
    s = _company_settings_cache.get(company_id)
    return s.morning_pulse_enabled if s is not None else True


def _company_pulse_time(company_id: int) -> tuple[int, int]:
    """Return (hour, minute) for this company's morning pulse time."""
    s = _company_settings_cache.get(company_id)
    time_str = s.morning_pulse_time if s else "09:00"
    try:
        h, m = time_str.split(":")
        return int(h), int(m)
    except Exception:
        return 9, 0


def _company_pulse_due(company_id: int, now: datetime) -> bool:
    """True exactly when THIS company's own configured pulse window is open
    right now and it hasn't already been evaluated today.

    Shared by _send_morning_pulse and _send_vertical_daily_hooks so a
    company's employee pulse and its vertical's daily hook — conceptually
    "this company's one daily proactive-message slot" — share one dedup
    state, the same coupling the two already had (the vertical sweep used to
    run only as a trailing call inside the employee sweep). What changes is
    that the slot is now keyed per company instead of shared globally: until
    2026-09-08 this was a single `_last_morning_pulse_date` checked ONCE
    against whichever company's window opened FIRST that day, via
    `break` on the first match. That meant:
      * only one company's window could ever open per day — a second
        company on a different configured time never fired at all, because
        the process-wide date flag was already set;
      * once ANY window opened, EVERY enabled company's employees (and every
        vertical-registered company) were swept immediately, not gated by
        their OWN configured time at all.
    Concretely: adding a broker_intel client at 05:00 UTC silently cut off
    every other tenant's 09:00 pulse for the rest of that day, because the
    05:00 window satisfied the one shared gate first.

    A company absent from _company_settings_cache (no CompanySettings row —
    true of every account created directly rather than through the Settings
    page, e.g. Mahmoud's and the broker_intel client's) was invisible to that
    scan entirely, since it only iterated cache entries. Such a company could
    still be swept by _send_morning_pulse's own per-employee loop (which
    tolerates a missing cache entry via _company_pulse_enabled/
    _company_pulse_time's defaults) but only as a side effect of some OTHER
    company's window happening to open that day — never reliably at its own
    effective default of 09:00. Evaluating every company that actually has
    something to do (a task-having employee, or a registered vertical),
    rather than only those already in the settings cache, fixes this too.
    """
    if _last_pulse_date_by_company.get(company_id) == now.date():
        return False
    if not _company_pulse_enabled(company_id):
        return False
    ph, pm = _company_pulse_time(company_id)
    pulse_dt = datetime(now.year, now.month, now.day, ph, pm)
    return pulse_dt <= now < pulse_dt + timedelta(minutes=30)


def _mark_company_pulsed(company_id: int, now: datetime) -> None:
    """Record that this company's daily slot was evaluated today — set once
    a company is found due, regardless of whether the send inside that slot
    ultimately succeeded, matching the original global flag's own semantics
    (it was set once the gate opened, not once a message was confirmed
    sent)."""
    _last_pulse_date_by_company[company_id] = now.date()


def _reset_pulse_state_for_tests() -> None:
    """Test-only escape hatch, matching the pattern in app.verticals.registry.
    Production never calls this."""
    _last_pulse_date_by_company.clear()


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


async def _send_morning_pulse(db, now: datetime) -> None:
    """Send a personalized morning WhatsApp to every employee with active
    tasks, at THEIR OWN company's configured pulse time.

    References the first incomplete checkpoint to make the message actionable.

    Safe to call every scheduler tick: which companies are actually due is
    decided once, up front, via _company_pulse_due, so a company already
    handled today or not yet in its own window is simply skipped — see that
    function's docstring for why this must be a per-company decision rather
    than one shared gate the caller checks before calling this at all.
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

    # Filter out junk tasks from morning pulse (temp guard for "Inform …" titles)
    for emp_id in list(emp_tasks.keys()):
        emp_tasks[emp_id] = [t for t in emp_tasks[emp_id] if "inform" not in t.title.lower()]
        if not emp_tasks[emp_id]:
            del emp_tasks[emp_id]

    # Decided once, per company, before touching any employee — not per
    # employee, so two employees at the same company share one decision
    # rather than the second seeing the first's pass already consumed it.
    company_ids = {emp_task_list[0].company_id for emp_task_list in emp_tasks.values()}
    due_companies = {cid for cid in company_ids if _company_pulse_due(cid, now)}

    from app.services.billing_service import check_can_send_morning_pulse

    for emp_id, emp_task_list in emp_tasks.items():
        employee = emp_task_list[0].assigned_employee
        if not employee or not employee.phone_number:
            continue

        company_id = emp_task_list[0].company_id
        if company_id not in due_companies:
            continue

        # Morning pulse is a paid feature (basic / premium only)
        if not await check_can_send_morning_pulse(db, company_id):
            logger.debug("Morning pulse skipped for company=%s (free tier)", company_id)
            continue

        # Build message — pick the most important task (overdue first, then nearest deadline)
        priority_task = sorted(emp_task_list, key=lambda t: (
            0 if t.status == TaskStatus.overdue else 1,
            t.due_at or datetime(2099, 12, 31),
        ))[0]

        next_cp = _get_next_checkpoint(priority_task)
        checkpoint_line = ""
        if next_cp:
            checkpoint_line = f"\nYour manager is looking for progress on: \"{next_cp}\".\n"

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

    # Marked once per due company, after the loop, regardless of whether that
    # company actually had a phone-having employee to message this tick —
    # matching the original global flag, which was set once the gate opened,
    # not once a specific send succeeded (see _mark_company_pulsed).
    for company_id in due_companies:
        _mark_company_pulsed(company_id, now)


async def _send_vertical_daily_hooks(db, now: datetime) -> None:
    """Run every registered vertical's daily hook, at THAT COMPANY's own
    configured pulse time, once per company on that vertical.

    Replaces what used to be a hardcoded call per vertical — before this,
    the only entry was _send_real_estate_pulses below, and a second
    vertical's daily nudge (broker_intel's content-nudge feature) would have
    meant a second hardcoded call appended right here. Now it means calling
    register_vertical(Vertical(name=..., daily=...)) once, from that
    vertical's own module — see app.verticals.registry and
    app.verticals.bootstrap.

    Called independently from _check_and_remind rather than nested inside
    _send_morning_pulse (which is where it used to live, run once
    unconditionally at that function's end): nesting meant an unrelated
    exception anywhere earlier in the employee-pulse loop — one bad phone
    number, say — would propagate out and this would never run that tick, for
    ANY company, employee-pulse or not. Each is now independently gated and
    wrapped by the caller, so the two can no longer take each other down.

    Company enumeration, the per-company pulse-enabled toggle, and the
    per-company try/except are all generic here rather than duplicated by
    each vertical's own hook — a hook is just "what to do for one company",
    same contract send_broker_pulse(db, company_id) already had.
    """
    from app.models.company import Company
    from app.verticals.registry import all_verticals

    for vertical in all_verticals():
        if vertical.daily is None:
            continue

        stmt = select(Company.id).where(Company.vertical == vertical.name)
        company_ids = list((await db.execute(stmt)).scalars().all())

        # _company_pulse_due folds in the enabled-toggle check already, and —
        # the actual fix — each company's OWN configured time, independent of
        # every other company's, on this vertical or any other.
        for company_id in company_ids:
            if not _company_pulse_due(company_id, now):
                continue
            try:
                await vertical.daily(db, company_id)
            except Exception:
                logger.exception(
                    "Daily hook failed for company=%s vertical=%s", company_id, vertical.name,
                )
            # Marked regardless of success/failure above — same reasoning as
            # _mark_company_pulsed's own docstring: this is "today's slot was
            # evaluated", not "today's send succeeded".
            _mark_company_pulsed(company_id, now)


async def _send_real_estate_pulses(db) -> None:
    """Send the broker pulse to every real-estate company.

    Kept byte-for-byte as it was before the platform-refactor: production no
    longer calls this directly (see _send_vertical_daily_hooks above, which
    reaches send_broker_pulse the same way, generically, now that
    real_estate is registered with the vertical registry), but
    test_real_estate.py calls this function directly by name, so it stays
    exactly as it always was rather than becoming a thin wrapper around
    something else.

    Runs on the same 9 AM tick as the employee pulse above but is a separate
    message to a different audience: the employee pulse nudges an assignee
    about their tasks, this one gives the broker their overnight deal flow
    (new leads, matches found, pipeline counts).

    Companies whose vertical is not "real_estate" are filtered out in SQL, so
    a generic account is never even considered. One company's failure must not
    stop the others, so each is wrapped individually.
    """
    from app.models.company import Company
    from app.services.real_estate_notifications import send_broker_pulse

    stmt = select(Company.id).where(Company.vertical == "real_estate")
    company_ids = list((await db.execute(stmt)).scalars().all())
    if not company_ids:
        return

    for company_id in company_ids:
        # Respect the same per-company pulse toggle the employee pulse honours.
        if not _company_pulse_enabled(company_id):
            logger.debug("Broker pulse skipped for company=%s (disabled in settings)", company_id)
            continue
        try:
            await send_broker_pulse(db, company_id)
        except Exception:
            logger.exception("Broker pulse failed for company=%s", company_id)


async def _check_and_remind() -> None:
    """Single tick: query active tasks and send tiered follow-ups."""
    now = datetime.now()

    async with async_session() as db:
        global _company_settings_cache
        _company_settings_cache = await _load_company_settings(db)

        stmt = (
            select(Task)
            .where(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue]))
            .options(selectinload(Task.assigned_employee))
        )
        result = await db.execute(stmt)
        tasks = list(result.scalars().all())

        for task in tasks:
            # ── Guard: skip if reminders disabled for this company ──
            if not _company_reminders_enabled(task.company_id):
                continue

            # ── Guard: per-task reminders explicitly disabled (hours=0) ──
            if task.reminder_interval_hours == 0:
                continue

            # ── Guard: skip junk / brand-new tasks ───────────────
            created = (
                task.created_at.replace(tzinfo=None)
                if task.created_at and task.created_at.tzinfo
                else task.created_at
            )
            if task.due_at is not None and created:
                due_naive = task.due_at.replace(tzinfo=None) if task.due_at.tzinfo else task.due_at
                if due_naive < created:
                    logger.debug("Skipping task #%s — deadline before created_at (junk)", task.id)
                    continue
                if (now - created) < timedelta(hours=1):
                    logger.debug("Skipping task #%s — less than 1 hour old", task.id)
                    continue

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
                        # Already overdue — nag at per-task frequency if set,
                        # otherwise fall back to company-configured frequency
                        freq_hours = task.reminder_interval_hours or _company_freq_hours(task.company_id)
                        nag_interval = timedelta(hours=freq_hours)
                        last_nag = task.last_urgent_reminder_sent or task.due_at
                        last_nag_naive = last_nag.replace(tzinfo=None) if last_nag.tzinfo else last_nag
                        if (now - last_nag_naive) >= nag_interval:
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

        # ── Morning Pulse + vertical daily hooks (per-company time, 30-min window) ──
        # Called every tick, unconditionally: each decides for itself, per
        # company, whether that company is due right now — see
        # _company_pulse_due. Independent try/except per call so one failing
        # can never block the other (see _send_vertical_daily_hooks's own
        # docstring for why that decoupling matters).
        today = now.date()
        try:
            await _send_morning_pulse(db, now)
        except Exception:
            logger.exception("Morning pulse failed")

        try:
            await _send_vertical_daily_hooks(db, now)
        except Exception:
            logger.exception("Vertical daily hooks failed")

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


async def _cleanup_archived_tasks() -> None:
    """Delete completed tasks older than 20 days. Runs at most once per day."""
    global _last_archive_cleanup_date
    today = datetime.now().date()
    if _last_archive_cleanup_date == today:
        return

    from sqlalchemy import delete
    cutoff = datetime.now() - timedelta(days=20)

    async with async_session() as db:
        result = await db.execute(
            delete(Task).where(
                Task.status == TaskStatus.completed,
                Task.completed_at.is_not(None),
                Task.completed_at < cutoff,
            )
        )
        await db.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info("Archive cleanup: deleted %d completed tasks older than 20 days", deleted)

    _last_archive_cleanup_date = today


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

        # Daily archive cleanup (auto-delete completed tasks older than 20 days)
        try:
            await _cleanup_archived_tasks()
        except Exception:
            logger.exception("Error in archive cleanup.")

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
