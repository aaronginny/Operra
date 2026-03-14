"""Analytics API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analytics_service import get_employee_performance

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/employees")
async def employee_performance(company_id: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Return performance metrics for all employees."""
    return await get_employee_performance(db, company_id=company_id)
