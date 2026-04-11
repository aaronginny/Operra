"""Billing routes — Razorpay order creation, payment verification, and status."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.schemas.auth_schema import CurrentUser
from app.services import razorpay_service
from app.services.billing_service import (
    BASIC_PRICE_PAISE,
    PREMIUM_PRICE_PAISE,
    get_billing_status,
    unlock_project_for_company,
    upgrade_to_premium,
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

PREMIUM_DURATION_DAYS = 30  # premium subscription lasts 30 days


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    tier: str               # "basic" or "premium"
    project_name: str | None = None  # required when tier == "basic"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int             # paise
    currency: str
    razorpay_key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    tier: str               # "basic" or "premium"
    project_name: str | None = None  # required when tier == "basic"


class VerifyPaymentResponse(BaseModel):
    success: bool
    tier: str
    project_id: int | None = None
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    payload: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a Razorpay payment order.

    - ``tier="basic"``   — ₹2,000, requires ``project_name``
    - ``tier="premium"`` — ₹5,000/month
    """
    if not settings.razorpay_key_id:
        raise HTTPException(status_code=503, detail="Payment gateway not configured.")

    tier = payload.tier.lower()
    if tier not in ("basic", "premium"):
        raise HTTPException(status_code=400, detail="tier must be 'basic' or 'premium'.")

    if tier == "basic" and not (payload.project_name or "").strip():
        raise HTTPException(status_code=400, detail="project_name is required for the Basic plan.")

    amount = BASIC_PRICE_PAISE if tier == "basic" else PREMIUM_PRICE_PAISE
    receipt = f"co{current_user.company_id}_{tier}"

    notes = {
        "company_id": str(current_user.company_id),
        "user_id": str(current_user.id),
        "tier": tier,
    }
    if tier == "basic" and payload.project_name:
        notes["project_name"] = payload.project_name.strip()[:100]

    try:
        order = razorpay_service.create_order(amount, receipt, notes)
    except RuntimeError as exc:
        logger.error("Razorpay create_order failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return CreateOrderResponse(
        order_id=order["id"],
        amount=amount,
        currency="INR",
        razorpay_key_id=settings.razorpay_key_id,
    )


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    payload: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Verify a completed Razorpay payment and upgrade the company tier.

    On success for ``tier="basic"``:
      - Creates a Project row for the given project_name.
      - Adds the project_id to company.projects_paid.
      - Returns ``project_id`` for the frontend to use.

    On success for ``tier="premium"``:
      - Sets company.subscription_level = "premium" with a 30-day expiry.
    """
    tier = payload.tier.lower()
    if tier not in ("basic", "premium"):
        raise HTTPException(status_code=400, detail="tier must be 'basic' or 'premium'.")

    # Verify signature
    try:
        valid = razorpay_service.verify_payment_signature(
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            payload.razorpay_signature,
        )
    except RuntimeError as exc:
        logger.error("Razorpay verification error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    if not valid:
        logger.warning(
            "Invalid Razorpay signature from user_id=%s company=%s",
            current_user.id, current_user.company_id,
        )
        raise HTTPException(status_code=400, detail="Payment verification failed. Signature mismatch.")

    project_id: int | None = None

    if tier == "basic":
        project_name = (payload.project_name or "").strip()
        if not project_name:
            raise HTTPException(status_code=400, detail="project_name is required for the Basic plan.")

        # Create the project row
        project = Project(
            company_id=current_user.company_id,
            name=project_name,
        )
        db.add(project)
        await db.flush()  # get project.id
        project_id = project.id

        # Unlock the project for this company
        await unlock_project_for_company(db, current_user.company_id, project_id)
        await db.commit()

        logger.info(
            "Basic payment verified: company=%s project_id=%s name=%r payment=%s",
            current_user.company_id, project_id, project_name, payload.razorpay_payment_id,
        )
        return VerifyPaymentResponse(
            success=True,
            tier="basic",
            project_id=project_id,
            message=f"Project '{project_name}' unlocked! Unlimited tasks enabled.",
        )

    else:  # premium
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=PREMIUM_DURATION_DAYS)
        await upgrade_to_premium(db, current_user.company_id, expires_at=expires_at)
        await db.commit()

        logger.info(
            "Premium payment verified: company=%s expires=%s payment=%s",
            current_user.company_id, expires_at.isoformat(), payload.razorpay_payment_id,
        )
        return VerifyPaymentResponse(
            success=True,
            tier="premium",
            project_id=None,
            message=f"Premium activated! Expires {expires_at.strftime('%b %d, %Y')}.",
        )


@router.get("/status")
async def billing_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the current company's billing/plan status.

    Mirrors GET /tasks/billing-status for use by billing-specific UI.
    """
    return await get_billing_status(
        db,
        current_user.company_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_role=current_user.role,
    )
