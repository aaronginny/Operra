"""Notifications routes — in-app inbox for the dashboard."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return all unread notifications for the company, newest first."""
    stmt = (
        select(Notification)
        .where(
            Notification.company_id == current_user.company_id,
            Notification.is_read == False,  # noqa: E712
        )
        .order_by(Notification.created_at.desc())
    )
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    return [
        {
            "id": n.id,
            "task_id": n.task_id,
            "employee_id": n.employee_id,
            "employee_name": n.employee_name,
            "message": n.message,
            "type": n.type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.get("/count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the number of unread notifications for the company."""
    stmt = select(func.count()).where(
        Notification.company_id == current_user.company_id,
        Notification.is_read == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a single notification as read."""
    n = await db.get(Notification, notification_id)
    if n and n.company_id == current_user.company_id:
        n.is_read = True
        await db.flush()
    await db.commit()
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark all unread notifications for the company as read."""
    await db.execute(
        update(Notification)
        .where(
            Notification.company_id == current_user.company_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"status": "ok"}
