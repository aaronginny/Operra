"""Billing routes.

Payment is handled manually via UPI (aaronginny@okhdfcbank).
Aaron activates plans after verifying the WhatsApp payment screenshot.

This module exposes GET /billing/status so the dashboard can read
the current tier, limit usage, and projects_paid list.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser
from app.services.billing_service import get_billing_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/status")
async def billing_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the current company's billing / plan status.

    Mirrors GET /tasks/billing-status for billing-specific UI consumers.
    """
    return await get_billing_status(
        db,
        current_user.company_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_role=current_user.role,
    )
