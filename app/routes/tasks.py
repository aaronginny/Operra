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
from app.services.messaging_service import send_whatsapp_message, send_whatsapp_message_detailed
from app.services.task_service import create_task, get_task, get_tasks, update_task
from app.services.billing_service import (
    check_can_create_task,
    check_can_use_checkpoints,
    increment_task_count,
    get_billing_status,
)
from app.dependencies import get_current_user
from app.schemas.auth_schema import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", status_code=201)
async def create_task_endpoint(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a task manually."""
    payload.company_id = current_user.company_id

    # ── Tiered Billing Gatekeeper ─────────────────────────────
    try:
        await check_can_create_task(
            db,
            current_user.company_id,
            user_id=current_user.id,
            user_email=current_user.email,
            user_role=current_user.role,
            project_id=payload.project_id,
        )
    except ValueError as e:
        logger.warning(
            "POST /tasks 403 blocked: user_id=%s email=%r role=%r company=%s",
            current_user.id, current_user.email, current_user.role, current_user.company_id,
        )
        raise HTTPException(status_code=403, detail=str(e))

    task = await create_task(db, payload)

    # ── Increment usage counter ───────────────────────────────
    await increment_task_count(db, current_user.company_id)

    notify_status = "skipped"
    notify_reason: str | None = None

    if not task.assigned_employee_id:
        logger.info(
            "=== TASK NOTIFY SKIP === task_id=%s title=%r — no employee assigned",
            task.id, task.title,
        )
        notify_reason = "No employee assigned."
    else:
        employee = await db.get(Employee, task.assigned_employee_id)
        if not employee:
            notify_status = "failed"
            notify_reason = "Employee not found."
            logger.warning("Cannot notify: employee id=%s not found", task.assigned_employee_id)
        elif not employee.phone_number:
            notify_status = "failed"
            notify_reason = f"{employee.name} has no phone number on file."
            logger.warning("Cannot notify employee id=%s — no phone number", task.assigned_employee_id)
        else:
            due_str = (
                task.due_at.strftime("%b %d %I:%M %p").lstrip("0") if task.due_at else "No deadline"
            )
            desc_str = task.description or "No description"
            task_notification = (
                f"PhantomPilot - New Task Assigned\n\n"
                f"Task: {task.title}\n"
                f"Description: {desc_str}\n"
                f"Due: {due_str}\n\n"
                f"Reply with:\n"
                f"DONE - mark complete\n"
                f"HELP - request assistance\n"
                f"UPDATE <text> - send progress"
            )
            logger.info(
                "=== TASK NOTIFY === employee=%r phone_raw=%r task_id=%s title=%r",
                employee.name, employee.phone_number, task.id, task.title,
            )
            sent, err = await send_whatsapp_message_detailed(employee.phone_number, task_notification)
            task.notification_sent = sent
            await db.flush()

            if sent:
                notify_status = "sent"
                logger.info("Notification sent to %s at %s", employee.name, employee.phone_number)
            else:
                notify_status = "failed"
                notify_reason = err or "WhatsApp delivery failed (see server logs)."
                logger.error(
                    "NOTIFICATION FAILED for %s at %s — %s",
                    employee.name, employee.phone_number, err,
                )

    response = TaskResponse.model_validate(task).model_dump(mode="json")
    response["notify_status"] = notify_status
    response["notify_reason"] = notify_reason
    return response


@router.get("/archive")
async def list_archive(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List completed tasks for the current company with a days-until-deletion
    countdown. Tasks are auto-deleted 20 days after completion."""
    from datetime import timedelta
    from app.models.task import TaskStatus

    stmt = (
        select(Task)
        .where(
            Task.company_id == current_user.company_id,
            Task.status == TaskStatus.completed,
        )
        .order_by(Task.completed_at.desc().nullslast())
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    now = datetime.utcnow()
    out = []
    for t in tasks:
        completed = t.completed_at
        completed_naive = completed.replace(tzinfo=None) if completed and completed.tzinfo else completed
        days_left = None
        if completed_naive:
            elapsed = (now - completed_naive).days
            days_left = max(0, 20 - elapsed)

        employee_name = None
        if t.assigned_employee_id:
            emp = await db.get(Employee, t.assigned_employee_id)
            if emp:
                employee_name = emp.name

        out.append({
            "id": t.id,
            "title": t.title,
            "employee_name": employee_name or t.assigned_to,
            "completed_at": completed.isoformat() if completed else None,
            "days_until_deletion": days_left,
        })
    return out


@router.post("/{task_id}/restore")
async def restore_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Restore an archived (completed) task back to pending status and
    notify the assigned employee."""
    from app.models.task import TaskStatus

    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.pending
    task.completed_at = None
    task.progress_percent = 0
    await db.flush()
    await db.refresh(task)

    if task.assigned_employee_id:
        employee = await db.get(Employee, task.assigned_employee_id)
        if employee and employee.phone_number:
            msg = (
                f"🔄 Your manager has restored task: *{task.title}*\n\n"
                f"Please continue working on it."
            )
            await send_whatsapp_message(employee.phone_number, msg)
            logger.info("Restore notification sent to %s (task #%s)", employee.name, task.id)

    return {"status": "restored", "task_id": task.id}


@router.get("/billing-status")
async def billing_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the current company's billing/plan status for the dashboard."""
    return await get_billing_status(
        db,
        current_user.company_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_role=current_user.role,
    )


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
    """Partially update a task. Tracks manager edits (title/description/due_at)
    and notifies the assigned employee on WhatsApp with a diff of what changed.
    """
    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # ── Capture pre-edit snapshot for diffing ─────────────────────────
    before = {
        "title": task.title,
        "description": task.description,
        "due_at": task.due_at,
    }

    updated_task = await update_task(db, task_id, payload)

    # ── Diff only manager-visible fields ──────────────────────────────
    changes: list[str] = []
    if payload.title is not None and payload.title != before["title"]:
        changes.append(f"Title → {updated_task.title}")
    if payload.description is not None and payload.description != before["description"]:
        changes.append("Description updated")
    if payload.due_at is not None and payload.due_at != before["due_at"]:
        due_display = updated_task.due_at.strftime("%b %d, %I:%M %p").lstrip("0") if updated_task.due_at else "—"
        changes.append(f"Due date → {due_display}")

    if changes:
        updated_task.edited_at = datetime.utcnow()
        await db.flush()
        await db.refresh(updated_task)

        if updated_task.assigned_employee_id:
            employee = await db.get(Employee, updated_task.assigned_employee_id)
            if employee and employee.phone_number:
                change_summary = "\n".join(f"• {c}" for c in changes)
                msg = (
                    f"✏️ Your manager updated task: *{updated_task.title}*\n\n"
                    f"{change_summary}\n\n"
                    f"Please check your updated task details."
                )
                await send_whatsapp_message(employee.phone_number, msg)
                logger.info("Task edit notification sent to %s (task #%s)", employee.name, updated_task.id)

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
                f"PhantomPilot - Task Update\n\n"
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


@router.patch("/{task_id}/checkpoints/{index}/toggle")
async def toggle_checkpoint(
    task_id: int,
    index: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle a checkpoint's done status by its index (0-based).

    Used by the dashboard when the CEO manually clicks a checkbox.
    """
    import json as _json

    task = await get_task(db, task_id)
    if task is None or task.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Checkpoints are a paid feature (basic / premium only)
    can_use = await check_can_use_checkpoints(db, current_user.company_id, user_role=current_user.role)
    if not can_use:
        raise HTTPException(
            status_code=403,
            detail="Smart Checkpoints require a Basic or Premium plan. Upgrade to unlock.",
        )

    if not task.checkpoints:
        raise HTTPException(status_code=400, detail="Task has no checkpoints")

    try:
        cps = _json.loads(task.checkpoints)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid checkpoints data")

    if index < 0 or index >= len(cps):
        raise HTTPException(status_code=400, detail=f"Checkpoint index {index} out of range")

    cps[index]["done"] = not cps[index].get("done", False)
    task.checkpoints = _json.dumps(cps)
    await db.flush()
    await db.refresh(task)

    return task
