"""End-to-end verification for the Launch Matcher vertical.

Runs the real FastAPI app over ASGI against a throwaway database — real routes,
real auth, real JWTs, real parser and matcher. WhatsApp is exercised through
RecordingProvider, which satisfies the same WhatsAppProvider protocol as the
Meta implementation, so the full inbound-to-reply path runs with no credentials
and the exact reply body is asserted.

Same convention as the other test scripts here: a plain asyncio script, no
pytest, run directly. Set TEST_DATABASE_URL to run it against Postgres.

    python test_launch_matcher.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_launch_matcher.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_launch_matcher.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")

os.environ["DATABASE_URL"] = TEST_DB_URL

import httpx  # noqa: E402
from sqlalchemy import inspect as sa_inspect, select, text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.database import Base, get_db  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import app  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.investor_criteria import InvestorCriteria  # noqa: E402
from app.models.message_log import MessageLog  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import create_access_token  # noqa: E402
from app.services.launch_matcher.handler import (  # noqa: E402
    build_reply,
    handle_launch_message,
    try_handle_launch_matcher,
)
from app.services.launch_matcher.providers import (  # noqa: E402
    InboundMessage,
    RecordingProvider,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

# Every send in this suite goes to a recorder, never to Meta. try_handle_launch_matcher
# resolves its provider through get_provider(), which would otherwise make a live
# Meta API call — and with working credentials that would send a real WhatsApp
# message to the test phone number. Swapping the factory keeps the suite offline
# and doubles as proof the provider seam is genuinely swappable.
_default_provider = RecordingProvider()


def install_recording_provider() -> RecordingProvider:
    import app.services.launch_matcher.handler as handler_module
    import app.services.launch_matcher.providers as providers_module

    providers_module.get_provider = lambda: _default_provider
    handler_module.get_provider = lambda: _default_provider
    return _default_provider


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ─────────────────────────────────────────────────

ADVISOR_PHONE = "+971500000001"
LENIN_PHONE = "+919000000001"
BROKER_PHONE = "+971500000009"


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
        # The Dubai advisor — the launch-matcher client.
        advisor_co = Company(name="Dubai Advisory", vertical="launch_matcher")
        db.add(advisor_co)
        await db.flush()
        advisor = User(
            company_id=advisor_co.id, name="Advisor", email="advisor@example.com",
            role=UserRole.ceo, whatsapp_number=ADVISOR_PHONE,
        )
        db.add(advisor)

        # Lenin — generic vertical, must be entirely unaffected.
        lenin_co = Company(name="Lenin Logistics")
        db.add(lenin_co)
        await db.flush()
        lenin = User(
            company_id=lenin_co.id, name="Lenin", email="lenin@example.com",
            role=UserRole.ceo, whatsapp_number=LENIN_PHONE,
        )
        db.add(lenin)

        # A broker-CRM company — the other vertical, must also be walled off.
        broker_co = Company(name="Chennai Realty", vertical="real_estate")
        db.add(broker_co)
        await db.flush()
        broker = User(
            company_id=broker_co.id, name="Priya", email="priya@example.com",
            role=UserRole.ceo, whatsapp_number=BROKER_PHONE,
        )
        db.add(broker)
        await db.flush()

        ctx.update(
            advisor_company_id=advisor_co.id,
            lenin_company_id=lenin_co.id,
            broker_company_id=broker_co.id,
            advisor_token=create_access_token({
                "sub": advisor.email, "user_id": advisor.id,
                "company_id": advisor_co.id, "role": "ceo", "name": advisor.name}),
            lenin_token=create_access_token({
                "sub": lenin.email, "user_id": lenin.id,
                "company_id": lenin_co.id, "role": "ceo", "name": lenin.name}),
            broker_token=create_access_token({
                "sub": broker.email, "user_id": broker.id,
                "company_id": broker_co.id, "role": "ceo", "name": broker.name}),
        )
        await db.commit()
    return ctx


# The investor book used by the matching tests. Criteria only — every one of
# these is identified by a label the advisor made up.
INVESTORS = [
    # Dubai, mid budget, off-plan, no area preference.
    {"label": "Investor 4", "emirate": "Dubai", "budget_min": 1_200_000,
     "budget_max": 1_600_000, "off_plan_or_ready": "off_plan"},
    # Dubai, wants Hartland specifically.
    {"label": "Investor 11", "emirate": "Dubai", "areas": "Hartland, Meydan",
     "budget_min": 1_000_000, "budget_max": 2_000_000, "off_plan_or_ready": "both"},
    # Dubai, wants a 2BR.
    {"label": "Investor 19", "emirate": "Dubai", "budget_min": 1_000_000,
     "budget_max": 3_000_000, "property_type": "2BR", "off_plan_or_ready": "both"},
    # Dubai but only ready units — must never match a launch.
    {"label": "Investor 22", "emirate": "Dubai", "budget_min": 1_000_000,
     "budget_max": 5_000_000, "off_plan_or_ready": "ready"},
    # Dubai but wants Marina — used for the area-miss case.
    {"label": "Investor 30", "emirate": "Dubai", "areas": "Dubai Marina",
     "budget_min": 1_000_000, "budget_max": 5_000_000, "off_plan_or_ready": "both"},
    # Abu Dhabi — must never appear for a Dubai launch.
    {"label": "Investor 7", "emirate": "Abu Dhabi", "budget_min": 1_000_000,
     "budget_max": 9_000_000, "off_plan_or_ready": "both"},
    # Dubai, budget ceiling exactly at the launch entry price (edge case).
    {"label": "Investor 40", "emirate": "Dubai", "budget_min": 900_000,
     "budget_max": 1_400_000, "off_plan_or_ready": "both"},
    # Dubai, budget ceiling just below it (edge case, must NOT match).
    {"label": "Investor 41", "emirate": "Dubai", "budget_min": 900_000,
     "budget_max": 1_399_999, "off_plan_or_ready": "both"},
    # Needs instalments — matches a launch with terms, excluded from one without.
    {"label": "Investor 50", "emirate": "Dubai", "budget_min": 1_000_000,
     "budget_max": 2_000_000, "off_plan_or_ready": "both",
     "payment_preference": "payment_plan"},
    # Buys outright — never constrained by payment terms either way.
    {"label": "Investor 51", "emirate": "Dubai", "budget_min": 1_000_000,
     "budget_max": 2_000_000, "off_plan_or_ready": "both",
     "payment_preference": "cash"},
]

HARTLAND_LAUNCH = (
    "Sobha Hartland II - Dubai\n"
    "1BR from AED 1.4M | 60/40 payment plan | EOI Thursday"
)


async def seed_investors(client: httpx.AsyncClient, ctx: dict) -> None:
    h = auth(ctx["advisor_token"])
    for payload in INVESTORS:
        r = await client.post("/launch-matcher/investors", headers=h, json=payload)
        if r.status_code != 201:
            raise SystemExit(f"seed failed for {payload['label']}: "
                             f"{r.status_code} {r.text[:200]}")


# ── A. The hard rule: no PII can be persisted ────────────────

async def test_names_now_allowed(client: httpx.AsyncClient, ctx: dict) -> None:
    """Investor identity policy, post client-requested change.

    This used to be test_no_pii_guardrail: it asserted names/phones/emails
    were REJECTED on every one of these fields. That rejection has been
    deliberately removed (client request) — see app/models/investor_criteria.py
    for the policy and app/routes/launch_matcher.py for what enforced it
    before. These checks now assert the opposite on purpose: the new
    behaviour is intentional, not a regression to catch.
    """
    print("\n-- A. Investor names are now allowed (policy changed) --")
    h = auth(ctx["advisor_token"])

    # Structural: `name` is now a real, intentional column.
    columns = {c.name for c in InvestorCriteria.__table__.columns}
    check("A1. investor_criteria now HAS a name column (intentional)",
          "name" in columns, f"columns={columns}")
    # Still true, and not part of what changed: no phone/email column exists,
    # and none was asked for.
    still_absent = {"phone", "phone_number", "email", "mobile", "contact"}
    overlap = columns & still_absent
    check("A2. still no phone/email column (only a name was requested)",
          not overlap, f"found {overlap}")

    # A real name in the dedicated field is accepted and stored verbatim.
    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor N1", "name": "Ahmed Al Maktoum",
        "emirate": "Dubai", "budget_min": 1_000_000, "budget_max": 2_000_000})
    check("A3. a real name in the name field is accepted (201)",
          r.status_code == 201, f"got {r.status_code} {r.text[:160]}")
    name_investor_id = r.json()["id"] if r.status_code == 201 else None
    if r.status_code == 201:
        check("A3b. the stored name round-trips exactly",
              r.json().get("name") == "Ahmed Al Maktoum", str(r.json().get("name")))

    # A phone/email typed into label/areas/timeline is no longer rejected —
    # the regex guardrail that used to 422 these is gone.
    formerly_rejected = [
        ("email in label", {"label": "ahmed@example.com"}),
        ("phone in label", {"label": "Investor P1 +971 50 123 4567"}),
        ("phone in timeline", {"label": "Investor P2", "timeline": "call 0509876543"}),
        ("email in areas", {"label": "Investor P3", "areas": "ahmed@example.com"}),
    ]
    created_ids = [name_investor_id] if name_investor_id else []
    for case_name, extra in formerly_rejected:
        body = {"emirate": "Dubai", "budget_min": 1, "budget_max": 2}
        body.update(extra)
        r = await client.post("/launch-matcher/investors", headers=h, json=body)
        check(f"A4. {case_name} is NO LONGER rejected (201, not 422)",
              r.status_code == 201, f"got {r.status_code} {r.text[:120]}")
        if r.status_code == 201:
            created_ids.append(r.json()["id"])

    # extra="forbid" is unrelated to the PII policy and still applies: an
    # unsupported key is still a 422, exactly as for any other unknown field.
    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor X", "emirate": "Dubai", "budget_min": 1, "budget_max": 2,
        "phone": "+971501234567"})
    check("A5. an unsupported 'phone' key is still refused (extra=forbid, "
          "unrelated to the PII policy)", r.status_code == 422,
          f"got {r.status_code} {r.text[:120]}")

    # Update path: name can be set, changed, and cleared.
    if name_investor_id:
        r = await client.patch(f"/launch-matcher/investors/{name_investor_id}",
                               headers=h, json={"name": None})
        check("A6. name can be explicitly cleared via update",
              r.status_code == 200 and r.json().get("name") is None,
              f"{r.status_code} {r.json().get('name') if r.status_code == 200 else ''}")

    # Cleanup.
    for cid in created_ids:
        await client.delete(f"/launch-matcher/investors/{cid}", headers=h)

    # payment_preference is still a closed vocabulary — unaffected by any of
    # this, since it was never part of the free-text guardrail being removed.
    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor PP", "emirate": "Dubai", "budget_min": 1, "budget_max": 2,
        "payment_preference": "Ahmed Al Maktoum 0501234567"})
    stored = r.json().get("payment_preference") if r.status_code == 201 else None
    check("A7. payment_preference still falls back to a safe value "
          "(unrelated closed-vocabulary validation, not the guardrail removed)",
          r.status_code == 201 and stored == "either", f"{r.status_code} stored={stored}")
    if r.status_code == 201:
        await client.delete(f"/launch-matcher/investors/{r.json()['id']}", headers=h)

    # An ordinary label-only record still works exactly as before.
    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor 99", "emirate": "Dubai",
        "budget_min": 1_000_000, "budget_max": 2_000_000})
    check("A8. a label-only investor (no name given) still works",
          r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        check("A8b. name defaults to null when not supplied",
              r.json().get("name") is None, str(r.json().get("name")))
        await client.delete(f"/launch-matcher/investors/{r.json()['id']}", headers=h)


# ── B. Isolation ─────────────────────────────────────────────

async def test_isolation(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- B. Isolation from every other tenant --")
    paths = [("GET", "/launch-matcher/investors"), ("GET", "/launch-matcher/constants"),
             ("POST", "/launch-matcher/preview")]

    for who, token in (("generic (Lenin)", ctx["lenin_token"]),
                       ("real_estate broker", ctx["broker_token"])):
        blocked = []
        for method, path in paths:
            r = await client.request(method, path, headers=auth(token),
                                     json={"text": "x"})
            if r.status_code != 404:
                blocked.append(f"{path}->{r.status_code}")
        check(f"B1. {who} gets 404 on every launch-matcher route",
              not blocked, "; ".join(blocked))

    r = await client.post("/launch-matcher/investors", headers=auth(ctx["lenin_token"]),
                          json={"label": "Investor 1", "emirate": "Dubai"})
    check("B2. a generic company cannot create investor criteria",
          r.status_code == 404, f"got {r.status_code}")

    # The broker CRM stays invisible to the advisor — mutually exclusive verticals.
    r = await client.get("/real-estate/buyers", headers=auth(ctx["advisor_token"]))
    check("B3. the advisor gets 404 on the broker CRM (verticals are exclusive)",
          r.status_code == 404, f"got {r.status_code}")

    # Inbound routing: only the advisor's number reaches the launch matcher.
    async with SessionLocal() as db:
        for who, phone in (("Lenin", LENIN_PHONE), ("broker", BROKER_PHONE)):
            handled = await try_handle_launch_matcher(db, phone, HARTLAND_LAUNCH)
            check(f"B4. inbound from {who} is NOT handled by the launch matcher",
                  handled is None, f"got {handled}")


# ── C. Matching ──────────────────────────────────────────────

async def test_matching(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- C. Matching (emirate first, then everything else) --")
    company_id = ctx["advisor_company_id"]

    async with SessionLocal() as db:
        reply, outcome = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=HARTLAND_LAUNCH))

    labels = [m.label for m in outcome.matches]
    check("C1. the launch parsed to Dubai", outcome.launch.emirate == "Dubai",
          str(outcome.launch.emirate))
    check("C2. exact emirate+area match is included (Investor 11 wanted Hartland)",
          "Investor 11" in labels, str(labels))
    check("C3. emirate+budget match with no area preference is included (Investor 4)",
          "Investor 4" in labels, str(labels))
    check("C4. area miss excluded — Investor 30 wanted Marina, launch is Hartland",
          "Investor 30" not in labels, str(labels))
    check("C5. off-plan vs ready mismatch excluded — Investor 22 wants ready only",
          "Investor 22" not in labels, str(labels))
    check("C6. other emirate excluded — Investor 7 is Abu Dhabi",
          "Investor 7" not in labels, str(labels))
    check("C7. unit-type mismatch excluded — Investor 19 wants 2BR, launch is 1BR",
          "Investor 19" not in labels, str(labels))

    # Budget edges: the launch is "from 1.4M".
    check("C8. budget ceiling exactly at the entry price matches (1.4M vs 1.4M)",
          "Investor 40" in labels, str(labels))
    check("C9. budget ceiling one dirham below does not match (1,399,999)",
          "Investor 41" not in labels, str(labels))

    # Reasons must be real, not decorative.
    inv11 = next((m for m in outcome.matches if m.label == "Investor 11"), None)
    check("C10. the area match explains itself ('wanted Hartland')",
          bool(inv11) and any("Hartland" in r for r in inv11.reasons),
          str(inv11.reasons if inv11 else None))
    inv4 = next((m for m in outcome.matches if m.label == "Investor 4"), None)
    check("C11. reasons name the emirate and the budget band",
          bool(inv4) and "Dubai" in inv4.reasons
          and any("1.2M" in r for r in inv4.reasons),
          str(inv4.reasons if inv4 else None))

    print("\n     Reply preview:")
    for line in reply.split("\n"):
        print(f"       {line}")


async def test_name_used_in_reply(client: httpx.AsyncClient, ctx: dict) -> None:
    """Requirement: the WhatsApp reply uses the investor's name when set.

    Exercised end-to-end through the real API and the real preview endpoint
    (which runs the same build_reply() the live WhatsApp path uses) rather
    than by importing matcher internals — this is what actually ships.
    """
    print("\n-- C2. WhatsApp reply prefers name over label when set --")
    h = auth(ctx["advisor_token"])

    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor NR1", "name": "Fatima Al Zaabi",
        "emirate": "Dubai", "budget_min": 1_000_000, "budget_max": 2_000_000})
    check("C2.1 named investor created", r.status_code == 201, f"{r.status_code}")
    named_id = r.json()["id"] if r.status_code == 201 else None

    r = await client.post("/launch-matcher/preview", headers=h,
                          json={"text": HARTLAND_LAUNCH})
    check("C2.2 preview call succeeds", r.status_code == 200, f"{r.status_code}")
    reply = r.json().get("reply", "") if r.status_code == 200 else ""

    check("C2.3 the reply shows the real name",
          "Fatima Al Zaabi" in reply, reply)
    check("C2.4 the reply does NOT show that investor's internal label",
          "Investor NR1" not in reply, reply)
    # And the fallback path is unaffected: investors with no name stored still
    # show their label, exactly as before this change.
    check("C2.5 label-only investors still show their label (fallback intact)",
          "Investor 4" in reply, reply)

    if named_id:
        await client.delete(f"/launch-matcher/investors/{named_id}", headers=h)


async def test_no_match_is_honest(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- D. No matches replies honestly --")
    company_id = ctx["advisor_company_id"]

    # A Dubai launch far above everyone's budget.
    expensive = ("Omniyat | Palm Jumeirah - Dubai\n"
                 "4BR penthouses from AED 85,000,000\n60/40 | EOI Monday")
    async with SessionLocal() as db:
        reply, outcome = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=expensive))

    check("D1. nothing matched", not outcome.matched, str([m.label for m in outcome.matches]))
    check("D2. it says so plainly", "No matches" in reply, reply[:160])
    check("D3. it reports how many were actually checked",
          "Checked" in reply and str(outcome.considered) in reply, reply[:160])
    check("D4. no investor label is offered as a near-miss",
          not any(f"Investor {n}" in reply for n in (4, 7, 11, 19, 22, 30, 40, 41)),
          reply[:200])

    # An emirate with no investors on file at all.
    sharjah = "Arada | Aljada - Sharjah\n1BR from AED 700K\nEOI Friday"
    async with SessionLocal() as db:
        reply2, outcome2 = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=sharjah))
    check("D5. an emirate with no investors says exactly that",
          not outcome2.matched and "No investors on file" in reply2, reply2[:160])

    # Emirate unreadable — refuse rather than guess the top-level filter.
    vague = "New launch!! Great payment plan, EOI soon. DM for details"
    async with SessionLocal() as db:
        reply3, outcome3 = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=vague))
    check("D6. an unreadable emirate asks instead of guessing",
          outcome3.blocked_reason == "emirate" and "emirate" in reply3.lower(),
          reply3[:160])
    check("D7. and offers no matches while blocked", not outcome3.matched, reply3[:120])

    print("\n     No-match reply preview:")
    for line in reply.split("\n"):
        print(f"       {line}")


# ── C2. Payment preference ───────────────────────────────────

async def test_payment_preference(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- C2. payment_preference (structured field, not notes) --")
    company_id = ctx["advisor_company_id"]

    # HARTLAND_LAUNCH states "60/40", so it has payment plan terms.
    async with SessionLocal() as db:
        reply, outcome = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=HARTLAND_LAUNCH))
    by_label = {m.label: m for m in outcome.matches}

    check("C2.1. a payment-plan buyer matches a launch with stated terms",
          "Investor 50" in by_label, str(list(by_label)))
    check("C2.2. and is surfaced as 'payment plan buyer'",
          "Investor 50" in by_label
          and "payment plan buyer" in by_label["Investor 50"].reasons,
          str(by_label.get("Investor 50").reasons if "Investor 50" in by_label else None))
    check("C2.3. a cash buyer also matches (payment terms don't constrain them)",
          "Investor 51" in by_label, str(list(by_label)))
    check("C2.4. and is surfaced as 'cash buyer'",
          "Investor 51" in by_label
          and "cash buyer" in by_label["Investor 51"].reasons,
          str(by_label.get("Investor 51").reasons if "Investor 51" in by_label else None))
    check("C2.5. an 'either' investor gets no payment reason (nothing was tested)",
          "Investor 4" in by_label
          and not any("buyer" in r for r in by_label["Investor 4"].reasons),
          str(by_label.get("Investor 4").reasons if "Investor 4" in by_label else None))

    # A launch with no stated payment terms: the plan buyer must drop out.
    no_terms = "Emaar | Dubai Hills - Dubai\n1BR from AED 1.5M\nEOI Friday"
    async with SessionLocal() as db:
        reply2, outcome2 = await build_reply(
            db, company_id, InboundMessage(sender=ADVISOR_PHONE, text=no_terms))
    labels2 = [m.label for m in outcome2.matches]
    check("C2.6. launch parsed with no payment plan",
          outcome2.launch.payment_plan is None, str(outcome2.launch.payment_plan))
    check("C2.7. payment-plan buyer excluded when terms are not stated",
          "Investor 50" not in labels2, str(labels2))
    check("C2.8. cash buyer still matches a launch with no stated terms",
          "Investor 51" in labels2, str(labels2))

    # The field must round-trip through the API.
    h = auth(ctx["advisor_token"])
    r = await client.get("/launch-matcher/investors", headers=h)
    rows = {row["label"]: row for row in r.json()}
    check("C2.9. payment_preference round-trips through the API",
          rows.get("Investor 50", {}).get("payment_preference") == "payment_plan",
          str(rows.get("Investor 50", {}).get("payment_preference")))
    check("C2.10. it defaults to 'either' when unspecified",
          rows.get("Investor 4", {}).get("payment_preference") == "either",
          str(rows.get("Investor 4", {}).get("payment_preference")))

    r = await client.get("/launch-matcher/constants", headers=h)
    check("C2.11. constants expose the choices for the setup screen",
          r.status_code == 200
          and r.json().get("payment_preference") == ["cash", "payment_plan", "either"],
          str(r.json() if r.status_code == 200 else r.status_code))

    print("\n     Reply with payment reasons:")
    for line in reply.split("\n"):
        print(f"       {line}")


# ── E. The WhatsApp round trip ───────────────────────────────

async def test_whatsapp_flow(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- E. Inbound to reply, through the provider interface --")
    provider = RecordingProvider()

    async with SessionLocal() as db:
        result = await handle_launch_message(
            db, ctx["advisor_company_id"],
            InboundMessage(sender=ADVISOR_PHONE, text=HARTLAND_LAUNCH),
            provider=provider,
        )

    check("E1. exactly one message was sent", len(provider.sent) == 1,
          f"{len(provider.sent)} sent")
    if provider.sent:
        to, body = provider.sent[0]
        check("E2. it went back to the advisor, nobody else", to == ADVISOR_PHONE, to)
        check("E3. the reply leads with the project and emirate",
              body.startswith("Sobha Hartland II"), body.split("\n")[0])
        check("E4. it states the match count", "Matches" in body,
              body[:160])
    check("E5. the handler reports a match", result["matched"], str(result))
    check("E6. delivery was reported ok", result["delivered"], str(result))

    # Nothing is ever sent to an investor: one recipient, the sender.
    recipients = {to for to, _ in provider.sent}
    check("E7. no message was sent to anyone but the sender",
          recipients == {ADVISOR_PHONE}, str(recipients))


async def test_no_pii_written_by_inbound(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- F. The inbound path writes no PII anywhere --")

    # A forwarded broadcast carrying an agent's details in the footer — exactly
    # what real forwards look like.
    forwarded = (
        "Sobha Hartland II - Dubai\n"
        "1BR from AED 1.4M | 60/40 | EOI Thursday\n"
        "For details contact Rashid Al Nuaimi +971 55 123 4567\n"
        "rashid@luxuryhomes.ae"
    )

    async with SessionLocal() as db:
        before = len((await db.execute(select(MessageLog))).scalars().all())

    provider = RecordingProvider()
    async with SessionLocal() as db:
        await handle_launch_message(
            db, ctx["advisor_company_id"],
            InboundMessage(sender=ADVISOR_PHONE, text=forwarded), provider=provider)

    async with SessionLocal() as db:
        logs = (await db.execute(select(MessageLog))).scalars().all()
    check("F1. no message_logs row was written (no sender, no raw text stored)",
          len(logs) == before, f"{before} -> {len(logs)}")

    # And the footer's details are nowhere in investor_criteria either.
    async with SessionLocal() as db:
        rows = (await db.execute(select(InvestorCriteria))).scalars().all()
    blob = " ".join(
        f"{r.label} {r.areas} {r.property_type} {r.timeline} {r.notes or ''}"
        for r in rows
    )
    for needle in ("Rashid", "971 55 123", "rashid@", "luxuryhomes"):
        check(f"F2.{needle} — forwarded footer detail {needle!r} not persisted",
              needle.lower() not in blob.lower(), "found in investor_criteria")

    # The full inbound dispatch (the real entry point) also logs nothing.
    async with SessionLocal() as db:
        before2 = len((await db.execute(select(MessageLog))).scalars().all())
    sends_before = len(_default_provider.sent)
    async with SessionLocal() as db:
        handled = await try_handle_launch_matcher(db, ADVISOR_PHONE, forwarded)
    async with SessionLocal() as db:
        after2 = len((await db.execute(select(MessageLog))).scalars().all())
    check("F3. the real inbound dispatcher handled it", handled is not None, str(handled))
    check("F3b. it routed through the injected provider, not a live Meta call",
          len(_default_provider.sent) == sends_before + 1,
          f"{sends_before} -> {len(_default_provider.sent)}")
    check("F4. and still wrote no message_logs row", after2 == before2,
          f"{before2} -> {after2}")


# ── G. Parser ────────────────────────────────────────────────

async def test_parser(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- G. Parser --")
    from app.services.launch_matcher.parser import parse_launch

    p = parse_launch(HARTLAND_LAUNCH)
    check("G1. developer", p.developer == "Sobha", str(p.developer))
    check("G2. project", p.project == "Sobha Hartland II", str(p.project))
    check("G3. emirate", p.emirate == "Dubai", str(p.emirate))
    check("G4. area", p.area == "Sobha Hartland", str(p.area))
    check("G5. unit types", p.unit_types == ["1BR"], str(p.unit_types))
    check("G6. price", p.price_min == 1_400_000, str(p.price_min))
    check("G7. payment plan", p.payment_plan == "60/40", str(p.payment_plan))
    check("G8. EOI date", p.launch_date == "Thursday", str(p.launch_date))
    check("G9. off-plan by default for a launch", p.completion_status == "off_plan",
          p.completion_status)

    # Emirate inferred from a known area when the message never says it.
    p2 = parse_launch("Danube Oasis - JVC\n1 & 2 bedroom\nfrom 850K\nEOI Monday")
    check("G10. emirate inferred from the area alone", p2.emirate == "Dubai", str(p2.emirate))
    check("G11. enumerated unit mix expands ('1 & 2 bedroom')",
          p2.unit_types == ["1BR", "2BR"], str(p2.unit_types))

    # Explicit price range.
    p3 = parse_launch("Aldar | Yas Island\n2BR townhouses\nAED 1.9M - 3.4M\n60/40")
    check("G12. price range", (p3.price_min, p3.price_max) == (1_900_000, 3_400_000),
          f"{p3.price_min}..{p3.price_max}")
    check("G13. Abu Dhabi area maps to its emirate", p3.emirate == "Abu Dhabi", str(p3.emirate))

    # 'ready' overrides the off-plan default.
    p4 = parse_launch("Ready to move units, Al Marjan Island RAK, studio from AED 750,000")
    check("G14. 'ready to move' is detected", p4.completion_status == "ready",
          p4.completion_status)
    check("G15. RAK area maps to its emirate", p4.emirate == "RAK", str(p4.emirate))

    # A payment-plan ratio must never be read as a price.
    p5 = parse_launch("Emaar Downtown Dubai\n2BR\n60/40 payment plan")
    check("G16. '60/40' is a payment plan, not a price",
          p5.payment_plan == "60/40" and p5.price_min is None,
          f"plan={p5.payment_plan} price={p5.price_min}")

    # The parser must not surface contact details it happens to see.
    p6 = parse_launch("Sobha Hartland II Dubai 1BR 1.4M\nAgent: Sara +971501112222")
    blob = f"{p6.developer} {p6.project} {p6.area} {p6.payment_plan} {p6.launch_date}"
    check("G17. an agent's name/number in the footer is not extracted into fields",
          "Sara" not in blob and "971501112222" not in blob, blob)


# ── H. Setup API ─────────────────────────────────────────────

async def test_setup_api(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- H. Setup API --")
    h = auth(ctx["advisor_token"])

    r = await client.get("/launch-matcher/investors", headers=h)
    check("H1. the advisor can list their investors",
          r.status_code == 200 and len(r.json()) == len(INVESTORS),
          f"{r.status_code} n={len(r.json()) if r.status_code == 200 else '?'}")

    r = await client.post("/launch-matcher/preview", headers=h,
                          json={"text": HARTLAND_LAUNCH})
    check("H2. preview parses and matches without sending",
          r.status_code == 200 and r.json()["matched"], r.text[:160])
    if r.status_code == 200:
        check("H3. preview echoes what it understood",
              r.json()["parsed"]["emirate"] == "Dubai", str(r.json().get("parsed")))

    r = await client.post("/launch-matcher/investors", headers=h, json={
        "label": "Investor 50", "emirate": "Dubai",
        "budget_min": 5_000_000, "budget_max": 1_000_000})
    check("H4. an inverted budget range is rejected", r.status_code == 400,
          f"{r.status_code} {r.text[:120]}")

    # Tenant scoping on update/delete.
    r = await client.get("/launch-matcher/investors", headers=h)
    some_id = r.json()[0]["id"]
    r = await client.patch(f"/launch-matcher/investors/{some_id}",
                           headers=auth(ctx["broker_token"]), json={"label": "Hacked"})
    check("H5. another tenant cannot touch these records", r.status_code == 404,
          f"got {r.status_code}")


# ── Runner ───────────────────────────────────────────────────

async def main() -> None:
    print("=" * 64)
    print("  Launch Matcher — end-to-end verification")
    print(f"  backend: {'SQLite' if IS_SQLITE else 'PostgreSQL'}")
    print("=" * 64)

    install_recording_provider()
    ctx = await setup_db()
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await test_names_now_allowed(client, ctx)
        await seed_investors(client, ctx)
        await test_isolation(client, ctx)
        await test_matching(client, ctx)
        await test_name_used_in_reply(client, ctx)
        await test_payment_preference(client, ctx)
        await test_no_match_is_honest(client, ctx)
        await test_whatsapp_flow(client, ctx)
        await test_no_pii_written_by_inbound(client, ctx)
        await test_parser(client, ctx)
        await test_setup_api(client, ctx)

    await engine.dispose()
    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print("\n" + "=" * 64)
    print(f"  Results: {passed}/{len(results)} passed  |  {failed} failed")
    print("=" * 64)
    if failed:
        print("\nFailed:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"  [XX] {name}" + (f"\n       {detail}" if detail else ""))
        sys.exit(1)
    print("\nAll launch matcher tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
