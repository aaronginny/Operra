"""Pydantic schemas for User endpoints."""

from pydantic import BaseModel


class UserCreate(BaseModel):
    """Payload to create a user."""

    company_id: int
    name: str
    role: str = "employee"
    whatsapp_number: str | None = None
    email: str | None = None


class UserResponse(BaseModel):
    """Serialised user returned by the API."""

    id: int
    company_id: int
    name: str
    role: str
    whatsapp_number: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}
