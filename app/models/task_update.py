"""TaskUpdate model — stores per-task progress updates from employees (UPDATE <text>)."""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskUpdate(Base):
    __tablename__ = "task_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    update_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
