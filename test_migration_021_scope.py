"""Regression guard: migration 021 must be a historical repair, not a rule.

Every entry in app/migrations.py reruns on every boot. Migration 021 was
written as a one-time fix — move the user holding a specific phone number
off a stale company 14 and onto company 1 — but its predicate was
`company_id != 1`, which made it a standing rule instead: any account
holding that number was pulled to company 1 on the next restart, forever.

It did exactly that to a freshly provisioned broker_intel account which had
been given the number as a live-test placeholder. The failure was silent —
the login still succeeded, resolving to the wrong tenant.

This test pins both halves of the corrected behaviour:
  * the historical repair still happens (a company-14 user IS moved), so
    narrowing the predicate did not quietly drop the fix on any database
    where it has not yet run;
  * no other account is touched, whatever its company or number.

Postgres only — migration 021 lives in _MIGRATIONS, which run_migrations
selects by dialect, and there is no SQLite mirror of it.

    TEST_DATABASE_URL=postgresql+asyncpg://... python test_migration_021_scope.py
"""

import asyncio
import os
import sys

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DB_URL or TEST_DB_URL.startswith("sqlite"):
    print("SKIPPED: migration 021 is Postgres-only; set TEST_DATABASE_URL to a "
          "Postgres URL to run this suite.")
    sys.exit(0)

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
from app.models.user import User, UserRole  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []
THE_NUMBER = "+919150016161"


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


async def main() -> None:
    print("=" * 68)
    print("  migration 021 scope — historical repair, not a standing rule")
    print("=" * 68)

    async with engine.begin() as conn:
        await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
        await conn.execute(sa_text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    # Companies with explicit ids so company 14 and a later company both exist.
    async with SessionLocal() as db:
        await db.execute(sa_text(
            "INSERT INTO companies (id, name, vertical) VALUES "
            "(1, 'Main', 'generic'), (14, 'Stale Signup', 'generic'), "
            "(22, 'Broker Intel Client', 'broker_intel')"))
        await db.commit()

    # The historical case: the number, sitting on the stale company 14.
    # The regression case: a LATER account holding the same number.
    async with SessionLocal() as db:
        db.add(User(id=101, company_id=14, name="Historical", email="hist@example.com",
                     role=UserRole.ceo, whatsapp_number=THE_NUMBER))
        db.add(User(id=102, company_id=22, name="Broker", email="broker@example.com",
                     role=UserRole.ceo, whatsapp_number=THE_NUMBER))
        db.add(User(id=103, company_id=22, name="Bystander", email="by@example.com",
                     role=UserRole.ceo, whatsapp_number="+971500000001"))
        await db.commit()

    await run_migrations(engine)

    async with SessionLocal() as db:
        rows = {u.id: u for u in (await db.execute(select(User))).scalars().all()}

    hist = rows.get(101)
    check("1 the historical company-14 user IS still repaired to company 1",
          hist is not None and hist.company_id == 1,
          f"company_id={hist.company_id if hist else 'MISSING'}")

    broker = rows.get(102)
    check("2 a LATER account with the same number is NOT reassigned",
          broker is not None and broker.company_id == 22,
          f"company_id={broker.company_id if broker else 'MISSING'}")

    bystander = rows.get(103)
    check("3 an unrelated account is untouched",
          bystander is not None and bystander.company_id == 22,
          f"company_id={bystander.company_id if bystander else 'MISSING'}")

    # Reruns must be stable — this is what actually bit us.
    await run_migrations(engine)
    async with SessionLocal() as db:
        rows2 = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    check("4 a SECOND boot changes nothing (the original failure mode)",
          rows2.get(102) is not None and rows2[102].company_id == 22
          and rows2.get(101) is not None and rows2[101].company_id == 1,
          f"101={rows2[101].company_id if 101 in rows2 else '-'} "
          f"102={rows2[102].company_id if 102 in rows2 else '-'}")

    check("5 the broker account survives both boots (not deleted by the "
          "company-14 orphan sweep)", 102 in rows2)

    await engine.dispose()
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
