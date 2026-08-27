"""Investor criteria — what an investor is looking for, and who they are.

CHANGE OF POLICY (client request): this table originally carried a hard rule
that it must never hold a name, phone, or email — enforced structurally (no
such columns) and at the API layer (regex rejection on label/areas/timeline).
That rule has been deliberately lifted. `name` is now a real, optional column,
and the API-layer rejection is gone — see app/routes/launch_matcher.py.

What is still true: there is no `phone` or `email` column, and none is
implied by this change — only a name was asked for. `label` remains the
advisor's own identifier (still commonly a shorthand like "Investor 4", but no
longer policed against looking like a name). `notes` was never restricted
either way. The forwarded-launch-message pipeline is untouched by this change:
inbound broadcasts are still never persisted anywhere (see
app/services/webhook_service.py and app/services/launch_matcher/handler.py),
so a footer with someone else's contact details still cannot leak into any
table via that path — that protection was always a separate mechanism from
this table's own field validation, and remains in place.

This is a separate feature from the broker CRM on this repo's real-estate
vertical (buyers/sellers/listings, which hold real contact details of their
own). The two share no tables and are gated on mutually exclusive vertical
values so a company can never be in both.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Emirate is the top-level match filter: an investor who wants Abu Dhabi is
# never shown a Dubai launch, whatever else lines up.
EMIRATES = ("Dubai", "Abu Dhabi", "RAK", "Sharjah", "Ajman", "Fujairah", "UAQ", "Other")

# What stage of build the investor will buy at.
OFF_PLAN_OR_READY = ("off_plan", "ready", "both")

# How the investor wants to pay.
#   cash         -- buys outright; imposes no requirement on the launch
#   payment_plan -- needs instalment terms; a launch with none is not a match
#   either       -- no preference
# A structured field on purpose: it is reason-worthy, so per the project rule
# it is a column, never something inferred from notes or timeline free text.
PAYMENT_PREFERENCE = ("cash", "payment_plan", "either")


class InvestorCriteria(Base):
    __tablename__ = "investor_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # The advisor's own identifier for this investor. Historically a shorthand
    # like "Investor 4" and still fine to use that way; no longer policed
    # against holding a real name — see the module docstring.
    label: Mapped[str] = mapped_column(String(80), nullable=False)

    # The investor's real name, when the advisor has it and chooses to store
    # it. Optional and nullable: existing rows predate this column and are not
    # backfilled. Used in the WhatsApp reply in preference to `label` when set
    # — see InvestorMatch.summary in app/services/launch_matcher/matcher.py.
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Top-level filter. Always set.
    emirate: Mapped[str] = mapped_column(String(20), nullable=False, server_default="Dubai")

    # Optional comma-separated area preferences ("Hartland, Meydan"). Empty
    # means no area constraint; when set, a launch outside those areas is not a
    # match rather than a weak one.
    areas: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")

    budget_min: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    budget_max: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    # Optional unit type: "1BR", "2BR", "studio", "villa", "townhouse".
    # Empty means no constraint.
    property_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")

    off_plan_or_ready: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="both"
    )

    # cash / payment_plan / either. See PAYMENT_PREFERENCE above.
    payment_preference: Mapped[str] = mapped_column(
        String(15), nullable=False, server_default="either"
    )

    # Free text the advisor writes for themselves: "Q4 2026", "after he sells
    # the Marina unit". Not parsed, not matched on.
    timeline: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")

    # The advisor's own shorthand. Deliberately never surfaced in the WhatsApp
    # reply and never matched against, so nothing about the design encourages
    # putting identifying detail here.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
