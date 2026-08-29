"""Verification for the contact_lookup bulk-import + autocomplete feature.

Runs the real FastAPI app over ASGI against a throwaway database, same
convention as test_launch_matcher.py. Covers:
  A. import classification, emirate/area extraction (incl. the new phrases
     and the Masaar/La Foret/Al Barari supplementary areas), in-batch dedup
  B. idempotency — DB-level, both at the module level and through the real
     CLI script end to end (subprocess)
  C. the autocomplete endpoint — prefix name match, phone substring match,
     per-company isolation, result shape
  D. contact_lookup is invisible to matching/WhatsApp — a static source check
     plus a live build_reply() call proving a contact_lookup-only name/phone
     never appears in a reply

Plain asyncio script, no pytest, run directly. Set TEST_DATABASE_URL to run
against Postgres.

    python test_contact_lookup.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_contact_lookup.py
"""

import asyncio
import csv
import os
import subprocess
import sys

TEST_DB_PATH = "_test_contact_lookup.db"
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_SQLITE_URL
IS_SQLITE = TEST_DB_URL.startswith("sqlite")

os.environ["DATABASE_URL"] = TEST_DB_URL

import httpx  # noqa: E402
from sqlalchemy import select, text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(TEST_DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.database import Base, get_db  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import app  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.contact_lookup import ContactLookup  # noqa: E402
from app.models.investor_criteria import InvestorCriteria  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import create_access_token  # noqa: E402
from app.services.launch_matcher.contact_lookup_importer import (  # noqa: E402
    RawContact,
    import_contact_lookup,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Synthetic contact export (no real data) ─────────────────────────────
# 16 rows, "Name" then "+phone" alternating — the shape described for the
# real export. Covers: short codes (SHJ/DXB/AD), an existing parser area
# (JVC), an existing parser emirate (abu dhabi), the supplementary areas
# (Masaar -> Sharjah, La Foret -> Abu Dhabi, Al Barari -> Dubai — the last
# corrected from the original brief's Sharjah claim, confirmed by Aaron),
# every new skip phrase from this task (switched off / no res / cnt reach /
# not working / no budget / not in service), a non-real-estate business name
# with no keyword at all, invalid rows, and a same-file repeat phone to prove
# in-batch dedup.
CONTACTS = [
    RawContact("Ahmed SHJ Buyer", "+971502220001"),
    RawContact("Fatima - JVC 2BR", "+971502220002"),
    RawContact("Khalid DXB Studio", "+971502220003"),
    RawContact("Sara AD Investor", "+971502220004"),
    RawContact("Yousef Masaar Villa", "+971502220005"),
    RawContact("Layla abu dhabi cash", "+971502220006"),
    RawContact("Omar La Foret AUH", "+971502220007"),
    RawContact("Noor Al Barari Buyer", "+971502220008"),
    RawContact("City Vet Clinic", "+971502220009"),        # no keyword -> skip
    RawContact("Rashid - blocked me", "+971502220010"),
    RawContact("Tariq switched off", "+971502220011"),
    RawContact("Hana no res", "+971502220012"),
    RawContact("Bilal cnt reach Dubai", "+971502220013"),  # phrase wins over "Dubai"
    RawContact("Salim not working", "+971502220014"),
    RawContact("Amir not in service", "+971502220015"),
    RawContact("Ahmed SHJ Buyer Two", "+971502220001"),    # same phone as row 1
]

EXPECTED_IMPORTED = {
    "Ahmed SHJ Buyer": ("Sharjah", None),
    "Fatima - JVC 2BR": ("Dubai", "JVC"),
    "Khalid DXB Studio": ("Dubai", None),
    "Sara AD Investor": ("Abu Dhabi", None),
    "Yousef Masaar Villa": ("Sharjah", "Masaar"),
    "Layla abu dhabi cash": ("Abu Dhabi", None),
    "Omar La Foret AUH": ("Abu Dhabi", "La Foret"),  # "AUH" and "la foret" agree
    "Noor Al Barari Buyer": ("Dubai", "Al Barari"),
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
        other_lm_co = Company(name="Other Advisor", vertical="launch_matcher")
        db.add(other_lm_co)
        generic_co = Company(name="Some Generic Co", vertical="generic")
        db.add(generic_co)
        await db.flush()

        mahmoud = User(company_id=mahmoud_co.id, name="Mahmoud", email="mahmoud@example.com",
                        role=UserRole.ceo, whatsapp_number="+971585888455")
        db.add(mahmoud)
        other_user = User(company_id=other_lm_co.id, name="Other", email="other@example.com",
                           role=UserRole.ceo, whatsapp_number="+971500000099")
        db.add(other_user)
        await db.flush()

        ctx.update(
            mahmoud_id=mahmoud_co.id, other_lm_id=other_lm_co.id, generic_id=generic_co.id,
            mahmoud_token=create_access_token({
                "sub": mahmoud.email, "user_id": mahmoud.id,
                "company_id": mahmoud_co.id, "role": "ceo", "name": mahmoud.name}),
            other_token=create_access_token({
                "sub": other_user.email, "user_id": other_user.id,
                "company_id": other_lm_co.id, "role": "ceo", "name": other_user.name}),
        )
        await db.commit()
    return ctx


async def contact_rows(company_id: int) -> list[ContactLookup]:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(ContactLookup).where(ContactLookup.company_id == company_id)
        )).scalars().all()
        return list(rows)


async def run_import_checks(company_id: int) -> None:
    print("\n== A. contact_lookup_importer — classification, extraction, dedup ==")
    async with SessionLocal() as db:
        summary = await import_contact_lookup(db, company_id, CONTACTS)

    check("A1 total rows processed == 16", summary.total == 16, str(summary.total))
    check("A2 imported == 8", summary.imported == 8, str(summary.imported))
    check("A3 skipped_no_area == 1 (vet clinic only, now Barari is recognised)",
          summary.count("skipped_no_area") == 1, str(summary.count("skipped_no_area")))
    check("A4 skipped_bad_phrase == 6 (incl. the one that also says Dubai)",
          summary.count("skipped_bad_phrase") == 6, str(summary.count("skipped_bad_phrase")))
    check("A5 skipped_duplicate == 1 (row 16 repeats row 1's phone)",
          summary.count("skipped_duplicate") == 1, str(summary.count("skipped_duplicate")))

    by_name = {r.name: r for r in summary.results}
    check("A6 'Noor Al Barari Buyer' imported as Dubai / Al Barari (corrected mapping)",
          by_name["Noor Al Barari Buyer"].status == "imported"
          and by_name["Noor Al Barari Buyer"].emirate == "Dubai"
          and by_name["Noor Al Barari Buyer"].area == "Al Barari")
    check("A7 'Bilal cnt reach Dubai' skipped as bad_phrase despite mentioning Dubai",
          by_name["Bilal cnt reach Dubai"].status == "skipped_bad_phrase")
    for n in ["Tariq switched off", "Hana no res", "Salim not working", "Amir not in service"]:
        check(f"A7b {n!r} skipped as bad_phrase (new phrase set)",
              by_name[n].status == "skipped_bad_phrase")

    rows = await contact_rows(company_id)
    check("A8 exactly 8 contact_lookup rows created", len(rows) == 8, str(len(rows)))

    row_by_name = {r.name: r for r in rows}
    for name, (emirate, area) in EXPECTED_IMPORTED.items():
        r = row_by_name.get(name)
        ok = r is not None and r.emirate == emirate and r.area == area
        check(f"A9 {name!r} -> emirate={emirate!r} area={area!r}", ok,
              f"got emirate={r.emirate if r else None!r} area={r.area if r else None!r}")

    check("A10 phone IS stored here (unlike investor_criteria)",
          all(r.phone for r in rows) and
          row_by_name["Ahmed SHJ Buyer"].phone == "+971502220001")

    print("\n== B. idempotency — DB-level rerun creates nothing new ==")
    async with SessionLocal() as db:
        summary2 = await import_contact_lookup(db, company_id, CONTACTS)
    check("B1 second run imports 0", summary2.imported == 0, str(summary2.imported))
    rows_after = await contact_rows(company_id)
    check("B2 row count unchanged after rerun (still 8)", len(rows_after) == 8,
          str(len(rows_after)))


def write_contacts_txt(path: str, contacts: list[RawContact]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in contacts:
            f.write(c.name + "\n")
            f.write(c.phone + "\n")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = TEST_DB_URL
    return subprocess.run(
        [sys.executable, "import_contact_lookup.py", *args],
        capture_output=True, text=True, env=env,
    )


async def run_cli_checks(company_id: int, generic_company_id: int) -> None:
    print("\n== C. the real CLI script (import_contact_lookup.py), end to end ==")
    txt_path = "_test_contact_lookup_contacts.txt"
    results_path = "_test_contact_lookup_results.csv"
    for p in (txt_path, results_path):
        if os.path.exists(p):
            os.remove(p)
    write_contacts_txt(txt_path, CONTACTS)

    proc = run_cli("--company-id", str(generic_company_id), "--file", txt_path, "--dry-run")
    check("C1 refuses a generic-vertical company (nonzero exit)", proc.returncode != 0)

    before = await contact_rows(company_id)
    proc = run_cli("--company-id", str(company_id), "--file", txt_path,
                    "--results-file", results_path, "--dry-run")
    check("C2 dry run exits 0", proc.returncode == 0, proc.stdout + proc.stderr)
    after = await contact_rows(company_id)
    check("C3 dry run creates no rows", len(after) == len(before),
          f"before={len(before)} after={len(after)}")

    proc = run_cli("--company-id", str(company_id), "--file", txt_path,
                    "--results-file", results_path)
    check("C4 real run exits 0", proc.returncode == 0, proc.stdout + proc.stderr)
    check("C5 stdout reports imported=8", "imported             : 8" in proc.stdout, proc.stdout)
    rows = await contact_rows(company_id)
    check("C6 real run created exactly 8 new rows via the CLI",
          len(rows) - len(before) == 8, f"before={len(before)} now={len(rows)}")
    check("C7 results CSV was written", os.path.exists(results_path))

    proc = run_cli("--company-id", str(company_id), "--file", txt_path,
                    "--results-file", results_path)
    check("C8 second CLI run reports imported=0",
          "imported             : 0" in proc.stdout, proc.stdout)
    rows2 = await contact_rows(company_id)
    check("C9 row count unchanged after second CLI run", len(rows2) == len(rows),
          f"{len(rows)} -> {len(rows2)}")

    for p in (txt_path, results_path):
        if os.path.exists(p):
            os.remove(p)


async def run_autocomplete_checks(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n== D. autocomplete endpoint — GET /launch-matcher/contact-lookup ==")

    # A contact only in the OTHER company, to prove isolation.
    async with SessionLocal() as db:
        db.add(ContactLookup(company_id=ctx["other_lm_id"], name="Ahmed SHJ Other Co",
                              phone="+971502220099", emirate="Sharjah"))
        await db.commit()

    res = await client.get("/launch-matcher/contact-lookup?q=Ahmed",
                            headers=auth(ctx["mahmoud_token"]))
    check("D1 name-prefix search returns 200", res.status_code == 200, res.text)
    names = [c["name"] for c in res.json()]
    check("D2 finds Mahmoud's own 'Ahmed SHJ Buyer'", "Ahmed SHJ Buyer" in names, str(names))
    check("D3 does NOT return the other company's 'Ahmed SHJ Other Co'",
          "Ahmed SHJ Other Co" not in names, str(names))

    res = await client.get("/launch-matcher/contact-lookup?q=971502220003",
                            headers=auth(ctx["mahmoud_token"]))
    check("D4 phone-substring search returns 200", res.status_code == 200, res.text)
    phone_names = [c["name"] for c in res.json()]
    check("D5 phone search finds 'Khalid DXB Studio'",
          "Khalid DXB Studio" in phone_names, str(phone_names))

    res = await client.get("/launch-matcher/contact-lookup?q=Fatima",
                            headers=auth(ctx["mahmoud_token"]))
    hit = next((c for c in res.json() if c["name"] == "Fatima - JVC 2BR"), None)
    check("D6 result includes phone/emirate/area for prefill",
          hit is not None and hit["phone"] == "+971502220002"
          and hit["emirate"] == "Dubai" and hit["area"] == "JVC",
          str(hit))

    res = await client.get("/launch-matcher/contact-lookup?q=zz-no-such-contact",
                            headers=auth(ctx["mahmoud_token"]))
    check("D7 no match -> empty list, still 200", res.status_code == 200 and res.json() == [])

    res = await client.get("/launch-matcher/contact-lookup?q=Ahmed", headers=auth(ctx["other_token"]))
    other_names = [c["name"] for c in res.json()]
    check("D8 the other company sees only its own contact via this endpoint",
          other_names == ["Ahmed SHJ Other Co"], str(other_names))


def run_fallback_tier_checks() -> None:
    """FALLBACK_EMIRATE_HINTS must sit below every other tier.

    These words (Astro/Shomous/Aludra/Kawther — confirmed Dubai) recur in
    this advisor's contact naming, but 14 contacts in the real list pair one
    of them with a Sharjah signal. If the fallback were promoted to the area
    tier it would flip all 14 to Dubai, so the ordering is the thing actually
    under test here, not just the lookup.
    """
    print("\n== F. fallback emirate hints — recognised, but lowest priority ==")
    from app.services.launch_matcher.contact_signals import guess_emirate_and_area as g

    check("F1 a bare fallback word resolves to Dubai with no area",
          g("Alaa Shomous") == ("Dubai", None), str(g("Alaa Shomous")))
    check("F2 'Khaled Azizi Kawther' -> Dubai", g("Khaled Azizi Kawther") == ("Dubai", None),
          str(g("Khaled Azizi Kawther")))
    check("F3 'Samar Azizi ALUDRA' -> Dubai (case-insensitive)",
          g("Samar Azizi ALUDRA") == ("Dubai", None), str(g("Samar Azizi ALUDRA")))

    # The load-bearing cases: a stronger signal must still win.
    check("F4 'Ahmed SHJ Azizi Kawther' stays Sharjah (SHJ beats the fallback)",
          g("Ahmed SHJ Azizi Kawther") == ("Sharjah", None),
          str(g("Ahmed SHJ Azizi Kawther")))
    check("F5 'Masaar Corner Astro' stays Sharjah/Masaar (area beats the fallback)",
          g("Masaar Corner Astro") == ("Sharjah", "Masaar"), str(g("Masaar Corner Astro")))
    check("F6 'Sadaf SHJ & Ajman Astro' keeps its emirate, not Dubai",
          g("Sadaf SHJ & Ajman Astro")[0] in ("Sharjah", "Ajman"),
          str(g("Sadaf SHJ & Ajman Astro")))
    check("F7 'Najib SHJ Astro Aljada 3BR' stays Sharjah/Aljada",
          g("Najib SHJ Astro Aljada 3BR") == ("Sharjah", "Aljada"),
          str(g("Najib SHJ Astro Aljada 3BR")))

    # Words deliberately NOT added stay unmatched.
    check("F8 'Shomokh Tarek Elie Saab' still unmatched (a name, not Shomous)",
          g("Shomokh Tarek Elie Saab") == (None, None), str(g("Shomokh Tarek Elie Saab")))
    check("F9 'Shomo5y Lagoons LCR' still unmatched (variant not confirmed)",
          g("Shomo5y Lagoons LCR") == (None, None), str(g("Shomo5y Lagoons LCR")))


async def run_isolation_checks(company_id: int) -> None:
    print("\n== E. contact_lookup is invisible to matching/WhatsApp ==")

    import inspect

    from app.services.launch_matcher import formatter, handler, matcher, providers

    source = "".join(
        inspect.getsource(m) for m in (matcher, formatter, handler, providers)
    )
    check("E1 'ContactLookup' never referenced in matcher/formatter/handler/providers",
          "ContactLookup" not in source and "contact_lookup" not in source)

    # Behavioural check: a contact_lookup row with a distinctive name/phone,
    # PLUS a real investor_criteria lead in the same area, then run a real
    # launch broadcast through build_reply and confirm the contact_lookup
    # data never appears -- proving it by outcome, not just by import graph.
    from app.services.launch_matcher.handler import build_reply
    from app.services.launch_matcher.providers import InboundMessage

    DISTINCTIVE_NAME = "Zzz Contact Lookup Only Person"
    DISTINCTIVE_PHONE = "+971509998887"

    async with SessionLocal() as db:
        db.add(ContactLookup(company_id=company_id, name=DISTINCTIVE_NAME,
                              phone=DISTINCTIVE_PHONE, emirate="Dubai", area="JVC"))
        db.add(InvestorCriteria(company_id=company_id, label="Isolation Test Investor",
                                 name="Isolation Test Investor", emirate="Dubai",
                                 areas="JVC"))
        await db.commit()

    async with SessionLocal() as db:
        message = InboundMessage(sender="isolation-test", text="Bayview JVC | 1BR from AED 1.2M")
        reply, outcome = await build_reply(db, company_id, message)

    check("E2 build_reply still matches normally with contact_lookup rows present",
          bool(outcome and outcome.matched))
    check("E3 the reply text never contains the contact_lookup-only name",
          DISTINCTIVE_NAME not in reply, reply)
    check("E4 the reply text never contains the contact_lookup-only phone",
          DISTINCTIVE_PHONE not in reply, reply)
    check("E5 the reply DOES surface the real investor_criteria lead",
          "Isolation Test Investor" in reply, reply)


async def main() -> None:
    print("=" * 68)
    print(f"  Contact lookup verification  (DB: {TEST_DB_URL})")
    print("=" * 68)

    ctx = await setup_db()
    await run_import_checks(ctx["mahmoud_id"])

    # A fresh company for the CLI section so section A's row-count math
    # doesn't get entangled with section C's own counts.
    async with SessionLocal() as db:
        cli_co = Company(name="Mahmoud Advisory CLI", vertical="launch_matcher")
        db.add(cli_co)
        await db.flush()
        cli_co_id = cli_co.id
        await db.commit()
    await run_cli_checks(cli_co_id, ctx["generic_id"])

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await run_autocomplete_checks(client, ctx)

    run_fallback_tier_checks()
    await run_isolation_checks(ctx["mahmoud_id"])

    await engine.dispose()
    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

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
