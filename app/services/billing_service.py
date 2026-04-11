"""Billing service — helper functions for subscription / plan gating.

All premium checks should go through this module so billing logic
stays centralised and easy to update as plans evolve.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company

logger = logging.getLogger(__name__)

# Free-tier task limit (number of tasks a basic company can create)
FREE_TASK_LIMIT = 1


async def is_company_premium(db: AsyncSession, company_id: int) -> bool:
    """Return True if the company has an active premium subscription."""
    company = await db.get(Company, company_id)
    if company is None:
        return False
    return bool(company.is_premium)


async def get_billing_status(db: AsyncSession, company_id: int) -> dict:
    """Return a billing status dict for use in API responses / dashboard.

    Keys:
        subscription_level: "basic" | "premium"
        is_premium: bool
        tasks_created_count: int
        free_task_limit: int
        limit_reached: bool
    """
    company = await db.get(Company, company_id)
    if company is None:
        return {
            "subscription_level": "basic",
            "is_premium": False,
            "tasks_created_count": 0,
            "free_task_limit": FREE_TASK_LIMIT,
            "limit_reached": False,
        }

    limit_reached = (
        not company.is_premium
        and company.tasks_created_count >= FREE_TASK_LIMIT
    )

    return {
        "subscription_level": company.subscription_level,
        "is_premium": company.is_premium,
        "tasks_created_count": company.tasks_created_count,
        "free_task_limit": FREE_TASK_LIMIT,
        "limit_reached": limit_reached,
    }


async def check_can_create_task(db: AsyncSession, company_id: int) -> None:
    """Raise ValueError if the company has hit its free-tier task limit.

    Call this before creating a task. ValueError is converted to HTTP 403
    in the route handler.
    """
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
