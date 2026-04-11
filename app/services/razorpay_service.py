"""Razorpay integration service.

Handles order creation and payment signature verification.
Uses the official razorpay Python SDK.

Environment variables required (set on Render):
    RAZORPAY_KEY_ID      — Razorpay API key ID (e.g. rzp_live_...)
    RAZORPAY_KEY_SECRET  — Razorpay API key secret
"""

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def _get_client():
    """Return an authenticated Razorpay client.

    Import is deferred so the app can start even when the package isn't
    installed yet (Render will install it on next deploy).
    """
    try:
        import razorpay  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "razorpay package not installed. Add 'razorpay>=1.3.0' to requirements.txt."
        ) from exc

    from app.config import settings
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set as environment variables."
        )

    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


def create_order(amount_paise: int, receipt: str, notes: dict | None = None) -> dict:
    """Create a Razorpay order and return the order object.

    Parameters
    ----------
    amount_paise : int
        Amount in smallest currency unit (paise for INR).
        ₹2,000 = 200_000 paise.
    receipt : str
        A unique receipt identifier (e.g. "company_5_basic").
    notes : dict, optional
        Arbitrary key-value pairs attached to the order.

    Returns
    -------
    dict with at least ``id``, ``amount``, ``currency``, ``status`` keys.
    """
    client = _get_client()
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt[:40],  # Razorpay max 40 chars
        "notes": notes or {},
    }
    order = client.order.create(data=payload)
    logger.info("Razorpay order created: id=%s amount=%s receipt=%s", order["id"], amount_paise, receipt)
    return order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Verify that a payment signature from the Razorpay checkout is authentic.

    Razorpay signs ``<order_id>|<payment_id>`` with HMAC-SHA256 using the
    key secret.  Returns True on success, False if the signature is invalid.
    """
    from app.config import settings
    if not settings.razorpay_key_secret:
        raise RuntimeError("RAZORPAY_KEY_SECRET not configured.")

    body = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    valid = hmac.compare_digest(expected, razorpay_signature)
    if not valid:
        logger.warning(
            "Razorpay signature mismatch: order=%s payment=%s",
            razorpay_order_id, razorpay_payment_id,
        )
    return valid
