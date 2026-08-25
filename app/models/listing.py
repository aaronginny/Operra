"""Listing model — a concrete property on the books.

A Seller is the *person*; a Listing is the *property*. DealKnot conflated the
two (its ListingsPage renders sellers), but PhantomPilot keeps them separate so
one owner can hold several properties. `seller_id` is optional so a listing can
be recorded before its owner is captured as a lead.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sellers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Single area here (not comma-separated): a property has one location.
    area: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    property_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="apt_resale")
    division: Mapped[str] = mapped_column(String(10), nullable=False, server_default="sales")

    price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    period: Mapped[str] = mapped_column(String(10), nullable=False, server_default="monthly")

    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_sqft: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # "available" | "under_offer" | "sold" | "withdrawn"
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="available")

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
