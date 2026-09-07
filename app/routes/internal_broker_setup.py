"""TEMPORARY — one-time broker_intel provisioning and live verification.

Render's free tier has no Shell, so this is the only way to reach the
production database and to exercise production's own content generation.
Same hardening as the provisioning endpoints before it: a shared-secret
header compared with hmac.compare_digest, failing closed as a 404 so a
wrong or missing secret is indistinguishable from the route not existing,
and hidden from the OpenAPI schema.

Four actions, all one-shot:

  diagnose      — is a usable OpenAI key configured here? Boolean only; the
                  key itself is never returned, logged, or echoed. This runs
                  BEFORE any account is created, because content generated
                  by the offline stub must never reach a real client.
  create        — create the broker's company + CEO user + CompanySettings.
  test_reply    — run broker_intel's own inbound handler in production, with
                  production's key, and send the result to a given number.
  test_nudge    — run the registered daily hook for a company, for real.

DELETE once provisioning is done:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
  3. Remove `broker_setup_secret` from app/config.py.
  4. Delete BROKER_SETUP_SECRET from Render.
"""

import hmac
import logging
import secrets
import string

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.company_settings import CompanySettings
from app.models.user import User, UserRole
from app.services.auth_service import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

# Ambiguous characters removed, and alphanumeric only: a password that has to
# survive a copy-paste into a login form should not contain punctuation, and
# the previous provisioning round proved a leading "-" breaks exactly that.
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "lIO01")


def _check_secret(provided: str | None) -> None:
    expected = settings.broker_setup_secret
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=404)


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    email: str | None = None
    name: str | None = None
    company_name: str | None = None
    whatsapp_number: str | None = None
    vertical: str = "broker_intel"
    morning_pulse_time: str = "05:00"
    company_id: int | None = None
    to: str | None = None
    text: str | None = None


@router.post("/broker-setup")
async def broker_setup(
    payload: SetupRequest,
    x_setup_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    _check_secret(x_setup_secret)

    if payload.action == "diagnose":
        from app.services.broker_intel.content import ai_configured, get_generator

        configured = ai_configured()
        return {
            "ai_configured": configured,
            "generator": type(get_generator()).__name__,
            "model": settings.openai_model,
        }

    if payload.action == "create":
        email = (payload.email or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="email required")

        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalars().first()
        if existing:
            company = await db.get(Company, existing.company_id)
            return {
                "status": "exists",
                "note": "no row was modified and no password was reset",
                "user_id": existing.id,
                "company_id": existing.company_id,
                "vertical": company.vertical if company else None,
            }

        company = Company(name=payload.company_name or "Broker", vertical=payload.vertical)
        db.add(company)
        await db.flush()

        password = "".join(secrets.choice(_ALPHABET) for _ in range(20))
        user = User(
            company_id=company.id,
            name=payload.name or "Broker",
            email=email,
            password_hash=get_password_hash(password),
            role=UserRole.ceo,
            whatsapp_number=payload.whatsapp_number,
            is_verified=True,  # no OTP step exists; unverified cannot log in
        )
        db.add(user)

        # The daily nudge fires from the existing per-company morning-pulse
        # window, which the scheduler evaluates in naive server time (UTC on
        # Render). 05:00 there is 09:00 Asia/Dubai, and the UAE has no DST.
        db.add(CompanySettings(
            company_id=company.id,
            morning_pulse_enabled=True,
            morning_pulse_time=payload.morning_pulse_time,
        ))
        await db.flush()

        logger.info("broker_setup created company=%s user=%s", company.id, user.id)
        return {
            "status": "created",
            "company_id": company.id,
            "company_name": company.name,
            "vertical": company.vertical,
            "user_id": user.id,
            "email": email,
            "password": password,  # returned once; caller stores it and never re-requests
            "morning_pulse_time": payload.morning_pulse_time,
        }

    if payload.action == "test_reply":
        from app.services.broker_intel.handler import build_reply
        from app.services.broker_intel.content import get_generator
        from app.services.launch_matcher.providers import get_provider

        reply = await build_reply(
            payload.company_id or 0, payload.to or "", payload.text or ""
        )
        result = await get_provider().send_text(payload.to or "", reply)
        return {
            "generator": type(get_generator()).__name__,
            "sent": bool(result.ok),
            "error": result.error,
            "reply": reply,
        }

    if payload.action == "test_nudge":
        from app.services.broker_intel.handler import send_daily_nudge

        sent = await send_daily_nudge(db, payload.company_id or 0)
        return {"recipients_messaged": sent}

    raise HTTPException(status_code=400, detail=f"unknown action {payload.action!r}")
