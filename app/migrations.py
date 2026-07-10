"""Lightweight startup migrations for columns added after initial deploy.

Each migration is idempotent — it uses IF NOT EXISTS / DO NOTHING so it is
safe to run on every startup regardless of whether the column already exists.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Individual migrations — add new ones at the bottom only
# ---------------------------------------------------------------------------

_MIGRATIONS = [
    # 001 — enquiry pipeline columns (added after initial PostgreSQL deploy)
    (
        "enquiries.stage",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS stage VARCHAR(30) DEFAULT NULL;
        """,
    ),
    (
        "enquiries.assigned_employee_id",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS assigned_employee_id INTEGER
            REFERENCES employees(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    (
        "enquiries.stage_history",
        """
        ALTER TABLE enquiries
        ADD COLUMN IF NOT EXISTS stage_history TEXT DEFAULT NULL;
        """,
    ),
    # 002 — ensure users.whatsapp_number exists (CEO Control Tower needs it)
    (
        "users.whatsapp_number",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(20) DEFAULT NULL;
        """,
    ),
    # 003 — smart checkpoints (sub-tasks) for tasks
    (
        "tasks.checkpoints",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS checkpoints TEXT DEFAULT NULL;
        """,
    ),
    # 004 — tiered billing columns for companies
    (
        "companies.subscription_level",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS subscription_level VARCHAR(50) NOT NULL DEFAULT 'basic';
        """,
    ),
    (
        "companies.is_premium",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT false;
        """,
    ),
    (
        "companies.tasks_created_count",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS tasks_created_count INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    # 005 — cleanup junk tasks created by CEO Control Tower bug (safe to re-run)
    (
        "cleanup.junk_ceo_tasks",
        """
        DELETE FROM tasks
        WHERE title ILIKE '%Inform Aaron about%'
           OR description ILIKE '%Tell Aaron that the deadline%';
        """,
    ),
    # 006 — owner account premium upgrade (whatsapp_number = '+919150016161')
    (
        "companies.owner_premium",
        """
        UPDATE companies
        SET is_premium = true, subscription_level = 'premium'
        WHERE id = (
            SELECT company_id FROM users
            WHERE whatsapp_number = '+919150016161'
            LIMIT 1
        );
        """,
    ),
    # 007 — premium + counter reset via role lookup (reliable fallback when
    #        whatsapp_number was not set in the DB — migration 006 may have hit 0 rows)
    (
        "companies.ceo_role_premium",
        """
        UPDATE companies
        SET is_premium = true, subscription_level = 'premium', tasks_created_count = 0
        WHERE id IN (
            SELECT DISTINCT company_id FROM users WHERE role = 'ceo'
        );
        """,
    ),
    # 008 — normalize subscription_level to 'free' for non-premium companies
    #        (old default was 'basic'; new tier vocabulary is free/basic/premium)
    (
        "companies.normalize_free_tier",
        """
        UPDATE companies
        SET subscription_level = 'free'
        WHERE subscription_level = 'basic' AND is_premium = false;
        """,
    ),
    # 009 — tiered billing: premium expiry timestamp
    (
        "companies.tier_expires_at",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS tier_expires_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 010 — tiered billing: JSON list of paid project IDs (basic per-project)
    (
        "companies.projects_paid",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS projects_paid TEXT DEFAULT NULL;
        """,
    ),
    # 011 — projects table (created by create_all; this migration is a safety net
    #        for existing deployments where the table may not yet exist)
    (
        "projects.table",
        """
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 012 — project_id FK on tasks (for per-project billing grouping)
    (
        "tasks.project_id",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # 013 — 7-day free trial: trial_ends_at column on companies
    (
        "companies.trial_ends_at",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 014 — 7-day free trial: backfill existing companies (created_at + 7 days)
    (
        "companies.trial_ends_at_backfill",
        """
        UPDATE companies
        SET trial_ends_at = created_at + INTERVAL '7 days'
        WHERE trial_ends_at IS NULL;
        """,
    ),
    # 015 — email OTP verification columns on users
    (
        "users.is_verified",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE;
        """,
    ),
    (
        "users.otp_code",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS otp_code VARCHAR(6) DEFAULT NULL;
        """,
    ),
    (
        "users.otp_expires_at",
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP DEFAULT NULL;
        """,
    ),
    # 016 — backfill: existing users (signed up before OTP) are already verified
    (
        "users.is_verified_backfill",
        """
        UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE;
        """,
    ),
    # 017 — Cashfree payment gateway: order ID and payment status columns
    (
        "companies.cashfree_order_id",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS cashfree_order_id VARCHAR(255) DEFAULT NULL;
        """,
    ),
    (
        "companies.payment_status",
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'unpaid';
        """,
    ),
    # 018 — employee↔manager message threads per task
    (
        "task_messages.table",
        """
        CREATE TABLE IF NOT EXISTS task_messages (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            sender VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 019 — task_updates table (employee UPDATE <text> messages saved per task)
    (
        "task_updates.table",
        """
        CREATE TABLE IF NOT EXISTS task_updates (
            id SERIAL PRIMARY KEY,
            task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
            employee_id INTEGER,
            update_text TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 020 — company_settings table (per-company reminder configuration)
    (
        "company_settings.table",
        """
        CREATE TABLE IF NOT EXISTS company_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
            morning_pulse_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            morning_pulse_time VARCHAR(5) NOT NULL DEFAULT '09:00',
            reminder_frequency_hours INTEGER NOT NULL DEFAULT 4,
            reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE
        );
        """,
    ),
    # 021 — fix CEO phone linked to wrong company_id
    #        The user with whatsapp_number '+919150016161' was registered under
    #        company_id=14 (a stale signup row) but all real data lives in company_id=1.
    #        Re-point their company_id so get_ceo_user() resolves the right company,
    #        then delete any remaining duplicate users in company 14 with no real data.
    (
        "users.fix_ceo_company",
        """
        UPDATE users
        SET company_id = 1
        WHERE whatsapp_number = '+919150016161'
          AND company_id != 1;
        """,
    ),
    (
        "users.drop_orphan_company14_users",
        """
        DELETE FROM users
        WHERE company_id = 14
          AND whatsapp_number IS NULL
          AND email NOT IN (
              SELECT email FROM users WHERE company_id = 1 AND email IS NOT NULL
          );
        """,
    ),
    # 022 — add pending_confirmation value to PostgreSQL taskstatus enum
    #        IF NOT EXISTS is supported since PostgreSQL 9.6 — safe to re-run.
    (
        "022_taskstatus_pending_confirmation",
        """
        ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'pending_confirmation';
        """,
    ),
    # 023 — per-task reminder schedule (hours)
    (
        "tasks.reminder_interval_hours",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS reminder_interval_hours INTEGER DEFAULT 4;
        """,
    ),
    # 024 — task edit tracking
    (
        "tasks.edited_at",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
        """,
    ),
    # 025 — notifications table (in-app inbox for employee activity)
    (
        "notifications.table",
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
            employee_id INTEGER,
            employee_name VARCHAR(255),
            message TEXT NOT NULL,
            type VARCHAR(20) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        """,
    ),
    # 026 — gender field for employee character avatars
    (
        "employees.gender",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS gender VARCHAR(10) NOT NULL DEFAULT 'neutral';
        """,
    ),
    # 027 — role field for employee cards (job title, editable from dashboard)
    (
        "employees.role",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS role VARCHAR(255) DEFAULT NULL;
        """,
    ),
    # 028 — departments/teams table (multi-business support)
    (
        "departments.table",
        """
        CREATE TABLE IF NOT EXISTS departments (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
    ),
    # 029 — department_id FK on employees (assign a team member to a department)
    (
        "employees.department_id",
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS department_id INTEGER
            REFERENCES departments(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
    # 030 — department_id FK on tasks (tag/filter tasks by team)
    (
        "tasks.department_id",
        """
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS department_id INTEGER
            REFERENCES departments(id) ON DELETE SET NULL DEFAULT NULL;
        """,
    ),
]


# ---------------------------------------------------------------------------
# SQLite fallbacks — the PostgreSQL migrations above use `IF NOT EXISTS`,
# `SERIAL` and `REFERENCES … ON DELETE`, which SQLite does not accept. On a
# fresh SQLite dev DB `create_all` builds every table/column from the ORM
# models, but existing SQLite DBs still need these ALTERs. SQLite ignores the
# duplicate-column error via the try/except in run_migrations().
# ---------------------------------------------------------------------------

_SQLITE_MIGRATIONS = [
    (
        "sqlite.departments.table",
        """
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id),
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "sqlite.employees.department_id",
        "ALTER TABLE employees ADD COLUMN department_id INTEGER REFERENCES departments(id);",
    ),
    (
        "sqlite.tasks.department_id",
        "ALTER TABLE tasks ADD COLUMN department_id INTEGER REFERENCES departments(id);",
    ),
]


async def run_migrations(engine: AsyncEngine) -> None:
    """Run all pending column migrations on startup."""
    is_sqlite = engine.dialect.name == "sqlite"
    migrations = _SQLITE_MIGRATIONS if is_sqlite else _MIGRATIONS

    async with engine.begin() as conn:
        for name, sql in migrations:
            try:
                await conn.execute(text(sql.strip()))
                logger.info("Migration OK: %s", name)
            except Exception as exc:
                # Log but don't crash — column may already exist on this driver
                logger.warning("Migration skipped (%s): %s", name, exc)
