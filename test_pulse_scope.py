"""Regression guard: each company's morning pulse / vertical daily hook must
fire at ITS OWN configured time, independent of every other company.

Until 2026-09-08, a single module-level `_last_morning_pulse_date` gated
BOTH the employee morning pulse and every vertical's daily hook (the latter
called only as a trailing step inside the former). The outer scan picked
whichever company's window opened first that day, fired everything once, and
set the flag — so a second company on a different configured time never
fired at all that day, and _send_vertical_daily_hooks (broker_intel's daily
nudge, real_estate's broker pulse) never ran independently of the employee
sweep, even for a company with zero employees.

Concretely: adding the broker_intel client at 05:00 UTC silently cut off
every other tenant's 09:00 pulse for the rest of that day.

This is the scenario Aaron asked to be proven directly: two companies with
different pulse times, both firing independently, neither blocking the
other — plus that Mahmoud's launch_matcher account (no employees, no daily
hook registered for that vertical) is structurally untouched by either
sweep regardless of this fix, and that a company with no CompanySettings row
at all (true of every account provisioned directly rather than through the
Settings page) still fires reliably at the 09:00 default rather than only as
a side effect of some other company's window.

Plain asyncio script, no pytest — same convention as every other suite here.

    python test_pulse_scope.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_pulse_scope.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

TEST_DB_PATH = "_test_pulse_scope.db"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
IS_SQLITE = TEST_DB_URL.startswith("sqlite")
os.environ["DATABASE_URL"] = TEST_DB_URL

from sqlalchemy import select, text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.company_settings import CompanySettings  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.task import Task, TaskStatus  # noqa: E402
import app.services.reminder_service as rs  # noqa: E402
from app.verticals import bootstrap  # noqa: F401,E402  (registers verticals)
from app.verticals.registry import all_verticals  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


class RecordingSender:
    """Stands in for send_whatsapp_message — records instead of sending."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def __call__(self, to: str, body: str) -> bool:
        self.sent.append((to, body))
        return True


async def setup_db() -> dict:
    if IS_SQLITE:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    else:
        async with engine.begin() as conn:
            await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa_text("CREATE SCHEMA public"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    # check_can_send_morning_pulse (billing_service.py) gates the employee
    # pulse on an active trial or a paid tier. A bare Company() with none of
    # that set is billing-BLOCKED on Postgres — but reads as billing-ELIGIBLE
    # on SQLite, because is_premium's server_default is the Python string
    # "false" (see app/models/company.py), which Postgres's native boolean
    # parses correctly but SQLite reads back as a non-empty, truthy string.
    # That is a real, pre-existing, backend-specific bug — entirely unrelated
    # to the pulse-scope fix this test covers — and it means every company
    # below sets trial_ends_at explicitly rather than relying on ambient
    # billing-tier defaults, so this suite's own pass/fail is never at the
    # mercy of that divergence on either backend.
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=7)

    ctx: dict = {}
    async with SessionLocal() as db:
        # Company A: generic vertical, employees with active tasks, an
        # EXPLICIT CompanySettings row at 05:00 (mirrors the broker_intel
        # client's real setup, minus the vertical itself).
        a = Company(name="Company A (05:00, generic, has employees)", vertical="generic",
                     trial_ends_at=trial_ends_at)
        db.add(a)
        await db.flush()
        db.add(CompanySettings(company_id=a.id, morning_pulse_enabled=True,
                                morning_pulse_time="05:00"))
        emp_a = Employee(company_id=a.id, name="Alice", phone_number="+919990000001")
        db.add(emp_a)
        await db.flush()
        db.add(Task(company_id=a.id, title="Task A", assigned_employee_id=emp_a.id,
                     status=TaskStatus.pending))

        # Company B: generic vertical, employees with active tasks, an
        # EXPLICIT CompanySettings row at 09:00 — the historical default
        # every existing tenant effectively had before broker_intel existed.
        b = Company(name="Company B (09:00, generic, has employees)", vertical="generic",
                     trial_ends_at=trial_ends_at)
        db.add(b)
        await db.flush()
        db.add(CompanySettings(company_id=b.id, morning_pulse_enabled=True,
                                morning_pulse_time="09:00"))
        emp_b = Employee(company_id=b.id, name="Bilal", phone_number="+919990000002")
        db.add(emp_b)
        await db.flush()
        db.add(Task(company_id=b.id, title="Task B", assigned_employee_id=emp_b.id,
                     status=TaskStatus.pending))

        # Company C: NO CompanySettings row at all — mirrors every account
        # provisioned directly (Mahmoud's, the broker_intel client's) rather
        # than through the Settings UI. Must still fire at the 09:00 default.
        c = Company(name="Company C (no settings row, generic, has employees)",
                     vertical="generic", trial_ends_at=trial_ends_at)
        db.add(c)
        await db.flush()
        emp_c = Employee(company_id=c.id, name="Chen", phone_number="+919990000003")
        db.add(emp_c)
        await db.flush()
        db.add(Task(company_id=c.id, title="Task C", assigned_employee_id=emp_c.id,
                     status=TaskStatus.pending))

        # Mahmoud's actual shape: launch_matcher vertical, zero employees,
        # zero tasks. No CompanySettings row either.
        lm = Company(name="Mahmoud (launch_matcher, no employees)", vertical="launch_matcher")
        db.add(lm)
        await db.flush()

        # broker_intel-vertical company at 05:00 — its own daily hook must
        # fire independently of companies A/B/C's employee pulses entirely.
        bi = Company(name="Broker Intel Co (05:00)", vertical="broker_intel")
        db.add(bi)
        await db.flush()
        db.add(CompanySettings(company_id=bi.id, morning_pulse_enabled=True,
                                morning_pulse_time="05:00"))

        await db.commit()
        ctx.update(a=a.id, b=b.id, c=c.id, lm=lm.id, bi=bi.id)
    return ctx


def _at(hh: int, mm: int) -> datetime:
    d = datetime.now()
    return datetime(d.year, d.month, d.day, hh, mm)


async def tick(db, now: datetime) -> None:
    """One scheduler tick's worth of state refresh + the two sweeps under
    test, exactly as _check_and_remind now calls them."""
    rs._company_settings_cache.clear()
    rs._company_settings_cache.update(await rs._load_company_settings(db))
    await rs._send_morning_pulse(db, now)
    await rs._send_vertical_daily_hooks(db, now)
    await db.commit()


async def run_new_behaviour_checks(ctx: dict, sender: RecordingSender) -> None:
    print("\n== the actual scenario: two companies, two times, independent ==")

    async with SessionLocal() as db:
        # 04:50 — before EITHER window. Nothing fires.
        await tick(db, _at(4, 50))
    check("1 before any window: nothing sent yet", len(sender.sent) == 0, str(sender.sent))

    async with SessionLocal() as db:
        # 05:10 — company A's window (05:00) is open. B's (09:00) is not.
        await tick(db, _at(5, 10))
    sent_to = {t[0] for t in sender.sent}
    check("2 at 05:10, company A's employee IS messaged",
          "+919990000001" in sent_to, str(sent_to))
    check("3 at 05:10, company B's employee is NOT messaged yet "
          "(this is the bug: it used to be, immediately, regardless of B's own time)",
          "+919990000002" not in sent_to, str(sent_to))
    check("4 at 05:10, company C (no settings row, effective default 09:00) "
          "is NOT messaged yet", "+919990000003" not in sent_to, str(sent_to))

    async with SessionLocal() as db:
        # 05:20 — still in A's window. A must NOT be messaged again (dedup).
        await tick(db, _at(5, 20))
    check("5 re-ticking within A's own window does not double-send",
          len([t for t in sender.sent if t[0] == "+919990000001"]) == 1,
          str([t for t in sender.sent if t[0] == "+919990000001"]))

    async with SessionLocal() as db:
        # 09:10 — SAME DAY. B's window (09:00) is now open.
        await tick(db, _at(9, 10))
    sent_to = {t[0] for t in sender.sent}
    check("6 later THE SAME DAY, company B's employee IS messaged — "
          "this is the fix: A's earlier window did not consume B's slot",
          "+919990000002" in sent_to, str(sent_to))
    check("7 company C (no settings row) fires at its 09:00 default — "
          "proves it is no longer only a side effect of another company's window",
          "+919990000003" in sent_to, str(sent_to))
    check("8 company A is not re-messaged just because B's window opened",
          len([t for t in sender.sent if t[0] == "+919990000001"]) == 1)


async def run_vertical_hook_checks(ctx: dict) -> None:
    print("\n== vertical daily hooks fire at their OWN company's time, "
          "independent of the employee pulse entirely ==")

    # The previous section already ticked through 05:00 today, which marked
    # ctx["bi"] pulsed for today via the REAL send_daily_nudge. Reset so this
    # section's own 4:50 -> 5:10 -> 5:20 sequence starts clean; this is test
    # isolation, not a claim about production (there, today only happens once).
    rs._reset_pulse_state_for_tests()

    calls: list[tuple[str, int]] = []

    async def fake_daily(db, company_id):
        calls.append(("broker_intel", company_id))

    # Swap broker_intel's real daily hook for a spy, restore after.
    v = next(v for v in all_verticals() if v.name == "broker_intel")
    original = v.daily
    object.__setattr__(v, "daily", fake_daily)
    try:
        async with SessionLocal() as db:
            await tick(db, _at(4, 50))
        check("9 before broker_intel's 05:00 window: hook not called", calls == [], str(calls))

        async with SessionLocal() as db:
            await tick(db, _at(5, 10))
        check("10 at 05:10, broker_intel's daily hook fires for its own company",
              calls == [("broker_intel", ctx["bi"])], str(calls))

        async with SessionLocal() as db:
            await tick(db, _at(5, 20))
        check("11 re-ticking within its own window does not call it twice",
              calls == [("broker_intel", ctx["bi"])], str(calls))
    finally:
        object.__setattr__(v, "daily", original)


async def run_mahmoud_untouched_checks(ctx: dict, sender: RecordingSender) -> None:
    print("\n== Mahmoud's launch_matcher account: structurally untouched ==")

    before = len(sender.sent)
    async with SessionLocal() as db:
        # A time nothing in this test is configured for — pure "does a
        # generic sweep touch a company it has no business touching" check.
        await tick(db, _at(14, 0))
    check("12 no NEW sends triggered by an arbitrary tick",
          len(sender.sent) == before, f"before={before} after={len(sender.sent)}")

    from app.verticals.registry import get_vertical
    v = get_vertical("launch_matcher")
    check("13 launch_matcher has no daily hook registered at all",
          v is not None and v.daily is None)

    async with SessionLocal() as db:
        emp_count = len((await db.execute(
            select(Employee).where(Employee.company_id == ctx["lm"])
        )).scalars().all())
    check("14 Mahmoud's company has zero employees — the employee-pulse "
          "sweep has nothing to iterate for him regardless of this fix",
          emp_count == 0)


async def run_old_behaviour_regression_proof(ctx: dict) -> None:
    """Prove this test suite actually catches the original bug, not just
    that new code passes it. Same rigor as migration 021 / get_ceo_user
    today: temporarily reinstate the old global-gate shape in isolation and
    show the two-companies-different-times scenario fails.

    Reuses the companies setup_db already created — no need to recreate the
    database, and doing so a second time in the same process hits a Windows
    file-lock on the still-open SQLite handle from the first creation."""
    print("\n== proving the OLD global-gate design fails this exact scenario ==")

    async def old_style_tick(db, now: datetime, state: dict) -> list[str]:
        """A faithful, minimal reimplementation of the pre-fix gate: one
        shared date flag, break on the first matching company, unconditional
        send to every enabled company once tripped."""
        rs._company_settings_cache.clear()
        rs._company_settings_cache.update(await rs._load_company_settings(db))

        sent: list[str] = []
        today = now.date()
        if state.get("last_date") != today:
            should_pulse = False
            for cid, cs in rs._company_settings_cache.items():
                if cs.morning_pulse_enabled:
                    ph, pm = rs._company_pulse_time(cid)
                    pulse_dt = datetime(now.year, now.month, now.day, ph, pm)
                    if pulse_dt <= now < pulse_dt + timedelta(minutes=30):
                        should_pulse = True
                        break
            if should_pulse:
                # Unconditional: every enabled company, regardless of ITS OWN time.
                for cid, cs in rs._company_settings_cache.items():
                    if cs.morning_pulse_enabled:
                        sent.append(f"company={cid}")
                state["last_date"] = today
        return sent

    state: dict = {}

    async with SessionLocal() as db:
        sent_at_5am = await old_style_tick(db, _at(5, 10), state)
    check("15 [old design] 05:10 fires — but for EVERY enabled company at once, "
          "not just A's", f"company={ctx['a']}" in sent_at_5am and f"company={ctx['bi']}" in sent_at_5am,
          str(sent_at_5am))
    check("16 [old design] company B (09:00) was ALSO swept in at 05:10 — "
          "the exact bug: B gets pulsed 4 hours early",
          f"company={ctx['b']}" in sent_at_5am, str(sent_at_5am))

    async with SessionLocal() as db:
        sent_at_9am = await old_style_tick(db, _at(9, 10), state)
    check("17 [old design] SAME DAY at 09:00, nothing fires again at all — "
          "the exact bug this fix addresses: B's own window is moot, "
          "the day's slot was already consumed by A",
          sent_at_9am == [], str(sent_at_9am))


async def main() -> None:
    print("=" * 68)
    print(f"  per-company pulse scope  (DB: {TEST_DB_URL})")
    print("=" * 68)

    ctx = await setup_db()
    rs._reset_pulse_state_for_tests()

    sender = RecordingSender()
    orig_send = rs.send_whatsapp_message
    rs.send_whatsapp_message = sender
    try:
        await run_new_behaviour_checks(ctx, sender)
        await run_vertical_hook_checks(ctx)
        await run_mahmoud_untouched_checks(ctx, sender)
    finally:
        rs.send_whatsapp_message = orig_send

    rs._reset_pulse_state_for_tests()
    await run_old_behaviour_regression_proof(ctx)
    rs._reset_pulse_state_for_tests()

    await engine.dispose()
    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    print("\n" + "=" * 68)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = [r for r in results if r[0] == FAIL]
    print(f"  {passed}/{len(results)} checks passed")
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
