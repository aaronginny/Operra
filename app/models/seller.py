"""Seller model — a listing owner / landlord in the real-estate vertical.

Same shape as Buyer (see app/models/buyer.py) but with a single asking
`price` instead of a budget range. Ported from DealKnot's `sellers` table.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dial: Mapped[str] = mapped_column(String(10), nullable=False, server_default="+91")
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="IN")

    # Comma-separated multi-area, as on Buyer.
    areas: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")

    property_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="apt_resale")
    division: Mapped[str] = mapped_column(String(10), nullable=False, server_default="sales")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")

    # Asking price (the "listing price" the buyer's budget window is tested against).
    price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    # Rentals only: whether `price` is quoted monthly or yearly.
    period: Mapped[str] = mapped_column(String(10), nullable=False, server_default="monthly")

    label: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    referred_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
