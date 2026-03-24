"""Analytics API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analytics_service import get_employee_performance
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/employees")
async def employee_performance(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Return performance metrics for all employees."""
    return await get_employee_performance(db, company_id=current_user.company_id)
