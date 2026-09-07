"""TEMPORARY — diagnose why an inbound WhatsApp message routed to the wrong
handler. Delete after use.

Everything checkable from outside production already checks out: the
account's vertical is broker_intel, the registry has broker_intel with an
inbound handler, the stored whatsapp_number is byte-identical to the sender,
and a local reproduction of that exact setup dispatches correctly. The
remaining difference is production's own user table, which nothing exposes.

This runs the real resolution chain — get_ceo_user, then the same company and
vertical lookups dispatch_inbound performs — against the CALLER'S OWN stored
number, and reports where it diverges.

Deliberately leak-free. It is gated on the caller's login and reports only
facts about a number the caller owns. When resolution lands on somebody
else's row it says so without returning that row's id, email or company
name: "not you", plus the vertical, is enough to explain the routing and
nothing more. The duplicate count is included because two users sharing one
number is the single most likely explanation, and it is a fact about the
caller's own number.

DELETE once diagnosed:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.ceo_command_service import get_ceo_user, normalize_phone_number
from app.verticals.registry import all_verticals, get_vertical

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.get("/diag-routing")
async def diag_routing(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    me = (
        await db.execute(select(User).where(User.email == current_user.email))
    ).scalars().first()
    if me is None:
        return {"error": "caller not found"}

    my_company = await db.get(Company, me.company_id)
    stored = me.whatsapp_number

    out: dict = {
        "caller": {
            "user_id": me.id,
            "company_id": me.company_id,
            "vertical": my_company.vertical if my_company else None,
            "stored_whatsapp_number": stored,
            "stored_repr": repr(stored),
            "stored_len": len(stored) if stored else None,
        },
        "registry": {
            "registered": sorted(v.name for v in all_verticals()),
            "my_vertical_registered": bool(
                my_company and get_vertical(my_company.vertical)
            ),
            "my_vertical_has_inbound": bool(
                my_company
                and get_vertical(my_company.vertical)
                and get_vertical(my_company.vertical).inbound
            ),
        },
    }

    if not stored:
        out["resolution"] = {"note": "no stored number; nothing to resolve"}
        return out

    # How many users share this exact number, and how many share its last 10
    # digits (what the suffix fallback matches on).
    exact_n = (await db.execute(
        select(func.count()).select_from(User).where(User.whatsapp_number == stored)
    )).scalar_one()
    digits = "".join(c for c in stored if c.isdigit())[-10:]
    suffix_n = (await db.execute(
        select(func.count()).select_from(User)
        .where(User.whatsapp_number.like(f"%{digits}"))
    )).scalar_one()

    resolved = await get_ceo_user(db, stored)
    resolved_company = (
        await db.get(Company, resolved.company_id) if resolved else None
    )
    resolved_vertical = resolved_company.vertical if resolved_company else None
    v = get_vertical(resolved_vertical) if resolved_vertical else None

    out["resolution"] = {
        "normalized_sender": normalize_phone_number(stored),
        "users_with_exact_number": exact_n,
        "users_with_same_last10": suffix_n,
        "resolved_to_caller": bool(resolved and resolved.id == me.id),
        "resolved_to": (
            "caller" if resolved and resolved.id == me.id
            else ("someone else" if resolved else "nobody")
        ),
        "resolved_company_vertical": resolved_vertical,
        "resolved_vertical_registered": v is not None,
        "would_dispatch_claim": bool(v and v.inbound),
    }
    return out
