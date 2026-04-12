"""OTP generation, email delivery, and verification for PhantomPilot signup."""

import logging
import random
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """Return a random 6-digit OTP string."""
    return "".join(random.choices(string.digits, k=6))


def send_otp_email(email: str, otp: str) -> None:
    """Send verification OTP via Gmail SMTP.

    Raises RuntimeError if credentials are not configured.
    Raises smtplib.SMTPException on delivery failure.
    """
    gmail_user = settings.gmail_user
    gmail_password = settings.gmail_app_password

    if not gmail_user or not gmail_password:
        raise RuntimeError("Gmail credentials not configured (GMAIL_USER / GMAIL_APP_PASSWORD)")

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',system-ui,sans-serif;background:#0a0f1a;margin:0;padding:40px 20px">
  <div style="max-width:480px;margin:0 auto;background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:40px;text-align:center">
    <h1 style="color:#ffffff;font-size:1.4rem;font-weight:700;margin:0 0 6px">PhantomPilot</h1>
    <p style="color:#64748b;font-size:.85rem;margin:0 0 32px">Smart Task Management</p>
    <p style="color:#94a3b8;font-size:.95rem;margin:0 0 20px">Your verification code:</p>
    <div style="background:#1e293b;border-radius:10px;padding:24px 16px;margin:0 0 24px">
      <span style="font-size:2.8rem;font-weight:700;color:#ffffff;letter-spacing:14px;font-variant-numeric:tabular-nums">{otp}</span>
    </div>
    <p style="color:#64748b;font-size:.82rem;margin:0 0 8px">
      This code expires in <strong style="color:#94a3b8">10 minutes</strong>.
    </p>
    <p style="color:#475569;font-size:.78rem;margin:0">
      If you didn't sign up for PhantomPilot, you can safely ignore this email.
    </p>
    <hr style="border:none;border-top:1px solid #1e293b;margin:28px 0">
    <p style="color:#334155;font-size:.72rem;margin:0">PhantomPilot &mdash; Smart Task Management</p>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your PhantomPilot verification code"
    msg["From"] = gmail_user
    msg["To"] = email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, email, msg.as_string())

    logger.info("[OTP] Verification email sent to %s", email)


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
