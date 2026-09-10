"""Verification for the broker_intel vertical.

Runs the real FastAPI app's own inbound path against a throwaway database.
Same convention as the other suites here: a plain asyncio script, no pytest.
Set TEST_DATABASE_URL to run it against Postgres.

    python test_broker_intel.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_broker_intel.py

Sections:
  A  intent parsing — how she names a project/area (design question 1)
  B  the caveat property — enforced over EVERY reply-producing entry point
  C  feature 1, lead intel, both formats, end to end
  D  feature 2, the daily nudge and its reply
  E  isolation — nothing written, generic pipeline never reached (session spy)
  F  other verticals unaffected
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_broker_intel.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")
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
from app.models.message_log import MessageLog  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.broker_intel import formatter, intents, state  # noqa: E402
from app.services.broker_intel.content import StubContentGenerator  # noqa: E402
from app.services.broker_intel.handler import (  # noqa: E402
    BROKER_INTEL_VERTICAL,
    build_reply,
    send_daily_nudge,
)
from app.services.launch_matcher import providers as providers_module  # noqa: E402
from app.services.launch_matcher.providers import RecordingProvider  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

BROKER_PHONE = "+971500000077"
STRANGER_NAME = "Zzq Stranger Leadperson"
STRANGER_PHONE = "+971509998887"


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


def install_recorder() -> RecordingProvider:
    """Every send in this suite goes to a recorder, never to Meta."""
    rec = RecordingProvider()
    providers_module.get_provider = lambda: rec
    import app.services.broker_intel.handler as h  # noqa: F401
    return rec


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
        co = Company(name="Mom Realty", vertical=BROKER_INTEL_VERTICAL)
        db.add(co)
        await db.flush()
        db.add(User(company_id=co.id, name="Mom", email="mom@placeholder.local",
                     role=UserRole.ceo, whatsapp_number=BROKER_PHONE))
        await db.flush()
        ctx["company_id"] = co.id
        await db.commit()
    return ctx


# ── A. intent parsing ────────────────────────────────────────

def run_intent_checks() -> None:
    print("\n== A. intent parsing — how she names a project/area ==")

    i = intents.parse("tell me about Sobha Hartland")
    check("A1 'tell me about X' -> lead_intel with the phrasing stripped",
          i.kind == "lead_intel" and i.subject == "Sobha Hartland", f"{i.kind}/{i.subject}")

    i = intents.parse("what about JVC?")
    check("A2 a known area resolves via the shared UAE table",
          i.kind == "lead_intel" and i.area == "JVC" and i.emirate == "Dubai",
          f"{i.area}/{i.emirate}")

    i = intents.parse("anything on Yas Island")
    check("A3 an Abu Dhabi area maps to its emirate",
          i.kind == "lead_intel" and i.emirate == "Abu Dhabi", str(i.emirate))

    i = intents.parse("ARTICLE")
    check("A4 bare ARTICLE is a content request", i.kind == "content" and i.value == "article",
          f"{i.kind}/{i.value}")
    i = intents.parse("fun fact")
    check("A5 bare FUN FACT is a content request", i.kind == "content" and i.value == "fun_fact",
          f"{i.kind}/{i.value}")

    i = intents.parse("ME")
    check("A6 bare ME is a format choice", i.kind == "audience" and i.value == "self",
          f"{i.kind}/{i.value}")
    i = intents.parse("lead")
    check("A7 bare LEAD is a format choice", i.kind == "audience" and i.value == "lead",
          f"{i.kind}/{i.value}")

    # The word-boundary cases: geography must not be eaten by keywords.
    i = intents.parse("tell me about Meydan")
    check("A8 'me' inside 'Meydan' is not a format choice",
          i.kind == "lead_intel" and i.emirate == "Dubai", f"{i.kind}/{i.emirate}")
    i = intents.parse("article about JVC")
    check("A9 'article about JVC' is a briefing, not a post request",
          i.kind == "lead_intel" and i.area == "JVC", f"{i.kind}/{i.area}")

    i = intents.parse("Sobha Hartland, for the lead")
    check("A10 project + format in one message needs no follow-up question",
          i.kind == "lead_intel" and i.audience == "lead", f"{i.kind}/{i.audience}")

    check("A11 empty/unusable text -> unknown",
          intents.parse("").kind == "unknown" and intents.parse("👍").kind == "unknown")


# ── B. the caveat property ───────────────────────────────────

def run_caveat_checks() -> None:
    print("\n== B. sourcing caveat — enforced on every content-bearing reply ==")
    lines = ["Prices in the area have risen sharply.", "Yields look strong."]

    contentful = {
        "render_lead_intel/self": formatter.render_lead_intel("X", lines, "self"),
        "render_lead_intel/lead": formatter.render_lead_intel("X", lines, "lead"),
        "render_social_caption/article": formatter.render_social_caption("article", lines),
        "render_social_caption/fun_fact": formatter.render_social_caption("fun_fact", lines),
    }
    for name, body in contentful.items():
        check(f"B1 {name} carries the caveat", formatter.MARKET_CAVEAT in body, body[-80:])

    check("B2 the caveat names DLD explicitly and marks the content AI-generated",
          "DLD" in formatter.MARKET_CAVEAT and "AI-generated" in formatter.MARKET_CAVEAT,
          formatter.MARKET_CAVEAT)

    # Structural: one bullets-to-body path, and it has no opt-out.
    import inspect
    src = inspect.getsource(formatter)
    check("B3 _content_reply is the only place bullets become a body",
          src.count("def _bullets(") == 1 and src.count("_bullets(") == 2,
          f"_bullets referenced {src.count('_bullets(')}x")
    check("B4 _content_reply takes no flag that could disable the caveat",
          "def _content_reply(header: str, lines: list[str]) -> str:" in src)

    # The lead-ready format is forwarded verbatim, so it must not address her.
    lead_body = contentful["render_lead_intel/lead"]
    check("B5 lead-ready format carries no internal-note language",
          not any(w in lead_body.lower() for w in ("your briefing", "for you", "fyi", "note:")),
          lead_body[:80])

    # A failed generation must not be papered over with market-sounding filler.
    unavailable = formatter.render_unavailable()
    check("B6 the generation-failure reply makes no market claim",
          formatter.MARKET_CAVEAT not in unavailable and "•" not in unavailable)


# ── C. feature 1 ─────────────────────────────────────────────

async def run_lead_intel_checks(company_id: int) -> None:
    print("\n== C. feature 1 — lead intel on demand ==")
    state._reset_for_tests()
    gen = StubContentGenerator()

    r1 = await build_reply(company_id, BROKER_PHONE, "tell me about Sobha Hartland", gen)
    check("C1 first message asks which format, and generates nothing yet",
          "ME" in r1 and "LEAD" in r1 and not gen.calls, f"calls={gen.calls}")

    r2 = await build_reply(company_id, BROKER_PHONE, "ME", gen)
    check("C2 answering ME returns the briefing", "•" in r2 and formatter.MARKET_CAVEAT in r2)
    check("C3 the briefing is bulleted, not paragraphs",
          r2.count("•") >= 3 and max(len(x) for x in r2.splitlines()) < 200)
    check("C4 the subject survived the two-step exchange",
          any("Sobha Hartland" in c[1] for c in gen.calls), str(gen.calls))
    check("C5 it generated for the 'self' audience",
          any(c[1].endswith("|self") for c in gen.calls), str(gen.calls))

    # Second turn: the LEAD format.
    gen2 = StubContentGenerator()
    await build_reply(company_id, BROKER_PHONE, "what about JVC", gen2)
    r3 = await build_reply(company_id, BROKER_PHONE, "LEAD", gen2)
    check("C6 LEAD generates for the forwardable audience",
          any(c[1].endswith("|lead") for c in gen2.calls), str(gen2.calls))
    check("C7 the forwardable reply still carries the caveat",
          formatter.MARKET_CAVEAT in r3)

    # Both in one message — no question needed.
    gen3 = StubContentGenerator()
    r4 = await build_reply(company_id, BROKER_PHONE, "Dubai Hills for the lead", gen3)
    check("C8 project + format in one message skips the question",
          "•" in r4 and gen3.calls, r4[:60])

    # State loss must degrade to a question, never to a wrong subject.
    state._reset_for_tests()
    r5 = await build_reply(company_id, BROKER_PHONE, "ME", StubContentGenerator())
    check("C9 answering ME with no pending question asks again rather than guessing",
          "lost track" in r5.lower())

    # Generation failure must not fabricate.
    class Dead:
        async def lead_intel(self, subject, audience): return None
        async def social_caption(self, kind): return None
    await build_reply(company_id, BROKER_PHONE, "tell me about Arjan", Dead())
    r6 = await build_reply(company_id, BROKER_PHONE, "ME", Dead())
    check("C10 a failed generation says so and invents nothing",
          "couldn't generate" in r6.lower() and "•" not in r6, r6[:80])

    r7 = await build_reply(company_id, BROKER_PHONE, "hi", StubContentGenerator())
    check("C11 an unreadable message asks for a project/area",
          "project" in r7.lower() or "area" in r7.lower())


# ── D. feature 2 ─────────────────────────────────────────────

async def run_daily_checks(company_id: int) -> None:
    print("\n== D. feature 2 — daily content nudge ==")
    rec = install_recorder()
    async with SessionLocal() as db:
        sent = await send_daily_nudge(db, company_id)
    check("D1 the nudge is sent to her number", sent == 1 and len(rec.sent) == 1, str(rec.sent[:1]))
    body = rec.sent[0][1] if rec.sent else ""
    check("D2 it offers both choices", "ARTICLE" in body and "FUN FACT" in body, body[:80])
    check("D3 the offer itself makes no market claim (so needs no caveat)",
          formatter.MARKET_CAVEAT not in body)

    gen = StubContentGenerator()
    r1 = await build_reply(company_id, BROKER_PHONE, "ARTICLE", gen)
    check("D4 ARTICLE returns a caption with the caveat",
          "•" in r1 and formatter.MARKET_CAVEAT in r1)
    check("D5 it is short enough to post", len(r1) < 700, f"len={len(r1)}")

    r2 = await build_reply(company_id, BROKER_PHONE, "FUN FACT", gen)
    check("D6 FUN FACT returns a caption with the caveat",
          "•" in r2 and formatter.MARKET_CAVEAT in r2)
    check("D7 the two kinds produce different copy", r1 != r2)

    # No state needed: a bare keyword works even after a restart.
    state._reset_for_tests()
    r3 = await build_reply(company_id, BROKER_PHONE, "article", StubContentGenerator())
    check("D8 ARTICLE still works with no pending state (restart-safe)",
          "•" in r3 and formatter.MARKET_CAVEAT in r3)


# ── G. polish: greetings + unrecognised subjects ─────────────

async def run_polish_checks(company_id: int) -> None:
    """Two rough edges found in live use with the real client.

    Bare greetings were read as project names, producing "Got it —
    *hello*. ME or LEAD?"; and an unrecognised name was accepted without
    question, so the bot would brief confidently on something that might not
    exist — which matters most under the forwardable format, where she could
    send it to a client before noticing.
    """
    print("\n== G. polish: greetings and unrecognised subjects ==")
    state._reset_for_tests()
    gen = StubContentGenerator()

    for greeting in ("hi", "hello", "Good morning", "hey", "thanks", "ok"):
        i = intents.parse(greeting)
        check(f"G1 {greeting!r} parses as a greeting, not a project",
              i.kind == "greeting", f"{i.kind}/{i.subject}")

    r = await build_reply(company_id, BROKER_PHONE, "hello", gen)
    check("G2 a greeting gets a natural reply, not 'Got it — *hello*'",
          "Got it" not in r and "ME or LEAD" not in r, r[:70])
    check("G3 the greeting reply explains what it can do (de-facto welcome)",
          "project" in r.lower() and "ARTICLE" in r)
    check("G4 no generation is triggered by small talk", not gen.calls, str(gen.calls))

    i = intents.parse("hi, what about JVC")
    check("G5 'hi, what about JVC' is still a briefing request",
          i.kind == "lead_intel" and i.area == "JVC", f"{i.kind}/{i.area}")

    check("G6 a known area is high confidence",
          intents.parse("Sobha Hartland").confidence == "high")
    check("G7 an unrecognised name is low confidence",
          intents.parse("Zzq Nonexistent Towers").confidence == "low")

    state._reset_for_tests()
    gen2 = StubContentGenerator()
    r = await build_reply(company_id, BROKER_PHONE, "Zzq Nonexistent Towers", gen2)
    check("G8 an unrecognised project asks for confirmation instead of briefing",
          "recognise" in r and "YES" in r, r[:80])
    check("G9 nothing is generated before she confirms", not gen2.calls, str(gen2.calls))

    r = await build_reply(company_id, BROKER_PHONE, "YES", gen2)
    check("G10 confirming proceeds to the format question with the ORIGINAL subject",
          "Zzq Nonexistent Towers" in r and "ME" in r and "LEAD" in r, r[:90])

    r = await build_reply(company_id, BROKER_PHONE, "ME", gen2)
    check("G11 and then briefs on it, caveat intact",
          "•" in r and formatter.MARKET_CAVEAT in r)

    state._reset_for_tests()
    gen3 = StubContentGenerator()
    r = await build_reply(company_id, BROKER_PHONE, "Sobha Hartland", gen3)
    check("G12 a KNOWN project still goes straight to the format question",
          "ME" in r and "LEAD" in r and "recognise" not in r, r[:70])

    state._reset_for_tests()
    r = await build_reply(company_id, BROKER_PHONE, "yes", StubContentGenerator())
    check("G13 a bare YES with no pending question asks again rather than guessing",
          "lost track" in r.lower(), r[:70])


# ── E. isolation ─────────────────────────────────────────────

async def run_isolation_checks(company_id: int) -> None:
    print("\n== E. isolation — stateless, and the generic pipeline is never reached ==")
    install_recorder()

    class SpySession:
        """Wraps a real session and records every add(), so a write that is
        staged and rolled back still fails this test — the same approach
        test_platform_refactor.py uses."""

        def __init__(self, inner):
            self._inner = inner
            self.added: list = []

        def add(self, obj, *a, **k):
            self.added.append(obj)
            return self._inner.add(obj, *a, **k)

        def __getattr__(self, item):
            return getattr(self._inner, item)

    from app.services.webhook_service import process_incoming_message

    forwarded = (
        f"Forwarded: {STRANGER_NAME} {STRANGER_PHONE} is asking about "
        "Sobha Hartland, 2BR, budget 2.4M"
    )
    async with SessionLocal() as inner:
        spy = SpySession(inner)
        await process_incoming_message(spy, BROKER_PHONE, forwarded)
        added_types = [type(o).__name__ for o in spy.added]

    check("E1 a forwarded lead message stages NO rows at all",
          spy.added == [], str(added_types))
    check("E2 specifically no MessageLog", "MessageLog" not in added_types, str(added_types))
    check("E3 specifically no Employee auto-registration",
          "Employee" not in added_types, str(added_types))

    async with SessionLocal() as db:
        logs = (await db.execute(select(MessageLog))).scalars().all()
        bodies = " ".join((getattr(l, "message", "") or "") for l in logs)
    check("E4 message_logs is empty after handling it", len(logs) == 0, f"{len(logs)} rows")
    check("E5 the stranger's name/number reached no table",
          STRANGER_NAME not in bodies and STRANGER_PHONE not in bodies)

    from app.verticals.registry import get_vertical
    v = get_vertical(BROKER_INTEL_VERTICAL)
    check("E6 registered persist_inbound=False", v is not None and v.persist_inbound is False)
    check("E7 registered with both an inbound handler and a daily hook",
          v.inbound is not None and v.daily is not None)


# ── F. other verticals unaffected ────────────────────────────

async def run_other_vertical_checks() -> None:
    print("\n== F. the other verticals are untouched ==")
    from app.verticals.registry import get_vertical

    lm = get_vertical("launch_matcher")
    check("F1 launch_matcher still registered, still persist_inbound=False",
          lm is not None and lm.persist_inbound is False and lm.inbound is not None)
    re_v = get_vertical("real_estate")
    check("F2 real_estate still registered with its daily hook",
          re_v is not None and re_v.daily is not None)
    check("F3 generic remains unregistered (fail-safe default)",
          get_vertical("generic") is None)
    check("F4 broker_intel did not displace anything",
          len({v.name for v in __import__(
              "app.verticals.registry", fromlist=["x"]).all_verticals()}) == 3)


async def main() -> None:
    print("=" * 68)
    print(f"  broker_intel verification  (DB: {TEST_DB_URL})")
    print("=" * 68)

    ctx = await setup_db()
    run_intent_checks()
    run_caveat_checks()
    await run_lead_intel_checks(ctx["company_id"])
    await run_daily_checks(ctx["company_id"])
    await run_polish_checks(ctx["company_id"])
    await run_isolation_checks(ctx["company_id"])
    await run_other_vertical_checks()

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
