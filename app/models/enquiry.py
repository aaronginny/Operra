"""Enquiry model."""

import datetime
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EnquiryStatus(str, enum.Enum):
    new = "new"
    assigned = "assigned"
    done = "done"


class EnquiryStage(str, enum.Enum):
    follow_up = "follow_up"
    send_options = "send_options"
    close_deal = "close_deal"
    payment_received = "payment_received"
    done = "done"


# Ordered list for stage progression
STAGE_ORDER = [
    EnquiryStage.follow_up,
    EnquiryStage.send_options,
    EnquiryStage.close_deal,
    EnquiryStage.payment_received,
    EnquiryStage.done,
]

# WhatsApp message template for each stage (sent to the assigned employee)
STAGE_MESSAGES = {
    EnquiryStage.follow_up: "PhantomPilot - Enquiry Update\n\nPlease follow up with {client_name}.",
    EnquiryStage.send_options: "PhantomPilot - Enquiry Update\n\nPlease send service options to {client_name}.",
    EnquiryStage.close_deal: "PhantomPilot - Enquiry Update\n\nPlease close the deal with {client_name}.",
    EnquiryStage.payment_received: "PhantomPilot - Enquiry Update\n\nPayment received from {client_name}. Job confirmed!",
}


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=False
    )
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_requested: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EnquiryStatus] = mapped_column(
        Enum(EnquiryStatus, native_enum=False), nullable=False, default=EnquiryStatus.new
    )
    stage: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=None
    )
    assigned_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id"), nullable=True
    )
    # JSON string: [{"stage": "follow_up", "at": "2026-04-10T12:00:00"}, ...]
    stage_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
