"""Analytics service — employee performance calculations."""

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


async def get_employee_performance(db: AsyncSession, company_id: int | None = None) -> list[dict]:
    """Calculate performance metrics for every employee who has tasks.

    Returns a list of dicts with:
      employee_id, employee_name, tasks_total, tasks_completed,
      tasks_delayed, help_requests, completion_rate, avg_delay_count
    """
    # Fetch all tasks with their employees in one query
    stmt = select(Task).where(Task.assigned_employee_id.isnot(None))
    if company_id is not None:
        stmt = stmt.where(Task.company_id == company_id)
    stmt = stmt.options(selectinload(Task.assigned_employee))
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # Group by employee
    by_employee: dict[int, dict] = {}

    for task in tasks:
        emp = task.assigned_employee
        if emp is None:
            continue

        if emp.id not in by_employee:
            by_employee[emp.id] = {
                "employee_id": emp.id,
                "employee_name": emp.name,
                "tasks_total": 0,
                "tasks_completed": 0,
                "tasks_delayed": 0,
                "help_requests": 0,
                "total_delay_count": 0,
                "on_time_completions": 0,
            }

        rec = by_employee[emp.id]
        rec["tasks_total"] += 1

        if task.status == TaskStatus.completed:
            rec["tasks_completed"] += 1
            # On-time if completed before or at deadline
            if task.due_at and task.completed_at:
                due = task.due_at.replace(tzinfo=None) if task.due_at.tzinfo else task.due_at
                done = task.completed_at.replace(tzinfo=None) if task.completed_at.tzinfo else task.completed_at
                if done <= due:
                    rec["on_time_completions"] += 1

        if (task.delayed_count or 0) > 0:
            rec["tasks_delayed"] += 1
            rec["total_delay_count"] += task.delayed_count or 0

        if task.help_requested:
            rec["help_requests"] += 1

    # Build final output
    results = []
    for rec in by_employee.values():
        total = rec["tasks_total"]
        completed = rec["tasks_completed"]
        completion_rate = round((completed / total * 100), 1) if total > 0 else 0.0

        results.append({
            "employee_id": rec["employee_id"],
            "employee_name": rec["employee_name"],
            "tasks_total": total,
            "tasks_completed": completed,
            "tasks_delayed": rec["tasks_delayed"],
            "help_requests": rec["help_requests"],
            "completion_rate": completion_rate,
            "on_time_completions": rec["on_time_completions"],
        })

    # Sort by completion rate descending
    results.sort(key=lambda r: r["completion_rate"], reverse=True)
    return results
