"""Real-estate vertical routes — buyers, sellers, listings, matches, commissions.

Every endpoint here is gated on `require_real_estate_company`, which is the
existing get_current_user dependency plus a check that the caller's company has
vertical = "real_estate". A generic company gets a 404, so the vertical is
invisible rather than merely locked.

Scoping follows the same pattern as the other route modules: read company_id
off the authenticated user and filter every query by it; never trust an id in
the payload. Ownership is re-checked on every by-id lookup before mutating.

The five resources share enough shape that they live in one module rather than
five near-identical ones — they are one feature, gated as one, and splitting
them would mean repeating the vertical gate and validation helpers five times.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_real_estate_company
from app.models.buyer import Buyer
from app.models.commission import Commission
from app.models.enquiry import Enquiry
from app.models.listing import Listing
from app.models.match import Match
from app.models.seller import Seller
from app.schemas.auth_schema import CurrentUser
from app.services import real_estate_constants as rc
from app.services.matching_service import run_matching_for_company

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/real-estate", tags=["Real Estate"])


# ── Validation helpers ───────────────────────────────────────
# Unknown values fall back to the documented default rather than 400ing, which
# is what DealKnot's routes did (VALID_* sets with a default). Keeps imports of
# messy spreadsheet data from failing wholesale on one bad cell.

def _valid(value: str | None, allowed, default: str) -> str:
    return value if value in allowed else default


def _clamp_radius(value) -> float:
    """Radius is clamped to 1-50km, as in DealKnot's buyers route."""
    try:
        return max(1.0, min(50.0, float(value)))
    except (TypeError, ValueError):
        return 5.0


def _norm_areas(areas: str | None) -> str:
    """Normalise a comma-separated area list: trim parts, drop empties."""
    return ", ".join(a.strip() for a in (areas or "").split(",") if a.strip())


# ── Schemas ──────────────────────────────────────────────────

class BuyerCreate(BaseModel):
    name: str
    phone: str | None = None
    dial: str = "+91"
    country: str = "IN"
    areas: str = ""
    property_type: str = "apt_resale"
    division: str = "sales"
    currency: str = "INR"
    budget_min: float = 0
    budget_max: float = 0
    period: str = "monthly"
    radius_km: float = 5
    label: str = "active"
    referred_by: str | None = None
    notes: str | None = None


class BuyerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    dial: str | None = None
    country: str | None = None
    areas: str | None = None
    property_type: str | None = None
    division: str | None = None
    currency: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    period: str | None = None
    radius_km: float | None = None
    label: str | None = None
    referred_by: str | None = None
    notes: str | None = None


class BuyerResponse(BaseModel):
    id: int
    company_id: int
    name: str
    phone: str | None = None
    dial: str
    country: str
    areas: str
    property_type: str
    division: str
    currency: str
    budget_min: float
    budget_max: float
    period: str
    radius_km: float
    label: str
    referred_by: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SellerCreate(BaseModel):
    name: str
    phone: str | None = None
    dial: str = "+91"
    country: str = "IN"
    areas: str = ""
    property_type: str = "apt_resale"
    division: str = "sales"
    currency: str = "INR"
    price: float = 0
    period: str = "monthly"
    label: str = "active"
    referred_by: str | None = None
    notes: str | None = None


class SellerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    dial: str | None = None
    country: str | None = None
    areas: str | None = None
    property_type: str | None = None
    division: str | None = None
    currency: str | None = None
    price: float | None = None
    period: str | None = None
    label: str | None = None
    referred_by: str | None = None
    notes: str | None = None


class SellerResponse(BaseModel):
    id: int
    company_id: int
    name: str
    phone: str | None = None
    dial: str
    country: str
    areas: str
    property_type: str
    division: str
    currency: str
    price: float
    period: str
    label: str
    referred_by: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingCreate(BaseModel):
    title: str
    seller_id: int | None = None
    area: str = ""
    property_type: str = "apt_resale"
    division: str = "sales"
    price: float = 0
    currency: str = "INR"
    period: str = "monthly"
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqft: float | None = None
    status: str = "available"
    notes: str | None = None


class ListingUpdate(BaseModel):
    title: str | None = None
    seller_id: int | None = None
    area: str | None = None
    property_type: str | None = None
    division: str | None = None
    price: float | None = None
    currency: str | None = None
    period: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqft: float | None = None
    status: str | None = None
    notes: str | None = None


class ListingResponse(BaseModel):
    id: int
    company_id: int
    seller_id: int | None = None
    title: str
    area: str
    property_type: str
    division: str
    price: float
    currency: str
    period: str
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqft: float | None = None
    status: str
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommissionCreate(BaseModel):
    enquiry_id: int | None = None
    deal_value: float = 0
    commission_percent: float = 0
    commission_amount: float | None = None
    split_percent: float = 100
    source: str = "both_sides"
    currency: str = "INR"
    status: str = "Pending"
    expected_date: datetime | None = None
    received_date: datetime | None = None
    notes: str | None = None


class CommissionUpdate(BaseModel):
    enquiry_id: int | None = None
    deal_value: float | None = None
    commission_percent: float | None = None
    commission_amount: float | None = None
    split_percent: float | None = None
    source: str | None = None
    currency: str | None = None
    status: str | None = None
    expected_date: datetime | None = None
    received_date: datetime | None = None
    notes: str | None = None


class CommissionResponse(BaseModel):
    id: int
    company_id: int
    enquiry_id: int | None = None
    deal_value: float
    commission_percent: float
    commission_amount: float
    split_percent: float
    source: str
    currency: str
    status: str
    expected_date: datetime | None = None
    received_date: datetime | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Reference data ───────────────────────────────────────────

@router.get("/constants")
async def get_constants(
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Static reference data for the dashboard's dropdowns."""
    return {
        "countries": rc.COUNTRIES,
        "currencies": rc.CURRENCIES,
        "divisions": rc.DIVISIONS,
        "labels": rc.LABELS,
        "property_types": rc.PROPERTY_TYPES,
        "commission_sources": rc.COMMISSION_SOURCES,
        "commission_statuses": rc.COMMISSION_STATUSES,
        "listing_statuses": rc.LISTING_STATUSES,
    }


# ── Buyers ───────────────────────────────────────────────────

@router.get("/buyers", response_model=list[BuyerResponse])
async def list_buyers(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """List this company's buyers, newest first."""
    stmt = (
        select(Buyer)
        .where(Buyer.company_id == current_user.company_id)
        .order_by(Buyer.created_at.desc(), Buyer.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/buyers", response_model=BuyerResponse, status_code=201)
async def create_buyer(
    payload: BuyerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Create a buyer, then re-run matching so new pairings surface immediately."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Buyer name cannot be empty")
    if payload.budget_max < payload.budget_min:
        raise HTTPException(status_code=400, detail="budget_max must be >= budget_min")

    buyer = Buyer(
        company_id=current_user.company_id,
        name=name,
        phone=payload.phone,
        dial=payload.dial or "+91",
        country=_valid(payload.country, rc.COUNTRY_CODES, "IN"),
        areas=_norm_areas(payload.areas),
        property_type=_valid(payload.property_type, rc.PROPERTY_TYPE_IDS, "apt_resale"),
        division=_valid(payload.division, rc.DIVISION_IDS, "sales"),
        currency=_valid(payload.currency, rc.CURRENCY_CODES, "INR"),
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        period=_valid(payload.period, rc.RENTAL_PERIODS, "monthly"),
        radius_km=_clamp_radius(payload.radius_km),
        label=_valid(payload.label, rc.LABEL_IDS, "active"),
        referred_by=payload.referred_by,
        notes=payload.notes,
    )
    db.add(buyer)
    await db.flush()
    await db.refresh(buyer)

    await _run_matching_and_notify(db, current_user.company_id)
    logger.info("Buyer created: id=%s company=%s", buyer.id, current_user.company_id)
    return buyer


@router.patch("/buyers/{buyer_id}", response_model=BuyerResponse)
async def update_buyer(
    buyer_id: int,
    payload: BuyerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Update a buyer and re-run matching (budget/area edits change matches)."""
    buyer = await db.get(Buyer, buyer_id)
    if not buyer or buyer.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Buyer not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        buyer.name = data["name"].strip() or buyer.name
    for field in ("phone", "dial", "referred_by", "notes"):
        if field in data:
            setattr(buyer, field, data[field])
    if "areas" in data and data["areas"] is not None:
        buyer.areas = _norm_areas(data["areas"])
    if data.get("country") is not None:
        buyer.country = _valid(data["country"], rc.COUNTRY_CODES, buyer.country)
    if data.get("property_type") is not None:
        buyer.property_type = _valid(data["property_type"], rc.PROPERTY_TYPE_IDS, buyer.property_type)
    if data.get("division") is not None:
        buyer.division = _valid(data["division"], rc.DIVISION_IDS, buyer.division)
    if data.get("currency") is not None:
        buyer.currency = _valid(data["currency"], rc.CURRENCY_CODES, buyer.currency)
    if data.get("period") is not None:
        buyer.period = _valid(data["period"], rc.RENTAL_PERIODS, buyer.period)
    if data.get("label") is not None:
        buyer.label = _valid(data["label"], rc.LABEL_IDS, buyer.label)
    if data.get("radius_km") is not None:
        buyer.radius_km = _clamp_radius(data["radius_km"])
    if data.get("budget_min") is not None:
        buyer.budget_min = data["budget_min"]
    if data.get("budget_max") is not None:
        buyer.budget_max = data["budget_max"]
    if float(buyer.budget_max) < float(buyer.budget_min):
        raise HTTPException(status_code=400, detail="budget_max must be >= budget_min")

    await db.flush()
    await db.refresh(buyer)
    await _run_matching_and_notify(db, current_user.company_id)
    return buyer


@router.delete("/buyers/{buyer_id}")
async def delete_buyer(
    buyer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Delete a buyer and any matches referencing them."""
    buyer = await db.get(Buyer, buyer_id)
    if not buyer or buyer.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Buyer not found")

    # Clear dependents explicitly — SQLite dev DBs don't enforce ON DELETE.
    for match in (
        await db.execute(select(Match).where(Match.buyer_id == buyer_id))
    ).scalars().all():
        await db.delete(match)
    for enquiry in (
        await db.execute(select(Enquiry).where(Enquiry.buyer_id == buyer_id))
    ).scalars().all():
        enquiry.buyer_id = None

    await db.delete(buyer)
    await db.flush()
    return {"status": "deleted", "id": buyer_id}


# ── Sellers ──────────────────────────────────────────────────

@router.get("/sellers", response_model=list[SellerResponse])
async def list_sellers(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """List this company's sellers, newest first."""
    stmt = (
        select(Seller)
        .where(Seller.company_id == current_user.company_id)
        .order_by(Seller.created_at.desc(), Seller.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/sellers", response_model=SellerResponse, status_code=201)
async def create_seller(
    payload: SellerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Create a seller, then re-run matching so new pairings surface immediately."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Seller name cannot be empty")

    seller = Seller(
        company_id=current_user.company_id,
        name=name,
        phone=payload.phone,
        dial=payload.dial or "+91",
        country=_valid(payload.country, rc.COUNTRY_CODES, "IN"),
        areas=_norm_areas(payload.areas),
        property_type=_valid(payload.property_type, rc.PROPERTY_TYPE_IDS, "apt_resale"),
        division=_valid(payload.division, rc.DIVISION_IDS, "sales"),
        currency=_valid(payload.currency, rc.CURRENCY_CODES, "INR"),
        price=payload.price,
        period=_valid(payload.period, rc.RENTAL_PERIODS, "monthly"),
        label=_valid(payload.label, rc.LABEL_IDS, "active"),
        referred_by=payload.referred_by,
        notes=payload.notes,
    )
    db.add(seller)
    await db.flush()
    await db.refresh(seller)

    await _run_matching_and_notify(db, current_user.company_id)
    logger.info("Seller created: id=%s company=%s", seller.id, current_user.company_id)
    return seller


@router.patch("/sellers/{seller_id}", response_model=SellerResponse)
async def update_seller(
    seller_id: int,
    payload: SellerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Update a seller and re-run matching (price/area edits change matches)."""
    seller = await db.get(Seller, seller_id)
    if not seller or seller.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Seller not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        seller.name = data["name"].strip() or seller.name
    for field in ("phone", "dial", "referred_by", "notes"):
        if field in data:
            setattr(seller, field, data[field])
    if "areas" in data and data["areas"] is not None:
        seller.areas = _norm_areas(data["areas"])
    if data.get("country") is not None:
        seller.country = _valid(data["country"], rc.COUNTRY_CODES, seller.country)
    if data.get("property_type") is not None:
        seller.property_type = _valid(data["property_type"], rc.PROPERTY_TYPE_IDS, seller.property_type)
    if data.get("division") is not None:
        seller.division = _valid(data["division"], rc.DIVISION_IDS, seller.division)
    if data.get("currency") is not None:
        seller.currency = _valid(data["currency"], rc.CURRENCY_CODES, seller.currency)
    if data.get("period") is not None:
        seller.period = _valid(data["period"], rc.RENTAL_PERIODS, seller.period)
    if data.get("label") is not None:
        seller.label = _valid(data["label"], rc.LABEL_IDS, seller.label)
    if data.get("price") is not None:
        seller.price = data["price"]

    await db.flush()
    await db.refresh(seller)
    await _run_matching_and_notify(db, current_user.company_id)
    return seller


@router.delete("/sellers/{seller_id}")
async def delete_seller(
    seller_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Delete a seller, its matches, and unlink dependent listings/enquiries."""
    seller = await db.get(Seller, seller_id)
    if not seller or seller.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Seller not found")

    for match in (
        await db.execute(select(Match).where(Match.seller_id == seller_id))
    ).scalars().all():
        await db.delete(match)
    for listing in (
        await db.execute(select(Listing).where(Listing.seller_id == seller_id))
    ).scalars().all():
        listing.seller_id = None
    for enquiry in (
        await db.execute(select(Enquiry).where(Enquiry.seller_id == seller_id))
    ).scalars().all():
        enquiry.seller_id = None

    await db.delete(seller)
    await db.flush()
    return {"status": "deleted", "id": seller_id}


# ── Listings ─────────────────────────────────────────────────

@router.get("/listings", response_model=list[ListingResponse])
async def list_listings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """List this company's property listings, newest first."""
    stmt = (
        select(Listing)
        .where(Listing.company_id == current_user.company_id)
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/listings", response_model=ListingResponse, status_code=201)
async def create_listing(
    payload: ListingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Create a property listing, optionally attached to a seller we hold."""
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Listing title cannot be empty")

    if payload.seller_id is not None:
        seller = await db.get(Seller, payload.seller_id)
        if not seller or seller.company_id != current_user.company_id:
            raise HTTPException(status_code=400, detail="Unknown seller")

    listing = Listing(
        company_id=current_user.company_id,
        seller_id=payload.seller_id,
        title=title,
        area=(payload.area or "").strip(),
        property_type=_valid(payload.property_type, rc.PROPERTY_TYPE_IDS, "apt_resale"),
        division=_valid(payload.division, rc.DIVISION_IDS, "sales"),
        price=payload.price,
        currency=_valid(payload.currency, rc.CURRENCY_CODES, "INR"),
        period=_valid(payload.period, rc.RENTAL_PERIODS, "monthly"),
        bedrooms=payload.bedrooms,
        bathrooms=payload.bathrooms,
        area_sqft=payload.area_sqft,
        status=_valid(payload.status, rc.LISTING_STATUS_IDS, "available"),
        notes=payload.notes,
    )
    db.add(listing)
    await db.flush()
    await db.refresh(listing)
    logger.info("Listing created: id=%s company=%s", listing.id, current_user.company_id)
    return listing


@router.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Update a property listing."""
    listing = await db.get(Listing, listing_id)
    if not listing or listing.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Listing not found")

    data = payload.model_dump(exclude_unset=True)
    if data.get("title") is not None:
        listing.title = data["title"].strip() or listing.title
    if data.get("area") is not None:
        listing.area = data["area"].strip()
    if "seller_id" in data:
        if data["seller_id"] is not None:
            seller = await db.get(Seller, data["seller_id"])
            if not seller or seller.company_id != current_user.company_id:
                raise HTTPException(status_code=400, detail="Unknown seller")
        listing.seller_id = data["seller_id"]
    if data.get("property_type") is not None:
        listing.property_type = _valid(data["property_type"], rc.PROPERTY_TYPE_IDS, listing.property_type)
    if data.get("division") is not None:
        listing.division = _valid(data["division"], rc.DIVISION_IDS, listing.division)
    if data.get("currency") is not None:
        listing.currency = _valid(data["currency"], rc.CURRENCY_CODES, listing.currency)
    if data.get("period") is not None:
        listing.period = _valid(data["period"], rc.RENTAL_PERIODS, listing.period)
    if data.get("status") is not None:
        listing.status = _valid(data["status"], rc.LISTING_STATUS_IDS, listing.status)
    for field in ("price", "bedrooms", "bathrooms", "area_sqft", "notes"):
        if field in data:
            setattr(listing, field, data[field])

    await db.flush()
    await db.refresh(listing)
    return listing


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Delete a property listing."""
    listing = await db.get(Listing, listing_id)
    if not listing or listing.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Listing not found")
    await db.delete(listing)
    await db.flush()
    return {"status": "deleted", "id": listing_id}


# ── Matches ──────────────────────────────────────────────────

async def _run_matching_and_notify(db: AsyncSession, company_id: int) -> list[Match]:
    """Re-run the engine and return the newly found matches."""
    new_matches, _ = await run_matching_for_company(db, company_id)
    return new_matches


async def _match_payload(db: AsyncSession, match: Match) -> dict:
    """Expand a Match row with the buyer/seller detail the UI needs."""
    buyer = await db.get(Buyer, match.buyer_id)
    seller = await db.get(Seller, match.seller_id)
    return {
        "id": match.id,
        "buyer_id": match.buyer_id,
        "seller_id": match.seller_id,
        "buyer_name": buyer.name if buyer else None,
        "buyer_phone": buyer.phone if buyer else None,
        "buyer_areas": buyer.areas if buyer else None,
        "buyer_budget_min": float(buyer.budget_min) if buyer else None,
        "buyer_budget_max": float(buyer.budget_max) if buyer else None,
        "seller_name": seller.name if seller else None,
        "seller_phone": seller.phone if seller else None,
        "seller_areas": seller.areas if seller else None,
        "seller_price": float(seller.price) if seller else None,
        "currency": buyer.currency if buyer else (seller.currency if seller else "INR"),
        "property_type": buyer.property_type if buyer else None,
        "division": buyer.division if buyer else None,
        "match_type": match.match_type,
        "distance_km": float(match.distance_km),
        "price_match_kind": match.price_match_kind,
        "score": match.score,
        "matched_buyer_area": match.matched_buyer_area,
        "matched_seller_area": match.matched_seller_area,
        "connected": match.connected,
        "created_at": match.created_at,
    }


@router.get("/matches")
async def list_matches(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """List stored matches, best first (exact price, then exact area, then score)."""
    stmt = (
        select(Match)
        .where(Match.company_id == current_user.company_id)
        .order_by(Match.score.desc(), Match.id.desc())
    )
    matches = (await db.execute(stmt)).scalars().all()
    matches = sorted(
        matches,
        key=lambda m: (
            0 if m.price_match_kind == "exact" else 1,
            0 if m.match_type == "exact" else 1,
            -m.score,
        ),
    )
    return [await _match_payload(db, m) for m in matches]


@router.post("/matches/run")
async def run_matches(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Re-run the matching engine for this company on demand."""
    new_matches = await _run_matching_and_notify(db, current_user.company_id)
    total = (
        await db.execute(
            select(sa_func.count(Match.id)).where(Match.company_id == current_user.company_id)
        )
    ).scalar() or 0
    return {
        "status": "ok",
        "new_matches": len(new_matches),
        "total_matches": total,
    }


@router.patch("/matches/{match_id}/connect")
async def toggle_match_connected(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Toggle whether the broker has introduced the two parties."""
    match = await db.get(Match, match_id)
    if not match or match.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Match not found")
    match.connected = not match.connected
    await db.flush()
    return {"id": match.id, "connected": match.connected}


# ── Commissions ──────────────────────────────────────────────

def _derive_commission_amount(deal_value: float, percent: float, explicit: float | None) -> float:
    """Use the amount the broker typed, else derive it from value x percent."""
    if explicit is not None:
        return explicit
    return round((float(deal_value or 0) * float(percent or 0)) / 100, 2)


@router.get("/commissions", response_model=list[CommissionResponse])
async def list_commissions(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """List this company's commissions, newest first."""
    stmt = (
        select(Commission)
        .where(Commission.company_id == current_user.company_id)
        .order_by(Commission.created_at.desc(), Commission.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/commissions", response_model=CommissionResponse, status_code=201)
async def create_commission(
    payload: CommissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Book a commission, optionally against the enquiry the deal came through."""
    if payload.enquiry_id is not None:
        enquiry = await db.get(Enquiry, payload.enquiry_id)
        if not enquiry or enquiry.company_id != current_user.company_id:
            raise HTTPException(status_code=400, detail="Unknown enquiry")

    commission = Commission(
        company_id=current_user.company_id,
        enquiry_id=payload.enquiry_id,
        deal_value=payload.deal_value,
        commission_percent=payload.commission_percent,
        commission_amount=_derive_commission_amount(
            payload.deal_value, payload.commission_percent, payload.commission_amount
        ),
        split_percent=payload.split_percent,
        source=_valid(payload.source, rc.COMMISSION_SOURCE_IDS, "both_sides"),
        currency=_valid(payload.currency, rc.CURRENCY_CODES, "INR"),
        status=_valid(payload.status, set(rc.COMMISSION_STATUSES), "Pending"),
        expected_date=payload.expected_date,
        received_date=payload.received_date,
        notes=payload.notes,
    )
    db.add(commission)
    await db.flush()
    await db.refresh(commission)
    logger.info("Commission created: id=%s company=%s", commission.id, current_user.company_id)
    return commission


@router.patch("/commissions/{commission_id}", response_model=CommissionResponse)
async def update_commission(
    commission_id: int,
    payload: CommissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Update a commission."""
    commission = await db.get(Commission, commission_id)
    if not commission or commission.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Commission not found")

    data = payload.model_dump(exclude_unset=True)
    if "enquiry_id" in data:
        if data["enquiry_id"] is not None:
            enquiry = await db.get(Enquiry, data["enquiry_id"])
            if not enquiry or enquiry.company_id != current_user.company_id:
                raise HTTPException(status_code=400, detail="Unknown enquiry")
        commission.enquiry_id = data["enquiry_id"]
    if data.get("source") is not None:
        commission.source = _valid(data["source"], rc.COMMISSION_SOURCE_IDS, commission.source)
    if data.get("currency") is not None:
        commission.currency = _valid(data["currency"], rc.CURRENCY_CODES, commission.currency)
    if data.get("status") is not None:
        commission.status = _valid(data["status"], set(rc.COMMISSION_STATUSES), commission.status)
    for field in ("deal_value", "commission_percent", "split_percent",
                  "expected_date", "received_date", "notes"):
        if field in data:
            setattr(commission, field, data[field])

    # Recompute the amount when value or percent moved and no explicit amount
    # was supplied, so the derived figure never goes stale.
    if data.get("commission_amount") is not None:
        commission.commission_amount = data["commission_amount"]
    elif "deal_value" in data or "commission_percent" in data:
        commission.commission_amount = _derive_commission_amount(
            float(commission.deal_value), float(commission.commission_percent), None
        )

    await db.flush()
    await db.refresh(commission)
    return commission


@router.delete("/commissions/{commission_id}")
async def delete_commission(
    commission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Delete a commission."""
    commission = await db.get(Commission, commission_id)
    if not commission or commission.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Commission not found")
    await db.delete(commission)
    await db.flush()
    return {"status": "deleted", "id": commission_id}


# ── Summary ──────────────────────────────────────────────────

@router.get("/summary")
async def real_estate_summary(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_real_estate_company),
):
    """Headline counts for the dashboard's real-estate cards."""
    company_id = current_user.company_id

    async def _count(model) -> int:
        return (
            await db.execute(
                select(sa_func.count(model.id)).where(model.company_id == company_id)
            )
        ).scalar() or 0

    connected = (
        await db.execute(
            select(sa_func.count(Match.id))
            .where(Match.company_id == company_id, Match.connected.is_(True))
        )
    ).scalar() or 0

    commission_total = (
        await db.execute(
            select(sa_func.coalesce(sa_func.sum(Commission.commission_amount), 0))
            .where(Commission.company_id == company_id, Commission.status == "Received")
        )
    ).scalar() or 0

    return {
        "buyers": await _count(Buyer),
        "sellers": await _count(Seller),
        "listings": await _count(Listing),
        "matches": await _count(Match),
        "connected_matches": connected,
        "commissions": await _count(Commission),
        "commission_received_total": float(commission_total),
    }
