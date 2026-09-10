"""Company model."""

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy import false as sa_false
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
    # A company has exactly one vertical, assigned once and deliberately by
    # the platform operator at account setup -- never a self-serve toggle a
    # client can flip. Known values today:
    #
    # "generic"        -- the default PhantomPilot task/enquiry product.
    # "real_estate"     -- additionally unlocks the broker CRM (buyers,
    #                      sellers, listings, matching engine, commissions).
    #                      Ported from DealKnot; built and Postgres-verified
    #                      but not yet activated for a live client.
    # "launch_matcher"  -- WhatsApp-only investor/launch matching for a
    #                      single Dubai real-estate advisor. No dashboard
    #                      screens beyond one-time setup; mutually exclusive
    #                      with "real_estate" by construction (see
    #                      app.dependencies.require_vertical).
    # "broker_intel"    -- WhatsApp-only market intel + daily content for a
    #                      Dubai broker: an AI-generated briefing on a
    #                      project/area on demand, and a daily ARTICLE /
    #                      FUN FACT caption. Entirely stateless -- it writes
    #                      no rows at all, not even its own, so it needs no
    #                      table and no migration (see
    #                      app.services.broker_intel.state for why, and what
    #                      would change if that is revisited).
    #
    # Every vertical-specific route, nav item, notification, and inbound
    # WhatsApp handler is gated on this column, so an existing "generic"
    # account sees no change whatsoever when a new vertical is added. Both
    # new and existing companies default to "generic" -- opting in is
    # always explicit.
    #
    # A vertical that needs to handle inbound WhatsApp messages or a daily
    # proactive nudge registers itself with app.verticals.registry (see
    # app.verticals.bootstrap for the list of what's currently registered)
    # rather than adding another hardcoded check keyed off this column's
    # value -- see app.services.webhook_service.dispatch_inbound and
    # app.services.reminder_service._send_vertical_daily_hooks.
    vertical: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="generic"
    )

    # ── Tiered Billing ────────────────────────────────────────
    # subscription_level: "free" | "basic" | "premium"
    subscription_level: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="free"
    )
    # server_default is the SQL literal false(), NOT the Python string
    # "false". As a string this renders DEFAULT 'false', which Postgres
    # parses correctly as boolean false but SQLite — which has no native
    # boolean — stores as the TEXT 'false' and reads back as a non-empty,
    # therefore TRUTHY, value. A brand-new company then read as premium on
    # SQLite and correctly non-premium on Postgres, so every local test of a
    # billing-gated feature was silently unreliable. false() renders 0 on
    # SQLite and false on Postgres.
    is_premium: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
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
