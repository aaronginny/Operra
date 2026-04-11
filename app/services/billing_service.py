"""Billing service — subscription tier enforcement for Foreman AI.

Tiers
-----
free     — 3 tasks max, no checkpoints, no God Mode, no morning pulse
basic    — ₹2,000 per project; unlimited tasks per paid project,
           checkpoints + God Mode + morning pulse enabled
premium  — ₹5,000 / month; unlimited everything, all features

Payment
-------
Payment handled manually via UPI — aaronginny@okhdfcbank
Aaron activates plans after verifying the WhatsApp screenshot
(9150016161).  No automated payment gateway is used.

Bypass
------
Any user with role='ceo' (or role='founder') is NEVER blocked — they are
treated as premium regardless of DB state.  The product owner should never
be locked out of their own product.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User

logger = logging.getLogger(__name__)

# ── Tier constants ────────────────────────────────────────────────────────────

FREE_TASK_LIMIT = 3  # max tasks for free tier


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_founder(whatsapp_number: str | None = None, email: str | None = None) -> bool:
    """Return True if the caller matches FOUNDER_PHONE or FOUNDER_EMAIL env vars."""
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


def _is_ceo_bypass(user_role: str | None) -> bool:
    """Role-based bypass — CEO/founder is always allowed, no DB lookups needed."""
    return user_role in ("ceo", "founder")


def _get_effective_tier(company: Company | None, is_founder_user: bool) -> str:
    """Resolve the actual tier string, honouring founder bypass and expiry.

    Returns "free", "basic", or "premium".
    """
    if is_founder_user:
        return "premium"
    if company is None:
        return "free"

    tier = (company.subscription_level or "free").lower()

    # Honour legacy is_premium flag (set by older code / migrations)
    if company.is_premium and tier != "premium":
        tier = "premium"

    # Check premium expiry
    if tier == "premium" and company.tier_expires_at is not None:
        now = datetime.now(tz=timezone.utc)
        expires = company.tier_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            tier = "free"  # expired premium → drop to free
            logger.info("Company #%s premium expired at %s, downgrading to free", company.id, expires)

    return tier


def _paid_projects(company: Company | None) -> list[int]:
    """Return list of project IDs the company has unlocked via Basic payments."""
    if company is None or not company.projects_paid:
        return []
    try:
        return [int(x) for x in json.loads(company.projects_paid)]
    except (ValueError, TypeError):
        return []


# ── Public API ────────────────────────────────────────────────────────────────

async def is_company_premium(db: AsyncSession, company_id: int) -> bool:
    """Return True if the company has an active premium subscription."""
    company = await db.get(Company, company_id)
    if company is None:
        return False
    tier = _get_effective_tier(company, False)
    return tier == "premium"


async def get_billing_status(
    db: AsyncSession,
    company_id: int,
    user_id: int | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> dict:
    """Return a billing status dict for use in API responses / dashboard.

    Keys
    ----
    tier                 "free" | "basic" | "premium"
    is_premium           bool
    tasks_created_count  int
    free_task_limit      int
    limit_reached        bool
    tier_expires_at      ISO-8601 string or null
    projects_paid        list[int]
    """
    # ── CEO/founder role bypass ───────────────────────────────
    role_bypass = _is_ceo_bypass(user_role)
    if role_bypass:
        logger.info("get_billing_status: role bypass for user_id=%s role=%r", user_id, user_role)

    # ── Env-var founder bypass ────────────────────────────────
    phone = await _user_whatsapp(db, user_id)
    env_bypass = _is_founder(whatsapp_number=phone, email=user_email)
    if env_bypass:
        logger.info("get_billing_status: env-var bypass for user_id=%s email=%r", user_id, user_email)

    is_founder_user = role_bypass or env_bypass

    company = await db.get(Company, company_id)
    tier = _get_effective_tier(company, is_founder_user)
    is_prem = tier == "premium"
    tasks_count = company.tasks_created_count if company else 0
    paid_projects = _paid_projects(company)

    limit_reached = (
        tier == "free"
        and tasks_count >= FREE_TASK_LIMIT
    )

    expires_iso = None
    if company and company.tier_expires_at:
        expires_iso = company.tier_expires_at.isoformat()

    return {
        "tier": tier,
        # keep is_premium for backwards-compat with existing JS
        "subscription_level": tier,
        "is_premium": is_prem,
        "tasks_created_count": tasks_count,
        "free_task_limit": FREE_TASK_LIMIT,
        "limit_reached": limit_reached,
        "tier_expires_at": expires_iso,
        "projects_paid": paid_projects,
    }


async def check_can_create_task(
    db: AsyncSession,
    company_id: int,
    user_id: int | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
    project_id: int | None = None,
) -> None:
    """Raise ValueError if the company has hit its tier limit.

    Bypass order
    ------------
    1. Role bypass  — role='ceo'/'founder' → always allowed
    2. Env-var bypass — FOUNDER_PHONE / FOUNDER_EMAIL match → always allowed
    3. Premium tier → always allowed
    4. Basic tier + paid project → allowed
    5. Free tier (or basic without paid project) → check FREE_TASK_LIMIT
    """
    # 1 — Role bypass
    if _is_ceo_bypass(user_role):
        logger.info("Billing check bypassed: user_id=%s role=%r is ceo/founder", user_id, user_role)
        return

    # 2 — Env-var founder bypass
    phone = await _user_whatsapp(db, user_id)
    if _is_founder(whatsapp_number=phone, email=user_email):
        logger.info("Billing check bypassed: user_id=%s email=%r founder env-var match", user_id, user_email)
        return

    company = await db.get(Company, company_id)
    tier = _get_effective_tier(company, False)

    # 3 — Premium
    if tier == "premium":
        return

    # 4 — Basic + paid project
    if tier == "basic" and project_id is not None:
        paid = _paid_projects(company)
        if project_id in paid:
            return

    # 5 — Free tier (or basic without a paid project) — check limit
    count = company.tasks_created_count if company else 0
    if count >= FREE_TASK_LIMIT:
        if tier == "basic":
            raise ValueError(
                f"This project hasn't been unlocked. "
                f"Pay ₹2,000 to unlock unlimited tasks for this project."
            )
        raise ValueError(
            f"Free limit reached! You've used {count}/{FREE_TASK_LIMIT} free tasks. "
            f"Upgrade to Basic (₹2,000/project) or Premium (₹5,000/month) to continue."
        )


async def check_can_use_checkpoints(
    db: AsyncSession,
    company_id: int,
    user_role: str | None = None,
) -> bool:
    """Return True if the company tier allows Smart Checkpoints.

    Free tier: blocked. Basic / Premium: allowed. CEO: always allowed.
    """
    if _is_ceo_bypass(user_role):
        return True
    company = await db.get(Company, company_id)
    tier = _get_effective_tier(company, False)
    return tier in ("basic", "premium")


async def check_can_use_god_mode(
    db: AsyncSession,
    company_id: int,
    user_role: str | None = None,
) -> bool:
    """Return True if the company tier allows WhatsApp God Mode.

    Free tier: blocked. Basic / Premium: allowed. CEO: always allowed.
    """
    if _is_ceo_bypass(user_role):
        return True
    company = await db.get(Company, company_id)
    tier = _get_effective_tier(company, False)
    return tier in ("basic", "premium")


async def check_can_send_morning_pulse(
    db: AsyncSession,
    company_id: int,
) -> bool:
    """Return True if the company tier allows morning pulse messages.

    Free tier: blocked. Basic / Premium: allowed.
    """
    company = await db.get(Company, company_id)
    tier = _get_effective_tier(company, False)
    return tier in ("basic", "premium")


async def increment_task_count(db: AsyncSession, company_id: int) -> None:
    """Atomically increment tasks_created_count for the given company."""
    company = await db.get(Company, company_id)
    if company is not None:
        company.tasks_created_count = (company.tasks_created_count or 0) + 1
        logger.info(
            "Company #%s task count incremented to %d",
            company_id, company.tasks_created_count,
        )


async def unlock_project_for_company(
    db: AsyncSession,
    company_id: int,
    project_id: int,
) -> None:
    """Add project_id to company.projects_paid and upgrade tier to 'basic' if needed."""
    company = await db.get(Company, company_id)
    if company is None:
        return

    paid = _paid_projects(company)
    if project_id not in paid:
        paid.append(project_id)
        company.projects_paid = json.dumps(paid)

    # Ensure tier is at least 'basic'
    current_tier = (company.subscription_level or "free").lower()
    if current_tier == "free":
        company.subscription_level = "basic"

    logger.info("Company #%s unlocked project #%s (projects_paid=%s)", company_id, project_id, paid)


async def upgrade_to_premium(
    db: AsyncSession,
    company_id: int,
    expires_at: datetime | None = None,
) -> None:
    """Set company tier to premium with an optional expiry date."""
    company = await db.get(Company, company_id)
    if company is None:
        return

    company.subscription_level = "premium"
    company.is_premium = True
    company.tier_expires_at = expires_at
    logger.info("Company #%s upgraded to premium (expires=%s)", company_id, expires_at)
