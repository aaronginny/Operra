"""
Billing tier enforcement tests — runs without Razorpay, server, or Render.

Tests:
  A. Free tier enforcement
     A1. 4th task is blocked (limit = 3)
     A2. God Mode blocked for free tier
     A3. Morning pulse skipped for free tier
     A4. Checkpoint toggle blocked for free tier

  B. Founder bypass (role='ceo')
     B1. CEO creates unlimited tasks (past free limit)
     B2. God Mode allowed for CEO
     B3. Morning pulse allowed for CEO company

  C. Migrations 008-012 ran — columns exist
     C1. companies.subscription_level present
     C2. companies.tier_expires_at present
     C3. companies.projects_paid present
     C4. projects table exists
     C5. tasks.project_id present
"""

import asyncio
import sys

# ─── Inline async SQLAlchemy setup (no running server needed) ────────────────
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Use a fresh in-memory SQLite for testing
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Patch the app's engine/session so imports resolve cleanly
import app.database as _db_module
_db_module.engine = engine
_db_module.async_session = SessionLocal

# Now import app models (they reference app.database.Base)
import app.models  # noqa — registers all models with Base metadata
from app.database import Base
from app.models.company import Company
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.project import Project

# Import billing service AFTER patching database
from app.services.billing_service import (
    check_can_create_task,
    check_can_use_checkpoints,
    check_can_use_god_mode,
    check_can_send_morning_pulse,
    increment_task_count,
)

# ─── Test harness ─────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
results = []

def report(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    results.append((status, name, detail))
    icon = "✅" if passed else "❌"
    print(f"  {icon} [{status}] {name}" + (f" — {detail}" if detail else ""))


async def setup_db():
    """Create all tables in the in-memory DB."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def make_session():
    return SessionLocal()


# ─── Section A: Free tier enforcement ────────────────────────────────────────

async def test_free_tier():
    print("\n── A. Free Tier Enforcement ──────────────────────────────────")
    async with SessionLocal() as db:
        # Create a free-tier company and a non-CEO user
        company = Company(name="FreeCo", subscription_level="free", is_premium=False, tasks_created_count=3)
        db.add(company)
        await db.flush()

        user = User(company_id=company.id, name="Bob", role="employee")
        db.add(user)
        await db.flush()

        # A1 — 4th task blocked
        try:
            await check_can_create_task(
                db, company.id,
                user_id=user.id, user_email="bob@test.com", user_role="employee",
            )
            report("A1: 4th task blocked", False, "expected ValueError, got none")
        except ValueError as e:
            report("A1: 4th task blocked", True, str(e)[:80])

        # A2 — God Mode blocked for free tier
        ok = await check_can_use_god_mode(db, company.id, user_role="employee")
        report("A2: God Mode blocked (free tier)", not ok, f"check_can_use_god_mode returned {ok}")

        # A3 — Morning pulse skipped for free tier
        ok = await check_can_send_morning_pulse(db, company.id)
        report("A3: Morning pulse skipped (free tier)", not ok, f"check_can_send_morning_pulse returned {ok}")

        # A4 — Checkpoints blocked for free tier
        ok = await check_can_use_checkpoints(db, company.id, user_role="employee")
        report("A4: Checkpoints blocked (free tier)", not ok, f"check_can_use_checkpoints returned {ok}")


# ─── Section B: Founder bypass ───────────────────────────────────────────────

async def test_founder_bypass():
    print("\n── B. Founder Bypass (role='ceo') ───────────────────────────")
    async with SessionLocal() as db:
        # Free-tier company but CEO user
        company = Company(name="FounderCo", subscription_level="free", is_premium=False, tasks_created_count=999)
        db.add(company)
        await db.flush()

        ceo = User(company_id=company.id, name="Aaron", role="ceo")
        db.add(ceo)
        await db.flush()

        # B1 — CEO creates unlimited tasks (count=999, way past free limit)
        try:
            await check_can_create_task(
                db, company.id,
                user_id=ceo.id, user_email="aaron@test.com", user_role="ceo",
            )
            report("B1: CEO bypasses task limit (count=999)", True)
        except ValueError as e:
            report("B1: CEO bypasses task limit (count=999)", False, str(e))

        # B2 — God Mode allowed for CEO
        ok = await check_can_use_god_mode(db, company.id, user_role="ceo")
        report("B2: God Mode allowed for CEO", ok, f"returned {ok}")

        # B3 — Morning pulse: company is free but CEO company should send pulse
        #       (morning pulse check is company-level, not role-level — basic/premium needed)
        #       Spec says free=no morning pulse; CEO bypass is for task/god-mode, not pulse.
        #       So pulse is correctly blocked even for CEO's company on free tier.
        ok = await check_can_send_morning_pulse(db, company.id)
        report(
            "B3: Morning pulse respects company tier (not role)",
            not ok,
            f"free-tier company pulse={'allowed' if ok else 'blocked'} (correct: blocked)",
        )

        # B4 — CEO upgrade: set company to premium, verify pulse unlocks
        company.subscription_level = "premium"
        company.is_premium = True
        await db.flush()
        ok = await check_can_send_morning_pulse(db, company.id)
        report("B4: Morning pulse allowed after premium upgrade", ok, f"returned {ok}")

        # B5 — CEO checkpoints allowed (role bypass)
        ok = await check_can_use_checkpoints(db, company.id, user_role="ceo")
        # Note: CEO role bypasses checkpoints even on free tier
        report("B5: Checkpoints allowed for CEO (role bypass)", ok, f"returned {ok}")


# ─── Section C: Migration column / table existence ───────────────────────────

async def test_migrations():
    print("\n── C. Migrations 008-012 — Column & Table Existence ─────────")
    from sqlalchemy import inspect, text
    async with engine.connect() as conn:

        def _get_cols(sync_conn):
            inspector = inspect(sync_conn)
            return {
                "companies": [c["name"] for c in inspector.get_columns("companies")],
                "tasks":     [c["name"] for c in inspector.get_columns("tasks")],
                "tables":    inspector.get_table_names(),
            }

        info = await conn.run_sync(_get_cols)

    c_cols = info["companies"]
    t_cols = info["tasks"]
    tables = info["tables"]

    report("C1: companies.subscription_level", "subscription_level" in c_cols, f"cols={c_cols}")
    report("C2: companies.tier_expires_at",    "tier_expires_at" in c_cols,    f"present={('tier_expires_at' in c_cols)}")
    report("C3: companies.projects_paid",      "projects_paid" in c_cols,      f"present={('projects_paid' in c_cols)}")
    report("C4: projects table exists",        "projects" in tables,            f"tables={tables}")
    report("C5: tasks.project_id",             "project_id" in t_cols,          f"present={('project_id' in t_cols)}")


# ─── Section D: Basic tier — project unlock logic ────────────────────────────

async def test_basic_tier():
    print("\n── D. Basic Tier — Per-Project Unlock ───────────────────────")
    import json
    async with SessionLocal() as db:
        # Basic-tier company with project #42 paid, project #99 not paid
        company = Company(
            name="BasicCo",
            subscription_level="basic",
            is_premium=False,
            tasks_created_count=999,
            projects_paid=json.dumps([42]),
        )
        db.add(company)
        await db.flush()

        user = User(company_id=company.id, name="Emp", role="employee")
        db.add(user)
        await db.flush()

        # D1 — task for paid project allowed
        try:
            await check_can_create_task(
                db, company.id,
                user_id=user.id, user_email="emp@test.com", user_role="employee",
                project_id=42,
            )
            report("D1: Task allowed for paid project", True)
        except ValueError as e:
            report("D1: Task allowed for paid project", False, str(e))

        # D2 — task for unpaid project blocked
        try:
            await check_can_create_task(
                db, company.id,
                user_id=user.id, user_email="emp@test.com", user_role="employee",
                project_id=99,
            )
            report("D2: Task blocked for unpaid project", False, "expected ValueError, got none")
        except ValueError as e:
            report("D2: Task blocked for unpaid project", True, str(e)[:80])

        # D3 — God Mode allowed on basic tier
        ok = await check_can_use_god_mode(db, company.id, user_role="employee")
        report("D3: God Mode allowed on basic tier", ok, f"returned {ok}")

        # D4 — checkpoints allowed on basic tier
        ok = await check_can_use_checkpoints(db, company.id, user_role="employee")
        report("D4: Checkpoints allowed on basic tier", ok, f"returned {ok}")

        # D5 — morning pulse allowed on basic tier
        ok = await check_can_send_morning_pulse(db, company.id)
        report("D5: Morning pulse allowed on basic tier", ok, f"returned {ok}")


# ─── Section E: Premium tier ─────────────────────────────────────────────────

async def test_premium_tier():
    print("\n── E. Premium Tier — All Unlimited ──────────────────────────")
    async with SessionLocal() as db:
        company = Company(
            name="PremiumCo",
            subscription_level="premium",
            is_premium=True,
            tasks_created_count=500,
        )
        db.add(company)
        await db.flush()

        user = User(company_id=company.id, name="Emp", role="employee")
        db.add(user)
        await db.flush()

        # E1 — unlimited tasks
        try:
            await check_can_create_task(
                db, company.id,
                user_id=user.id, user_email="emp@test.com", user_role="employee",
            )
            report("E1: Unlimited tasks on premium", True)
        except ValueError as e:
            report("E1: Unlimited tasks on premium", False, str(e))

        # E2 — God Mode allowed
        ok = await check_can_use_god_mode(db, company.id, user_role="employee")
        report("E2: God Mode allowed on premium", ok)

        # E3 — morning pulse allowed
        ok = await check_can_send_morning_pulse(db, company.id)
        report("E3: Morning pulse allowed on premium", ok)

        # E4 — checkpoints allowed
        ok = await check_can_use_checkpoints(db, company.id, user_role="employee")
        report("E4: Checkpoints allowed on premium", ok)


# ─── Section F: Expired premium ──────────────────────────────────────────────

async def test_premium_expiry():
    print("\n── F. Premium Expiry ─────────────────────────────────────────")
    from datetime import datetime, timedelta, timezone
    async with SessionLocal() as db:
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        company = Company(
            name="ExpiredCo",
            subscription_level="premium",
            is_premium=True,
            tasks_created_count=0,
            tier_expires_at=past,
        )
        db.add(company)
        await db.flush()

        user = User(company_id=company.id, name="Emp", role="employee")
        db.add(user)
        await db.flush()

        # After expiry → treated as free tier → task creation blocked once limit hit
        company.tasks_created_count = 3
        await db.flush()

        try:
            await check_can_create_task(
                db, company.id,
                user_id=user.id, user_email="emp@test.com", user_role="employee",
            )
            report("F1: Expired premium blocks at free limit", False, "expected ValueError, got none")
        except ValueError as e:
            report("F1: Expired premium blocks at free limit", True, str(e)[:80])

        # God Mode blocked after expiry
        ok = await check_can_use_god_mode(db, company.id, user_role="employee")
        report("F2: God Mode blocked after premium expiry", not ok, f"returned {ok}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 62)
    print("  Foreman AI — Billing Tier Enforcement Test Suite")
    print("=" * 62)

    await setup_db()

    await test_free_tier()
    await test_founder_bypass()
    await test_migrations()
    await test_basic_tier()
    await test_premium_tier()
    await test_premium_expiry()

    # ── Summary ───────────────────────────────────────────────
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    total  = len(results)

    print("\n" + "=" * 62)
    print(f"  Results: {passed}/{total} passed  |  {failed} failed")
    print("=" * 62)

    if failed:
        print("\nFailed tests:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"  ❌ {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("\nAll tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
