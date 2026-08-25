"""Commission model — brokerage earned on a closed deal.

Linked to an Enquiry (the pipeline record the deal came through) rather than
directly to a buyer/seller, per the merge spec: the enquiry is what moves to
the "Payment" kanban stage, and that's the moment a commission is booked.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enquiry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True, index=True
    )

    deal_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    # Brokerage as a percentage of deal_value (e.g. 2.00 = 2%).
    commission_percent: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, server_default="0")
    commission_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    # Split with a co-broker, as a percentage of commission_amount retained by
    # this company (100 = no split).
    split_percent: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, server_default="100")

    # Where the deal came from: "buyer_side" | "seller_side" | "both_sides" |
    # "referral" | "other". DealKnot recorded this as free text; constrained
    # here so the commissions summary can group on it.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="both_sides")

    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    # "Pending" | "Partial" | "Received" -- DealKnot's VALID_STATUSES.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="Pending")

    expected_date: Mapped[datetime.date | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_date: Mapped[datetime.date | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
