"""Authentication API routes."""

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
from app.services.otp_service import generate_otp, send_otp_email, verify_otp as _verify_otp

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


def _is_founder(email: str) -> bool:
    """Return True if this email is the configured founder — always bypasses OTP."""
    founder = settings.founder_email
    return bool(founder and email.lower() == founder.lower())


@router.post("/signup")
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new company + admin user account, then send OTP for verification."""
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

    # Founder always starts verified; everyone else needs OTP
    founder_bypass = _is_founder(payload.email)

    # Create user
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        company_id=company.id,
        role=UserRole.ceo,
        whatsapp_number=_normalize_whatsapp(payload.whatsapp_number),
        is_verified=founder_bypass,  # founder skips verification
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("[PhantomPilot] Signup OK for: %s  |  company_id=%s", payload.email, company.id)

    if founder_bypass:
        # Founder bypasses OTP — issue token immediately
        token = create_access_token({
            "sub": user.email,
            "user_id": user.id,
            "company_id": user.company_id,
            "role": user.role.value,
        })
        return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}

    # Generate and store OTP
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.flush()

    # Send OTP email
    try:
        send_otp_email(user.email, otp)
    except Exception as exc:
        logger.error("[OTP] Failed to send email to %s: %s", user.email, exc)
        # Don't block signup — user can resend via /auth/send-otp
        return {"success": True, "needs_otp": True, "email": user.email, "warning": "OTP email failed — use Resend."}

    return {"success": True, "needs_otp": True, "email": user.email}


@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT token (or prompt OTP if unverified)."""
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

    # Founder always bypasses verification
    if not user.is_verified and not _is_founder(user.email):
        logger.info("[PhantomPilot] Login blocked — unverified: %s", payload.email)
        # Auto-send a fresh OTP so the user can verify
        otp = generate_otp()
        user.otp_code = otp
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        await db.flush()
        try:
            send_otp_email(user.email, otp)
        except Exception as exc:
            logger.error("[OTP] Failed to send email to %s: %s", user.email, exc)
        return {"success": True, "needs_otp": True, "email": user.email}

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "company_id": user.company_id,
        "role": user.role.value,
    })
    logger.info("[PhantomPilot] Login OK for: %s  |  company_id=%s", payload.email, user.company_id)
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


# ── OTP endpoints ─────────────────────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    email: str


@router.post("/send-otp")
async def send_otp(payload: SendOtpRequest, db: AsyncSession = Depends(get_db)):
    """Generate a fresh OTP and email it to the user."""
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        # Don't reveal whether the email exists
        return {"message": "OTP sent"}

    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.flush()

    try:
        send_otp_email(user.email, otp)
    except Exception as exc:
        logger.error("[OTP] send-otp failed for %s: %s", user.email, exc)
        raise HTTPException(status_code=500, detail="Failed to send OTP email — check server Gmail credentials")

    logger.info("[OTP] Fresh OTP sent to %s", user.email)
    return {"message": "OTP sent"}


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    """Verify the OTP, mark the user as verified, and return an access token."""
    user = await _verify_otp(db, payload.email, payload.otp)
    if not user:
        return {"success": False, "error": "Invalid or expired code"}

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "company_id": user.company_id,
        "role": user.role.value,
    })
    logger.info("[PhantomPilot] OTP verified — issuing token for %s", user.email)
    return {
        "success": True,
        "message": "verified",
        "access_token": token,
        "token_type": "bearer",
        "company_id": user.company_id,
    }


# ── Profile endpoints ─────────────────────────────────────────────────────────

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
