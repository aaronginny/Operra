"""Bulk-import investor_criteria rows from a contact export.

Turns a batch of (name, phone, tag) contact rows — the shape of a typical
phone/CRM contact export — into investor_criteria rows, best-effort guessing
each investor's emirate/area from keywords in the free-text tag, and silently
skipping contacts that clearly aren't real-estate leads.

PHONE NUMBERS ARE NEVER PERSISTED. Nothing downstream of investor_criteria —
matching (see matcher.py) or the WhatsApp reply — reads a phone number, so
storing one would be pure PII exposure with no functional use. A phone number
is only ever hashed in memory to support idempotency (see IdempotencyLedger
below); the raw number never reaches the database or disk.

REUSE OF THE LAUNCH PARSER'S TABLES: EMIRATES and AREA_TO_EMIRATE (imported
from parser.py) are reused as-is — they are already the vetted, deployed
keyword tables for exactly this kind of "spot an emirate/area in some text"
job. They are NOT reused via parser.py's own _extract_emirate_and_area
function, because that function only reports one shot at each and this module
also needs to fold in a supplementary short-code table (see
_SHORT_CODE_EMIRATES) that is deliberately kept separate from parser.py's own
EMIRATES dict — see the comment on that table for why.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investor_criteria import InvestorCriteria
from app.services.launch_matcher.parser import AREA_DISPLAY, AREA_TO_EMIRATE, EMIRATES

# ── Skip rules ───────────────────────────────────────────────

# Substrings that mark a contact as clearly not worth importing, regardless of
# anything else in the tag — checked case-insensitively, and checked before
# area/emirate detection, so "wrong number, was asking about Dubai" is still
# skipped rather than imported because "Dubai" also appears.
SKIP_PHRASES = (
    "wrong number", "blocked me", "blocked", "no response", "not responding",
    "unresponsive", "don't send", "dont send", "do not send", "not interested",
    "spam", "do not contact", "dnc", "invalid number", "duplicate",
    "unsubscribe",
)

# Contact-tag shorthand for an emirate, e.g. how a broker jots a phone
# contact's tag ("DXB investor", "SHJ - 2BR"), as opposed to how an emirate
# would be named in a full launch-broadcast sentence. Deliberately NOT merged
# into parser.py's own EMIRATES table: that table backs the already-deployed
# launch-broadcast parser, where a bare 2-3 letter code risks matching inside
# unrelated prose. A contact tag is short, curated shorthand — a different
# risk profile — so the codes live here instead, and are only consulted after
# parser.py's own (longer, safer) tables have already had a chance to match.
# AUH, RAK and UAQ are skipped here because parser.py's EMIRATES already
# recognises them.
_SHORT_CODE_EMIRATES = {
    "DXB": "Dubai",
    "SHJ": "Sharjah",
    "AJM": "Ajman",
    "FUJ": "Fujairah",
    # AD is 2 letters and far too generic to trust case-insensitively (would
    # match inside "ad campaign", "add", ...). Matched literal-uppercase only.
    "AD": "Abu Dhabi",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")
_BARE_PHONE_RE = re.compile(r"^[\d\s\-+()]{7,}$")


def _guess_emirate_and_area(tag: str) -> tuple[str | None, str | None]:
    """Best-effort emirate/area guess from a contact tag.

    Checks, in order: a known area name (longest first, same approach as
    parser.py), then a known full/long-form emirate name, then the
    contact-tag-specific short-code table above. Returns (emirate, area) —
    area is None whenever only an emirate-level signal was found.
    """
    lowered = tag.lower()

    for name in sorted(AREA_TO_EMIRATE, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return AREA_TO_EMIRATE[name], AREA_DISPLAY.get(name, name.title())

    for name, canonical in sorted(EMIRATES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return canonical, None

    for code, canonical in _SHORT_CODE_EMIRATES.items():
        if len(code) == 2:
            if re.search(rf"\b{code}\b", tag):  # case-sensitive on purpose
                return canonical, None
        elif re.search(rf"\b{code}\b", tag, re.I):
            return canonical, None

    return None, None


def _skip_phrase(tag: str) -> str | None:
    lowered = tag.lower()
    for phrase in SKIP_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def _hash_phone(phone: str) -> str:
    """One-way digest used only for idempotency — never reversible to the
    original number, and never stored anywhere the number itself would be."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return hashlib.sha256(digits.encode()).hexdigest()


# ── Data shapes ──────────────────────────────────────────────

@dataclass
class ContactRow:
    name: str
    phone: str
    tag: str


@dataclass
class ImportResult:
    status: str  # imported | skipped_invalid | skipped_bad_phrase | skipped_no_area | skipped_duplicate
    name: str
    reason: str = ""
    investor_id: int | None = None
    emirate: str | None = None
    area: str | None = None


@dataclass
class ImportSummary:
    results: list[ImportResult] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def imported(self) -> int:
        return self.count("imported")

    def print_report(self) -> None:
        print(f"\n  total contacts       : {self.total}")
        print(f"  imported             : {self.imported}")
        print(f"  skipped (no area)    : {self.count('skipped_no_area')}")
        print(f"  skipped (bad phrase) : {self.count('skipped_bad_phrase')}")
        print(f"  skipped (duplicate)  : {self.count('skipped_duplicate')}")
        print(f"  skipped (invalid)    : {self.count('skipped_invalid')}")


# ── Core import logic ────────────────────────────────────────

async def import_contact(
    db: AsyncSession,
    company_id: int,
    contact: ContactRow,
    ledger: dict[str, dict],
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Classify and, if it qualifies, import one contact. Never raises for
    ordinary bad data — every rejection path returns a `skipped_*` result so
    one malformed row can't abort a batch.

    dry_run=True still flushes the row (so investor_id is real and the ledger
    is updated for accurate duplicate detection within the dry run) but rolls
    back instead of committing, so nothing is actually written."""
    name = (contact.name or "").strip()
    tag = (contact.tag or "").strip()
    phone = (contact.phone or "").strip()

    if not name:
        return ImportResult(status="skipped_invalid", name=name, reason="empty name")

    if len(name) > 80:
        return ImportResult(status="skipped_invalid", name=name,
                             reason="name too long for the label field (>80 chars)")

    if _BARE_PHONE_RE.match(name):
        return ImportResult(status="skipped_invalid", name=name,
                             reason="name field is just a phone number, not a real name")

    if not phone:
        return ImportResult(status="skipped_invalid", name=name,
                             reason="no phone number — cannot dedupe reliably")

    bad_phrase = _skip_phrase(tag)
    if bad_phrase:
        return ImportResult(status="skipped_bad_phrase", name=name,
                             reason=f"tag contains {bad_phrase!r}")

    emirate, area = _guess_emirate_and_area(tag)
    if not emirate:
        return ImportResult(status="skipped_no_area", name=name,
                             reason="no real-estate emirate/area keyword found in tag")

    phone_hash = _hash_phone(phone)
    if phone_hash in ledger:
        return ImportResult(
            status="skipped_duplicate", name=name,
            reason="already imported in a previous run",
            investor_id=ledger[phone_hash].get("investor_criteria_id"),
        )

    if _EMAIL_RE.search(name) or _PHONE_RE.search(name):
        return ImportResult(status="skipped_invalid", name=name,
                             reason="name looks like it contains a phone/email; "
                                    "cannot use it as the label")

    record = InvestorCriteria(
        company_id=company_id,
        label=name,
        name=name,
        emirate=emirate,
        areas=area or "",
        # budget_min, budget_max, off_plan_or_ready, payment_preference are
        # deliberately left unset — they fall back to the column defaults.
        # Mahmoud fills these in himself via the dashboard.
    )
    db.add(record)
    await db.flush()
    # Captured now, as a plain value: rollback (the dry-run path) expires ORM
    # objects, so record.id would no longer be safely readable afterward.
    investor_id = record.id

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    ledger[phone_hash] = {"investor_criteria_id": investor_id, "name": name}

    return ImportResult(status="imported", name=name, investor_id=investor_id,
                         emirate=emirate, area=area)


async def import_contacts(
    db: AsyncSession,
    company_id: int,
    contacts: list[ContactRow],
    ledger: dict[str, dict],
    *,
    dry_run: bool = False,
    on_result=None,
) -> ImportSummary:
    """Import a batch, committing after each row (unless dry_run) — so a
    crash partway through a large batch loses at most the one row in flight,
    not everything already written. Call on_result after each row (e.g. to
    persist the ledger incrementally) for the same reason."""
    summary = ImportSummary()
    for contact in contacts:
        try:
            result = await import_contact(db, company_id, contact, ledger,
                                           dry_run=dry_run)
        except Exception as exc:
            await db.rollback()
            result = ImportResult(status="skipped_invalid", name=contact.name,
                                   reason=f"unexpected error: {exc}")
        summary.results.append(result)
        if on_result:
            on_result(result)
    return summary
