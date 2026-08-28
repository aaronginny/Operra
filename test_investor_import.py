"""Verification for the investor_criteria bulk-import feature.

Covers, against a throwaway database: classification (import vs. the three
skip categories), the emirate/area guess (parser tables + the supplementary
short-code table), that no phone number ever reaches a stored row, and
idempotency both at the importer-module level and through the real CLI
script end to end (subprocess), including the company vertical safety gate.

Same convention as the other test scripts here: a plain asyncio script, no
pytest, run directly. Set TEST_DATABASE_URL to run it against Postgres.

    python test_investor_import.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_investor_import.py
"""

import asyncio
import csv
import os
import subprocess
import sys

TEST_DB_PATH = "_test_investor_import.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")

os.environ["DATABASE_URL"] = TEST_DB_URL

from sqlalchemy import select, text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.investor_criteria import InvestorCriteria  # noqa: E402
from app.services.launch_matcher.importer import ContactRow, import_contacts  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


# ── Synthetic contact export (no real data) ─────────────────────────────
# 16 rows: 6 real leads across every guess path (short code, existing parser
# area table, existing parser emirate table, the case-sensitive 2-letter
# "AD" code), 2 with no recognisable keyword, 4 hit by a skip phrase (one of
# which also mentions "Dubai", to prove the phrase wins), 3 invalid rows, and
# a same-file repeat of row 1's phone number to prove in-run dedup.
CONTACTS = [
    ContactRow("Ahmed Al Maktoum", "+971501110001", "SHJ investor looking for villa"),
    ContactRow("Fatima Hassan", "+971501110002", "Interested in JVC 2BR"),
    ContactRow("Khalid Rahman", "+971501110003", "DXB studio buyer"),
    ContactRow("Sara Ali", "+971501110004", "AD - looking for apartment"),
    ContactRow("Yousef Nasser", "+971501110005", "Sharjah waterfront buyer"),
    ContactRow("Layla Omar", "+971501110006", "abu dhabi cash buyer"),
    ContactRow("Peter Old Colleague", "+971501110007", "old friend from university"),
    ContactRow("Random Contact", "+971501110008", ""),
    ContactRow("Bad Lead One", "+971501110009", "wrong number"),
    ContactRow("Bad Lead Two", "+971501110010", "blocked me on whatsapp"),
    ContactRow("Bad Lead Three", "+971501110011", "no response after 3 tries, Dubai buyer"),
    ContactRow("Bad Lead Four", "+971501110012", "don't send more messages"),
    ContactRow("971501234599", "+971501234599", "Dubai buyer"),
    ContactRow("", "+971501110014", "Dubai"),
    ContactRow("Valid Name No Phone", "", "Dubai"),
    ContactRow("Ahmed M.", "+971501110001", "Dubai too — same phone as row 1"),
]

EXPECTED_IMPORTED = {
    "Ahmed Al Maktoum": ("Sharjah", None),
    "Fatima Hassan": ("Dubai", "JVC"),
    "Khalid Rahman": ("Dubai", None),
    "Sara Ali": ("Abu Dhabi", None),
    "Yousef Nasser": ("Sharjah", "Sharjah Waterfront"),
    "Layla Omar": ("Abu Dhabi", None),
}


async def setup_db() -> dict:
    if IS_SQLITE:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    else:
        async with engine.begin() as conn:
            await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa_text("CREATE SCHEMA public"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    ctx: dict = {}
    async with SessionLocal() as db:
        mahmoud_co = Company(name="Mahmoud Advisory", vertical="launch_matcher")
        db.add(mahmoud_co)
        other_co = Company(name="Some Generic Co", vertical="generic")
        db.add(other_co)
        await db.flush()
        ctx["mahmoud_id"] = mahmoud_co.id
        ctx["other_id"] = other_co.id
        await db.commit()
    return ctx


async def investor_rows(company_id: int) -> list[InvestorCriteria]:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(InvestorCriteria).where(InvestorCriteria.company_id == company_id)
        )).scalars().all()
        return list(rows)


async def run_module_level_checks(company_id: int) -> None:
    print("\n== A. importer.import_contacts — classification, extraction, defaults ==")
    ledger: dict = {}
    async with SessionLocal() as db:
        summary = await import_contacts(db, company_id, CONTACTS, ledger)

    check("A1 total rows processed == 16", summary.total == 16, str(summary.total))
    check("A2 imported == 6", summary.imported == 6, str(summary.imported))
    check("A3 skipped_no_area == 2", summary.count("skipped_no_area") == 2,
          str(summary.count("skipped_no_area")))
    check("A4 skipped_bad_phrase == 4", summary.count("skipped_bad_phrase") == 4,
          str(summary.count("skipped_bad_phrase")))
    check("A5 skipped_invalid == 3 (empty name, no phone, bare-digits name)",
          summary.count("skipped_invalid") == 3, str(summary.count("skipped_invalid")))
    check("A6 skipped_duplicate == 1 (row 16 repeats row 1's phone)",
          summary.count("skipped_duplicate") == 1, str(summary.count("skipped_duplicate")))

    by_name = {r.name: r for r in summary.results}
    bad_phrase_names = {"Bad Lead One", "Bad Lead Two", "Bad Lead Three", "Bad Lead Four"}
    check("A7 all four bad-phrase contacts skipped, incl. the one that also says Dubai",
          all(by_name[n].status == "skipped_bad_phrase" for n in bad_phrase_names))

    check("A8 ledger now has exactly 6 entries (one per real import)", len(ledger) == 6,
          str(len(ledger)))

    rows = await investor_rows(company_id)
    check("A9 exactly 6 investor_criteria rows created", len(rows) == 6, str(len(rows)))

    row_by_name = {r.name: r for r in rows}
    for name, (emirate, area) in EXPECTED_IMPORTED.items():
        r = row_by_name.get(name)
        ok = r is not None and r.emirate == emirate and (r.areas or None) == area
        check(f"A10 {name!r} -> emirate={emirate!r} area={area!r}", ok,
              f"got emirate={r.emirate if r else None!r} area={r.areas if r else None!r}")

    check("A11 label == name for every imported row (import script's convention)",
          all(r.label == r.name for r in rows))
    check("A12 budget_min/budget_max left at column default (0)",
          all(float(r.budget_min) == 0 and float(r.budget_max) == 0 for r in rows))
    check("A13 off_plan_or_ready left at column default ('both')",
          all(r.off_plan_or_ready == "both" for r in rows))
    check("A14 payment_preference left at column default ('either')",
          all(r.payment_preference == "either" for r in rows))

    # Requirement 5: no phone number anywhere in what got stored.
    phone_fragments = ["971501110001", "971501110002", "5011100", "501110"]
    leaked = []
    for r in rows:
        haystack = " ".join(str(v) for v in (r.label, r.name, r.areas, r.notes) if v)
        for frag in phone_fragments:
            if frag in haystack:
                leaked.append((r.name, frag))
    check("A15 no phone-number fragment appears in any stored field", not leaked, str(leaked))

    print("\n== B. idempotency — rerunning the same batch creates nothing new ==")
    async with SessionLocal() as db:
        summary2 = await import_contacts(db, company_id, CONTACTS, ledger)
    check("B1 second run imports 0", summary2.imported == 0, str(summary2.imported))
    check("B2 second run's 6 previously-imported contacts now report skipped_duplicate",
          all(summary2.results[i].status == "skipped_duplicate"
              for i, c in enumerate(CONTACTS) if c.name in EXPECTED_IMPORTED))
    rows_after = await investor_rows(company_id)
    check("B3 row count unchanged after rerun (still 6, no duplicates)",
          len(rows_after) == 6, str(len(rows_after)))


def write_csv(path: str, contacts: list[ContactRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "phone", "tag"])
        for c in contacts:
            w.writerow([c.name, c.phone, c.tag])


def run_cli(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = TEST_DB_URL
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "import_investors.py", *args],
        capture_output=True, text=True, env=env,
    )


async def run_cli_checks(company_id: int, other_company_id: int) -> None:
    print("\n== C. the real CLI script (import_investors.py), end to end ==")
    csv_path = "_test_investor_import_contacts.csv"
    ledger_path = "_test_investor_import_ledger.json"
    results_path = "_test_investor_import_results.csv"
    for p in (csv_path, ledger_path, results_path):
        if os.path.exists(p):
            os.remove(p)
    write_csv(csv_path, CONTACTS)

    # C1: vertical gate refuses a non-launch_matcher company.
    proc = run_cli("--company-id", str(other_company_id), "--file", csv_path,
                    "--ledger-file", ledger_path, "--dry-run")
    check("C1 refuses a generic-vertical company (nonzero exit)", proc.returncode != 0,
          proc.stdout[-300:] + proc.stderr[-300:])
    rows = await investor_rows(other_company_id)
    check("C2 nothing created for the generic-vertical company", len(rows) == 0, str(len(rows)))

    # C3: --dry-run writes nothing.
    before = await investor_rows(company_id)
    proc = run_cli("--company-id", str(company_id), "--file", csv_path,
                    "--ledger-file", ledger_path, "--results-file", results_path,
                    "--dry-run")
    check("C3 dry run exits 0", proc.returncode == 0, proc.stdout + proc.stderr)
    after = await investor_rows(company_id)
    check("C4 dry run creates no rows", len(after) == len(before),
          f"before={len(before)} after={len(after)}")
    check("C5 dry run does not write a ledger file", not os.path.exists(ledger_path))

    # C6: the real run.
    proc = run_cli("--company-id", str(company_id), "--file", csv_path,
                    "--ledger-file", ledger_path, "--results-file", results_path)
    check("C6 real run exits 0", proc.returncode == 0, proc.stdout + proc.stderr)
    check("C7 stdout reports imported=6", "imported             : 6" in proc.stdout,
          proc.stdout)
    rows = await investor_rows(company_id)
    check("C8 real run created exactly 6 new rows via the CLI",
          len(rows) - len(before) == 6, f"before={len(before)} now={len(rows)}")
    check("C9 ledger file was written", os.path.exists(ledger_path))
    check("C10 results CSV was written", os.path.exists(results_path))

    # C11: rerunning the CLI with the same ledger imports nothing new.
    proc = run_cli("--company-id", str(company_id), "--file", csv_path,
                    "--ledger-file", ledger_path, "--results-file", results_path)
    check("C11 second CLI run exits 0", proc.returncode == 0, proc.stdout + proc.stderr)
    check("C12 second CLI run reports imported=0", "imported             : 0" in proc.stdout,
          proc.stdout)
    rows2 = await investor_rows(company_id)
    check("C13 row count unchanged after second CLI run", len(rows2) == len(rows),
          f"{len(rows)} -> {len(rows2)}")

    for p in (csv_path, ledger_path, results_path):
        if os.path.exists(p):
            os.remove(p)


async def main() -> None:
    print("=" * 68)
    print(f"  Investor bulk-import verification  (DB: {TEST_DB_URL})")
    print("=" * 68)

    ctx = await setup_db()
    await run_module_level_checks(ctx["mahmoud_id"])

    # A fresh company for the CLI section so the "6 real leads" arithmetic in
    # section A doesn't get entangled with section C's own counts.
    async with SessionLocal() as db:
        cli_co = Company(name="Mahmoud Advisory CLI", vertical="launch_matcher")
        db.add(cli_co)
        await db.flush()
        cli_co_id = cli_co.id
        await db.commit()

    await run_cli_checks(cli_co_id, ctx["other_id"])

    await engine.dispose()
    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass  # Windows may still hold the handle briefly; not a test failure

    print("\n" + "=" * 68)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = [r for r in results if r[0] == FAIL]
    print(f"  {passed}/{len(results)} checks passed")
    if failed:
        print("  FAILURES:")
        for status, name, detail in failed:
            print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
