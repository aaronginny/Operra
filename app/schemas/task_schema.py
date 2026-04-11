"""Pydantic schemas for Task endpoints."""

from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    """Payload to create a task manually (outside the webhook flow)."""

    company_id: int
    title: str
    description: str | None = None
    assigned_to: str | None = None
    assigned_employee_id: int | None = None
    owner_id: int | None = None
    due_at: datetime | None = None
    source_type: str = "whatsapp"
    reminder_interval_days: int | None = None
    progress_percent: int = 0
    last_update: datetime | None = None
    checkpoints: list[str] | None = None  # e.g. ["Check logo", "Buy fabric"]
    project_id: int | None = None          # optional project grouping for billing


class TaskUpdate(BaseModel):
    """Payload to partially update a task."""

    title: str | None = None
    description: str | None = None
    assigned_to: str | None = None
    assigned_employee_id: int | None = None
    owner_id: int | None = None
    due_at: datetime | None = None
    status: str | None = None
    reminder_interval_days: int | None = None
    progress_percent: int | None = None
    last_update: datetime | None = None
    checkpoints: str | None = None  # Raw JSON string


class TaskResponse(BaseModel):
    """Serialised task returned by the API."""

    id: int
    company_id: int
    title: str
    description: str | None = None
    assigned_to: str | None = None
    assigned_employee_id: int | None = None
    owner_id: int | None = None
    due_at: datetime | None = None
    status: str
    source_type: str
    created_at: datetime
    reminder_interval_days: int | None = None
    progress_percent: int
    last_update: datetime | None = None
    last_update_summary: str | None = None
    checkpoints: str | None = None  # JSON string
    project_id: int | None = None

    model_config = {"from_attributes": True}


class OnboardTaskRequest(BaseModel):
    """Payload to onboard an employee and assign a task instantly."""

    employee_name: str
    phone_number: str
    title: str
    description: str | None = None
    due_at: datetime | None = None
    company_id: int = 1
