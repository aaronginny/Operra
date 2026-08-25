"""User model."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    founder = "founder"
    employee = "employee"
    ceo = "ceo"

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Case-insensitive uniqueness on email. Emails are stored lowercased
        # (see auth_routes._normalize_email), so lower(email) matches each row
        # 1:1 — this index is the safety net that stops two accounts differing
        # only by letter case from ever being created, even if some future code
        # path forgets to normalize. NULL emails are exempt (multiple allowed).
        Index("ux_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), nullable=False, default=UserRole.employee
    )
    whatsapp_number: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    otp_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
