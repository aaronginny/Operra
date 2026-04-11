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
