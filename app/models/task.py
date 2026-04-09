"""Task model."""

import datetime
import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    delayed = "delayed"
    overdue = "overdue"
    needs_help = "needs_help"
    archived = "archived"



class SourceType(str, enum.Enum):
    whatsapp = "whatsapp"
    email = "email"
    dashboard = "dashboard"
    web = "web"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False), nullable=False, default=TaskStatus.pending
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False), nullable=False, default=SourceType.whatsapp
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Follow-up tracking — prevent repeated nudges
    last_followup_sent: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_urgent_reminder_sent: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Task intelligence tracking
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delayed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    help_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    notification_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    reminder_interval_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_update: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_update_summary: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Relationships
    assigned_employee = relationship("Employee", back_populates="tasks")
