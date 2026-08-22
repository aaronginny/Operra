"""Buyer <-> seller matching engine.

Python port of DealKnot's api/routes/matches.js. The matching *rules* are
unchanged — same gates, same 25% stretch band, same scoring formula, same
sort order — so a pair matched by the Node app is matched identically here.

The one structural change is persistence. DealKnot recomputed matches on every
GET and never stored them; PhantomPilot writes them to the `matches` table so
that:

  * the WhatsApp hook can tell a *new* match from one the broker already saw,
    and notify exactly once (see Match.notified_at); and
  * the morning pulse can count "matches found overnight" against created_at.

Everything here is scoped to a single company_id. Nothing in this module runs
for a company whose vertical is not "real_estate" — the routes gate on that
before calling in.
"""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buyer import Buyer
from app.models.match import Match
from app.models.seller import Seller
from app.services.real_estate_areas import check_area_match
from app.services.real_estate_constants import type_group

logger = logging.getLogger(__name__)

# Up to 25% above the buyer's max budget still counts as a "stretch" match.
STRETCH_PCT = 0.25

# Fallback proximity radius when a buyer has none set, matching DealKnot's
# `b.radius_km || 5`.
DEFAULT_RADIUS_KM = 5.0


def parse_areas(areas: str | None) -> list[str]:
    """Split a comma-separated area field into trimmed, non-empty parts.

    Original casing is preserved so the UI can echo back what the broker typed;
    comparison is case-insensitive further down.
    """
    return [a.strip() for a in (areas or "").split(",") if a.strip()]


def _to_monthly(amount: float, period: str | None) -> float:
    """Normalise a rental amount to monthly so monthly and yearly can compare."""
    value = float(amount or 0)
    return value / 12 if period == "yearly" else value


def _best_area_match(
    buyer_areas: list[str], seller_areas: list[str], radius_km: float
) -> tuple[str, float, str, str] | None:
    """Find the best area pairing between a buyer's and a seller's area lists.

    Returns (match_type, distance_km, buyer_area, seller_area) or None.
    Preference order is DealKnot's: any exact match beats any proximity match,
    and among proximity matches the closest wins.
    """
    best: tuple[str, float, str, str] | None = None

    for buyer_area in buyer_areas:
        for seller_area in seller_areas:
            result = check_area_match(buyer_area, seller_area, radius_km)
            if not result:
                continue
            match_type, distance = result
            if (
                best is None
                or (match_type == "exact" and best[0] != "exact")
                or (match_type == best[0] and distance < best[1])
            ):
                best = (match_type, distance, buyer_area, seller_area)

    return best


def compute_matches(buyers: list[Buyer], sellers: list[Seller]) -> list[dict]:
    """Score every buyer against every seller and return the matches found.

    Gates, in the order DealKnot applies them: same division, same property
    match group, same currency, an area match within the buyer's radius, and a
    price inside the budget window (or within the stretch band above it).
    """
    out: list[dict] = []

    for buyer in buyers:
        buyer_areas = parse_areas(buyer.areas)
        if not buyer_areas:
            continue
        radius_km = float(buyer.radius_km or DEFAULT_RADIUS_KM)

        for seller in sellers:
            if buyer.division != seller.division:
                continue
            if type_group(buyer.property_type) != type_group(seller.property_type):
                continue
            if buyer.currency != seller.currency:
                continue

            seller_areas = parse_areas(seller.areas)
            if not seller_areas:
                continue

            area_match = _best_area_match(buyer_areas, seller_areas, radius_km)
            if not area_match:
                continue
            match_type, distance_km, matched_buyer_area, matched_seller_area = area_match

            # Rentals are quoted monthly or yearly per record; normalise both
            # sides before comparing so the two conventions can meet.
            is_rental = buyer.division == "rentals"
            if is_rental:
                seller_price = _to_monthly(seller.price, seller.period)
                budget_min = _to_monthly(buyer.budget_min, buyer.period)
                budget_max = _to_monthly(buyer.budget_max, buyer.period)
            else:
                seller_price = float(seller.price or 0)
                budget_min = float(buyer.budget_min or 0)
                budget_max = float(buyer.budget_max or 0)

            if budget_min <= seller_price <= budget_max:
                price_match_kind = "exact"
            elif budget_max < seller_price <= budget_max * (1 + STRETCH_PCT):
                price_match_kind = "stretch"
            else:
                continue

            # Score: 85-98 based on how close the price sits to the middle of
            # the budget window, minus penalties for a stretch price and for
            # proximity distance. Floor of 60. (DealKnot's formula, unchanged.)
            mid = (budget_min + budget_max) / 2
            span = (budget_max - budget_min) / 2 or 1
            base_score = round(85 + (1 - min(1, abs(seller_price - mid) / span)) * 13)
            proximity_penalty = round(distance_km * 0.5) if match_type == "proximity" else 0
            if price_match_kind == "stretch":
                score = max(60, base_score - 18 - proximity_penalty)
            else:
                score = max(60, base_score - proximity_penalty)

            out.append({
                "buyer_id": buyer.id,
                "seller_id": seller.id,
                "match_type": match_type,
                "distance_km": distance_km,
                "price_match_kind": price_match_kind,
                "score": int(score),
                "matched_buyer_area": matched_buyer_area,
                "matched_seller_area": matched_seller_area,
            })

    # Sort: exact price before stretch, then exact area before proximity, then
    # by descending score.
    out.sort(key=lambda m: (
        0 if m["price_match_kind"] == "exact" else 1,
        0 if m["match_type"] == "exact" else 1,
        -m["score"],
    ))
    return out


async def run_matching_for_company(
    db: AsyncSession, company_id: int
) -> tuple[list[Match], list[Match]]:
    """Recompute matches for one company and persist the results.

    Returns (new_matches, all_matches). `new_matches` holds only pairings that
    did not already exist — that is what the WhatsApp hook notifies on, so a
    broker is never re-notified about a pair they have already been told about.

    Existing rows are updated in place when the underlying numbers change (a
    buyer widening their budget can turn a stretch match into an exact one),
    and matches that no longer hold are deleted — except where the broker has
    already connected the two parties, which is a human decision this engine
    does not get to overrule.
    """
    buyers = (
        await db.execute(select(Buyer).where(Buyer.company_id == company_id))
    ).scalars().all()
    sellers = (
        await db.execute(select(Seller).where(Seller.company_id == company_id))
    ).scalars().all()

    computed = compute_matches(list(buyers), list(sellers))

    existing_rows = (
        await db.execute(select(Match).where(Match.company_id == company_id))
    ).scalars().all()
    existing_by_pair = {(m.buyer_id, m.seller_id): m for m in existing_rows}

    new_matches: list[Match] = []
    all_matches: list[Match] = []
    computed_pairs: set[tuple[int, int]] = set()

    for data in computed:
        pair = (data["buyer_id"], data["seller_id"])
        computed_pairs.add(pair)
        row = existing_by_pair.get(pair)

        if row is None:
            row = Match(
                company_id=company_id,
                buyer_id=data["buyer_id"],
                seller_id=data["seller_id"],
                match_type=data["match_type"],
                distance_km=Decimal(str(data["distance_km"])),
                price_match_kind=data["price_match_kind"],
                score=data["score"],
                matched_buyer_area=data["matched_buyer_area"],
                matched_seller_area=data["matched_seller_area"],
            )
            db.add(row)
            new_matches.append(row)
        else:
            # Refresh the scoring fields; leave `connected` and `notified_at`
            # alone — those record what the broker and the notifier have done.
            row.match_type = data["match_type"]
            row.distance_km = Decimal(str(data["distance_km"]))
            row.price_match_kind = data["price_match_kind"]
            row.score = data["score"]
            row.matched_buyer_area = data["matched_buyer_area"]
            row.matched_seller_area = data["matched_seller_area"]

        all_matches.append(row)

    # Drop matches that no longer hold, unless the broker already connected them.
    for pair, row in existing_by_pair.items():
        if pair not in computed_pairs and not row.connected:
            await db.delete(row)

    await db.flush()

    logger.info(
        "Matching run for company=%s: %d buyers x %d sellers -> %d matches (%d new)",
        company_id, len(buyers), len(sellers), len(all_matches), len(new_matches),
    )
    return new_matches, all_matches
