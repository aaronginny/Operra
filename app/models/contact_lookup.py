"""Contact lookup — a raw contact pool for the setup-screen autocomplete.

Deliberately a SEPARATE table from investor_criteria, with a different
privacy posture: investor_criteria is the table that matters for the
WhatsApp/matching pipeline and has been through two rounds of client-directed
PII narrowing (see that model's own docstring). This table is neither of
those things — it exists purely so Mahmoud can search his own contact list
while setting up an investor and have the form pre-fill itself. Nothing here
is ever read by the matcher or the WhatsApp reply (see
app/services/launch_matcher/matcher.py and formatter.py, neither of which
import this model at all — enforced by test_contact_lookup.py, not just this
docstring).

Because of that different purpose, phone numbers ARE stored here — the whole
point is Mahmoud can find a contact by the number he half-remembers. This is
explicitly not the same guarantee investor_criteria makes.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContactLookup(Base):
    __tablename__ = "contact_lookup"
    __table_args__ = (
        UniqueConstraint("company_id", "phone", name="uq_contact_lookup_company_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)

    # Best-effort guess from the contact's name at import time. Null means no
    # keyword matched — left unset rather than guessed wrong, per policy.
    emirate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    area: Mapped[str | None] = mapped_column(String(60), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
