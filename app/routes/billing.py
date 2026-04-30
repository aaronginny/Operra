"""Billing routes for PhantomPilot.

Endpoints
---------
GET  /billing/status         — current plan/tier for the dashboard
POST /billing/create-order   — create a Cashfree payment order
POST /billing/webhook        — Cashfree webhook (called after payment)
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.company import Company
from app.schemas.auth_schema import CurrentUser
from app.services.billing_service import get_billing_status, upgrade_to_premium, unlock_project_for_company
from app.services.payment_service import create_payment_order, verify_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


# ── GET /billing/status ───────────────────────────────────────────────────────

@router.get("/status")
async def billing_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the current company's billing / plan status."""
    return await get_billing_status(
        db,
        current_user.company_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_role=current_user.role,
    )


# ── POST /billing/create-order ────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    plan: str  # "basic" or "premium"


@router.post("/create-order")
async def create_order(
    body: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a Cashfree payment order for the given plan.

    Returns {"payment_url": "...", "order_id": "..."}
    The client should redirect to payment_url to complete checkout.
    """
    plan = body.plan.lower()
    if plan not in ("basic", "premium"):
        raise HTTPException(status_code=400, detail="plan must be 'basic' or 'premium'")

    try:
        result = await create_payment_order(
            company_id=current_user.company_id,
            plan=plan,
            customer_email=current_user.email,
            customer_name=current_user.email.split("@")[0],
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Cashfree create-order failed: %s", exc)
        raise HTTPException(status_code=502, detail="Payment gateway error. Please try again.")

    # Persist the pending order ID on the company row
    company = await db.get(Company, current_user.company_id)
    if company:
        company.cashfree_order_id = result["order_id"]
        company.payment_status = "pending"
        await db.commit()

    logger.info(
        "Payment order created: company=%s plan=%s order_id=%s",
        current_user.company_id, plan, result["order_id"],
    )

    return {
        "payment_url": result["payment_url"],
        "order_id": result["order_id"],
        "amount": result["amount"],
        "plan": plan,
    }


# ── POST /billing/webhook ─────────────────────────────────────────────────────

@router.post("/webhook")
async def cashfree_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Cashfree webhook — called by Cashfree when a payment is completed.

    Verifies the HMAC-SHA256 signature, then upgrades the company plan.
    Cashfree sends the signature in the x-webhook-signature header.
    """
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    # ── Signature verification ────────────────────────────────
    secret = settings.cashfree_secret_key or ""
    received_sig = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")

    # Production must have CASHFREE_SECRET_KEY set; signature verification is
    # mandatory there. Without it, an attacker can forge a "PAID" webhook.
    is_prod = (settings.app_env or "development").lower() == "production"
    if not secret or not received_sig:
        if is_prod:
            logger.error("Cashfree webhook: rejected — signature/secret missing in production")
            raise HTTPException(status_code=400, detail="Webhook signature required")
        logger.warning("Cashfree webhook: signature verification skipped (dev/sandbox)")
    else:
        message = timestamp + body_text
        expected = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, received_sig):
            logger.warning("Cashfree webhook: invalid signature")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # ── Parse payload ─────────────────────────────────────────
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Cashfree 2023-08-01 webhook schema
    order_data = payload.get("data", {}).get("order", {})
    order_id = order_data.get("order_id") or payload.get("order_id")
    order_status = order_data.get("order_status") or payload.get("order_status")

    logger.info("Cashfree webhook received: order_id=%s status=%s", order_id, order_status)

    if not order_id:
        return {"status": "ignored", "reason": "no order_id"}

    if order_status != "PAID":
        return {"status": "ignored", "reason": f"order_status={order_status}"}

    # ── Upgrade plan ──────────────────────────────────────────
    # Find the company by cashfree_order_id
    from sqlalchemy import select
    stmt = select(Company).where(Company.cashfree_order_id == order_id)
    result = await db.execute(stmt)
    company = result.scalars().first()

    if not company:
        # Fallback: verify directly with Cashfree and match by inferred company_id
        logger.warning("Cashfree webhook: no company found for order_id=%s, verifying with API", order_id)
        try:
            verification = await verify_payment(order_id)
            logger.info("Cashfree verification result: %s", verification)
        except Exception as exc:
            logger.error("Cashfree verification failed: %s", exc)
        return {"status": "ignored", "reason": "company not found"}

    # ── Idempotency guard ─────────────────────────────────────
    # If the same order_id is replayed (Cashfree retries on timeout, attacker
    # replays, etc.) and we've already marked it paid, exit cleanly without
    # re-running the upgrade. The (cashfree_order_id, payment_status) pair is
    # the natural dedup key — same order can't move from "paid" back to unpaid.
    if company.payment_status == "paid":
        logger.info(
            "Cashfree webhook: order_id=%s already processed for company #%s, skipping",
            order_id, company.id,
        )
        return {"status": "ok", "reason": "already_processed", "company_id": company.id}

    # Infer plan from order_id (PP-BAS-... or PP-PRE-...)
    plan = "premium"
    if "-BAS-" in order_id:
        plan = "basic"
    elif "-PRE-" in order_id:
        plan = "premium"

    if plan == "premium":
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=30)
        await upgrade_to_premium(db, company.id, expires_at=expires_at)
        company.payment_status = "paid"
        logger.info("Company #%s upgraded to PREMIUM via Cashfree webhook", company.id)
    else:
        # Basic: unlock first project (user can specify later; for now mark paid)
        company.subscription_level = "basic"
        company.payment_status = "paid"
        logger.info("Company #%s upgraded to BASIC via Cashfree webhook", company.id)

    await db.commit()
    return {"status": "ok", "plan": plan, "company_id": company.id}
