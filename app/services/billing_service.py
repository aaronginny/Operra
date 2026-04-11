"""Billing service — helper functions for subscription / plan gating.

All premium checks should go through this module so billing logic
stays centralised and easy to update as plans evolve.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User

logger = logging.getLogger(__name__)

# Free-tier task limit (number of tasks a basic company can create)
FREE_TASK_LIMIT = 1


def _is_founder(whatsapp_number: str | None = None, email: str | None = None) -> bool:
    """Return True if the caller is the product owner.

    Checks (in order):
      1. whatsapp_number matches FOUNDER_PHONE env var
      2. email matches FOUNDER_EMAIL env var

    Two paths because whatsapp_number may be NULL in the DB for dashboard
    logins — email comes from the JWT and is always present.
    """
    from app.config import settings

    if whatsapp_number:
        founder_phone = settings.founder_phone
        if founder_phone:
            if whatsapp_number.strip().lstrip("+") == founder_phone.strip().lstrip("+"):
                return True

    if email:
        founder_email = settings.founder_email
        if founder_email and email.strip().lower() == founder_email.strip().lower():
            return True

    return False


async def _user_whatsapp(db: AsyncSession, user_id: int | None) -> str | None:
    """Look up a user's WhatsApp number by their user_id."""
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    return user.whatsapp_number if user else None


async def is_company_premium(db: AsyncSession, company_id: int) -> bool:
    """Return True if the company has an active premium subscription."""
    company = await db.get(Company, company_id)
    if company is None:
        return False
    return bool(company.is_premium)


async def get_billing_status(
    db: AsyncSession,
    company_id: int,
    user_id: int | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> dict:
    """Return a billing status dict for use in API responses / dashboard.

    Keys:
        subscription_level: "basic" | "premium"
        is_premium: bool
        tasks_created_count: int
        free_task_limit: int
        limit_reached: bool
    """
    # ── Role bypass — CEO/founder is always premium ───────────────
    role_bypass = user_role in ("ceo", "founder")
    if role_bypass:
        logger.info("get_billing_status: role bypass for user_id=%s role=%r", user_id, user_role)

    # ── Founder bypass (phone OR email env var) ───────────────────
    phone = await _user_whatsapp(db, user_id)
    env_bypass = _is_founder(whatsapp_number=phone, email=user_email)
    if env_bypass:
        logger.info("get_billing_status: env-var founder bypass for user_id=%s email=%r", user_id, user_email)

    founder = role_bypass or env_bypass

    company = await db.get(Company, company_id)
    if company is None:
        return {
            "subscription_level": "premium" if founder else "basic",
            "is_premium": founder,
            "tasks_created_count": 0,
            "free_task_limit": FREE_TASK_LIMIT,
            "limit_reached": False,
        }

    is_prem = founder or bool(company.is_premium)
    limit_reached = (
        not is_prem
        and company.tasks_created_count >= FREE_TASK_LIMIT
    )

    return {
        "subscription_level": "premium" if is_prem else company.subscription_level,
        "is_premium": is_prem,
        "tasks_created_count": company.tasks_created_count,
        "free_task_limit": FREE_TASK_LIMIT,
        "limit_reached": limit_reached,
    }


async def check_can_create_task(
    db: AsyncSession,
    company_id: int,
    user_id: int | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> None:
    """Raise ValueError if the company has hit its free-tier task limit.

    Call this before creating a task. ValueError is converted to HTTP 403
    in the route handler.

    Pass user_role (from JWT), user_id, and/or user_email for the founder
    bypass — the owner is never blocked from their own product.
    """
    # ── Role bypass — CEO/founder is always allowed ───────────────
    # Role comes directly from the JWT — no DB lookup needed.
    if user_role in ("ceo", "founder"):
        logger.info("Billing check bypassed: user_id=%s role=%r is ceo/founder", user_id, user_role)
        print(f"=== BILLING CHECK === BYPASSED (role={user_role!r}) user_id={user_id} email={user_email!r}")
        return

    # ── Founder bypass (phone OR email env var) ───────────────────
    phone = await _user_whatsapp(db, user_id)
    is_founder_user = _is_founder(whatsapp_number=phone, email=user_email)
    print(f"=== BILLING CHECK === user_id={user_id} role={user_role!r} email={user_email!r} phone={phone!r} founder_bypass={is_founder_user}")
    if is_founder_user:
        logger.info("Billing check bypassed: user_id=%s email=%r is founder (env var match)", user_id, user_email)
        return

    company = await db.get(Company, company_id)
    if company is None:
        return  # Unknown company — let other checks handle it

    if company.is_premium or company.subscription_level == "premium":
        return  # Premium users are never blocked

    if company.tasks_created_count >= FREE_TASK_LIMIT:
        raise ValueError(
            "Free limit reached! Your first project was free. "
            "Upgrade to Premium to manage unlimited tasks."
        )


async def increment_task_count(db: AsyncSession, company_id: int) -> None:
    """Atomically increment tasks_created_count for the given company."""
    company = await db.get(Company, company_id)
    if company is not None:
        company.tasks_created_count = (company.tasks_created_count or 0) + 1
        logger.info(
            "Company #%s task count incremented to %d",
            company_id, company.tasks_created_count,
        )
