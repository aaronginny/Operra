"""Enquiry CRUD routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.enquiry import Enquiry, EnquiryStatus
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enquiries", tags=["Enquiries"])


# ── Schemas ──────────────────────────────────────────────────

class EnquiryCreate(BaseModel):
    client_name: str
    service_requested: str | None = None
    notes: str | None = None
    status: str = "new"


class EnquiryUpdate(BaseModel):
    client_name: str | None = None
    service_requested: str | None = None
    notes: str | None = None
    status: str | None = None


class EnquiryResponse(BaseModel):
    id: int
    company_id: int
    client_name: str
    service_requested: str | None = None
    notes: str | None = None
    status: str
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────

@router.get("", response_model=list[EnquiryResponse])
async def list_enquiries(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all enquiries for the current company, newest first."""
    stmt = (
        select(Enquiry)
        .where(Enquiry.company_id == current_user.company_id)
        .order_by(Enquiry.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=EnquiryResponse, status_code=201)
async def create_enquiry(
    payload: EnquiryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Manually create an enquiry from the dashboard."""
    enquiry = Enquiry(
        company_id=current_user.company_id,
        client_name=payload.client_name,
        service_requested=payload.service_requested,
        notes=payload.notes,
        status=EnquiryStatus(payload.status) if payload.status else EnquiryStatus.new,
    )
    db.add(enquiry)
    await db.flush()
    await db.refresh(enquiry)
    logger.info("Enquiry created: %s — %s", payload.client_name, payload.service_requested)
    return enquiry


@router.patch("/{enquiry_id}", response_model=EnquiryResponse)
async def update_enquiry(
    enquiry_id: int,
    payload: EnquiryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an existing enquiry."""
    enquiry = await db.get(Enquiry, enquiry_id)
    if not enquiry or enquiry.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    if payload.client_name is not None:
        enquiry.client_name = payload.client_name
    if payload.service_requested is not None:
        enquiry.service_requested = payload.service_requested
    if payload.notes is not None:
        enquiry.notes = payload.notes
    if payload.status is not None:
        enquiry.status = EnquiryStatus(payload.status)

    await db.flush()
    await db.refresh(enquiry)
    return enquiry


@router.delete("/{enquiry_id}")
async def delete_enquiry(
    enquiry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete an enquiry."""
    enquiry = await db.get(Enquiry, enquiry_id)
    if not enquiry or enquiry.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    await db.delete(enquiry)
    await db.flush()
    return {"success": True}
