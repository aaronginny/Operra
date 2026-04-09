"""Task CRUD routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.employee import Employee
from app.models.task import Task
from app.schemas.task_schema import TaskCreate, TaskResponse, TaskUpdate
from app.services.messaging_service import send_whatsapp_message
from app.services.task_service import create_task, get_task, get_tasks, update_task
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task_endpoint(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a task manually."""
    payload.company_id = current_user.company_id
    task = await create_task(db, payload)

    if task.assigned_employee_id:
        employee = await db.get(Employee, task.assigned_employee_id)
        if employee and employee.phone_number:
            due_str = (
                task.due_at.strftime("%I:%M %p").lstrip("0") if task.due_at else "No deadline"
            )
            desc_str = task.description or "No description"
            task_notification = (
                f"Foreman AI - New Task Assigned\n\n"
                f"Task: {task.title}\n"
                f"Description: {desc_str}\n"
                f"Due: {due_str}\n\n"
                f"Reply with:\n"
                f"DONE - mark complete\n"
                f"HELP - request assistance\n"
                f"UPDATE <text> - send progress"
            )
            logger.info(
                "Sending task notification to %s (%s) for task '%s'",
                employee.name, employee.phone_number, task.title,
            )
            sent = await send_whatsapp_message(employee.phone_number, task_notification)
            task.notification_sent = sent
            await db.flush()

            if sent:
                logger.info("Notification sent to %s at %s", employee.name, employee.phone_number)
            else:
                logger.error(
                    "NOTIFICATION FAILED for %s at %s — check Render logs for Twilio errors",
                    employee.name, employee.phone_number,
                )
        else:
            logger.warning(
                "Cannot notify employee id=%s — %s",
                task.assigned_employee_id,
                "no phone number" if employee else "employee not found in DB",
            )

    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """List tasks with optional filters."""
    return await get_tasks(db, company_id=current_user.company_id, status=status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get a single task by ID."""
    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Partially update a task (e.g. mark as completed)."""
    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")

    updated_task = await update_task(db, task_id, payload)
    return updated_task


class DueDateUpdate(BaseModel):
    due_at: datetime


@router.patch("/{task_id}/due-date", response_model=TaskResponse)
async def update_due_date(
    task_id: int,
    payload: DueDateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a task's due date and notify the assigned employee via WhatsApp."""
    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")

    task.due_at = payload.due_at
    await db.flush()
    await db.refresh(task)

    # Notify the employee if they have a phone number
    if task.assigned_employee_id:
        employee = await db.get(Employee, task.assigned_employee_id)
        if employee and employee.phone_number:
            due_str = payload.due_at.strftime("%b %d, %Y %I:%M %p").lstrip("0")
            msg = (
                f"Foreman AI - Task Update\n\n"
                f"Task: {task.title}\n"
                f"Your deadline has been updated.\n"
                f"New due date: {due_str}\n\n"
                f"Please plan accordingly."
            )
            sent = await send_whatsapp_message(employee.phone_number, msg)
            if sent:
                logger.info("Due-date update notification sent to %s", employee.phone_number)
            else:
                logger.warning("Due-date notification FAILED for employee id=%s", task.assigned_employee_id)

    return task
