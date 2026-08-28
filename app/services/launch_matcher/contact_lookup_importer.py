"""Bulk-import contact_lookup rows from a raw contact export.

Unlike the investor_criteria importer (app/services/launch_matcher/
importer.py), the input here has no separate tag field — the source data is
just (name, phone) pairs, so the name itself is the only text to guess an
emirate/area from, and phone numbers ARE stored (see contact_lookup's own
model docstring for why that's fine here and isn't for investor_criteria).

Because phone is stored, idempotency doesn't need the hash-ledger trick the
investor importer uses: a unique (company_id, phone) constraint on the table
itself is the dedupe key, checked against the DB directly.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_lookup import ContactLookup
from app.services.launch_matcher.contact_signals import (
    BARE_PHONE_RE,
    guess_emirate_and_area,
    skip_phrase,
)

MAX_NAME = 120

_PHONE_LINE_RE = re.compile(r"^\+?[\d\s\-().]{7,}$")


def _looks_like_phone(line: str) -> bool:
    return bool(_PHONE_LINE_RE.match(line.strip()))


def parse_contacts_text(text: str, *, is_csv: bool = False) -> list["RawContact"]:
    """Parse contact export text into RawContact rows. Auto-detects three
    shapes: CSV with name/phone header columns; same-line pairs ("Name<tab or
    2+ spaces>+phone"); or alternating lines (a name line, then its phone
    line). Shared by the CLI script (import_contact_lookup.py, which reads a
    local file) and the internal upload endpoint (which reads a POSTed file),
    so both take a raw export exactly the same way."""
    if is_csv:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames and {"name", "phone"} <= {
            (c or "").strip().lower() for c in reader.fieldnames
        }:
            return [
                RawContact(name=row.get("name", "") or "", phone=row.get("phone", "") or "")
                for row in reader
            ]

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    same_line_re = re.compile(r"^(.*?)(?:\t|  +)(\+?[\d\s\-().]{7,})$")
    if lines and all(same_line_re.match(ln) or _looks_like_phone(ln) for ln in lines[:20]):
        contacts = []
        for ln in lines:
            m = same_line_re.match(ln)
            if m:
                contacts.append(RawContact(name=m.group(1).strip(), phone=m.group(2).strip()))
        if contacts:
            return contacts

    contacts = []
    pending_name = None
    for ln in lines:
        if _looks_like_phone(ln):
            if pending_name is not None:
                contacts.append(RawContact(name=pending_name, phone=ln))
                pending_name = None
        else:
            pending_name = ln
    return contacts


def normalize_phone(phone: str) -> str:
    """Digits plus a single leading '+' if present — same convention as
    create_accounts.py's normalize_phone, so the same number always ends up
    stored the same way regardless of how the source formatted it."""
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    digits = cleaned.lstrip("+")
    return f"+{digits}" if cleaned.startswith("+") and digits else digits


@dataclass
class RawContact:
    name: str
    phone: str


@dataclass
class ContactImportResult:
    status: str  # imported | skipped_invalid | skipped_bad_phrase | skipped_no_area | skipped_duplicate
    name: str
    reason: str = ""
    contact_id: int | None = None
    emirate: str | None = None
    area: str | None = None


@dataclass
class ContactImportSummary:
    results: list[ContactImportResult] = field(default_factory=list)

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


async def _existing_phones(db: AsyncSession, company_id: int) -> set[str]:
    rows = (await db.execute(
        select(ContactLookup.phone).where(ContactLookup.company_id == company_id)
    )).scalars().all()
    return set(rows)


async def import_contact_lookup(
    db: AsyncSession,
    company_id: int,
    contacts: list[RawContact],
    *,
    dry_run: bool = False,
    on_result=None,
) -> ContactImportSummary:
    """Import a batch into contact_lookup, committing after each row (unless
    dry_run) — a crash partway through a ~2000-row batch loses at most the
    row in flight. Never raises for ordinary bad data — every rejection path
    is a `skipped_*` result so one malformed row can't abort the batch."""
    seen_phones = await _existing_phones(db, company_id)
    summary = ContactImportSummary()

    for contact in contacts:
        try:
            result = await _import_one(db, company_id, contact, seen_phones, dry_run=dry_run)
        except Exception as exc:
            await db.rollback()
            result = ContactImportResult(status="skipped_invalid", name=contact.name,
                                          reason=f"unexpected error: {exc}")
        summary.results.append(result)
        if on_result:
            on_result(result)

    return summary


async def _import_one(
    db: AsyncSession,
    company_id: int,
    contact: RawContact,
    seen_phones: set[str],
    *,
    dry_run: bool,
) -> ContactImportResult:
    name = (contact.name or "").strip()
    phone = normalize_phone(contact.phone or "")

    if not name:
        return ContactImportResult(status="skipped_invalid", name=name, reason="empty name")

    if len(name) > MAX_NAME:
        return ContactImportResult(status="skipped_invalid", name=name,
                                    reason=f"name too long (>{MAX_NAME} chars)")

    if BARE_PHONE_RE.match(name):
        return ContactImportResult(status="skipped_invalid", name=name,
                                    reason="name field is just a phone number, not a real name")

    if not phone:
        return ContactImportResult(status="skipped_invalid", name=name,
                                    reason="no usable phone number")

    bad_phrase = skip_phrase(name)
    if bad_phrase:
        return ContactImportResult(status="skipped_bad_phrase", name=name,
                                    reason=f"name contains {bad_phrase!r}")

    emirate, area = guess_emirate_and_area(name)
    if not emirate:
        return ContactImportResult(status="skipped_no_area", name=name,
                                    reason="no real-estate emirate/area keyword found in name")

    if phone in seen_phones:
        return ContactImportResult(status="skipped_duplicate", name=name,
                                    reason="already imported (same phone number)")

    record = ContactLookup(
        company_id=company_id, name=name, phone=phone, emirate=emirate, area=area,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        # Defense in depth against the (company_id, phone) unique constraint
        # racing the in-memory seen_phones check — shouldn't happen given
        # this function is only ever awaited sequentially, but a duplicate is
        # a skip, not a crash, either way.
        await db.rollback()
        return ContactImportResult(status="skipped_duplicate", name=name,
                                    reason="already imported (same phone number)")

    contact_id = record.id

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    seen_phones.add(phone)

    return ContactImportResult(status="imported", name=name, contact_id=contact_id,
                                emirate=emirate, area=area)
