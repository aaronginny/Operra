"""Authentication API routes."""

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

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


@router.post("/signup")
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new company + admin user account."""
    logger.info("[PhantomPilot] Signup attempt for: %s", payload.email)

    # Check if user exists
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        return {"success": False, "error": "Email already registered"}

    # Create company (set 7-day trial immediately)
    company = Company(
        name=payload.company_name,
        trial_ends_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    db.add(company)
    await db.flush()

    # Create user
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        company_id=company.id,
        role=UserRole.ceo,
        whatsapp_number=_normalize_whatsapp(payload.whatsapp_number),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("[PhantomPilot] Signup OK for: %s  |  company_id=%s", payload.email, company.id)

    # Generate token
    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT token."""
    logger.info("[PhantomPilot] Login attempt for: %s", payload.email)

    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.password_hash:
        logger.warning("[PhantomPilot] Login FAILED for: %s (user not found)", payload.email)
        return {"success": False, "error": "Incorrect email or password"}

    if not verify_password(payload.password, user.password_hash):
        logger.warning("[PhantomPilot] Login FAILED for: %s (bad password)", payload.email)
        return {"success": False, "error": "Incorrect email or password"}

    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    logger.info("[PhantomPilot] Login OK for: %s  |  company_id=%s", payload.email, user.company_id)
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


class ProfileUpdate(BaseModel):
    whatsapp_number: str | None = None
    name: str | None = None


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
    """Update the current user's profile (WhatsApp number, name)."""
    if payload.whatsapp_number is not None:
        current_user.whatsapp_number = _normalize_whatsapp(payload.whatsapp_number)
        logger.info(
            "User %s updated whatsapp_number to %r",
            current_user.email, current_user.whatsapp_number,
        )
    if payload.name:
        current_user.name = payload.name.strip()

    await db.flush()

    return {
        "success": True,
        "whatsapp_number": current_user.whatsapp_number,
        "name": current_user.name,
    }


@router.post("/reset")
async def reset_users(db: AsyncSession = Depends(get_db)):
    """Clear all users and companies so a fresh signup can be done.

    WARNING: destructive — only for dev / early-stage use.
    """
    await db.execute(delete(User))
    await db.execute(delete(Company))
    logger.warning("[PhantomPilot] All users and companies have been deleted via /auth/reset")
    return {"success": True, "message": "All users and companies cleared. You can now sign up again."}