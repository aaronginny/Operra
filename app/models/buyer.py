"""Buyer model — a purchase/rental lead in the real-estate vertical.

Ported from DealKnot's `buyers` table. Only active for companies with
`vertical = "real_estate"`; the generic PhantomPilot product never touches it.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dial: Mapped[str] = mapped_column(String(10), nullable=False, server_default="+91")
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="IN")

    # Comma-separated multi-area, exactly like DealKnot ("Adyar, Velachery").
    # Kept as free text rather than a join table so a broker can type an area
    # that isn't in the Chennai coordinate map — the matching engine falls back
    # to exact string comparison for those.
    areas: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")

    property_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="apt_resale")
    division: Mapped[str] = mapped_column(String(10), nullable=False, server_default="sales")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")

    # Budget range. DealKnot matches a seller price against this window (with a
    # 25% "stretch" band above budget_max), so both ends are required.
    budget_min: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    budget_max: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    # Rentals only: whether budget_min/max are quoted monthly or yearly.
    period: Mapped[str] = mapped_column(String(10), nullable=False, server_default="monthly")

    # Proximity search radius in km (1-50). Drives the Haversine fallback when
    # the buyer's area and the seller's area are not the same string.
    radius_km: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="5")

    label: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    referred_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
