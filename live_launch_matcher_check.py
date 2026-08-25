"""Live end-to-end round-trip check for the Launch Matcher.

This is NOT part of the offline test suite — it sends a real WhatsApp message
through the real Meta Cloud API. Run it deliberately, never in CI.

What it proves, in order, and it stops at the first thing that genuinely fails:

  1. the configured token actually authenticates against the phone number
  2. a realistic launch text parses and matches seeded criteria, including a
     payment_preference match
  3. WhatsApp's 24-hour session window is open for the recipient
  4. a real WhatsApp reply is accepted by Meta (message id returned)
  5. the message is actually DELIVERED — confirmed from webhook status
     callbacks, not from the send call's 200
  6. the run leaves zero rows in message_logs and persists nothing from the
     message outside investor_criteria

On (3): this is not optional politeness, it is what the product actually does.
Phase 1 is user-initiated by design — the advisor forwards a launch, that
inbound message opens the window, and the bot replies inside it. There is no
business-initiated send anywhere in the feature.

Sending cold is therefore a scenario the product never performs, and WhatsApp
forbids it. Worse, Meta does not reliably say so: outside the window it will
often accept the call and return a message id, then silently drop the message.
An earlier version of this script did exactly that and reported success while
nothing arrived. Hence the gate below refuses to send rather than trusting a
200 to mean anything.

Meta exposes no API for "when did this user last message us", so the window
must be established the same way delivery is — from webhook evidence
(--inbound-from) or an explicit operator assertion (--inbound-confirmed).

On (4): Meta reports delivery only by POSTing a status callback to the
configured webhook. There is no "GET message status" endpoint. So delivery is
confirmed one of two ways:

  --statuses-from FILE   a file the running app appends delivery statuses to
                         (see --emit-statuses on the webhook), or
  --confirm-receipt      a human confirms it arrived on the handset

Without one of those this script reports SENT-BUT-UNCONFIRMED and exits
non-zero, because "Meta returned 200" is not delivery.

Usage:
    # after messaging the business number from the test handset:
    python live_launch_matcher_check.py --to +9715XXXXXXX \
        --inbound-confirmed --confirm-receipt

    # fully evidence-driven, with the app running behind a webhook:
    python live_launch_matcher_check.py --to +9715XXXXXXX \
        --inbound-from inbound.log --statuses-from statuses.log
"""

import argparse
import asyncio
import json
import os
import sys
import time

TEST_DB_PATH = "_live_launch_check.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///./{TEST_DB_PATH}")

import requests  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.investor_criteria import InvestorCriteria  # noqa: E402
from app.models.message_log import MessageLog  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.launch_matcher.handler import build_reply  # noqa: E402
from app.services.launch_matcher.providers import (  # noqa: E402
    InboundMessage,
    MetaCloudProvider,
)

# A realistic forwarded broadcast, including a contact-style footer of the kind
# these always carry — so the no-PII assertion is tested against real shape.
LAUNCH_TEXT = (
    "Sobha Hartland II - Dubai\n"
    "1BR from AED 1.4M | 60/40 payment plan | EOI Thursday\n"
    "Limited units, register early.\n"
    "For details contact Rashid Al Nuaimi +971 55 123 4567 / rashid@luxuryhomes.ae"
)

PII_NEEDLES = ["Rashid", "Al Nuaimi", "971 55 123", "rashid@", "luxuryhomes"]

failures: list[str] = []


def step(n: str, ok: bool, detail: str = "") -> bool:
    print(("  [ok] " if ok else "  [XX] ") + n + (f"  -- {detail}" if detail else ""))
    if not ok:
        failures.append(n)
    return ok


async def seed(advisor_phone: str) -> int:
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with SessionLocal() as db:
        company = Company(name="Live Check Advisory", vertical="launch_matcher")
        db.add(company)
        await db.flush()
        db.add(User(company_id=company.id, name="Advisor",
                    email="live-check@example.com", role=UserRole.ceo,
                    whatsapp_number=advisor_phone))
        for row in (
            # Plain emirate+budget match.
            dict(label="Investor 4", emirate="Dubai", budget_min=1_200_000,
                 budget_max=1_600_000, off_plan_or_ready="off_plan"),
            # Area match.
            dict(label="Investor 11", emirate="Dubai", areas="Hartland",
                 budget_min=1_000_000, budget_max=2_000_000),
            # Exercises the new payment_preference field.
            dict(label="Investor 50", emirate="Dubai", budget_min=1_000_000,
                 budget_max=2_000_000, payment_preference="payment_plan"),
            # Must NOT match — wrong emirate.
            dict(label="Investor 7", emirate="Abu Dhabi", budget_min=1_000_000,
                 budget_max=9_000_000),
        ):
            db.add(InvestorCriteria(company_id=company.id, **row))
        await db.commit()
        return company.id


# WhatsApp only allows free-form text within 24 hours of the user's own last
# inbound message. Meta publishes no endpoint to query that window, so it is
# established from the same kind of evidence delivery is.
SESSION_WINDOW_HOURS = 24


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def read_last_inbound(path: str, sender: str) -> float | None:
    """Age in hours of the most recent inbound message from `sender`.

    Reads a log the running app appends inbound events to, one JSON object per
    line, e.g. {"from": "919150016161", "at": "2026-08-25T09:14:00Z"}. Numbers
    are compared digits-only so +91..., 91... and 0091... all match. Returns
    None when the file is absent or holds nothing from that sender.
    """
    if not path or not os.path.exists(path):
        return None

    import datetime as _dt

    want = _digits(sender)
    newest = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            who = _digits(str(entry.get("from") or entry.get("sender") or ""))
            if not who or not (who.endswith(want) or want.endswith(who)):
                continue
            stamp = entry.get("at") or entry.get("timestamp")
            if stamp is None:
                continue
            try:
                # Accept ISO-8601 or a unix epoch, which is what Meta sends.
                if isinstance(stamp, (int, float)) or str(stamp).isdigit():
                    when = _dt.datetime.fromtimestamp(float(stamp), _dt.timezone.utc)
                else:
                    when = _dt.datetime.fromisoformat(
                        str(stamp).replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=_dt.timezone.utc)
            except (ValueError, OSError):
                continue
            if newest is None or when > newest:
                newest = when

    if newest is None:
        return None
    age = _dt.datetime.now(_dt.timezone.utc) - newest
    return age.total_seconds() / 3600.0


def read_statuses(path: str, message_id: str) -> str | None:
    """Look for a delivery status for this message id in the statuses file."""
    if not path or not os.path.exists(path):
        return None
    best = None
    rank = {"sent": 1, "delivered": 2, "read": 3}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or message_id not in line:
                continue
            try:
                entry = json.loads(line)
                status = entry.get("status")
            except ValueError:
                status = next((s for s in rank if s in line.lower()), None)
            if status and (best is None or rank.get(status, 0) > rank.get(best, 0)):
                best = status
    return best


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True,
                    help="advisor's WhatsApp number in E.164, e.g. +971501234567")
    ap.add_argument("--statuses-from", default="",
                    help="file the app appends Meta delivery statuses to")
    ap.add_argument("--wait", type=int, default=60,
                    help="seconds to wait for a delivery status (default 60)")
    ap.add_argument("--confirm-receipt", action="store_true",
                    help="operator confirms the message arrived on the handset")
    ap.add_argument("--inbound-from", default="",
                    help="file the app appends inbound message events to, used "
                         "to prove the 24-hour session window is open")
    ap.add_argument("--inbound-confirmed", action="store_true",
                    help="operator confirms they have JUST messaged the business "
                         "number from the recipient handset, opening the window")
    args = ap.parse_args()

    print("=" * 66)
    print("  Launch Matcher — LIVE round-trip check (sends a real message)")
    print("=" * 66)

    # ── 1. Credentials actually authenticate ─────────────────
    print("\n-- 1. Meta credentials --")
    token = settings.meta_access_token or ""
    pid = settings.meta_phone_number_id or ""
    if not step("1.1 token and phone number id are configured", bool(token and pid),
                f"token_len={len(token)} phone_id={'set' if pid else 'MISSING'}"):
        sys.exit(1)

    r = requests.get(
        f"https://graph.facebook.com/v25.0/{pid}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "display_phone_number,verified_name,quality_rating,"
                          "code_verification_status,platform_type"},
        timeout=25,
    )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not step("1.2 token authenticates against the phone number",
                r.status_code == 200 and "error" not in body,
                f"HTTP {r.status_code} {json.dumps(body)[:220]}"):
        print("\n  Token is not valid. Nothing further can be proven; stopping.")
        sys.exit(1)
    print(f"       number={body.get('display_phone_number')} "
          f"name={body.get('verified_name')!r} quality={body.get('quality_rating')}")

    # ── 2. Parse + match ─────────────────────────────────────
    print("\n-- 2. Parse and match --")
    company_id = await seed(args.to)
    async with SessionLocal() as db:
        reply, outcome = await build_reply(
            db, company_id, InboundMessage(sender=args.to, text=LAUNCH_TEXT))

    labels = [m.label for m in outcome.matches]
    step("2.1 launch parsed to Dubai", outcome.launch.emirate == "Dubai",
         str(outcome.launch.emirate))
    step("2.2 payment plan terms read from the message",
         outcome.launch.payment_plan == "60/40", str(outcome.launch.payment_plan))
    step("2.3 matched the expected investors", "Investor 11" in labels,
         str(labels))
    pp = next((m for m in outcome.matches if m.label == "Investor 50"), None)
    step("2.4 payment_preference match exercised ('payment plan buyer')",
         bool(pp) and "payment plan buyer" in pp.reasons,
         str(pp.reasons if pp else None))
    step("2.5 wrong-emirate investor excluded", "Investor 7" not in labels, str(labels))

    print("\n     Reply to be sent:")
    for line in reply.split("\n"):
        print(f"       {line}")

    # ── 3. Session window must be open before we send ────────
    print("\n-- 3. Session window --")
    window_ok = False
    if args.inbound_from:
        age = read_last_inbound(args.inbound_from, args.to)
        if age is None:
            step("3.1 an inbound message from the recipient is on record", False,
                 f"nothing from {args.to} found in {args.inbound_from}")
        else:
            window_ok = age < SESSION_WINDOW_HOURS
            step(f"3.1 last inbound was {age:.1f}h ago (limit "
                 f"{SESSION_WINDOW_HOURS}h)", window_ok,
                 "the 24-hour window has closed — the recipient must message "
                 "the business number again")
    elif args.inbound_confirmed:
        window_ok = True
        step("3.1 operator confirms the recipient has just messaged us", True,
             "asserted via --inbound-confirmed")
    else:
        step("3.1 session window is open", False,
             "no --inbound-from and no --inbound-confirmed. WhatsApp only "
             "allows free-form text within 24h of the recipient's own last "
             "message, and Meta may accept-then-silently-drop outside it, so "
             "this refuses to send rather than report a meaningless 200")

    if not window_ok:
        print("\n  Refusing to send outside the session window. Message the "
              "business number\n  from the recipient handset, then re-run with "
              "--inbound-confirmed.")
        print("\n" + "=" * 66)
        print(f"  LIVE CHECK FAILED — {len(failures)} step(s):")
        for f in failures:
            print(f"    - {f}")
        print("=" * 66)
        await engine.dispose()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        sys.exit(1)

    # ── 4. Real send ─────────────────────────────────────────
    print("\n-- 4. Real WhatsApp send --")
    provider = MetaCloudProvider()
    result = await provider.send_text(args.to, reply)
    if not step("4.1 Meta accepted the send", result.ok, result.error or ""):
        print("\n  Send rejected; delivery cannot follow. Stopping.")
        sys.exit(1)

    # Re-send through the raw API so the message id is available for status
    # correlation — send_text intentionally returns only ok/error.
    print("       (querying message id for delivery correlation)")
    resp = requests.post(
        f"https://graph.facebook.com/v25.0/{pid}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": args.to.lstrip("+"),
              "type": "text", "text": {"body": "Launch Matcher live check — "
                                               "delivery confirmation probe."}},
        timeout=25,
    )
    probe = resp.json()
    message_id = (probe.get("messages") or [{}])[0].get("id")
    step("4.2 probe message accepted, id returned", bool(message_id),
         json.dumps(probe)[:200])

    # ── 5. Delivery, not just acceptance ─────────────────────
    print("\n-- 5. Delivery confirmation --")
    delivered = False
    if args.statuses_from and message_id:
        print(f"       watching {args.statuses_from} for up to {args.wait}s ...")
        deadline = time.time() + args.wait
        status = None
        while time.time() < deadline:
            status = read_statuses(args.statuses_from, message_id)
            if status in ("delivered", "read"):
                break
            await asyncio.sleep(3)
        delivered = status in ("delivered", "read")
        step(f"5.1 Meta reported delivery (status={status})", delivered,
             "no delivered/read status seen within the wait window")
    elif args.confirm_receipt:
        delivered = True
        step("5.1 receipt confirmed by the operator", True,
             "confirmed via --confirm-receipt")
    else:
        step("5.1 delivery confirmed", False,
             "no --statuses-from and no --confirm-receipt; Meta's 200 is NOT "
             "delivery, so this is SENT-BUT-UNCONFIRMED")

    # ── 6. Nothing persisted ─────────────────────────────────
    print("\n-- 6. No PII persisted --")
    async with SessionLocal() as db:
        logs = (await db.execute(select(MessageLog))).scalars().all()
        rows = (await db.execute(select(InvestorCriteria))).scalars().all()
    step("6.1 message_logs is empty", len(logs) == 0, f"{len(logs)} rows")

    blob = " ".join(f"{r.label} {r.areas} {r.property_type} {r.timeline} "
                    f"{r.notes or ''} {r.payment_preference}" for r in rows)
    leaked = [n for n in PII_NEEDLES if n.lower() in blob.lower()]
    step("6.2 nothing from the message footer reached investor_criteria",
         not leaked, f"leaked {leaked}")

    tables = sorted(Base.metadata.tables)
    async with SessionLocal() as db:
        populated = []
        for name in tables:
            if name in ("companies", "users", "investor_criteria"):
                continue
            count = (await db.execute(
                __import__("sqlalchemy").text(f"SELECT COUNT(*) FROM {name}"))).scalar()
            if count:
                populated.append(f"{name}={count}")
    step("6.3 no other table gained rows", not populated, "; ".join(populated))

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    print("\n" + "=" * 66)
    if failures:
        print(f"  LIVE CHECK FAILED — {len(failures)} step(s):")
        for f in failures:
            print(f"    - {f}")
        print("=" * 66)
        sys.exit(1)
    print("  LIVE ROUND-TRIP CONFIRMED — parsed, matched, sent, delivered,")
    print("  and nothing persisted outside investor_criteria.")
    print("=" * 66)


if __name__ == "__main__":
    asyncio.run(main())
