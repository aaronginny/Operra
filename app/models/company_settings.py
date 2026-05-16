"""CompanySettings model — per-company reminder configuration."""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    morning_pulse_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    morning_pulse_time: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default="09:00"
    )
    reminder_frequency_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="4"
    )
    reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
