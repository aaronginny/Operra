"""Task service — CRUD helpers for the Task model."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus, SourceType
from app.schemas.task_schema import TaskCreate, TaskUpdate
from app.services.employee_service import get_or_create_employee


async def create_task(db: AsyncSession, data: TaskCreate) -> Task:
    """Insert a new task and return it.

    If ``assigned_to`` (a name) is provided but ``assigned_employee_id`` is
    not, the employee is looked up (or created) automatically.
    """
    employee_id = data.assigned_employee_id

    # Auto-resolve name → employee when no explicit ID is given
    if employee_id is None and data.assigned_to:
        employee = await get_or_create_employee(
            db,
            name=data.assigned_to,
            company_id=data.company_id,
        )
        employee_id = employee.id

    # Convert checkpoints list → JSON string
    checkpoints_json = None
    if data.checkpoints:
        checkpoints_json = json.dumps(
            [{"text": cp.strip(), "done": False} for cp in data.checkpoints if cp.strip()]
        )

    task = Task(
        company_id=data.company_id,
        title=data.title,
        description=data.description,
        assigned_to=data.assigned_to,
        assigned_employee_id=employee_id,
        owner_id=data.owner_id,
        due_at=data.due_at,
        status=TaskStatus.pending,
        source_type=SourceType(data.source_type),
        checkpoints=checkpoints_json,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def get_tasks(
    db: AsyncSession,
    company_id: int | None = None,
    status: str | None = None,
) -> list[Task]:
    """Return tasks, optionally filtered by company and/or status."""
    stmt = select(Task).order_by(Task.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(Task.company_id == company_id)
    if status is not None:
        stmt = stmt.where(Task.status == TaskStatus(status))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    """Return a single task by primary key."""
    return await db.get(Task, task_id)


async def update_task(db: AsyncSession, task_id: int, data: TaskUpdate) -> Task | None:
    """Partially update a task. Returns None if not found."""
    task = await db.get(Task, task_id)
    if task is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value is not None:
            value = TaskStatus(value)
        setattr(task, field, value)

    await db.flush()
    await db.refresh(task)
    return task
