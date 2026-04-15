"""Cashfree payment gateway integration for PhantomPilot.

Covers two operations:
  create_payment_order — creates a Cashfree order and returns the payment_url
  verify_payment       — fetches order status from Cashfree and returns it

Plans
-----
  basic   — ₹2,000 per project (one-time)
  premium — ₹5,000 per month

Environment variables required (set in Render):
  CASHFREE_APP_ID     — Cashfree App ID
  CASHFREE_SECRET_KEY — Cashfree Secret Key
  CASHFREE_ENV        — "sandbox" or "production"
"""

import logging
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PLAN_AMOUNTS = {
    "basic": 2000.00,
    "premium": 5000.00,
}


def _headers() -> dict:
    return {
        "x-client-id": settings.cashfree_app_id or "",
        "x-client-secret": settings.cashfree_secret_key or "",
        "x-api-version": "2023-08-01",
        "Content-Type": "application/json",
    }


async def create_payment_order(
    company_id: int,
    plan: str,
    customer_email: str,
    customer_name: str = "PhantomPilot User",
    customer_phone: str = "9999999999",
) -> dict:
    """Create a Cashfree payment order and return the payment session URL.

    Returns a dict with keys:
      payment_url  — redirect the user here to complete payment
      order_id     — Cashfree order ID (store on the company row)
      amount       — amount charged

    Raises ValueError if plan is unknown or Cashfree is not configured.
    Raises httpx.HTTPStatusError on API errors.
    """
    if not settings.cashfree_app_id or not settings.cashfree_secret_key:
        raise ValueError(
            "Cashfree is not configured. "
            "Set CASHFREE_APP_ID and CASHFREE_SECRET_KEY environment variables."
        )

    plan = plan.lower()
    if plan not in PLAN_AMOUNTS:
        raise ValueError(f"Unknown plan '{plan}'. Must be 'basic' or 'premium'.")

    amount = PLAN_AMOUNTS[plan]
    order_id = f"PP-{plan[:3].upper()}-{company_id}-{uuid.uuid4().hex[:8].upper()}"

    payload = {
        "order_id": order_id,
        "order_amount": amount,
        "order_currency": "INR",
        "order_note": f"PhantomPilot {plan.capitalize()} plan — company {company_id}",
        "customer_details": {
            "customer_id": f"company_{company_id}",
            "customer_email": customer_email,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
        },
        "order_meta": {
            "return_url": (
                "https://operra-bo0x.onrender.com/static/dashboard/index.html"
                "?payment=success&order_id={order_id}"
            ),
            "notify_url": "https://operra-bo0x.onrender.com/billing/webhook",
        },
    }

    url = f"{settings.cashfree_base_url}/orders"
    logger.info("Creating Cashfree order: order_id=%s plan=%s amount=%.2f", order_id, plan, amount)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    payment_url = data.get("payment_link") or data.get("payment_session_id")
    if not payment_url:
        # Build the hosted checkout URL from the payment_session_id if present
        session_id = data.get("payment_session_id", "")
        if session_id:
            if settings.cashfree_env == "production":
                payment_url = f"https://payments.cashfree.com/order/#token={session_id}"
            else:
                payment_url = f"https://payments-test.cashfree.com/order/#token={session_id}"

    logger.info("Cashfree order created: order_id=%s payment_url=%s", order_id, payment_url)

    return {
        "order_id": order_id,
        "payment_url": payment_url,
        "amount": amount,
        "plan": plan,
    }


async def verify_payment(order_id: str) -> dict:
    """Fetch order status from Cashfree.

    Returns a dict with keys:
      order_id      — the order ID queried
      order_status  — "PAID", "ACTIVE", "EXPIRED", etc.
      order_amount  — amount from Cashfree
      plan          — inferred plan from order_id prefix (e.g. "basic"/"premium")

    Raises ValueError if Cashfree is not configured.
    Raises httpx.HTTPStatusError on API errors.
    """
    if not settings.cashfree_app_id or not settings.cashfree_secret_key:
        raise ValueError("Cashfree is not configured.")

    url = f"{settings.cashfree_base_url}/orders/{order_id}"
    logger.info("Verifying Cashfree order: order_id=%s", order_id)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    # Infer plan from order_id prefix (PP-BAS-... or PP-PRE-...)
    plan = "unknown"
    if "-BAS-" in order_id:
        plan = "basic"
    elif "-PRE-" in order_id:
        plan = "premium"

    return {
        "order_id": order_id,
        "order_status": data.get("order_status", "UNKNOWN"),
        "order_amount": data.get("order_amount"),
        "plan": plan,
        "raw": data,
    }
