"""Regression guard for the platform-refactor branch.

A persist_inbound=False vertical (launch_matcher today) must never let a
message it claims reach the generic pipeline's message_logs write or its
Employee auto-registration write — regardless of how dispatch_inbound and
process_incoming_message happen to be wired internally. Before this branch,
that guarantee existed as an ordering convention inside one function,
documented in a comment ("runs before everything below, including the
MessageLog write"). This file turns it into an assertion: it spies on the
database session's own add() calls during a real process_incoming_message()
call, so it fails on ANY code path that stages one of these writes for a
launch-matcher-routed message — committed or not — rather than only on
today's specific implementation shape.

Two scenarios, both required to trust the spy is measuring anything real:

  A. A launch-matcher advisor forwards a broadcast with a fake name+phone in
     the footer (the shape of a real forwarded developer broadcast) — this
     MUST NOT add a MessageLog or an Employee to the session.
  B. An unknown sender on a generic company sends an ADD-employee command —
     this MUST add both, exactly as every other tenant already relies on.
     Without this half, scenario A passing could just mean the spy never
     sees anything, not that the guarantee holds.

Also checks the registration guarantee itself: that importing
app.services.webhook_service alone — nothing more — is sufficient to
populate the vertical registry, which is what makes the ordering guarantee
above hold regardless of import order elsewhere in the app.

Same convention as the other test scripts here: a plain asyncio script, no
pytest, run directly. Set TEST_DATABASE_URL to run it against Postgres.

    python test_platform_refactor.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_platform_refactor.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_platform_refactor.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")

os.environ["DATABASE_URL"] = TEST_DB_URL

# run_generic_control_checks below sends a real generic-pipeline command
# through process_incoming_message, which routes to ai_service.py's OpenAI-
# guarded extraction. That must stay on the rule-based fallback regardless
# of what real key sits in the local .env (kept there for broker_intel's
# live-verification probes — see search.py/extraction.py) or this suite
# silently starts making live OpenAI calls.
os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key-here"

from sqlalchemy import select as sa_select, text as sa_text  # noqa: E402
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
from app.models.message_log import MessageLog  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# Importing webhook_service is the entire point of this import: it is what
# should populate the vertical registry as a side effect (see
# app.verticals.bootstrap), with nothing else imported first. That is a
# stronger check than importing app.main (which pulls in every route module
# and would pass even if webhook_service itself didn't do the eager import).
from app.services.webhook_service import process_incoming_message  # noqa: E402
import app.services.webhook_service as webhook_service_module  # noqa: E402
from app.services.launch_matcher.providers import RecordingProvider  # noqa: E402
from app.verticals.registry import get_vertical  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


# ── WhatsApp stubs — nothing in this file may hit the real Meta API ───────
#
# Two separate provider seams exist in this codebase, so both need stubbing:
# launch_matcher resolves its own provider via get_provider() (same
# mechanism, same reasoning as test_launch_matcher.py); the generic pipeline
# in webhook_service calls messaging_service.send_whatsapp_message /
# send_welcome_message directly, bound into webhook_service's own module
# namespace by its `from ... import ...` — patching the source module alone
# would miss that binding, so webhook_service's own names are patched
# instead (same pattern test_real_estate.py already uses for its equivalent
# modules).
sent_messages: list[tuple[str, str]] = []
_default_provider = RecordingProvider()


def install_recording_provider() -> None:
    import app.services.launch_matcher.handler as handler_module
    import app.services.launch_matcher.providers as providers_module

    providers_module.get_provider = lambda: _default_provider
    handler_module.get_provider = lambda: _default_provider


async def _fake_send_whatsapp_message(phone_number: str, message: str) -> bool:
    sent_messages.append((phone_number, message))
    return True


async def _fake_send_welcome_message(phone_number: str) -> None:
    return None


def install_whatsapp_stub() -> None:
    webhook_service_module.send_whatsapp_message = _fake_send_whatsapp_message
    webhook_service_module.send_welcome_message = _fake_send_welcome_message


class AddSpy:
    """Records the class name of every object passed to db.add() while
    installed, then restores the session's original add().

    Hooks add() itself rather than checking the database afterward on
    purpose: add() is where an object is staged into the session, which
    happens before flush and before commit. That means this catches a write
    even if something downstream rolled it back — the object still touched
    the session, which is the property this file cares about (a
    launch-matcher-routed message must never even momentarily stage a
    MessageLog or an Employee, not just "never permanently persist one").
    """

    def __init__(self, session):
        self._session = session
        self._orig_add = session.add
        self.added_types: list[str] = []

    def __enter__(self) -> "AddSpy":
        def spy_add(instance, *a, **kw):
            self.added_types.append(type(instance).__name__)
            return self._orig_add(instance, *a, **kw)

        self._session.add = spy_add
        return self

    def __exit__(self, *exc_info) -> None:
        self._session.add = self._orig_add


ADVISOR_PHONE = "+971500000091"
UNKNOWN_EMPLOYEE_PHONE = "+919876500091"

# Distinctive enough that it could only appear in message_logs via this
# exact call — if either piece ever shows up in raw_text, it leaked from
# here.
PII_FINGERPRINT_NAME = "Zzz Regression Canary"
PII_FINGERPRINT_PHONE = "+971509998888"
FORWARDED_BROADCAST = (
    "Sobha Hartland II | 1BR from AED 1.4M | 60/40 | EOI Thursday\n\n"
    f"For more info contact {PII_FINGERPRINT_NAME} {PII_FINGERPRINT_PHONE}"
)

# A fully self-contained, synchronous command — matched entirely by regex in
# handle_add_employee, with no AI/network call on the path to a result. Kept
# deliberately different from an AI-routed task message so this scenario
# stays fast, deterministic, and offline like the rest of this suite.
GENERIC_ADD_COMMAND = "ADD Ravi +919876543210"


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

    ctx: dict = {}
    async with SessionLocal() as db:
        advisor_co = Company(name="Regression Advisory", vertical="launch_matcher")
        db.add(advisor_co)
        await db.flush()
        advisor = User(
            company_id=advisor_co.id, name="Advisor", email="advisor-canary@example.com",
            role=UserRole.ceo, whatsapp_number=ADVISOR_PHONE,
        )
        db.add(advisor)

        generic_co = Company(name="Generic Co Canary")  # vertical defaults to "generic"
        db.add(generic_co)
        await db.flush()

        ctx.update(
            advisor_company_id=advisor_co.id,
            generic_company_id=generic_co.id,
        )
        await db.commit()
    return ctx


async def run_registration_checks() -> None:
    print("\n-- A. Registry is populated by importing webhook_service alone --")

    lm = get_vertical("launch_matcher")
    check("A1. launch_matcher is registered", lm is not None, str(lm))
    check("A2. launch_matcher has an inbound handler registered",
          lm is not None and lm.inbound is not None)
    check("A3. launch_matcher is registered with persist_inbound=False",
          lm is not None and lm.persist_inbound is False)

    re_v = get_vertical("real_estate")
    check("A4. real_estate is registered", re_v is not None, str(re_v))
    check("A5. real_estate has a daily hook registered",
          re_v is not None and re_v.daily is not None)


async def run_pii_isolation_checks() -> None:
    print("\n-- B. launch-matcher-routed message never reaches message_logs/employees --")

    async with SessionLocal() as db:
        with AddSpy(db) as spy:
            try:
                result = await process_incoming_message(
                    db=db, sender=ADVISOR_PHONE, text=FORWARDED_BROADCAST,
                )
            except Exception as exc:  # defensive: a crash must still show as a check, not a stack trace
                result = {"status": "exception", "error": repr(exc)}
        try:
            await db.commit()
        except Exception:
            await db.rollback()

    check("B1. message was actually claimed by the launch_matcher vertical",
          result.get("status") == "launch_matcher", str(result))
    check("B2. nothing at all was added to the session",
          spy.added_types == [], str(spy.added_types))
    check("B3. no MessageLog was ever added to the session",
          "MessageLog" not in spy.added_types, str(spy.added_types))
    check("B4. no Employee was ever added to the session",
          "Employee" not in spy.added_types, str(spy.added_types))

    # Belt and braces beyond the spy: confirm the fingerprint never landed
    # in the table, in case some future write reaches message_logs by a
    # route db.add() wouldn't see (a raw INSERT, a bulk helper). The spy
    # above is the primary guard; this is a second, independent check on
    # the actual persisted state.
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sa_select(MessageLog).where(
                    MessageLog.raw_text.contains(PII_FINGERPRINT_PHONE)
                )
            )
        ).scalars().all()
    check("B5. the PII fingerprint never landed in message_logs.raw_text",
          len(rows) == 0, f"{len(rows)} matching row(s)")


async def run_generic_control_checks(ctx: dict) -> None:
    print("\n-- C. control: a generic-company message DOES log + auto-register --")
    print("   (proves B's spy isn't vacuously passing because nothing ever adds anything)")

    async with SessionLocal() as db:
        with AddSpy(db) as spy:
            try:
                result = await process_incoming_message(
                    db=db, sender=UNKNOWN_EMPLOYEE_PHONE, text=GENERIC_ADD_COMMAND,
                    force_company_id=ctx["generic_company_id"],
                )
            except Exception as exc:
                result = {"status": "exception", "error": repr(exc)}
        try:
            await db.commit()
        except Exception:
            await db.rollback()

    check("C1. a MessageLog WAS added for a normal generic-company message",
          "MessageLog" in spy.added_types, str(spy.added_types))
    check("C2. an Employee WAS auto-registered for a first-contact sender",
          "Employee" in spy.added_types, str(spy.added_types))
    check("C3. was not accidentally routed into the launch_matcher vertical",
          result.get("status") != "launch_matcher", str(result))


async def main() -> None:
    install_recording_provider()
    install_whatsapp_stub()
    ctx = await setup_db()

    await run_registration_checks()
    await run_pii_isolation_checks()
    await run_generic_control_checks(ctx)

    passed = sum(1 for r, _, _ in results if r == PASS)
    failed = sum(1 for r, _, _ in results if r == FAIL)
    print("\n" + "=" * 64)
    print(f"  Results: {passed}/{len(results)} passed  |  {failed} failed")
    print("=" * 64)

    if failed:
        print("\nFAILED checks:")
        for r, name, detail in results:
            if r == FAIL:
                print(f"  - {name}" + (f"  ({detail})" if detail else ""))
        sys.exit(1)
    print("\nAll platform-refactor regression checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
