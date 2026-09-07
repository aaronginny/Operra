"""TEMPORARY — repair one account, then delete this file.

Why this exists. The broker_intel client was provisioned with
whatsapp_number = '+919150016161' as a live-test placeholder. That is the
exact number hardcoded in migration 021 (users.fix_ceo_company), which runs
on EVERY startup and force-moves any user holding it to company_id=1. The
next deploy therefore detached her user from her own company. Her login
still worked, which is what made it easy to miss: the account resolved to
the wrong tenant rather than failing.

This repair puts her user back on her broker_intel company and clears the
number, so the migration has nothing to match on subsequent boots. It stays
cleared until her real number is known — with no number, the daily hook
simply finds no recipient and sends nothing, which is the correct quiet
state rather than messaging the wrong person every morning.

Auth is her own login (require the caller to BE the user being repaired), so
no shared secret has to exist in production for this. The target company is
resolved by vertical rather than passed in, so this cannot be pointed at an
arbitrary tenant.

DELETE once the repair is confirmed:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

_TARGET_VERTICAL = "broker_intel"


@router.post("/repair-broker-account")
async def repair_broker_account(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Re-attach the calling user to their broker_intel company and clear the
    placeholder WhatsApp number. Reports state before and after."""
    user = (
        await db.execute(select(User).where(User.email == current_user.email))
    ).scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    before_company = user.company_id
    before_number = user.whatsapp_number

    # Resolve the destination by vertical, not from the request: there is
    # exactly one broker_intel company, and this must not be aimable elsewhere.
    companies = (
        await db.execute(select(Company).where(Company.vertical == _TARGET_VERTICAL))
    ).scalars().all()
    if len(companies) != 1:
        raise HTTPException(
            status_code=409,
            detail=f"expected exactly 1 {_TARGET_VERTICAL} company, found {len(companies)}",
        )
    target = companies[0]

    user.company_id = target.id
    # Cleared so migration 021 has nothing to match on the next boot.
    user.whatsapp_number = None
    await db.flush()

    logger.info("repaired user=%s company %s -> %s", user.id, before_company, target.id)
    return {
        "user_id": user.id,
        "email": user.email,
        "company_id_before": before_company,
        "company_id_after": user.company_id,
        "company_name": target.name,
        "vertical": target.vertical,
        "whatsapp_number_before": before_number,
        "whatsapp_number_after": user.whatsapp_number,
    }
