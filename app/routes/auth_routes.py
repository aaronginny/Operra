"""Authentication API routes."""

import hmac
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.auth_schema import UserCreate, UserLogin, Token
from app.services.auth_service import get_password_hash, verify_password, create_access_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _normalize_whatsapp(number: str | None) -> str | None:
    """Normalize WhatsApp number to E.164: strip spaces/dashes, ensure leading +."""
    if not number:
        return None
    cleaned = re.sub(r"[\s\-()]", "", number.strip())
    if cleaned and not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return cleaned or None


def _normalize_email(email: str | None) -> str | None:
    """Canonicalize an email for both storage and lookup: strip + lowercase.

    Email equality in Postgres is case-sensitive, so a login typed with
    different casing than signup (e.g. mobile auto-capitalization) would miss
    the row. Storing *and* querying one canonical lowercased form is what makes
    lookups case-insensitive — it must be applied on every read and every write
    or the two halves won't agree.
    """
    if email is None:
        return None
    return email.strip().lower() or None


def _is_founder(email: str) -> bool:
    """Return True if this email is the configured founder."""
    founder = settings.founder_email
    return bool(founder and email.lower() == founder.lower())


@router.post("/signup")
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new company + admin user account and issue a JWT immediately."""
    email = _normalize_email(payload.email)
    logger.info("[PhantomPilot] Signup attempt for: %s", email)

    # Check if user exists (case-insensitive: emails are stored lowercased)
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    existing_user = result.scalars().first()
    if existing_user:
        return {"success": False, "error": "Email already registered. Please log in instead."}

    # Create company (set 7-day trial immediately)
    company = Company(
        name=payload.company_name,
        trial_ends_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    db.add(company)
    await db.flush()

    # Create user — verified immediately, no OTP step
    user = User(
        name=payload.name,
        email=email,
        password_hash=get_password_hash(payload.password),
        company_id=company.id,
        role=UserRole.ceo,
        whatsapp_number=_normalize_whatsapp(payload.whatsapp_number),
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("[PhantomPilot] Signup OK for: %s  |  company_id=%s", email, company.id)

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "company_id": user.company_id,
        "role": user.role.value,
        "name": user.name,
    })
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate on email + password and return a JWT token."""
    email = _normalize_email(payload.email)
    logger.info("[PhantomPilot] Login attempt for: %s", email)

    # Match case-insensitively: emails are stored lowercased, so the lookup
    # value must be lowercased too or a differently-cased login misses the row.
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.password_hash:
        logger.warning("[PhantomPilot] Login FAILED for: %s (user not found)", email)
        return {"success": False, "error": "Incorrect email or password"}

    if not verify_password(payload.password, user.password_hash):
        logger.warning("[PhantomPilot] Login FAILED for: %s (bad password)", email)
        return {"success": False, "error": "Incorrect email or password"}

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "company_id": user.company_id,
        "role": user.role.value,
        "name": user.name,
    })
    logger.info("[PhantomPilot] Login OK for: %s  |  company_id=%s", payload.email, user.company_id)
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


# ── Profile endpoints ─────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    whatsapp_number: str | None = None
    name: str | None = None
    username: str | None = None


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """Return the current authenticated user's profile."""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "company_id": current_user.company_id,
        "role": current_user.role.value,
        "whatsapp_number": current_user.whatsapp_number,
    }


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's profile (WhatsApp number, name/username)."""
    if payload.whatsapp_number is not None:
        current_user.whatsapp_number = _normalize_whatsapp(payload.whatsapp_number)
        logger.info(
            "User %s updated whatsapp_number to %r",
            current_user.email, current_user.whatsapp_number,
        )
    # username is an alias for name — both update the same field
    new_name = (payload.username or payload.name or "").strip()
    if new_name:
        current_user.name = new_name
        logger.info("User %s updated name to %r", current_user.email, new_name)

    await db.flush()

    # Issue a fresh token so the new name is reflected immediately
    new_token = create_access_token({
        "sub": current_user.email,
        "user_id": current_user.id,
        "company_id": current_user.company_id,
        "role": current_user.role.value,
        "name": current_user.name,
    })

    return {
        "success": True,
        "whatsapp_number": current_user.whatsapp_number,
        "name": current_user.name,
        "access_token": new_token,
    }


class ResetRequest(BaseModel):
    confirm: str


@router.post("/reset")
async def reset_users(
    payload: ResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear all users and companies. Founder-only; requires env-configured token.

    Returns 404 unless ADMIN_RESET_TOKEN is set, so the route is invisible
    in production. Requires the caller to be the configured founder *and*
    pass the matching token in the request body.
    """
    import os
    expected = os.getenv("ADMIN_RESET_TOKEN")
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not _is_founder(current_user.email or ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not hmac.compare_digest(payload.confirm, expected):
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.execute(delete(User))
    await db.execute(delete(Company))
    logger.warning("[PhantomPilot] /auth/reset invoked by founder %s — all users/companies deleted", current_user.email)
    return {"success": True, "message": "All users and companies cleared."}
