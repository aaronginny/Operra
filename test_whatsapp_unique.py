"""One WhatsApp number, one user — the constraint, its write points, and the
boot check that proves it is in force.

Built from the production bug of 2026-09-25: Manju (company 22, broker_intel)
messaged the bot from her own number and was answered by the generic
pipeline, because a lower-id real_estate row held the same number. real_estate
is non-generic, so it won get_ceo_user's tie-break; it has no inbound
WhatsApp handler, so dispatch declined and the generic pipeline replied. See
app/services/whatsapp_identity.py.

The point of these checks is that the bad state cannot be CREATED, not that
it is resolved well once it exists.

    python test_whatsapp_unique.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_whatsapp_unique.py

Sections:
  A  fresh database: the index exists, the boot check passes, /health says so
  B  the database refuses a second holder — any code path, any format
  C  tonight's exact bug cannot be built, in either order, and routes right
  D  signup and PATCH /auth/profile: readable refusals, nothing left behind
  E  a database upgraded WITH a legacy duplicate: the boot check catches the
     missing index, the tripwire logs the ambiguous lookup, new duplicates
     are still refused, and resolving the duplicate completes the constraint
  F  every other account is untouched
"""

import asyncio
import logging
import os
import sys

TEST_DB_PATH = "_test_whatsapp_unique.db"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
IS_SQLITE = TEST_DB_URL.startswith("sqlite")
os.environ["DATABASE_URL"] = TEST_DB_URL
# Hermetic: broker_intel must never reach real Tavily/OpenAI from this suite.
os.environ["TAVILY_API_KEY"] = "tvly-your-tavily-api-key-here"
os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key-here"

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select, text as sa_text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import health_check  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.routes.auth_routes import ProfileUpdate, signup, update_profile  # noqa: E402
from app.schemas.auth_schema import UserCreate  # noqa: E402
from app.services import whatsapp_identity  # noqa: E402
from app.services.ceo_command_service import get_ceo_user  # noqa: E402
from app.services.launch_matcher import providers as providers_module  # noqa: E402
from app.services.launch_matcher.providers import RecordingProvider  # noqa: E402
from app.services.webhook_service import process_incoming_message  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

MANJU = "+919150390233"
MAHMOUD = "+971501112233"


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


class Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def at(self, level: int) -> list[str]:
        return [r.getMessage() for r in self.records if r.levelno == level]


async def reset(migrate: bool) -> None:
    """Empty schema, then create_all; `migrate` also runs the migrations —
    which is what a real boot does. Without it the database is in the state
    main's schema leaves it: no index."""
    await engine.dispose()
    if IS_SQLITE:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    else:
        async with engine.begin() as conn:
            await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa_text("CREATE SCHEMA public"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if migrate:
        await run_migrations(engine)


async def company(name: str, vertical: str) -> int:
    async with SessionLocal() as db:
        co = Company(name=name, vertical=vertical)
        db.add(co)
        await db.commit()
        return co.id


async def add_user(company_id: int, email: str, number: str | None) -> tuple[bool, int | None]:
    """(created, user_id). False when the database refused it."""
    async with SessionLocal() as db:
        u = User(company_id=company_id, name=email.split("@")[0], email=email,
                 role=UserRole.ceo, whatsapp_number=number)
        db.add(u)
        try:
            await db.commit()
            return True, u.id
        except IntegrityError:
            await db.rollback()
            return False, None


async def count(model) -> int:
    async with SessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def call_signup(email: str, number: str | None) -> dict:
    async with SessionLocal() as db:
        out = await signup(UserCreate(name="New", email=email, password="Password123",
                                      company_name=f"{email} Co", whatsapp_number=number), db)
        await db.commit()
        return out


async def call_profile(user_id: int, **fields) -> tuple[int, str | None]:
    """(status, stored number afterwards)."""
    async with SessionLocal() as db:
        me = await db.get(User, user_id)
        try:
            await update_profile(ProfileUpdate(**fields), db, me)
            await db.commit()
            status = 200
        except HTTPException as exc:
            await db.rollback()
            status = exc.status_code
    async with SessionLocal() as db:
        return status, (await db.get(User, user_id)).whatsapp_number


# ── A ────────────────────────────────────────────────────────

async def section_a() -> None:
    print("\n== A. fresh database ==")
    await reset(migrate=True)
    result = await whatsapp_identity.check_uniqueness(engine)
    check("A1 migration 037 creates the unique index on a fresh database",
          result["index_present"], str(result))
    check("A2 the boot check passes", result["ok"], str(result))
    health = await health_check()
    check("A3 /health reports whatsapp_unique=true, and nothing more about numbers",
          health == {"status": "ok", "whatsapp_unique": True}, str(health))


# ── B ────────────────────────────────────────────────────────

async def section_b() -> None:
    print("\n== B. the database refuses a second holder ==")
    await reset(migrate=True)
    c1, c2 = await company("One", "generic"), await company("Two", "generic")
    ok1, _ = await add_user(c1, "a@example.com", MANJU)
    ok2, _ = await add_user(c2, "b@example.com", MANJU)
    check("B1 the same number on a second user is refused by the database",
          ok1 and not ok2, f"{ok1}/{ok2}")
    ok3, _ = await add_user(c2, "c@example.com", "+9150390233")
    check("B2 ...so is a format variant with the same last 10 digits "
          "(the resolver's suffix fallback treats it as the same number)", not ok3)
    ok4, _ = await add_user(c2, "d@example.com", "+91 91503 90233")
    check("B3 ...and one with spaces in it", not ok4)
    ok5, _ = await add_user(c2, "e@example.com", "+919000000001")
    check("B4 a genuinely different number is fine", ok5)
    nulls = [await add_user(c2, f"n{i}@example.com", None) for i in range(3)]
    empties = [await add_user(c2, f"z{i}@example.com", "") for i in range(2)]
    check("B5 any number of users may have no number (NULL or empty)",
          all(ok for ok, _ in nulls + empties), str(nulls + empties))

    # Every other write path — a provisioning endpoint, a script, raw SQL.
    refused = False
    try:
        async with engine.begin() as conn:
            await conn.execute(sa_text(
                "UPDATE users SET whatsapp_number = :n WHERE email = 'e@example.com'"), {"n": MANJU})
    except IntegrityError:
        refused = True
    check("B6 a raw SQL UPDATE onto a held number is refused too — the guarantee "
          "does not depend on which code path writes", refused)


# ── C ────────────────────────────────────────────────────────

async def section_c() -> None:
    print("\n== C. tonight's exact bug cannot be built ==")
    for first, second in (("real_estate", "broker_intel"), ("broker_intel", "real_estate")):
        await reset(migrate=True)
        a = await company(f"{first} co", first)
        b = await company(f"{second} co", second)
        ok_a, _ = await add_user(a, "first@example.com", MANJU)
        ok_b, _ = await add_user(b, "second@example.com", MANJU)
        check(f"C1 {first} holds the number, then {second} tries: refused",
              ok_a and not ok_b, f"{ok_a}/{ok_b}")

    # And with the constraint in force, her real number reaches broker_intel.
    await reset(migrate=True)
    re_co = await company("Old RE test", "real_estate")
    bi_co = await company("Manju Ginny Real Estate", "broker_intel")
    await add_user(re_co, "re@example.com", "+919876500000")
    _ok, manju_id = await add_user(bi_co, "manju@example.com", MANJU)
    rec = RecordingProvider()
    providers_module.get_provider = lambda: rec
    async with SessionLocal() as db:
        resolved = await get_ceo_user(db, MANJU)
        result = await process_incoming_message(db, MANJU, "what landmarks are near JVC")
    check("C2 her number resolves to her", resolved is not None and resolved.id == manju_id,
          f"got {resolved.id if resolved else None}")
    check("C3 ...and broker_intel answers — not the generic pipeline",
          result.get("status") == "broker_intel" and rec.sent and rec.sent[0][0] == MANJU,
          str(result.get("status")))


# ── D ────────────────────────────────────────────────────────

async def section_d() -> None:
    print("\n== D. signup and profile edit ==")
    await reset(migrate=True)
    held_co = await company("Held", "broker_intel")
    _ok, holder_id = await add_user(held_co, "holder@example.com", MANJU)
    companies_before = await count(Company)

    out = await call_signup("taken@example.com", MANJU)
    check("D1 signup with a held number is refused with a readable message",
          out == {"success": False, "error": whatsapp_identity.NUMBER_IN_USE}, str(out))
    check("D2 ...and leaves no orphan company behind",
          await count(Company) == companies_before, f"{await count(Company)} vs {companies_before}")
    out = await call_signup("variant@example.com", "9150390233")
    check("D3 signup with the number typed without its country code is refused too",
          out.get("success") is False, str(out))
    out = await call_signup("fresh@example.com", "+919812345678")
    check("D4 signup with a free number works as before",
          out.get("success") is True and out.get("access_token"), str(out)[:80])
    out = await call_signup("nonumber@example.com", None)
    check("D5 signup with no number works as before", out.get("success") is True, str(out)[:80])

    async with SessionLocal() as db:
        fresh_id = (await db.execute(select(User.id).where(User.email == "fresh@example.com"))).scalar_one()
    status, stored = await call_profile(fresh_id, whatsapp_number=MANJU)
    check("D6 PATCH /auth/profile onto a held number -> 409, number unchanged",
          status == 409 and stored == "+919812345678", f"{status}/{stored}")
    status, stored = await call_profile(holder_id, whatsapp_number="+91 91503 90233")
    check("D7 re-saving your own number (any format) is not a conflict",
          status == 200 and stored == "+919150390233", f"{status}/{stored}")
    status, stored = await call_profile(fresh_id, whatsapp_number="+919800000099")
    check("D8 moving to a free number works", status == 200 and stored == "+919800000099",
          f"{status}/{stored}")
    status, stored = await call_profile(fresh_id, name="Renamed")
    check("D9 a name-only edit is untouched by any of this", status == 200, str(status))


# ── E ────────────────────────────────────────────────────────

async def section_e() -> None:
    print("\n== E. a database upgraded with a legacy duplicate ==")
    # main's schema, before this change: no index, and the duplicate that
    # production actually holds.
    await reset(migrate=False)
    re_co = await company("Old RE test", "real_estate")
    bi_co = await company("Manju Ginny Real Estate", "broker_intel")
    _ok, stale_id = await add_user(re_co, "stale@example.com", MANJU)
    _ok, manju_id = await add_user(bi_co, "manju@example.com", MANJU)

    cap = Captured()
    for name in ("app.services.whatsapp_identity", "app.services.ceo_command_service"):
        logging.getLogger(name).addHandler(cap)
        logging.getLogger(name).setLevel(logging.DEBUG)
    try:
        await run_migrations(engine)  # the boot: 037 fails, and is swallowed
        result = await whatsapp_identity.check_uniqueness(engine)
        check("E1 the index could not be created over the duplicate",
              not result["index_present"], str(result))
        check("E2 ...and the boot check says so instead of passing silently",
              result == {"index_present": False, "duplicate_groups": 1, "ok": False}
              and any("held by more than one user" in m for m in cap.at(logging.CRITICAL)),
              f"{result} / {cap.at(logging.CRITICAL)}")
        check("E3 the CRITICAL line carries a count, never a number",
              all(MANJU not in m and "9150390233" not in m for m in cap.at(logging.CRITICAL)))
        check("E4 /health reports whatsapp_unique=false",
              (await health_check())["whatsapp_unique"] is False)

        async with SessionLocal() as db:
            winner = await get_ceo_user(db, MANJU)
        check("E5 until it is resolved, routing is exactly as before (no silent change)",
              winner is not None and winner.id == stale_id, f"got {winner.id if winner else None}")
        check("E6 ...but the ambiguous lookup is now logged as an ERROR",
              any("users share this WhatsApp number" in m for m in cap.at(logging.ERROR)),
              str(cap.at(logging.ERROR)))

        out = await call_signup("third@example.com", MANJU)
        check("E7 even without the index, the write points refuse a third holder",
              out.get("success") is False, str(out))

        # Resolve it the recommended way: clear the number from the wrong row.
        async with SessionLocal() as db:
            (await db.get(User, stale_id)).whatsapp_number = None
            await db.commit()
        await run_migrations(engine)  # the next boot
        result = await whatsapp_identity.check_uniqueness(engine)
        check("E8 once resolved, the next boot creates the index and the check passes",
              result == {"index_present": True, "duplicate_groups": 0, "ok": True}, str(result))
        async with SessionLocal() as db:
            winner = await get_ceo_user(db, MANJU)
        check("E9 ...and her number now resolves to her",
              winner is not None and winner.id == manju_id, f"got {winner.id if winner else None}")
        ok, _ = await add_user(re_co, "again@example.com", MANJU)
        check("E10 ...and the duplicate can never come back", not ok)
    finally:
        for name in ("app.services.whatsapp_identity", "app.services.ceo_command_service"):
            logging.getLogger(name).removeHandler(cap)


# ── F ────────────────────────────────────────────────────────

async def section_f() -> None:
    print("\n== F. every other account is untouched ==")
    await reset(migrate=False)
    lm = await company("Mahmoud Advisory", "launch_matcher")
    gen = await company("Lenin Co", "generic")
    _ok, mahmoud_id = await add_user(lm, "mahmoud@example.com", MAHMOUD)
    _ok, lenin_id = await add_user(gen, "lenin@example.com", "+919444455555")
    async with SessionLocal() as db:
        before = {u.id: (u.whatsapp_number, u.company_id)
                  for u in (await db.execute(select(User))).scalars()}
    await run_migrations(engine)
    async with SessionLocal() as db:
        after = {u.id: (u.whatsapp_number, u.company_id)
                 for u in (await db.execute(select(User))).scalars()}
        m = await get_ceo_user(db, MAHMOUD)
        g = await get_ceo_user(db, "+919444455555")
    check("F1 the migration changes no row's data", before == after, f"{before} -> {after}")
    check("F2 a launch_matcher account's number still resolves to it",
          m is not None and m.id == mahmoud_id)
    check("F3 a generic account's number still resolves to it",
          g is not None and g.id == lenin_id)


async def main() -> None:
    print("=" * 68)
    print(f"  one WhatsApp number, one user  (DB: {TEST_DB_URL.split('@')[-1]})")
    print("=" * 68)
    await section_a()
    await section_b()
    await section_c()
    await section_d()
    await section_e()
    await section_f()

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
