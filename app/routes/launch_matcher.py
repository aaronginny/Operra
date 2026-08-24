"""Launch Matcher setup routes — investor criteria CRUD.

Gated on `require_launch_matcher_company`, which 404s for every other tenant,
so the feature is invisible rather than merely locked — the same fail-safe
pattern the real-estate vertical uses. The two verticals are mutually
exclusive, so a broker-CRM company cannot reach these routes either.

These exist for one-time setup. The daily flow is entirely WhatsApp; the
advisor never needs to open a screen to match a launch.

PII: this is the only write path into investor_criteria, and it is built so PII
cannot go in. See `_reject_contact_details` and the `extra="forbid"` config —
between them, an unknown field like `name`/`phone`/`email` is refused outright
and a contact detail smuggled into a structured field is refused on sight.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_launch_matcher_company
from app.models.investor_criteria import (
    EMIRATES,
    OFF_PLAN_OR_READY,
    PAYMENT_PREFERENCE,
    InvestorCriteria,
)
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/launch-matcher", tags=["Launch Matcher"])

MAX_LABEL = 80
MAX_AREAS = 500
MAX_PROPERTY_TYPE = 40
MAX_TIMELINE = 120


# ── The no-PII guardrail ─────────────────────────────────────
# An email address and a phone number are both mechanically detectable, so
# anything carrying one is refused before it reaches the database.
#
# A personal *name* is not mechanically detectable, and pretending otherwise
# would give false confidence while rejecting legitimate labels. The guarantee
# against names is structural instead, and stronger than a regex: the table has
# no name column, the schemas below forbid unknown fields, and nothing in the
# matching or reply path ever asks for an identity. A label is the advisor's
# own shorthand and never leaves their own account.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 7+ digits allowing spaces/dashes/parens, with or without a country code —
# catches "+971 50 123 4567", "0501234567", "971-50-1234567".
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")


def _reject_contact_details(field_name: str, value: str | None) -> None:
    """Refuse a value carrying an email address or phone number.

    Applied to the structured fields the advisor fills in. Deliberately NOT
    applied to `notes`: that is their own scratch space, and policing it would
    be both unreliable and beside the point. The design simply never asks for
    identity anywhere, and notes are never parsed, matched on, or echoed back
    in a reply.
    """
    if not value:
        return
    if _EMAIL_RE.search(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} looks like it contains an email address. "
                "Investor records are criteria-only — use a label such as "
                "'Investor 4'."
            ),
        )
    if _PHONE_RE.search(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} looks like it contains a phone number. "
                "Investor records are criteria-only — use a label such as "
                "'Investor 4'."
            ),
        )


def _valid(value: str | None, allowed, default: str) -> str:
    return value if value in allowed else default


def _norm_areas(areas: str | None) -> str:
    normalised = ", ".join(a.strip() for a in (areas or "").split(",") if a.strip())
    if len(normalised) > MAX_AREAS:
        raise HTTPException(
            status_code=400,
            detail=f"Area list is too long ({len(normalised)} characters, limit {MAX_AREAS}).",
        )
    return normalised


# ── Schemas ──────────────────────────────────────────────────
# extra="forbid" is load-bearing: it turns a stray `name`/`phone`/`email` key
# into a 422 instead of a silently dropped field, so an attempt to store
# identity fails loudly rather than looking like it worked.

class _NoExtraFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestorCriteriaCreate(_NoExtraFields):
    label: str = Field(max_length=MAX_LABEL)
    emirate: str = "Dubai"
    areas: str = Field(default="", max_length=MAX_AREAS)
    budget_min: float = 0
    budget_max: float = 0
    property_type: str = Field(default="", max_length=MAX_PROPERTY_TYPE)
    off_plan_or_ready: str = "both"
    payment_preference: str = "either"
    timeline: str = Field(default="", max_length=MAX_TIMELINE)
    notes: str | None = None


class InvestorCriteriaUpdate(_NoExtraFields):
    label: str | None = Field(default=None, max_length=MAX_LABEL)
    emirate: str | None = None
    areas: str | None = Field(default=None, max_length=MAX_AREAS)
    budget_min: float | None = None
    budget_max: float | None = None
    property_type: str | None = Field(default=None, max_length=MAX_PROPERTY_TYPE)
    off_plan_or_ready: str | None = None
    payment_preference: str | None = None
    timeline: str | None = Field(default=None, max_length=MAX_TIMELINE)
    notes: str | None = None


class InvestorCriteriaResponse(BaseModel):
    id: int
    company_id: int
    label: str
    emirate: str
    areas: str
    budget_min: float
    budget_max: float
    property_type: str
    off_plan_or_ready: str
    payment_preference: str
    timeline: str
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Reference data ───────────────────────────────────────────

@router.get("/constants")
async def get_constants(
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Dropdown values for the one-time setup screen."""
    return {
        "emirates": list(EMIRATES),
        "off_plan_or_ready": list(OFF_PLAN_OR_READY),
        "payment_preference": list(PAYMENT_PREFERENCE),
    }


# ── Investor criteria ────────────────────────────────────────

@router.get("/investors", response_model=list[InvestorCriteriaResponse])
async def list_investors(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """List this company's investor criteria, grouped by emirate then label."""
    stmt = (
        select(InvestorCriteria)
        .where(InvestorCriteria.company_id == current_user.company_id)
        .order_by(InvestorCriteria.emirate, InvestorCriteria.id)
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/investors", response_model=InvestorCriteriaResponse, status_code=201)
async def create_investor(
    payload: InvestorCriteriaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Create one criteria-only investor record."""
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label cannot be empty")

    _reject_contact_details("Label", label)
    _reject_contact_details("Areas", payload.areas)
    _reject_contact_details("Property type", payload.property_type)
    _reject_contact_details("Timeline", payload.timeline)

    if payload.budget_max and payload.budget_max < payload.budget_min:
        raise HTTPException(status_code=400, detail="budget_max must be >= budget_min")

    record = InvestorCriteria(
        company_id=current_user.company_id,
        label=label,
        emirate=_valid(payload.emirate, EMIRATES, "Dubai"),
        areas=_norm_areas(payload.areas),
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        property_type=(payload.property_type or "").strip(),
        off_plan_or_ready=_valid(payload.off_plan_or_ready, OFF_PLAN_OR_READY, "both"),
        payment_preference=_valid(payload.payment_preference, PAYMENT_PREFERENCE, "either"),
        timeline=(payload.timeline or "").strip(),
        notes=payload.notes,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    # Logged by id and label only — the label is the advisor's own shorthand.
    logger.info(
        "Investor criteria created: id=%s label=%r company=%s",
        record.id, record.label, current_user.company_id,
    )
    return record


@router.patch("/investors/{investor_id}", response_model=InvestorCriteriaResponse)
async def update_investor(
    investor_id: int,
    payload: InvestorCriteriaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Update one investor's criteria."""
    record = await db.get(InvestorCriteria, investor_id)
    if not record or record.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Investor not found")

    data = payload.model_dump(exclude_unset=True)

    if data.get("label") is not None:
        label = data["label"].strip()
        if not label:
            raise HTTPException(status_code=400, detail="Label cannot be empty")
        _reject_contact_details("Label", label)
        record.label = label
    if data.get("areas") is not None:
        _reject_contact_details("Areas", data["areas"])
        record.areas = _norm_areas(data["areas"])
    if data.get("property_type") is not None:
        _reject_contact_details("Property type", data["property_type"])
        record.property_type = data["property_type"].strip()
    if data.get("timeline") is not None:
        _reject_contact_details("Timeline", data["timeline"])
        record.timeline = data["timeline"].strip()
    if data.get("emirate") is not None:
        record.emirate = _valid(data["emirate"], EMIRATES, record.emirate)
    if data.get("off_plan_or_ready") is not None:
        record.off_plan_or_ready = _valid(
            data["off_plan_or_ready"], OFF_PLAN_OR_READY, record.off_plan_or_ready
        )
    if data.get("payment_preference") is not None:
        record.payment_preference = _valid(
            data["payment_preference"], PAYMENT_PREFERENCE, record.payment_preference
        )
    if "notes" in data:
        record.notes = data["notes"]
    if data.get("budget_min") is not None:
        record.budget_min = data["budget_min"]
    if data.get("budget_max") is not None:
        record.budget_max = data["budget_max"]
    if float(record.budget_max or 0) and float(record.budget_max) < float(record.budget_min or 0):
        raise HTTPException(status_code=400, detail="budget_max must be >= budget_min")

    await db.flush()
    await db.refresh(record)
    return record


@router.delete("/investors/{investor_id}")
async def delete_investor(
    investor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Delete an investor criteria record."""
    record = await db.get(InvestorCriteria, investor_id)
    if not record or record.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Investor not found")
    await db.delete(record)
    await db.flush()
    return {"status": "deleted", "id": investor_id}


# ── Dry-run preview ──────────────────────────────────────────

class PreviewRequest(_NoExtraFields):
    text: str


@router.post("/preview")
async def preview_match(
    payload: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Parse and match a launch without sending anything.

    Lets the advisor check their criteria are set up correctly during setup,
    and gives support a way to reproduce a bad match without touching WhatsApp.
    Sends nothing and persists nothing.
    """
    from app.services.launch_matcher.handler import build_reply
    from app.services.launch_matcher.providers import InboundMessage

    message = InboundMessage(sender="preview", text=payload.text)
    reply, outcome = await build_reply(db, current_user.company_id, message)

    return {
        "reply": reply,
        "matched": bool(outcome and outcome.matched),
        "considered": outcome.considered if outcome else 0,
        "parsed": {
            "developer": outcome.launch.developer,
            "project": outcome.launch.project,
            "emirate": outcome.launch.emirate,
            "area": outcome.launch.area,
            "unit_types": outcome.launch.unit_types,
            "price_min": outcome.launch.price_min,
            "price_max": outcome.launch.price_max,
            "payment_plan": outcome.launch.payment_plan,
            "launch_date": outcome.launch.launch_date,
            "completion_status": outcome.launch.completion_status,
        } if outcome else None,
    }
