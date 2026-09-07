"""Regression guard: get_ceo_user's FOUNDER_PHONE fallback must resolve the
founder by identity, never by position.

The fallback used to resolve to `select(User).order_by(User.id.asc())
.limit(1)` — the oldest user in the database, whatever company they belong
to. On a multi-tenant database "first row" and "the founder" stopped being
the same person long ago, so any sender whose last 10 digits matched
FOUNDER_PHONE was answered as that arbitrary user, inside that user's
company, under that company's vertical.

Same shape as migration 021: a broad rule written for one historical
convenience, still firing for everyone.

    python test_get_ceo_user_scope.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_get_ceo_user_scope.db"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
IS_SQLITE = TEST_DB_URL.startswith("sqlite")
os.environ["DATABASE_URL"] = TEST_DB_URL

from sqlalchemy import text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.models.company import Company  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.ceo_command_service import get_ceo_user  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

FOUNDER_PHONE = "+919150016161"
FOUNDER_EMAIL = "founder@example.com"
TENANT_PHONE = "+919150390233"


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


async def main() -> None:
    print("=" * 68)
    print("  get_ceo_user — FOUNDER_PHONE fallback resolves by identity")
    print("=" * 68)

    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        if not IS_SQLITE:
            await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa_text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        db.add(Company(id=1, name="Oldest Signup", vertical="generic"))
        db.add(Company(id=22, name="Broker Client", vertical="broker_intel"))
        db.add(Company(id=30, name="Founder Co", vertical="generic"))
        await db.flush()
        # user id 1 is the oldest row and is NOT the founder — the whole point.
        db.add(User(id=1, company_id=1, name="Oldest", email="oldest@example.com",
                     role=UserRole.ceo, whatsapp_number="+919000000001"))
        db.add(User(id=22, company_id=22, name="Broker", email="broker@example.com",
                     role=UserRole.ceo, whatsapp_number=TENANT_PHONE))
        db.add(User(id=30, company_id=30, name="Founder", email=FOUNDER_EMAIL,
                     role=UserRole.ceo, whatsapp_number=None))
        await db.commit()

    orig_phone, orig_email = settings.founder_phone, settings.founder_email
    settings.founder_phone, settings.founder_email = FOUNDER_PHONE, FOUNDER_EMAIL
    try:
        async with SessionLocal() as db:
            u = await get_ceo_user(db, FOUNDER_PHONE)
            check("1 FOUNDER_PHONE resolves to the FOUNDER, not the oldest row",
                  u is not None and u.id == 30 and u.email == FOUNDER_EMAIL,
                  f"got user_id={u.id if u else None}")

            u = await get_ceo_user(db, TENANT_PHONE)
            check("2 a tenant's own number resolves to that tenant",
                  u is not None and u.id == 22 and u.company_id == 22,
                  f"got user_id={u.id if u else None}")

            u = await get_ceo_user(db, "+971509999999")
            check("3 an unknown sender resolves to nobody (falls through to generic)",
                  u is None, f"got user_id={u.id if u else None}")

        # No user carries FOUNDER_EMAIL: must decline, not grab row 1.
        settings.founder_email = "nobody@example.com"
        async with SessionLocal() as db:
            u = await get_ceo_user(db, FOUNDER_PHONE)
            check("4 FOUNDER_EMAIL matching no user declines rather than "
                  "falling back to an arbitrary user",
                  u is None, f"got user_id={u.id if u else None}")

        # FOUNDER_EMAIL unset entirely: the fallback is inert.
        settings.founder_email = None
        async with SessionLocal() as db:
            u = await get_ceo_user(db, FOUNDER_PHONE)
            check("5 with FOUNDER_EMAIL unset the fallback cannot fire",
                  u is None, f"got user_id={u.id if u else None}")

        # ── The actual production failure: two users, one number ──
        # A stale generic row (lower id, so it wins a naive unordered query)
        # holding the same number as the vertical client.
        settings.founder_phone, settings.founder_email = FOUNDER_PHONE, FOUNDER_EMAIL
        async with SessionLocal() as db:
            db.add(User(id=5, company_id=1, name="Stale Duplicate",
                         email="stale@example.com", role=UserRole.ceo,
                         whatsapp_number=TENANT_PHONE))
            await db.commit()

        async with SessionLocal() as db:
            u = await get_ceo_user(db, TENANT_PHONE)
            check("6 with a DUPLICATE number, the vertical account wins over "
                  "the generic one (the production bug)",
                  u is not None and u.id == 22,
                  f"got user_id={u.id if u else None} "
                  f"(5 = the stale generic row that used to win)")

        # Stable across repeated calls — not luck of row order.
        async with SessionLocal() as db:
            ids = []
            for _ in range(4):
                u = await get_ceo_user(db, TENANT_PHONE)
                ids.append(u.id if u else None)
            check("7 resolution is deterministic across repeated lookups",
                  set(ids) == {22}, str(ids))

        # A duplicate where BOTH are generic still resolves deterministically.
        async with SessionLocal() as db:
            db.add(User(id=6, company_id=1, name="Second Generic",
                         email="gen2@example.com", role=UserRole.ceo,
                         whatsapp_number="+919111111111"))
            db.add(User(id=7, company_id=30, name="Third Generic",
                         email="gen3@example.com", role=UserRole.ceo,
                         whatsapp_number="+919111111111"))
            await db.commit()
        async with SessionLocal() as db:
            u = await get_ceo_user(db, "+919111111111")
            check("8 two generic rows tie-break to the lowest id, stably",
                  u is not None and u.id == 6, f"got user_id={u.id if u else None}")
    finally:
        settings.founder_phone, settings.founder_email = orig_phone, orig_email

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
