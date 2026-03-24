"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.auth_schema import UserCreate, UserLogin, Token
from app.services.auth_service import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/signup")
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
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
        role=UserRole.ceo
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate token
    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}

@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.password_hash:
        return {"success": False, "error": "Incorrect email or password"}
    
    if not verify_password(payload.password, user.password_hash):
        return {"success": False, "error": "Incorrect email or password"}
    
    token = create_access_token({"sub": user.email, "user_id": user.id, "company_id": user.company_id, "role": user.role.value})
    return {"success": True, "access_token": token, "token_type": "bearer", "company_id": user.company_id}