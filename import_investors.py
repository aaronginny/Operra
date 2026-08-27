"""Bulk-import investor_criteria records from a contact export.

Aaron runs this himself using Mahmoud's contact list -- Mahmoud never touches
this step; he only reviews/corrects the results afterward on the dashboard.

For each contact (name, phone, tag):
  * an empty/invalid name or phone skips the row (see importer.py for the
    exact checks -- e.g. a name that's just digits, or one that itself looks
    like a phone/email)
  * a tag containing a phrase like "wrong number", "blocked me", "no
    response", "don't send" (or similar -- see SKIP_PHRASES in importer.py)
    skips the row outright, even if the tag also mentions a real area
  * otherwise the tag is scanned for a recognisable emirate or area, reusing
    the launch parser's own EMIRATES/AREA_TO_EMIRATE tables, plus a small
    supplementary table of contact-tag shorthand (DXB, SHJ, AD, ...) --
    see the comment on _SHORT_CODE_EMIRATES in importer.py for why that
    table is kept separate from the parser's own
  * no emirate/area found -> skipped, not imported as junk
  * otherwise: one investor_criteria row is created with `name` (the real
    name) and a best-effort `emirate`/`areas`. budget_min, budget_max,
    off_plan_or_ready and payment_preference are left at their column
    defaults on purpose -- Mahmoud fills these in himself via the dashboard.

PHONE NUMBERS ARE NEVER STORED. Matching and the WhatsApp reply never read
one (see app/services/launch_matcher/matcher.py), so keeping them out avoids
PII exposure the feature has no use for. A phone number is only ever hashed,
transiently, to detect repeat runs -- see IDEMPOTENCY below. This script's
own results CSV omits phone too, for the same reason.

IDEMPOTENCY: re-running this on the same (or a superset of the same) contact
list will not create duplicate investor_criteria rows. This is tracked in a
local ledger file (--ledger-file) that stores a SHA-256 hash of each
imported contact's phone number -- never the number itself, and never
written to the database. Use a different --ledger-file for test runs vs. the
real one (or delete the test ledger first), so a test run's entries don't
block the real import later.

Known limitation: if an imported investor is later deleted from the
dashboard, re-running this script will NOT recreate it -- the ledger still
marks that contact as imported. That's deliberate (this script guarantees
"no duplicates on repeat runs", not "the database always mirrors the contact
list"), but worth knowing before relying on a rerun to undo a deletion.

INPUT FORMAT: a CSV or JSON file, one row/object per contact, with `name`,
`phone`, and `tag` (also accepts `notes` as a synonym for `tag`, since that's
the column name in many contact exports).

  CSV example:
    name,phone,tag
    Ahmed Al Maktoum,+971501234567,SHJ investor looking for villa
    Fatima Hassan,+971509876543,wrong number

  JSON example:
    [
      {"name": "Ahmed Al Maktoum", "phone": "+971501234567",
       "tag": "SHJ investor looking for villa"},
      {"name": "Fatima Hassan", "phone": "+971509876543", "tag": "wrong number"}
    ]

USAGE
-----
    # dry run against whatever DATABASE_URL is configured (defaults to this
    # project's local dev DB, same convention as the rest of the codebase):
    python import_investors.py --company-id 21 --file contacts.csv --dry-run

    # the real run, against production -- set DATABASE_URL to foreman-db
    # first (check Render's dashboard -> your Postgres -> Connections for an
    # external connection string, if your plan exposes one; if not, this
    # needs the same kind of temporary internal endpoint used for account
    # provisioning before -- ask for that if a direct connection isn't
    # available):
    DATABASE_URL=postgresql+asyncpg://... \\
      python import_investors.py --company-id 21 --file mahmoud_contacts.csv
"""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import async_session
from app.models.company import Company
from app.services.launch_matcher.importer import ContactRow, import_contacts


def load_contacts(path: Path) -> list[ContactRow]:
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

    contacts = []
    for row in rows:
        tag = row.get("tag")
        if tag is None:
            tag = row.get("notes", "")
        contacts.append(ContactRow(
            name=row.get("name", "") or "",
            phone=row.get("phone", "") or "",
            tag=tag or "",
        ))
    return contacts


def load_ledger(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_ledger(path: Path, ledger: dict) -> None:
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def write_results_csv(path: Path, summary) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "status", "reason", "emirate", "area", "investor_id"])
        for r in summary.results:
            writer.writerow([r.name, r.status, r.reason, r.emirate or "",
                              r.area or "", r.investor_id or ""])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True,
                     help="the launch_matcher company to import into")
    ap.add_argument("--file", required=True, help="CSV or JSON contact export")
    ap.add_argument("--ledger-file", default=".launch_matcher_import_ledger.json",
                     help="idempotency ledger; use a different one for test runs")
    ap.add_argument("--results-file", default=None,
                     help="optional CSV to write per-contact outcomes to "
                          "(default: import_results_<company-id>.csv)")
    ap.add_argument("--dry-run", action="store_true",
                     help="show what would happen, write nothing to the "
                          "database or the ledger")
    args = ap.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1

    ledger_path = Path(args.ledger_file)
    results_path = Path(args.results_file or f"import_results_{args.company_id}.csv")

    contacts = load_contacts(file_path)
    ledger = load_ledger(ledger_path)

    print("=" * 68)
    print("  Launch Matcher — investor bulk import")
    if args.dry_run:
        print("  DRY RUN — nothing will be written")
    print("=" * 68)
    print(f"  contacts file : {file_path} ({len(contacts)} rows)")
    print(f"  ledger file   : {ledger_path} ({len(ledger)} previously imported)")

    async with async_session() as db:
        company = await db.get(Company, args.company_id)
        if company is None:
            print(f"\nERROR: no company with id={args.company_id}", file=sys.stderr)
            return 1
        if company.vertical != "launch_matcher":
            print(f"\nERROR: company {args.company_id} ({company.name!r}) has "
                  f"vertical={company.vertical!r}, not 'launch_matcher'. "
                  "Refusing to import — this doesn't look like the intended "
                  "target.", file=sys.stderr)
            return 1
        print(f"  target company: {company.name!r} (id={company.id})\n")

        # A dry run works against its own throwaway copy of the ledger, so
        # nothing from it can ever be saved back to the real ledger file.
        working_ledger = dict(ledger) if args.dry_run else ledger

        def on_result(_result):
            if not args.dry_run:
                save_ledger(ledger_path, working_ledger)

        summary = await import_contacts(
            db, args.company_id, contacts, working_ledger,
            dry_run=args.dry_run, on_result=on_result,
        )

    summary.print_report()
    write_results_csv(results_path, summary)
    print(f"\n  per-contact detail written to: {results_path}")
    if args.dry_run:
        print("\n(dry run — nothing written to the database or the ledger)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
