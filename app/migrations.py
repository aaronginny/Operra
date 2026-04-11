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
