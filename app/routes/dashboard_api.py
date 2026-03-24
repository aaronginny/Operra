"""Dashboard API routes — lightweight endpoints for the demo dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser
from app.models.task import Task
from app.models.employee import Employee
from app.schemas.task_schema import OnboardTaskRequest, TaskCreate, TaskResponse
from app.services.employee_service import get_or_create_employee
from app.services.task_service import create_task
from app.services.messaging_service import send_whatsapp_message
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/tasks")
async def dashboard_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Return all non-archived tasks in a simple format for the dashboard."""
    from app.models.task import TaskStatus

    stmt = (
        select(Task)
        .options(selectinload(Task.assigned_employee))
        .where(Task.company_id == current_user.company_id)
        .where(Task.status != TaskStatus.archived)
        .order_by(Task.created_at.desc())
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    return [
        {
            "id": t.id,
            "task": t.title,
            "employee": (
                t.assigned_employee.name
                if t.assigned_employee
                else t.assigned_to or "Unassigned"
            ),
            "deadline": (
                t.due_at.strftime("%H:%M") if t.due_at else "No deadline"
            ),
            "status": t.status.value,
        }
        for t in tasks
    ]


@router.get("/employees")
async def dashboard_employees(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Return all employees for the dashboard dropdown."""
    stmt = (
        select(Employee)
        .where(Employee.company_id == current_user.company_id)
        .order_by(Employee.name.asc())
    )
    result = await db.execute(stmt)
    employees = result.scalars().all()
    
    return [
        {
            "id": e.id,
            "name": e.name,
            "phone_number": e.phone_number,
        }
        for e in employees
        if not e.name.startswith("Employee_") and not e.name.startswith("+") and not e.name.isdigit()
    ]


@router.post("/onboard-assign", response_model=TaskResponse)
async def onboard_and_assign(
    payload: OnboardTaskRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Onboard a new employee and assign a task instantly."""
    employee = await get_or_create_employee(
        db,
        name=payload.employee_name,
        phone_number=payload.phone_number,
        company_id=current_user.company_id,
    )

    task_data = TaskCreate(
        company_id=current_user.company_id,
        title=payload.title,
        description=payload.description,
        assigned_to=employee.name,
        assigned_employee_id=employee.id,
        due_at=payload.due_at,
        source_type="whatsapp",
    )
    task = await create_task(db, task_data)

    if employee.phone_number:
        due_str = (
            task.due_at.strftime("%I:%M %p").lstrip("0") if task.due_at else "No deadline"
        )
        task_notification = (
            f"New Task Assigned\n\n"
            f"Task: {task.title}\n"
            f"Deadline: {due_str}\n\n"
            f"Reply with:\n"
            f"DONE\n"
            f"DELAY 30\n"
            f"HELP\n"
            f"UPDATE <progress>"
        )
        sent = await send_whatsapp_message(employee.phone_number, task_notification)
        task.notification_sent = sent
        await db.flush()
        if sent:
            logger.info("Notification sent to: %s", employee.phone_number)
        else:
            logger.warning("Notification not sent to: %s", employee.phone_number)
    else:
        logger.warning(
            "Employee %s has no phone number — cannot notify.", employee.name,
        )

    return task
