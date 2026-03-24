from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.schemas.auth_schema import CurrentUser
from app.services.auth_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("user_id")
    company_id = payload.get("company_id")
    if user_id is None or company_id is None:
        raise credentials_exception
    
    # We could fetch user from db here, but returning payload details is faster
    # Let's just return CurrentUser structure.
    return CurrentUser(
        id=user_id,
        email=payload.get("sub", ""),
        name="User",
        company_id=company_id,
        role=payload.get("role", "employee")
    )