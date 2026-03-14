"""Pydantic schemas for Employee endpoints."""

from datetime import datetime

from pydantic import BaseModel


class EmployeeCreate(BaseModel):
    """Payload to create an employee."""

    name: str
    phone_number: str | None = None
    email: str | None = None
    is_active: bool = True
    company_id: int | None = None


class EmployeeResponse(BaseModel):
    """Serialised employee returned by the API."""

    id: int
    name: str
    phone_number: str | None = None
    email: str | None = None
    is_active: bool = True
    company_id: int | None = None
    created_at: datetime
    active_task_count: int = 0

    model_config = {"from_attributes": True}

