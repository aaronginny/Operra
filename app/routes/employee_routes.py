"""Employee CRUD routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.models.task import Task, TaskStatus
from app.schemas.employee_schema import EmployeeCreate, EmployeeResponse
from app.schemas.task_schema import TaskResponse
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser
from app.services.employee_service import normalize_phone_number

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.post("", response_model=EmployeeResponse, status_code=200)
async def create_or_update_employee(
    payload: EmployeeCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create an employee or update phone_number if name already exists."""     
    # Case-insensitive lookup by name
    stmt = select(Employee).where(
        sa_func.lower(Employee.name) == payload.name.strip().lower(),
        Employee.company_id == current_user.company_id
    )
    result = await db.execute(stmt)
    employee = result.scalars().first()

    if employee:
        # Update fields
        if payload.phone_number is not None:
            employee.phone_number = normalize_phone_number(payload.phone_number)
        if payload.email is not None:
            employee.email = payload.email
        employee.is_active = payload.is_active
        await db.flush()
        await db.refresh(employee)
        return employee

    # Create new
    normalized_phone = normalize_phone_number(payload.phone_number) if payload.phone_number else None
    logger.info("Creating employee: %s / %s", payload.name.strip(), normalized_phone)
    employee = Employee(
        name=payload.name.strip(),
        phone_number=normalized_phone,
        email=payload.email,
        company_id=current_user.company_id,
        is_active=payload.is_active,
    )
    db.add(employee)
    await db.flush()
    await db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Return all employees with active task count."""

    active_statuses = [
        TaskStatus.pending, TaskStatus.in_progress,
        TaskStatus.delayed, TaskStatus.needs_help, TaskStatus.overdue
    ]

    subq = (
        select(
            Task.assigned_employee_id,
            sa_func.count(Task.id).label("active_task_count")
        )
        .where(Task.status.in_(active_statuses))
        .where(Task.assigned_employee_id.is_not(None))
        .where(Task.company_id == current_user.company_id)
        .group_by(Task.assigned_employee_id)
        .subquery()
    )

    stmt = (
        select(Employee, sa_func.coalesce(subq.c.active_task_count, 0).label("active_task_count"))
        .outerjoin(subq, Employee.id == subq.c.assigned_employee_id)
        .where(Employee.company_id == current_user.company_id)
        .order_by(Employee.name)
    )

    result = await db.execute(stmt)

    employees = []
    for emp, count in result:
        emp.active_task_count = count
        employees.append(emp)

    return employees


@router.get("/{employee_id}")
async def get_employee(
    employee_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):   
    """Return a single employee and their assigned tasks."""
    
    employee = await db.get(Employee, employee_id)
    if not employee or employee.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")       

    stmt = (
        select(Task)
        .where(Task.assigned_employee_id == employee_id)
        .where(Task.company_id == current_user.company_id)
        .order_by(Task.created_at.desc())
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    return {
        "employee": EmployeeResponse.model_validate(employee).model_dump(),     
        "tasks": [TaskResponse.model_validate(t).model_dump() for t in tasks]   
    }
