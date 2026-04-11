"""Company model."""

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
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
    # subscription_level: "free" | "basic" | "premium"
    subscription_level: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="free"
    )
    is_premium: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    tasks_created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # Premium subscription expiry (NULL = no expiry / lifetime)
    tier_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # JSON list of Project IDs unlocked via Basic per-project payments
    # e.g. "[1, 5, 12]"
    projects_paid: Mapped[str | None] = mapped_column(Text, nullable=True)
