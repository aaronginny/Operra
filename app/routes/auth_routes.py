"""Authentication API routes."""

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


# ── Change password ───────────────────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 8


class ChangePasswordRequest(BaseModel):
    """extra="forbid" is deliberate: a stray `email`/`user_id` key must be a
    422, not a silently ignored field that leaves the caller believing they
    changed someone else's password."""

    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the authenticated user's own password.

    Until now there was no in-app way to do this — signup only creates, and
    PATCH /auth/profile covers name and WhatsApp number only — so every
    rotation needed a temporary secret-gated endpoint deployed and removed
    again. This is the permanent replacement.

    The account is taken from the JWT and is never a parameter, so this
    cannot be aimed at another user. Requiring the current password means a
    borrowed or stolen token alone is not enough to lock the owner out of
    their own account.
    """
    if not current_user.password_hash or not verify_password(
        payload.current_password, current_user.password_hash
    ):
        # Deliberately vague, and the same shape the login route uses: this
        # must not become an oracle for whether a given account has a
        # password set.
        raise HTTPException(status_code=403, detail="Current password is incorrect")

    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=400, detail="New password must be different from the current one"
        )

    current_user.password_hash = get_password_hash(payload.new_password)
    await db.flush()

    # Never log the password itself — only that a rotation happened.
    logger.info(
        "Password changed for user_id=%s company_id=%s",
        current_user.id, current_user.company_id,
    )
    return {"success": True, "message": "Password updated."}
