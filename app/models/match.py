"""Match model — a persisted buyer<->seller pairing found by the matching engine.

DealKnot recomputed matches on every GET /matches and never stored them. That
works for a single-broker SPA, but PhantomPilot needs them persisted for two
reasons: the WhatsApp hook must know which matches are *new* (so a broker isn't
re-notified about the same pair every run), and the morning pulse reports
"matches found overnight", which needs a created_at to count against.

See app/services/matching_service.py for how these rows are produced.
"""

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        # One row per (company, buyer, seller). The engine re-runs whenever a
        # buyer or seller is added, so this is what makes re-runs idempotent
        # and keeps the "new match" WhatsApp hook from firing twice.
        UniqueConstraint("company_id", "buyer_id", "seller_id", name="uq_matches_company_buyer_seller"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    buyer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("buyers.id"), nullable=False, index=True
    )
    seller_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sellers.id"), nullable=False, index=True
    )

    # How the *areas* matched: "exact" (same area string) or "proximity"
    # (different areas within the buyer's radius, per Haversine).
    match_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default="exact")
    # Haversine distance in km. 0 for an exact area match.
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")

    # How the *price* matched: "exact" (inside budget) or "stretch" (up to 25%
    # over budget_max). Kept separate from match_type -- DealKnot treats area
    # and price as two independent quality axes and sorts on both.
    price_match_kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="exact")
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Which of the comma-separated areas actually matched (for the UI badge).
    matched_buyer_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_seller_area: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Broker has introduced the two parties (DealKnot's `connections` table).
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Set once the "new match" WhatsApp notification has gone out, so the
    # notification fires exactly once per match.
    notified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
