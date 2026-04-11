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
    # 002 — ensure users.whatsapp_number exists (CEO God Mode needs it)
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
    # 005 — cleanup junk tasks created by CEO God Mode bug (safe to re-run)
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
]


async def run_migrations(engine: AsyncEngine) -> None:
    """Run all pending column migrations on startup."""
    async with engine.begin() as conn:
        for name, sql in _MIGRATIONS:
            try:
                await conn.execute(text(sql.strip()))
                logger.info("Migration OK: %s", name)
            except Exception as exc:
                # Log but don't crash — column may already exist on non-PG drivers
                logger.warning("Migration skipped (%s): %s", name, exc)
