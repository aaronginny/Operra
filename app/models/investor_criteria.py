"""Investor criteria — what an investor is looking for, and nothing about who they are.

PII-FREE BY CONSTRUCTION. This table has no name, phone, or email column and
must never gain one. An investor is identified only by `label`, a string the
advisor chooses ("Investor 4"), which is deliberately meaningless outside their
own head.

If a future change appears to need an identity field here — to parse something,
to match on something, to format a reply — that is a signal the design has
drifted, not a reason to add the column. The reply format quotes labels only.

This is a separate feature from the broker CRM on this repo's real-estate
vertical (buyers/sellers/listings, which do hold real contact details). The two
share no tables and are gated on mutually exclusive vertical values so a
company can never be in both. There is deliberately no link of any kind between
this table and any contact/campaign data.
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

    # The advisor's own shorthand for this investor — "Investor 4", "the
    # Sharjah guy's brother". Never a real name; see the module docstring.
    label: Mapped[str] = mapped_column(String(80), nullable=False)

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
