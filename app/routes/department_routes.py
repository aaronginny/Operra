"""Department (team) CRUD routes.

Departments let a multi-business operator group employees and tasks by
business line (e.g. Logistics, Import & Export, Agriculture, Plywood,
Rentals & Leasing). All endpoints are scoped to the authenticated user's
company.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.department import Department
from app.models.employee import Employee
from app.models.task import Task
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["Departments"])


class DepartmentCreate(BaseModel):
    name: str


class DepartmentUpdate(BaseModel):
    name: str


class DepartmentResponse(BaseModel):
    id: int
    company_id: int | None = None
    name: str | None = None
    employee_count: int = 0

    model_config = {"from_attributes": True}


@router.get("", response_model=list[DepartmentResponse])
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all departments for the current company, with employee counts."""
    subq = (
        select(
            Employee.department_id,
            sa_func.count(Employee.id).label("employee_count"),
        )
        .where(Employee.company_id == current_user.company_id)
        .where(Employee.department_id.is_not(None))
        .group_by(Employee.department_id)
        .subquery()
    )

    stmt = (
        select(
            Department,
            sa_func.coalesce(subq.c.employee_count, 0).label("employee_count"),
        )
        .outerjoin(subq, Department.id == subq.c.department_id)
        .where(Department.company_id == current_user.company_id)
        .order_by(Department.name)
    )
    result = await db.execute(stmt)

    out = []
    for dept, count in result:
        dept.employee_count = count
        out.append(dept)
    return out


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new department for the current company."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name cannot be empty")

    # Avoid duplicate names (case-insensitive) within the same company
    existing = await db.execute(
        select(Department).where(
            Department.company_id == current_user.company_id,
            sa_func.lower(Department.name) == name.lower(),
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"Department '{name}' already exists")

    dept = Department(name=name, company_id=current_user.company_id)
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    dept.employee_count = 0
    logger.info("Department created: id=%s name=%r company=%s", dept.id, dept.name, current_user.company_id)
    return dept


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def rename_department(
    department_id: int,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename an existing department."""
    dept = await db.get(Department, department_id)
    if not dept or dept.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Department not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name cannot be empty")

    dept.name = name
    await db.flush()
    await db.refresh(dept)

    count = await db.execute(
        select(sa_func.count(Employee.id)).where(
            Employee.department_id == department_id
        )
    )
    dept.employee_count = count.scalar() or 0
    logger.info("Department renamed: id=%s name=%r", dept.id, dept.name)
    return dept


@router.delete("/{department_id}", status_code=200)
async def delete_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a department. Employees and tasks in it are unassigned (kept)."""
    dept = await db.get(Department, department_id)
    if not dept or dept.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Department not found")

    # Detach employees and tasks so the FK delete never orphans records.
    await db.execute(
        update(Employee)
        .where(Employee.department_id == department_id)
        .values(department_id=None)
    )
    await db.execute(
        update(Task)
        .where(Task.department_id == department_id)
        .values(department_id=None)
    )

    await db.delete(dept)
    await db.flush()
    logger.info("Department deleted: id=%s company=%s", department_id, current_user.company_id)
    return {"status": "deleted", "id": department_id}
