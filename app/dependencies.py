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

async def require_real_estate_company(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Authorize a request against the real-estate vertical.

    Layers on top of get_current_user (same JWT, same company_id scoping) and
    additionally requires the caller's company to have opted into the
    real-estate vertical.

    Deliberately raises 404 rather than 403: to a generic company these routes
    should look like they don't exist, not like something they're forbidden
    from. That keeps the vertical genuinely invisible to accounts such as
    Lenin's rather than merely locked.
    """
    from app.models.company import Company

    company = await db.get(Company, current_user.company_id)
    if company is None or company.vertical != "real_estate":
        raise HTTPException(status_code=404, detail="Not found")
    return current_user


async def require_launch_matcher_company(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Authorize a request against the Launch Matcher vertical.

    Same shape as require_real_estate_company: same JWT, same company_id
    scoping, plus a check on the company's vertical, and a 404 rather than a
    403 so the feature is invisible to everyone else rather than merely locked.

    "launch_matcher" is a distinct top-level vertical rather than a sub-flag of
    "real_estate", which makes the two mutually exclusive by construction: a
    launch-matcher company fails the real-estate gate and a real-estate company
    fails this one, so the broker CRM and this feature can never see each
    other's data no matter what is added to either later.
    """
    from app.models.company import Company

    company = await db.get(Company, current_user.company_id)
    if company is None or company.vertical != "launch_matcher":
        raise HTTPException(status_code=404, detail="Not found")
    return current_user
