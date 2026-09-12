"""Verification for the broker_intel vertical.

Runs the real FastAPI app's own inbound path against a throwaway database.
Same convention as the other suites here: a plain asyncio script, no pytest.
Set TEST_DATABASE_URL to run it against Postgres.

    python test_broker_intel.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_broker_intel.py

See also test_broker_intel_sourcing.py for the search/extraction/assembly
pipeline's own unit tests (the mixed-unit regression, scope isolation,
defensive JSON parsing) — this file covers the conversational flow and its
integration with the rest of the app.

Sections:
  A  intent parsing — how she names a project/area (design question 1)
  B  the two caveats — enforced over EVERY reply-producing entry point
  C  feature 1, lead intel, both formats, end to end (stub search+extraction)
  D  feature 2, the daily nudge and its reply
  E  isolation — nothing written, generic pipeline never reached (session spy)
  F  other verticals unaffected
  G  polish: greetings and unrecognised subjects
  H  real-usage regressions (from Manju's actual conversation)
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_broker_intel.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")
os.environ["DATABASE_URL"] = TEST_DB_URL

# This suite must be hermetic regardless of what real keys happen to sit in
# the local .env (they're there for live manual verification — see
# search.py / extraction.py docstrings). Any test that does NOT explicitly
# inject a stub search/extraction provider falls through to
# get_search_provider()/get_extraction_provider(), which read these two
# settings — so they're pinned to placeholder shapes here, the same way
# .env.example ships a placeholder OPENAI_API_KEY. Without this, Section E's
# isolation check would make a real, live Tavily/OpenAI call every run.
os.environ["TAVILY_API_KEY"] = "tvly-your-tavily-api-key-here"
os.environ["OPENAI_API_KEY"] = "sk-your-openai-api-key-here"

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
from app.services.broker_intel.extraction import Claim, StubExtractionProvider  # noqa: E402
from app.services.broker_intel.handler import (  # noqa: E402
    BROKER_INTEL_VERTICAL,
    build_reply,
    send_daily_nudge,
)
from app.services.broker_intel.search import SourceResult, StubSearchProvider  # noqa: E402
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


def src(domain: str, content: str = "search result text") -> SourceResult:
    return SourceResult(url=f"https://{domain}/x", domain=domain, title="x", content=content)


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


# ── B. the two caveats ────────────────────────────────────────

def run_caveat_checks() -> None:
    print("\n== B. the two caveats — enforced on every content-bearing reply ==")
    lines = ["Prices in the area have risen sharply.", "Yields look strong."]
    sourced_lines = ["Price/sqft: AED 1,500-1,650 [1][2]"]
    cited = [(1, src("bayut.com")), (2, src("propertyfinder.ae"))]

    contentful = {
        "render_lead_intel/self": formatter.render_lead_intel("X", sourced_lines, "self", cited),
        "render_lead_intel/lead": formatter.render_lead_intel("X", sourced_lines, "lead", cited),
        "render_comparison/self": formatter.render_comparison(["X", "Y"], sourced_lines, "self", cited),
    }
    ungrounded = {
        "render_social_caption/article": formatter.render_social_caption("article", lines),
        "render_social_caption/fun_fact": formatter.render_social_caption("fun_fact", lines),
    }

    for name, body in contentful.items():
        check(f"B1 {name} carries SOURCED_CAVEAT", formatter.SOURCED_CAVEAT in body, body[-90:])
        check(f"B1b {name} does NOT carry the old ungrounded MARKET_CAVEAT",
              formatter.MARKET_CAVEAT not in body, body[-90:])
        check(f"B1c {name} lists the sources actually cited",
              "bayut.com" in body and "propertyfinder.ae" in body, body)

    for name, body in ungrounded.items():
        check(f"B2 {name} carries MARKET_CAVEAT (ungrounded content stays labelled as such)",
              formatter.MARKET_CAVEAT in body, body[-80:])
        check(f"B2b {name} does NOT carry SOURCED_CAVEAT",
              formatter.SOURCED_CAVEAT not in body, body[-80:])

    check("B3 SOURCED_CAVEAT names DLD explicitly and does not call itself AI-generated",
          "DLD" in formatter.SOURCED_CAVEAT and "AI-generated" not in formatter.SOURCED_CAVEAT,
          formatter.SOURCED_CAVEAT)
    check("B4 MARKET_CAVEAT still names DLD and is explicitly AI-generated",
          "DLD" in formatter.MARKET_CAVEAT and "AI-generated" in formatter.MARKET_CAVEAT,
          formatter.MARKET_CAVEAT)

    # Structural: exactly two bullets-to-body paths, neither with an opt-out.
    import inspect
    src_text = inspect.getsource(formatter)
    check("B5 _bullets has exactly one definition",
          src_text.count("def _bullets(") == 1, str(src_text.count("def _bullets(")))

    # The invariant that matters is WHICH functions turn bullets into a
    # body, not how many times the helper is called inside them (the
    # grouped-sections layout added a second call site inside
    # _sourced_reply). Walk the AST and confirm the only callers are still
    # the two caveat-appending chokepoints.
    import ast
    tree = ast.parse(src_text)
    callers = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_bullets":
                callers.add(fn.name)
    check("B6 _bullets is called ONLY from the two caveat-appending "
          "chokepoints — a third caller would be a reply path that could "
          "skip the caveat",
          callers == {"_content_reply", "_sourced_reply"}, str(sorted(callers)))

    check("B7 _content_reply takes no flag that could disable MARKET_CAVEAT",
          "def _content_reply(header: str, lines: list[str]) -> str:" in src_text)

    # _sourced_reply may gain parameters (it took `sections` for the grouped
    # layout) but none of them may be able to turn the caveat off: assert
    # the caveat is appended unconditionally, outside any branch.
    sourced_fn = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "_sourced_reply")
    appends_caveat_at_top_level = any(
        isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
        and getattr(stmt.value.func, "attr", None) == "append"
        and any(getattr(a, "id", None) == "SOURCED_CAVEAT" for a in stmt.value.args)
        for stmt in sourced_fn.body
    )
    check("B8 _sourced_reply appends SOURCED_CAVEAT unconditionally at its "
          "top level — not inside an if, so no argument can skip it",
          appends_caveat_at_top_level)

    # The lead-ready format is forwarded verbatim, so it must not address her.
    lead_body = contentful["render_lead_intel/lead"]
    check("B9 lead-ready format carries no internal-note language",
          not any(w in lead_body.lower() for w in ("your briefing", "for you", "fyi", "note:")),
          lead_body[:80])

    # A failed generation must not be papered over with market-sounding filler.
    unavailable = formatter.render_unavailable()
    check("B10 the generation-failure reply makes no market claim",
          formatter.MARKET_CAVEAT not in unavailable
          and formatter.SOURCED_CAVEAT not in unavailable
          and "•" not in unavailable)

    thin = formatter.render_thin_sources("Ghost Towers")
    check("B11 the thin-sources reply also makes no market claim",
          formatter.MARKET_CAVEAT not in thin and formatter.SOURCED_CAVEAT not in thin
          and "•" not in thin, thin)


# ── C. feature 1 ─────────────────────────────────────────────

async def run_lead_intel_checks(company_id: int) -> None:
    print("\n== C. feature 1 — lead intel on demand (stub search + extraction) ==")
    state._reset_for_tests()

    sobha_search = StubSearchProvider({
        "Sobha Hartland": [src("bayut.com"), src("propertyfinder.ae")],
    })
    sobha_extractor = StubExtractionProvider(claims=[
        Claim("price_per_sqft", "Sobha Hartland", 1500, "", "", 1),
        Claim("price_per_sqft", "Sobha Hartland", 1700, "", "", 2),
        Claim("qualitative", "Sobha Hartland", None, "",
              "Waterfront community with strong tenant demand", 1),
    ])

    r1 = await build_reply(company_id, BROKER_PHONE, "tell me about Sobha Hartland")
    check("C1 first message asks which format, and searches nothing yet",
          "ME" in r1 and "LEAD" in r1 and not sobha_extractor.calls, r1[:60])

    r2 = await build_reply(company_id, BROKER_PHONE, "ME",
                            search=sobha_search, extractor=sobha_extractor)
    check("C2 answering ME returns the briefing", "•" in r2 and formatter.SOURCED_CAVEAT in r2)
    bullet_lines = [x for x in r2.splitlines() if x.startswith("•")]
    check("C3 the briefing is bulleted, not paragraphs, and each bullet stays scannable",
          r2.count("•") >= 2 and max(len(x) for x in bullet_lines) < 120,
          str(bullet_lines))
    check("C4 the subject survived the two-step exchange",
          any(c[0] == "Sobha Hartland" for c in sobha_extractor.calls), str(sobha_extractor.calls))
    check("C5 the ME reply uses the terse label style ('Price/sqft:'), not a sentence",
          "Price/sqft:" in r2, r2)

    # Second turn: the LEAD format, from scratch.
    state._reset_for_tests()
    lead_search = StubSearchProvider({"JVC": [src("bayut.com"), src("engelvoelkers.com")]})
    lead_extractor = StubExtractionProvider(claims=[
        Claim("price_per_sqft", "JVC", 1450, "", "", 1),
        Claim("price_per_sqft", "JVC", 1600, "", "", 2),
    ])
    await build_reply(company_id, BROKER_PHONE, "what about JVC",
                       search=lead_search, extractor=lead_extractor)
    r3 = await build_reply(company_id, BROKER_PHONE, "LEAD",
                            search=lead_search, extractor=lead_extractor)
    check("C6 the LEAD reply reads as a sentence naming the area, not the ME label style",
          "JVC" in r3 and "Price/sqft:" not in r3, r3[:100])
    check("C7 the forwardable reply still carries SOURCED_CAVEAT",
          formatter.SOURCED_CAVEAT in r3)

    # Both in one message — no question needed.
    state._reset_for_tests()
    dh_search = StubSearchProvider({"Dubai Hills": [src("bayut.com")]})
    dh_extractor = StubExtractionProvider(claims=[
        Claim("price_per_sqft", "Dubai Hills", 1800, "", "", 1),
    ])
    r4 = await build_reply(company_id, BROKER_PHONE, "Dubai Hills for the lead",
                            search=dh_search, extractor=dh_extractor)
    check("C8 project + format in one message skips the question",
          "•" in r4 and dh_search.calls == ["Dubai Hills"], r4[:60])

    # State loss must degrade to a question, never to a wrong subject.
    state._reset_for_tests()
    r5 = await build_reply(company_id, BROKER_PHONE, "ME")
    check("C9 answering ME with no pending question asks again rather than guessing",
          "lost track" in r5.lower())

    # Search found sources, but extraction hard-failed — must not fabricate.
    state._reset_for_tests()

    class DeadExtractor:
        async def extract_claims(self, subject, sources):
            return None

    dead_search = StubSearchProvider({"Arjan": [src("bayut.com")]})
    await build_reply(company_id, BROKER_PHONE, "tell me about Arjan",
                       search=dead_search, extractor=DeadExtractor())
    r6 = await build_reply(company_id, BROKER_PHONE, "ME",
                            search=dead_search, extractor=DeadExtractor())
    check("C10 a failed extraction says so and invents nothing",
          "couldn't generate" in r6.lower() and "•" not in r6, r6[:80])

    # Nothing usable found by search at all — the honest thin-sources reply.
    state._reset_for_tests()
    empty_search = StubSearchProvider({})
    await build_reply(company_id, BROKER_PHONE, "tell me about Zzq Ghost Towers",
                       search=empty_search, extractor=StubExtractionProvider(claims=[]))
    # "Zzq Ghost Towers" is a low-confidence subject, so this first asks to
    # confirm — mirrors G8-G11 below. Confirm, then check the thin reply.
    r6b = await build_reply(company_id, BROKER_PHONE, "yes",
                             search=empty_search, extractor=StubExtractionProvider(claims=[]))
    r6c = await build_reply(company_id, BROKER_PHONE, "ME",
                             search=empty_search, extractor=StubExtractionProvider(claims=[]))
    check("C10b nothing found by search -> honest thin reply, no fabrication",
          "couldn't find" in r6c.lower() and "•" not in r6c, r6c[:80])

    r7 = await build_reply(company_id, BROKER_PHONE, "hi")
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
          formatter.MARKET_CAVEAT not in body and formatter.SOURCED_CAVEAT not in body)

    gen = StubContentGenerator()
    r1 = await build_reply(company_id, BROKER_PHONE, "ARTICLE", gen)
    check("D4 ARTICLE returns a caption with MARKET_CAVEAT (still ungrounded content)",
          "•" in r1 and formatter.MARKET_CAVEAT in r1)
    check("D5 it is short enough to post", len(r1) < 700, f"len={len(r1)}")

    r2 = await build_reply(company_id, BROKER_PHONE, "FUN FACT", gen)
    check("D6 FUN FACT returns a caption with MARKET_CAVEAT",
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
    zzq_search = StubSearchProvider({"Zzq Nonexistent Towers": [src("bayut.com")]})
    zzq_extractor = StubExtractionProvider(claims=[
        Claim("qualitative", "Zzq Nonexistent Towers", None, "",
              "A newly listed development with limited public information", 1),
    ])
    r = await build_reply(company_id, BROKER_PHONE, "Zzq Nonexistent Towers",
                           search=zzq_search, extractor=zzq_extractor)
    check("G8 an unrecognised project asks for confirmation instead of briefing",
          "recognise" in r and "YES" in r, r[:80])
    check("G9 nothing is searched or extracted before she confirms",
          not zzq_search.calls and not zzq_extractor.calls,
          f"search={zzq_search.calls} extract={zzq_extractor.calls}")

    r = await build_reply(company_id, BROKER_PHONE, "YES",
                           search=zzq_search, extractor=zzq_extractor)
    check("G10 confirming proceeds to the format question with the ORIGINAL subject",
          "Zzq Nonexistent Towers" in r and "ME" in r and "LEAD" in r, r[:90])

    r = await build_reply(company_id, BROKER_PHONE, "ME",
                           search=zzq_search, extractor=zzq_extractor)
    check("G11 and then briefs on it, SOURCED_CAVEAT intact",
          "•" in r and formatter.SOURCED_CAVEAT in r, r)

    state._reset_for_tests()
    gen3 = StubContentGenerator()
    r = await build_reply(company_id, BROKER_PHONE, "Sobha Hartland", gen3)
    check("G12 a KNOWN project still goes straight to the format question",
          "ME" in r and "LEAD" in r and "recognise" not in r, r[:70])

    state._reset_for_tests()
    r = await build_reply(company_id, BROKER_PHONE, "yes")
    check("G13 a bare YES with no pending question asks again rather than guessing",
          "lost track" in r.lower(), r[:70])


# ── H. real-usage regressions (from Manju's actual conversation) ──

async def run_real_usage_checks(company_id: int) -> None:
    """Both cases come verbatim from her live conversation log — and the
    stub sources/claims below are deliberately shaped to reproduce the two
    concrete defects found while building the sourced-briefing pipeline:
    a total-price/price-per-sqft mixup for Arjan, and a Dubai-wide yield
    figure that must not attach itself to JVC.

    1. "Compare Arjan and JVC in terms of real estate rates and ROI" — the
       bot recognised Arjan, answered about it alone, and gave no sign it
       had dropped JVC or that a comparison was asked for.
    2. "I need data backed reply, with numbers" — an explicit request for
       real figures was parsed as a project name, so she was asked to
       confirm it was a real place.
    """
    print("\n== H. real-usage regressions (her actual messages) ==")
    state._reset_for_tests()

    HER_COMPARISON = "Compare Arjan and JVC in terms of real estate rates and ROI"
    HER_DATA_ASK = "I need data backed reply, with numbers"

    def h_claims(subject: str, sources) -> list[Claim]:
        if subject == "Arjan":
            return [
                # THE mixed-unit bug: a total price and a price-per-sqft
                # figure from the same source. Must render as two bullets.
                Claim("total_price", "Arjan", 1_000_000, "", "", 1),
                Claim("price_per_sqft", "Arjan", 1_564, "", "", 1),
                Claim("price_per_sqft", "Arjan", 1_450, "", "", 2),
                Claim("rental_yield_pct", "Arjan", 8.0, "", "", 1),
                Claim("qualitative", "Arjan", None, "",
                      "Popular with first-time investors for its affordability", 1),
            ]
        if subject == "JVC":
            return [
                Claim("price_per_sqft", "JVC", 1_469, "", "", 1),
                Claim("rental_yield_pct", "JVC", 7.5, "", "", 1),
                # THE citywide-leak bug: a Dubai-wide figure that must NOT
                # attach itself to JVC's briefing.
                Claim("rental_yield_pct", "citywide", 6.68, "", "", 2),
                Claim("qualitative", "JVC", None, "",
                      "Well-established with strong rental demand", 1),
            ]
        return []

    # ── 1. multi-area comparison ──
    i = intents.parse(HER_COMPARISON)
    check("H1 her comparison message parses as a comparison, not one area",
          i.kind == "comparison", f"{i.kind}/{i.subject}")
    check("H2 BOTH areas are captured — JVC is no longer dropped",
          i.subjects == ["Arjan", "JVC"], str(i.subjects))

    h_search = StubSearchProvider({
        "Arjan": [src("propertyfinder.ae"), src("bayut.com")],
        "JVC": [src("bayut.com"), src("engelvoelkers.com")],
    })
    h_extractor = StubExtractionProvider(claims=h_claims)
    r = await build_reply(company_id, BROKER_PHONE, HER_COMPARISON,
                           search=h_search, extractor=h_extractor)
    check("H3 the reply names both areas", "Arjan" in r and "JVC" in r, r[:80])
    check("H4 it actually searched BOTH areas, not a single-area briefing",
          h_search.calls == ["Arjan", "JVC"], str(h_search.calls))
    check("H5 the comparison still carries SOURCED_CAVEAT", formatter.SOURCED_CAVEAT in r)

    lines_in_r = r.splitlines()
    check("H5b Arjan's total price and price/sqft never share one bullet "
          "(the mixed-unit bug this pipeline replaced)",
          any("1,000,000" in ln for ln in lines_in_r)
          and any("/sqft" in ln for ln in lines_in_r)
          and not any("1,000,000" in ln and "/sqft" in ln for ln in lines_in_r),
          r)
    check("H5c the Dubai-wide yield figure (6.68) is dropped from JVC's briefing",
          "6.68" not in r, r)

    # ── 2. partial comparison: say so, don't answer half ──
    state._reset_for_tests()
    partial_search = StubSearchProvider({"Arjan": [src("bayut.com")], "Nakheel Heights": []})
    partial_extractor = StubExtractionProvider(claims=[])
    r = await build_reply(company_id, BROKER_PHONE,
                           "compare Arjan and Nakheel Heights",
                           search=partial_search, extractor=partial_extractor)
    check("H6 one area found where several were meant -> says which it got",
          "Arjan" in r and "only" in r.lower(), r[:90])
    check("H7 ...and searches/extracts nothing rather than answering half",
          not partial_search.calls and not partial_extractor.calls,
          f"search={partial_search.calls} extract={partial_extractor.calls}")

    # ── 3. explicit data request ──
    i = intents.parse(HER_DATA_ASK)
    check("H8 her data request parses as data_request, not a project name",
          i.kind == "data_request", f"{i.kind}/{i.subject!r}")

    state._reset_for_tests()
    data_search = StubSearchProvider({})
    data_extractor = StubExtractionProvider(claims=[])
    r = await build_reply(company_id, BROKER_PHONE, HER_DATA_ASK,
                           search=data_search, extractor=data_extractor)
    check("H9 it answers honestly: still no official DLD transaction data",
          "official dld transaction data" in r.lower(), r[:100])
    check("H10 it does NOT ask her to confirm it's a real place (the old bug)",
          "recognise" not in r and "YES" not in r, r[:80])
    check("H11 it searches/extracts nothing — no briefing dressed up as data",
          not data_search.calls and not data_extractor.calls)
    check("H12 it now invites her to name an area to get real search-backed "
          "figures, rather than flatly refusing",
          "arjan" in r.lower() and "jvc" in r.lower() and "search" in r.lower(), r)

    # ── 4. the fixes must not swallow ordinary messages ──
    state._reset_for_tests()
    check("H13 a plain single-area request is still a normal briefing",
          intents.parse("what about Arjan").kind == "lead_intel")
    check("H14 'and' in a sentence about ONE area is not a comparison",
          intents.parse("tell me about JVC and the market there").kind == "lead_intel",
          intents.parse("tell me about JVC and the market there").kind)
    check("H15 mentioning rates/ROI alongside real areas stays a comparison, "
          "not a data_request",
          intents.parse(HER_COMPARISON).kind == "comparison")
    check("H16 'give me actual numbers' is a data request, not a ME/LEAD choice",
          intents.parse("give me actual numbers").kind == "data_request",
          intents.parse("give me actual numbers").kind)


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
    # No search/extractor override here on purpose: this exercises the real
    # get_search_provider()/get_extraction_provider() fallback path, which
    # is why TAVILY_API_KEY/OPENAI_API_KEY are pinned to placeholders at the
    # top of this file — this call resolves to the stubs and returns no
    # sources, never a live network call.
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
    await run_real_usage_checks(ctx["company_id"])
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
