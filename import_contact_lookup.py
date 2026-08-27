"""Bulk-import contact_lookup rows from a raw contact export.

Aaron runs this himself. This table is a raw contact pool purely for the
setup-screen autocomplete (see app/routes/launch_matcher.py's GET
/contact-lookup and the dashboard's investor-add modal) — it is never read by
matching or the WhatsApp reply (see test_contact_lookup.py, section D).

For each contact (name, phone):
  * an empty/invalid name or phone skips the row (empty name, name that's
    just digits, unusable phone — see contact_lookup_importer.py)
  * a name containing a phrase like "wrong number", "blocked me", "no
    response", "don't send", "switched off", "no res", "cnt reach", "not
    working", "no budget", "not in service" (or similar) skips the row
    outright, even if the name also contains an area keyword
  * otherwise the name is scanned for a recognisable emirate or area, reusing
    the launch parser's own EMIRATES/AREA_TO_EMIRATE tables, plus small
    supplementary tables for contact-shorthand codes (DXB, SHJ, AD, ...) and
    a few UAE development names (Masaar, ...) — see contact_signals.py
  * no emirate/area found -> skipped. This is also what filters out
    non-real-estate contacts (vet clinics, restaurants, ...) without any
    special business-name detection: a name with no real-estate/area keyword
    just never matches, so it's skipped the same way any other no-signal
    contact is
  * otherwise: one contact_lookup row is created with name, phone, and the
    best-effort emirate/area guess (area left null when only an emirate-level
    signal was found)

IDEMPOTENCY: contact_lookup has a unique (company_id, phone) constraint, and
this script dedupes against it directly — no ledger file needed (unlike the
investor_criteria importer, which never stores phone at all and so has
nothing to dedupe against in the database itself). Re-running this on the
same or a superset of the same export will not create duplicate rows.

INPUT FORMAT: this script accepts three shapes, auto-detected:
  1. CSV with `name`/`phone` header columns.
  2. Plain text, alternating lines: a name line, then its phone line
     (a line is treated as a phone if it looks like one — mostly digits,
     optionally with a leading + and spaces/dashes).
  3. Plain text, one contact per line, name and phone on the same line
     separated by a tab or 2+ spaces.

  NOTE: this was written from a description of the real export ("documents,
  ~2000 entries in 'Name' / '+phone number' pairs"), not from an actual
  sample file — if none of the three shapes above match what the real
  export looks like, this loader will need a quick adjustment once the
  actual file is available.

USAGE
-----
    python import_contact_lookup.py --company-id 21 --file contacts.txt --dry-run
    python import_contact_lookup.py --company-id 21 --file contacts.txt
"""

import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path

from app.database import async_session
from app.models.company import Company
from app.services.launch_matcher.contact_lookup_importer import (
    RawContact,
    import_contact_lookup,
)

_PHONE_LINE_RE = re.compile(r"^\+?[\d\s\-().]{7,}$")


def _looks_like_phone(line: str) -> bool:
    return bool(_PHONE_LINE_RE.match(line.strip()))


def load_contacts(path: Path) -> list[RawContact]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and {"name", "phone"} <= {
                (c or "").strip().lower() for c in reader.fieldnames
            }:
                return [
                    RawContact(name=row.get("name", "") or "", phone=row.get("phone", "") or "")
                    for row in reader
                ]

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8-sig").splitlines()]
    lines = [ln for ln in lines if ln]

    # Same-line pairs: "Name<tab or 2+ spaces>+phone".
    same_line_re = re.compile(r"^(.*?)(?:\t|  +)(\+?[\d\s\-().]{7,})$")
    if lines and all(same_line_re.match(ln) or _looks_like_phone(ln) for ln in lines[:20]):
        contacts = []
        for ln in lines:
            m = same_line_re.match(ln)
            if m:
                contacts.append(RawContact(name=m.group(1).strip(), phone=m.group(2).strip()))
        if contacts:
            return contacts

    # Fall back to alternating lines: name, then its phone.
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


def write_results_csv(path: Path, summary) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "status", "reason", "emirate", "area", "contact_id"])
        for r in summary.results:
            writer.writerow([r.name, r.status, r.reason, r.emirate or "",
                              r.area or "", r.contact_id or ""])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True,
                     help="the launch_matcher company to import into")
    ap.add_argument("--file", required=True, help="contact export (CSV or plain text)")
    ap.add_argument("--results-file", default=None,
                     help="optional CSV of per-contact outcomes "
                          "(default: contact_lookup_results_<company-id>.csv)")
    ap.add_argument("--dry-run", action="store_true",
                     help="show what would happen, write nothing")
    args = ap.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1

    results_path = Path(args.results_file or f"contact_lookup_results_{args.company_id}.csv")
    contacts = load_contacts(file_path)

    print("=" * 68)
    print("  Launch Matcher — contact lookup bulk import")
    if args.dry_run:
        print("  DRY RUN — nothing will be written")
    print("=" * 68)
    print(f"  contacts file : {file_path} ({len(contacts)} parsed)")

    async with async_session() as db:
        company = await db.get(Company, args.company_id)
        if company is None:
            print(f"\nERROR: no company with id={args.company_id}", file=sys.stderr)
            return 1
        if company.vertical != "launch_matcher":
            print(f"\nERROR: company {args.company_id} ({company.name!r}) has "
                  f"vertical={company.vertical!r}, not 'launch_matcher'. "
                  "Refusing to import.", file=sys.stderr)
            return 1
        print(f"  target company: {company.name!r} (id={company.id})\n")

        summary = await import_contact_lookup(db, args.company_id, contacts, dry_run=args.dry_run)

    summary.print_report()
    write_results_csv(results_path, summary)
    print(f"\n  per-contact detail written to: {results_path}")
    if args.dry_run:
        print("\n(dry run — nothing written to the database)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
