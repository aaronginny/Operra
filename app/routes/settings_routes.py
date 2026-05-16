"""Settings routes — reminder configuration per company."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.company_settings import CompanySettings
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


class ReminderSettings(BaseModel):
    morning_pulse_enabled: bool = True
    morning_pulse_time: str = "09:00"
    reminder_frequency_hours: int = 4
    reminders_enabled: bool = True


async def _get_or_create_settings(
    db: AsyncSession, company_id: int
) -> CompanySettings:
    result = await db.execute(
        select(CompanySettings).where(CompanySettings.company_id == company_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = CompanySettings(company_id=company_id)
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


@router.get("/reminders", response_model=ReminderSettings)
async def get_reminder_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    s = await _get_or_create_settings(db, current_user.company_id)
    return ReminderSettings(
        morning_pulse_enabled=s.morning_pulse_enabled,
        morning_pulse_time=s.morning_pulse_time,
        reminder_frequency_hours=s.reminder_frequency_hours,
        reminders_enabled=s.reminders_enabled,
    )


@router.post("/reminders", response_model=ReminderSettings)
async def save_reminder_settings(
    payload: ReminderSettings,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if payload.reminder_frequency_hours not in (2, 4, 8, 24):
        payload.reminder_frequency_hours = 4

    s = await _get_or_create_settings(db, current_user.company_id)
    s.morning_pulse_enabled = payload.morning_pulse_enabled
    s.morning_pulse_time = payload.morning_pulse_time
    s.reminder_frequency_hours = payload.reminder_frequency_hours
    s.reminders_enabled = payload.reminders_enabled

    await db.flush()
    await db.refresh(s)
    await db.commit()
    logger.info(
        "Reminder settings saved for company=%s: %s",
        current_user.company_id, payload.model_dump(),
    )
    return ReminderSettings(
        morning_pulse_enabled=s.morning_pulse_enabled,
        morning_pulse_time=s.morning_pulse_time,
        reminder_frequency_hours=s.reminder_frequency_hours,
        reminders_enabled=s.reminders_enabled,
    )
