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

    # -- Product vertical --------------------------------------
    # "generic"     -- the default PhantomPilot task/enquiry product.
    # "real_estate" -- additionally unlocks the broker CRM (buyers, sellers,
    #                  listings, matching engine, commissions).
    # Every real-estate route, nav item and notification is gated on this
    # column, so an existing "generic" account sees no change whatsoever.
    # Both new and existing companies default to "generic" -- opting in is
    # always explicit.
    vertical: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="generic"
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
    # 7-day free trial expiry (set at signup; NULL for pre-trial accounts)
    trial_ends_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Cashfree Payment Gateway ──────────────────────────────
    cashfree_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="unpaid"
    )
