"""Investor criteria — what an investor is looking for, and who they are.

POLICY HISTORY (client request, changed twice): this table originally carried
a hard rule that it must never hold a name, phone, or email — enforced
structurally (no such columns) and at the API layer (regex rejection on
label/areas/property_type/timeline). That rule was first lifted entirely, then
deliberately narrowed back down once the actual request became clear: the
client wants real names, not open phone/email entry across every field.

Where it stands now: `name` is a real, optional column — the one place a real
name belongs, with no pattern rejection, since rejecting phone/email patterns
there would defeat the field's purpose. `label`, `areas`, `property_type` and
`timeline` are guarded again exactly as they always were before any of this —
see `_reject_contact_details` in app/routes/launch_matcher.py, which is the
enforcement point (this file only defines the column). `notes` was never
restricted in any version of this policy — the advisor's own scratch space,
never policed.

There is still no `phone` or `email` column, and none is implied by any of
this — only a name was ever asked for. The forwarded-launch-message pipeline
is untouched throughout: inbound broadcasts are still never persisted anywhere
(see app/services/webhook_service.py and
app/services/launch_matcher/handler.py), so a footer with someone else's
contact details still cannot leak into any table via that path — that
protection was always a separate mechanism from this table's own field
validation, and remains in place regardless of what this table's own policy
does.

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

    # The advisor's own identifier for this investor — a shorthand like
    # "Investor 4", or any reference they prefer. Phone/email patterns are
    # rejected here (see _reject_contact_details in
    # app/routes/launch_matcher.py); a real name belongs in `name` below, not
    # here — see the module docstring for why.
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
