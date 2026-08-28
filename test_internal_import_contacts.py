"""Verification for the TEMPORARY /internal/import-contacts endpoint, before
it goes anywhere near production. Delete this alongside the endpoint itself.

Plain asyncio script, no pytest, run directly.

    python test_internal_import_contacts.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_internal_import_contacts.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import app  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.contact_lookup import ContactLookup  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SAMPLE = "Ahmed SHJ Buyer\n+971501110001\nCity Vet Clinic\n+971501110002\n"


async def main() -> None:
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with SessionLocal() as db:
        lm_co = Company(name="Mahmoud Advisory", vertical="launch_matcher")
        db.add(lm_co)
        generic_co = Company(name="Generic Co", vertical="generic")
        db.add(generic_co)
        await db.flush()
        lm_id, generic_id = lm_co.id, generic_co.id
        await db.commit()

    settings.import_secret = "test-secret-value-not-real"
    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("contacts.txt", SAMPLE, "text/plain")}

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": lm_id, "dry_run": True}, files=files)
        check("A1 no secret header -> 404 (route looks nonexistent)", res.status_code == 404)

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": lm_id, "dry_run": True}, files=files,
                                 headers={"X-Import-Secret": "wrong-secret"})
        check("A2 wrong secret -> 404", res.status_code == 404)

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": generic_id, "dry_run": True}, files=files,
                                 headers={"X-Import-Secret": "test-secret-value-not-real"})
        check("A3 non-launch_matcher company -> 400", res.status_code == 400, res.text)

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": lm_id, "dry_run": True}, files=files,
                                 headers={"X-Import-Secret": "test-secret-value-not-real"})
        check("B1 correct secret + dry_run -> 200", res.status_code == 200, res.text)
        body = res.json()
        check("B2 dry_run reports imported=1, skipped_no_area=1",
              body["imported"] == 1 and body["skipped_no_area"] == 1, str(body))
        async with SessionLocal() as db:
            rows = (await db.execute(
                select(ContactLookup).where(ContactLookup.company_id == lm_id)
            )).scalars().all()
        check("B3 dry_run wrote nothing to the DB", len(rows) == 0, str(len(rows)))

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": lm_id, "dry_run": False}, files=files,
                                 headers={"X-Import-Secret": "test-secret-value-not-real"})
        check("C1 real run -> 200", res.status_code == 200, res.text)
        body = res.json()
        check("C2 real run reports imported=1", body["imported"] == 1, str(body))
        check("C3 response 'results' has no phone field anywhere",
              all("phone" not in r for r in body["results"]), str(body["results"]))
        async with SessionLocal() as db:
            rows = (await db.execute(
                select(ContactLookup).where(ContactLookup.company_id == lm_id)
            )).scalars().all()
        check("C4 exactly 1 row actually created", len(rows) == 1, str(len(rows)))
        check("C5 correct name/emirate stored",
              len(rows) == 1 and rows[0].name == "Ahmed SHJ Buyer" and rows[0].emirate == "Sharjah")

        res = await client.post("/internal/import-contacts",
                                 data={"company_id": lm_id, "dry_run": False}, files=files,
                                 headers={"X-Import-Secret": "test-secret-value-not-real"})
        body = res.json()
        check("D1 re-running the same file imports 0 (idempotent via this endpoint too)",
              body["imported"] == 0 and body["skipped_duplicate"] == 1, str(body))

        res = await client.get("/openapi.json")
        paths = res.json().get("paths", {})
        check("E1 route is hidden from the OpenAPI schema",
              "/internal/import-contacts" not in paths, str(list(paths)[:5]))

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
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
