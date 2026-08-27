"""Launch Matcher setup routes — investor criteria CRUD.

Gated on `require_launch_matcher_company`, which 404s for every other tenant,
so the feature is invisible rather than merely locked — the same fail-safe
pattern the real-estate vertical uses. The two verticals are mutually
exclusive, so a broker-CRM company cannot reach these routes either.

These exist for one-time setup. The daily flow is entirely WhatsApp; the
advisor never needs to open a screen to match a launch.

PII POLICY (narrowed, client request): this table originally shipped with a
hard "no name/phone/email anywhere" rule, enforced by a regex check on
label/areas/property_type/timeline. That rule was fully lifted once (client
request), then deliberately narrowed back: the client wants real names
specifically, not phone numbers or emails scattered across every free-text
field. So:

  * `name` — the one field this was actually for. No pattern rejection here;
    typing a real name is the entire point of the field.
  * `label`, `areas`, `property_type`, `timeline` — phone/email patterns are
    rejected again, exactly as before this feature's PII policy was ever
    touched. See `_reject_contact_details` below.
  * `notes` was never restricted either way, in any version of this policy —
    it's the advisor's own scratch space; policing it would be unreliable and
    beside the point.

See app/models/investor_criteria.py for the full history of this field's
policy — it has now changed twice, and that file tracks why.

`extra="forbid"` is unrelated to any of this and unaffected: it is ordinary
API hygiene (an unrecognised key is a 422, not a silently-dropped field), and
still applies to anything that isn't an explicitly supported field — `phone`
and `email` included, since neither is a supported field name.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_launch_matcher_company
from app.models.contact_lookup import ContactLookup
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
MAX_NAME = 120
MAX_AREAS = 500
MAX_PROPERTY_TYPE = 40
MAX_TIMELINE = 120


# ── Contact-detail guardrail — restored, deliberately NOT applied to `name` ──
# Reinstated after a brief period (this feature's git history) where it was
# removed everywhere. The client's actual request was "let me store a real
# name", not "stop validating every field" — so this is scoped back down to
# exactly the fields it originally covered, and `name` is the one deliberate
# exception: rejecting phone/email patterns THERE would defeat the field's
# entire purpose.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 7+ digits allowing spaces/dashes/parens, with or without a country code —
# catches "+971 50 123 4567", "0501234567", "971-50-1234567".
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")


def _reject_contact_details(field_name: str, value: str | None) -> None:
    """Refuse a value carrying an email address or phone number.

    Applied to label/areas/property_type/timeline. Deliberately NOT applied to
    `name` (that field exists specifically to hold a real name) or `notes`
    (the advisor's own scratch space, never policed in any version of this
    policy).
    """
    if not value:
        return
    if _EMAIL_RE.search(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} looks like it contains an email address. "
                "That's not allowed here — use the Name field for a real name."
            ),
        )
    if _PHONE_RE.search(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} looks like it contains a phone number. "
                "That's not allowed here — use the Name field for a real name."
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
# extra="forbid" is load-bearing: it turns a stray `phone`/`email` key (neither
# is a supported field) into a 422 instead of a silently dropped field, so an
# attempt to store one fails loudly rather than looking like it worked. `name`
# IS a supported field below — see the guardrail above for what's still
# rejected in the other free-text fields.

class _NoExtraFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestorCriteriaCreate(_NoExtraFields):
    label: str = Field(max_length=MAX_LABEL)
    name: str | None = Field(default=None, max_length=MAX_NAME)
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
    name: str | None = Field(default=None, max_length=MAX_NAME)
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
    name: str | None = None
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


# ── Contact lookup — setup-screen autocomplete ──────────────────
# contact_lookup is a separate table from investor_criteria (see that
# model's docstring) purely to let Mahmoud search his own contact list while
# adding an investor. This endpoint only ever reads it for that search; it is
# never written by anything in this file (only by the bulk-import script) and
# never read by matching or the WhatsApp reply — see test_contact_lookup.py.

class ContactLookupSuggestion(BaseModel):
    id: int
    name: str
    phone: str
    emirate: str | None = None
    area: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/contact-lookup", response_model=list[ContactLookupSuggestion])
async def search_contact_lookup(
    q: str = Query(min_length=1, max_length=120),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Search this company's imported contacts by name-prefix or phone match,
    for the "add investor" modal's lookup field. Selecting a result only
    pre-fills the form client-side — this endpoint never creates or touches
    an investor_criteria row."""
    q = q.strip()
    stmt = (
        select(ContactLookup)
        .where(
            ContactLookup.company_id == current_user.company_id,
            or_(ContactLookup.name.ilike(f"{q}%"), ContactLookup.phone.like(f"%{q}%")),
        )
        .order_by(ContactLookup.name)
        .limit(8)
    )
    return (await db.execute(stmt)).scalars().all()


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
    """Create one investor record."""
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label cannot be empty")

    # `name` is deliberately exempt — see the guardrail's own docstring.
    _reject_contact_details("Label", label)
    _reject_contact_details("Areas", payload.areas)
    _reject_contact_details("Property type", payload.property_type)
    _reject_contact_details("Timeline", payload.timeline)

    if payload.budget_max and payload.budget_max < payload.budget_min:
        raise HTTPException(status_code=400, detail="budget_max must be >= budget_min")

    name = payload.name.strip() if payload.name else None

    record = InvestorCriteria(
        company_id=current_user.company_id,
        label=label,
        name=name or None,
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
    # Logged by id and label only, deliberately never `name` — application
    # logs often have broader retention and access than the database itself,
    # so keeping the name out of them is worth doing even though the table
    # may now hold one.
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
    if "name" in data:
        # Presence-checked, not None-checked, like notes below: an explicit
        # {"name": null} clears a previously-stored name back to unset. No
        # guardrail call here — name is the deliberate exemption.
        record.name = (data["name"] or "").strip() or None
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
