"""Authentication API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.auth_schema import UserCreate, UserLogin, Token
from app.services.auth_service import get_password_hash, verify_password, create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup")
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new company + admin user account."""
    logger.info("[Foreman AI] Signup attempt for: %s", payload.email)

    # Check if user exists
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        return {"success": False, "error": "Email already registered"}

    # Create company
    company = Company(name=payload.company_name)
    db.add(company)
    await db.flush()

    # Create user
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        company_id=company.id,
        role=UserRole.ceo,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("[Foreman AI] Signup OK for: %s  |  company_id=%s", payload.email, company.id)

    # Generate token
    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT token."""
    logger.info("[Foreman AI] Login attempt for: %s", payload.email)

    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.password_hash:
        logger.warning("[Foreman AI] Login FAILED for: %s (user not found)", payload.email)
        return {"success": False, "error": "Incorrect email or password"}

    if not verify_password(payload.password, user.password_hash):
        logger.warning("[Foreman AI] Login FAILED for: %s (bad password)", payload.email)
        return {"success": False, "error": "Incorrect email or password"}

    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    logger.info("[Foreman AI] Login OK for: %s  |  company_id=%s", payload.email, user.company_id)
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}


@router.post("/reset")
async def reset_users(db: AsyncSession = Depends(get_db)):
    """Clear all users and companies so a fresh signup can be done.

    WARNING: destructive — only for dev / early-stage use.
    """
    await db.execute(delete(User))
    await db.execute(delete(Company))
    logger.warning("[Foreman AI] All users and companies have been deleted via /auth/reset")
    return {"success": True, "message": "All users and companies cleared. You can now sign up again."}