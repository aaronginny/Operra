"""OTP generation, email delivery, and verification for PhantomPilot signup."""

import logging
import os
import random
import string
from datetime import datetime, timedelta, timezone

import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """Return a random 6-digit OTP string."""
    return "".join(random.choices(string.digits, k=6))


def send_otp_email(email: str, otp: str) -> bool:
    """Send verification OTP via Resend API.

    Returns True on success, False on failure (never raises — callers
    check the return value and decide whether to surface an error).
    """
    resend.api_key = os.getenv("RESEND_API_KEY")

    if not resend.api_key:
        logger.error("=== RESEND NOT CONFIGURED === RESEND_API_KEY env var is missing")
        return False

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;margin:0;padding:48px 20px">
  <div style="max-width:460px;margin:0 auto;background:#0d0d14;border:1px solid #1a1a2e;border-radius:14px;padding:44px 40px;text-align:center">
    <h1 style="font-family:Georgia,'Times New Roman',serif;color:#ffffff;font-size:1.5rem;font-weight:400;letter-spacing:-.02em;margin:0 0 4px">PhantomPilot</h1>
    <p style="color:#4a4a6a;font-size:.78rem;text-transform:uppercase;letter-spacing:.12em;margin:0 0 36px">Smart Task Management</p>
    <p style="color:#8888aa;font-size:.9rem;margin:0 0 20px">Your verification code</p>
    <div style="background:#13131e;border:1px solid #222236;border-radius:10px;padding:28px 16px;margin:0 0 28px">
      <span style="font-size:3rem;font-weight:700;color:#ffffff;letter-spacing:16px;font-variant-numeric:tabular-nums;font-family:'Courier New',monospace">{otp}</span>
    </div>
    <p style="color:#5a5a7a;font-size:.82rem;margin:0 0 8px">
      This code expires in <strong style="color:#8888aa">10 minutes</strong>.
    </p>
    <p style="color:#4a4a6a;font-size:.78rem;margin:0 0 32px">
      Do not share this code with anyone.
    </p>
    <hr style="border:none;border-top:1px solid #1a1a2e;margin:0 0 24px">
    <p style="color:#333348;font-size:.72rem;margin:0">
      If you didn't create a PhantomPilot account, you can safely ignore this email.
    </p>
  </div>
</body>
</html>"""

    try:
        resend.Emails.send({
            "from": "PhantomPilot <noreply@phantompilot.xyz>",
            "to": email,
            "subject": "Your PhantomPilot verification code",
            "html": html_body,
        })
        logger.info("=== RESEND SENT OK === to %s", email)
        return True
    except Exception as exc:
        logger.error("=== RESEND FAILED === %s", exc)
        return False


async def verify_otp(db: AsyncSession, email: str, otp: str):
    """Check OTP code + expiry for the given email.

    Returns the User object on success, None on failure.
    On success, sets is_verified=True and clears OTP fields.
    """
    from app.models.user import User  # local import to avoid circular deps

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        logger.warning("[OTP] verify_otp: no user found for %s", email)
        return None

    if not user.otp_code or not user.otp_expires_at:
        logger.warning("[OTP] verify_otp: no OTP stored for %s", email)
        return None

    now = datetime.now(timezone.utc)
    expires = user.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        logger.warning("[OTP] verify_otp: OTP expired for %s", email)
        return None

    if user.otp_code != otp:
        logger.warning("[OTP] verify_otp: wrong code for %s", email)
        return None

    # Mark verified and clear OTP fields
    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    await db.flush()

    logger.info("[OTP] Email verified for %s", email)
    return user
