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
    
    return CurrentUser(
        id=user_id,
        email=payload.get("sub", ""),
        name=payload.get("name") or payload.get("sub", "").split("@")[0] or "User",
        company_id=company_id,
        role=payload.get("role", "employee")
    )

def require_vertical(name: str):
    """Build a FastAPI dependency that 404s unless the caller's company has
    `vertical == name`.

    Extracted (platform-refactor) from what were two hand-copied,
    byte-for-byte-identical-but-for-one-string functions —
    require_real_estate_company and require_launch_matcher_company below.
    A third vertical no longer means a third copy: it means calling this
    once with its name.

    Layers on top of get_current_user (same JWT, same company_id scoping)
    and additionally requires the caller's company to have opted into the
    named vertical.

    Deliberately raises 404 rather than 403: to a company on a different
    vertical these routes should look like they don't exist, not like
    something they're forbidden from. That keeps a vertical genuinely
    invisible to every other tenant rather than merely locked — and since a
    company has exactly one `vertical` value, gating two verticals this way
    makes them mutually exclusive by construction: neither can ever see the
    other's data no matter what is added to either later.
    """

    async def _require_vertical(
        db: AsyncSession = Depends(get_db),
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        from app.models.company import Company

        company = await db.get(Company, current_user.company_id)
        if company is None or company.vertical != name:
            raise HTTPException(status_code=404, detail="Not found")
        return current_user

    return _require_vertical


# Kept as top-level names — every route file imports these specifically —
# but both are now the same factory called with a different string, not two
# separately maintained functions.
require_real_estate_company = require_vertical("real_estate")
require_launch_matcher_company = require_vertical("launch_matcher")
