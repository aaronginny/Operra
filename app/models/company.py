"""Company model."""

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Tiered Billing ────────────────────────────────────────
    subscription_level: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="basic"
    )
    is_premium: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    tasks_created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
