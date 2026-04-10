"""Enquiry CRUD routes."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.employee import Employee
from app.models.enquiry import (
    Enquiry,
    EnquiryStage,
    EnquiryStatus,
    STAGE_MESSAGES,
    STAGE_ORDER,
)
from app.schemas.auth_schema import CurrentUser
from app.services.messaging_service import send_whatsapp_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enquiries", tags=["Enquiries"])


# ── Schemas ──────────────────────────────────────────────────

class EnquiryCreate(BaseModel):
    client_name: str
    service_requested: str | None = None
    notes: str | None = None
    status: str = "new"
    assigned_employee_id: int | None = None


class EnquiryUpdate(BaseModel):
    client_name: str | None = None
    service_requested: str | None = None
    notes: str | None = None
    status: str | None = None
    assigned_employee_id: int | None = None


class EnquiryResponse(BaseModel):
    id: int
    company_id: int
    client_name: str
    service_requested: str | None = None
    notes: str | None = None
    status: str
    stage: str | None = None
    assigned_employee_id: int | None = None
    assigned_employee_name: str | None = None
    stage_history: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ──────────────────────────────────────────────────

def _append_stage_history(enquiry: Enquiry, stage: str) -> None:
    """Append a stage entry to the JSON stage_history field."""
    history = json.loads(enquiry.stage_history) if enquiry.stage_history else []
    history.append({"stage": stage, "at": datetime.utcnow().isoformat()})
    enquiry.stage_history = json.dumps(history)


async def _resolve_employee_name(db: AsyncSession, employee_id: int | None) -> str | None:
    if not employee_id:
        return None
    emp = await db.get(Employee, employee_id)
    return emp.name if emp else None


async def _enrich_response(db: AsyncSession, enquiry: Enquiry) -> dict:
    """Build an EnquiryResponse-compatible dict with the employee name resolved."""
    data = {
        "id": enquiry.id,
        "company_id": enquiry.company_id,
        "client_name": enquiry.client_name,
        "service_requested": enquiry.service_requested,
        "notes": enquiry.notes,
        "status": enquiry.status.value if hasattr(enquiry.status, "value") else enquiry.status,
        "stage": enquiry.stage,
        "assigned_employee_id": enquiry.assigned_employee_id,
        "assigned_employee_name": await _resolve_employee_name(db, enquiry.assigned_employee_id),
        "stage_history": enquiry.stage_history,
        "created_at": enquiry.created_at,
    }
    return data


# ── Endpoints ────────────────────────────────────────────────

@router.get("")
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
    enquiries = result.scalars().all()
    return [await _enrich_response(db, eq) for eq in enquiries]


@router.post("", status_code=201)
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
        assigned_employee_id=payload.assigned_employee_id,
    )
    db.add(enquiry)
    await db.flush()
    await db.refresh(enquiry)
    logger.info("Enquiry created: %s — %s", payload.client_name, payload.service_requested)
    return await _enrich_response(db, enquiry)


@router.patch("/{enquiry_id}")
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
    if payload.assigned_employee_id is not None:
        enquiry.assigned_employee_id = payload.assigned_employee_id
        if enquiry.status == EnquiryStatus.new:
            enquiry.status = EnquiryStatus.assigned

    await db.flush()
    await db.refresh(enquiry)
    return await _enrich_response(db, enquiry)


@router.post("/{enquiry_id}/advance-stage")
async def advance_stage(
    enquiry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Advance an enquiry to the next pipeline stage and notify the assigned employee."""
    enquiry = await db.get(Enquiry, enquiry_id)
    if not enquiry or enquiry.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    # Determine current and next stage
    current_stage = EnquiryStage(enquiry.stage) if enquiry.stage else None
    if current_stage is None:
        next_stage = STAGE_ORDER[0]  # follow_up
    else:
        try:
            idx = STAGE_ORDER.index(current_stage)
        except ValueError:
            raise HTTPException(status_code=400, detail="Unknown current stage")
        if idx >= len(STAGE_ORDER) - 1:
            raise HTTPException(status_code=400, detail="Enquiry already at final stage")
        next_stage = STAGE_ORDER[idx + 1]

    # Update stage
    enquiry.stage = next_stage.value
    _append_stage_history(enquiry, next_stage.value)

    # Auto-update status
    if enquiry.status == EnquiryStatus.new:
        enquiry.status = EnquiryStatus.assigned
    if next_stage == EnquiryStage.done:
        enquiry.status = EnquiryStatus.done

    await db.flush()
    await db.refresh(enquiry)

    # Send WhatsApp to assigned employee
    whatsapp_sent = False
    msg_template = STAGE_MESSAGES.get(next_stage)
    if msg_template and enquiry.assigned_employee_id:
        employee = await db.get(Employee, enquiry.assigned_employee_id)
        if employee and employee.phone_number:
            msg = msg_template.format(client_name=enquiry.client_name)
            whatsapp_sent = await send_whatsapp_message(employee.phone_number, msg)
            if whatsapp_sent:
                logger.info(
                    "Stage notification sent: enquiry=%s stage=%s employee=%s",
                    enquiry_id, next_stage.value, employee.name,
                )
            else:
                logger.warning(
                    "Stage notification FAILED: enquiry=%s stage=%s employee=%s",
                    enquiry_id, next_stage.value, employee.name,
                )

    resp = await _enrich_response(db, enquiry)
    resp["whatsapp_sent"] = whatsapp_sent
    return resp


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
