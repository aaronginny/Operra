"""WhatsApp notifications for the real-estate vertical.

Reuses the existing Meta Cloud API sender in app.services.messaging_service —
nothing about delivery, phone normalisation or error handling is rebuilt here.
This module only decides *who* to notify and *what to say*.

Every entry point is a no-op for companies whose vertical is not
"real_estate", so a generic account such as Lenin's can never receive one of
these messages even if a code path is reached by mistake.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buyer import Buyer
from app.models.company import Company
from app.models.enquiry import Enquiry
from app.models.match import Match
from app.models.seller import Seller
from app.models.user import User, UserRole
from app.services.messaging_service import send_whatsapp_message

logger = logging.getLogger(__name__)

# Cap on how many matches are listed in one message — a broker who bulk-imports
# 200 buyers should get a digest, not 200 lines of WhatsApp.
MAX_MATCHES_PER_MESSAGE = 5


async def is_real_estate_company(db: AsyncSession, company_id: int) -> bool:
    """True only when this company has opted into the real-estate vertical."""
    company = await db.get(Company, company_id)
    return bool(company and company.vertical == "real_estate")


async def get_broker_recipients(db: AsyncSession, company_id: int) -> list[User]:
    """Users who should receive broker alerts for a company.

    The CEO/founder accounts are the brokers here — employees get task
    reminders through the existing channels, not deal flow. Users without a
    WhatsApp number on file are skipped rather than erroring.
    """
    stmt = select(User).where(
        User.company_id == company_id,
        User.role.in_([UserRole.ceo, UserRole.founder]),
    )
    users = (await db.execute(stmt)).scalars().all()
    return [u for u in users if u.whatsapp_number]


def _format_price(amount: float | None, currency: str = "INR") -> str:
    """Compact money for a WhatsApp line: 85L / 1.2Cr for INR, 1.2M otherwise."""
    if amount is None:
        return "-"
    value = float(amount)
    if currency == "INR":
        if value >= 10_000_000:
            return f"{value / 10_000_000:.2f}".rstrip("0").rstrip(".") + " Cr"
        if value >= 100_000:
            return f"{value / 100_000:.2f}".rstrip("0").rstrip(".") + " L"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
    return f"{value:.0f}"


async def _match_line(db: AsyncSession, match: Match) -> str:
    """One human-readable line describing a match."""
    buyer = await db.get(Buyer, match.buyer_id)
    seller = await db.get(Seller, match.seller_id)
    buyer_name = buyer.name if buyer else f"Buyer #{match.buyer_id}"
    seller_name = seller.name if seller else f"Seller #{match.seller_id}"
    currency = (buyer.currency if buyer else None) or "INR"

    if match.match_type == "proximity":
        distance = float(match.distance_km)
        area_note = (
            f"{match.matched_buyer_area} ~ {match.matched_seller_area} "
            f"({distance:.1f} km away)"
        )
    else:
        area_note = f"{match.matched_buyer_area or (buyer.areas if buyer else '')}"

    price = _format_price(float(seller.price) if seller else None, currency)
    stretch = " (slightly over budget)" if match.price_match_kind == "stretch" else ""

    return (
        f"• {buyer_name} <-> {seller_name}\n"
        f"  {area_note}\n"
        f"  Asking {price}{stretch} — score {match.score}"
    )


async def notify_new_matches(
    db: AsyncSession, company_id: int, matches: list[Match]
) -> int:
    """Alert the company's brokers about newly found matches.

    Stamps Match.notified_at so a given pairing is announced exactly once, even
    though the engine re-runs on every buyer/seller write. Returns the number
    of messages actually sent.

    Delivery failures do not raise: the caller has already saved the matches
    and a broker's data must not be lost because Meta was unreachable or the
    24-hour messaging window had closed.
    """
    if not matches:
        return 0
    if not await is_real_estate_company(db, company_id):
        logger.debug("notify_new_matches skipped — company=%s is not real_estate", company_id)
        return 0

    unnotified = [m for m in matches if m.notified_at is None]
    if not unnotified:
        return 0

    recipients = await get_broker_recipients(db, company_id)
    if not recipients:
        logger.info(
            "New matches for company=%s but no broker has a WhatsApp number on file",
            company_id,
        )
        # Still stamp them: without a recipient there is nothing to announce,
        # and leaving them unstamped would queue a burst for whenever a number
        # is finally added.
        for match in unnotified:
            match.notified_at = datetime.utcnow()
        await db.flush()
        return 0

    ranked = sorted(unnotified, key=lambda m: -m.score)
    shown = ranked[:MAX_MATCHES_PER_MESSAGE]
    lines = [await _match_line(db, m) for m in shown]

    header = (
        f"PhantomPilot - {len(unnotified)} new match"
        f"{'es' if len(unnotified) != 1 else ''} found"
    )
    body = "\n\n".join(lines)
    footer = ""
    if len(unnotified) > len(shown):
        footer = f"\n\n...and {len(unnotified) - len(shown)} more. Open your dashboard to view all."
    message = f"{header}\n\n{body}{footer}"

    sent = 0
    for user in recipients:
        ok = await send_whatsapp_message(user.whatsapp_number, message)
        if ok:
            sent += 1
        else:
            logger.warning(
                "New-match alert not delivered to user=%s company=%s", user.id, company_id
            )

    stamped_at = datetime.utcnow()
    for match in unnotified:
        match.notified_at = stamped_at
    await db.flush()

    logger.info(
        "New-match alert: company=%s matches=%d recipients=%d delivered=%d",
        company_id, len(unnotified), len(recipients), sent,
    )
    return sent


async def notify_enquiry_stage_change(
    db: AsyncSession, enquiry: Enquiry, stage: str
) -> int:
    """Tell the brokers that a real-estate enquiry moved kanban stage.

    This is *in addition to* the existing per-employee stage message that
    /enquiries/{id}/advance-stage already sends — that one tells the assignee
    what to do next, this one keeps the broker across their pipeline. No-op for
    generic companies, so the existing behaviour is untouched for them.
    """
    if not await is_real_estate_company(db, enquiry.company_id):
        return 0

    recipients = await get_broker_recipients(db, enquiry.company_id)
    if not recipients:
        return 0

    stage_labels = {
        "follow_up": "Follow Up",
        "send_options": "Send Options",
        "close_deal": "Close Deal",
        "payment_received": "Payment",
        "done": "Done",
    }
    label = stage_labels.get(stage, stage)

    context = ""
    if enquiry.buyer_id:
        buyer = await db.get(Buyer, enquiry.buyer_id)
        if buyer:
            context += f"\nBuyer: {buyer.name} ({buyer.areas})"
    if enquiry.seller_id:
        seller = await db.get(Seller, enquiry.seller_id)
        if seller:
            context += f"\nSeller: {seller.name} ({seller.areas})"

    message = (
        f"PhantomPilot - Enquiry moved to {label}\n\n"
        f"Client: {enquiry.client_name}{context}"
    )

    sent = 0
    for user in recipients:
        if await send_whatsapp_message(user.whatsapp_number, message):
            sent += 1
    logger.info(
        "Enquiry stage alert: enquiry=%s stage=%s delivered=%d",
        enquiry.id, stage, sent,
    )
    return sent


async def build_broker_pulse(db: AsyncSession, company_id: int) -> str | None:
    """Build the real-estate section of the morning pulse for one company.

    Covers the last 24 hours: new leads captured, matches the engine found
    overnight, and where everything sits on the kanban. Returns None when the
    company is not real-estate or when there is genuinely nothing to report —
    a silent morning is better than a message full of zeroes.
    """
    if not await is_real_estate_company(db, company_id):
        return None

    since = datetime.utcnow() - timedelta(hours=24)

    new_buyers = (await db.execute(
        select(Buyer).where(Buyer.company_id == company_id, Buyer.created_at >= since)
    )).scalars().all()
    new_sellers = (await db.execute(
        select(Seller).where(Seller.company_id == company_id, Seller.created_at >= since)
    )).scalars().all()
    new_matches = (await db.execute(
        select(Match).where(Match.company_id == company_id, Match.created_at >= since)
    )).scalars().all()

    open_enquiries = (await db.execute(
        select(Enquiry).where(Enquiry.company_id == company_id)
    )).scalars().all()

    stage_labels = [
        ("follow_up", "Follow Up"),
        ("send_options", "Send Options"),
        ("close_deal", "Close Deal"),
        ("payment_received", "Payment"),
    ]
    stage_counts = {key: 0 for key, _ in stage_labels}
    for enquiry in open_enquiries:
        if enquiry.stage in stage_counts:
            stage_counts[enquiry.stage] += 1

    lead_count = len(new_buyers) + len(new_sellers)
    if not lead_count and not new_matches and not any(stage_counts.values()):
        return None

    lines = ["Your overnight summary:"]
    if lead_count:
        parts = []
        if new_buyers:
            parts.append(f"{len(new_buyers)} buyer{'s' if len(new_buyers) != 1 else ''}")
        if new_sellers:
            parts.append(f"{len(new_sellers)} seller{'s' if len(new_sellers) != 1 else ''}")
        lines.append(f"New leads: {' and '.join(parts)}")
    else:
        lines.append("New leads: none")

    if new_matches:
        exact = sum(1 for m in new_matches if m.match_type == "exact")
        nearby = len(new_matches) - exact
        detail = f"{exact} exact" if exact else ""
        if nearby:
            detail += (", " if detail else "") + f"{nearby} nearby"
        lines.append(f"Matches found: {len(new_matches)} ({detail})")
    else:
        lines.append("Matches found: none")

    pipeline = " | ".join(
        f"{label}: {stage_counts[key]}" for key, label in stage_labels
    )
    lines.append(f"Pipeline — {pipeline}")

    return "\n".join(lines)


async def send_broker_pulse(db: AsyncSession, company_id: int) -> int:
    """Send the real-estate morning pulse to a company's brokers."""
    body = await build_broker_pulse(db, company_id)
    if not body:
        return 0

    recipients = await get_broker_recipients(db, company_id)
    sent = 0
    for user in recipients:
        message = f"Good morning {user.name}!\n\n{body}"
        if await send_whatsapp_message(user.whatsapp_number, message):
            sent += 1
    logger.info("Broker pulse: company=%s delivered=%d", company_id, sent)
    return sent
