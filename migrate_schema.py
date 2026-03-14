"""One-time migration: add columns introduced in recent updates.

Works with both SQLite and PostgreSQL.

Run with:
    python migrate_schema.py
"""

import asyncio

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# Columns to add: (table, column, type_sql)
NEW_COLUMNS = [
    ("employees", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("tasks", "last_followup_sent", "TIMESTAMP"),
    ("tasks", "last_urgent_reminder_sent", "TIMESTAMP"),
    ("tasks", "started_at", "TIMESTAMP"),
    ("tasks", "completed_at", "TIMESTAMP"),
    ("tasks", "delayed_count", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "help_requested", "BOOLEAN NOT NULL DEFAULT 0"),
    ("message_logs", "direction", "VARCHAR(10) NOT NULL DEFAULT 'incoming'"),
    ("tasks", "notification_sent", "BOOLEAN NOT NULL DEFAULT 0"),
    ("tasks", "reminder_interval_days", "INTEGER"),
    ("tasks", "progress_percent", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "last_update", "TIMESTAMP"),
]


async def main():
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.connect() as conn:
        for table, column, col_type in NEW_COLUMNS:
            # Check if column already exists
            existing = await conn.run_sync(
                lambda sync_conn, t=table: [
                    c["name"] for c in inspect(sync_conn).get_columns(t)
                ]
            )
            if column in existing:
                print(f"SKIP: {table}.{column} already exists")
                continue

            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            await conn.execute(text(sql))
            await conn.commit()
            print(f"OK:   {table}.{column} added")

    await engine.dispose()
    print("\nMigration complete.")


if __name__ == "__main__":
    asyncio.run(main())
