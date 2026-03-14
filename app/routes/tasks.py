"""Task CRUD routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.schemas.task_schema import TaskCreate, TaskResponse, TaskUpdate
from app.services.messaging_service import send_whatsapp_message
from app.services.task_service import create_task, get_task, get_tasks, update_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task_endpoint(
    payload: TaskCreate, db: AsyncSession = Depends(get_db)
):
    """Create a task manually."""
    task = await create_task(db, payload)

    if task.assigned_employee_id:
        employee = await db.get(Employee, task.assigned_employee_id)
        if employee and employee.phone_number:
            due_str = (
                task.due_at.strftime("%I:%M %p").lstrip("0") if task.due_at else "No deadline"
            )
            task_notification = (
                f"New Task Assigned\n\n"
                f"Task: {task.title}\n"
                f"Deadline: {due_str}\n\n"
                f"Reply:\n"
                f"DONE\n"
                f"DELAY 30\n"
                f"HELP\n"
                f"UPDATE <progress>"
            )
            await send_whatsapp_message(employee.phone_number, task_notification)
            task.notification_sent = True
            await db.flush()
            
            logger.info("Task created via dashboard")
            logger.info("Notification sent to %s at %s", employee.name, employee.phone_number)

    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    company_id: int | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List tasks with optional filters."""
    return await get_tasks(db, company_id=company_id, status=status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single task by ID."""
    task = await get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(
    task_id: int, payload: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    """Partially update a task (e.g. mark as completed)."""
    task = await update_task(db, task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
