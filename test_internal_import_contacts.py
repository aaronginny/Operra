"""Verification for the TEMPORARY /internal/import-contacts endpoint (login-
gated variant), before it goes near production. Delete with the endpoint.

The property that matters most here: the import target comes from the
caller's own token, so a valid login for company A cannot write rows into
company B. That is the reason this variant was chosen over a shared secret,
so it is tested directly (section C) rather than assumed.

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

from app.database import Base, get_db  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import app  # noqa: E402
from app.migrations import run_migrations  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.contact_lookup import ContactLookup  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import create_access_token  # noqa: E402

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


SAMPLE = "Ahmed SHJ Buyer\n+971501110001\nCity Vet Clinic\n+971501110002\n"
FALLBACK_SAMPLE = "Alaa Shomous\n+971501110003\nKhaled Azizi Kawther\n+971501110004\n"


async def rows_for(company_id: int):
    async with SessionLocal() as db:
        return list((await db.execute(
            select(ContactLookup).where(ContactLookup.company_id == company_id)
        )).scalars().all())


async def main() -> None:
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with SessionLocal() as db:
        lm_a = Company(name="Mahmoud Advisory", vertical="launch_matcher")
        lm_b = Company(name="Other Advisor", vertical="launch_matcher")
        generic = Company(name="Generic Co", vertical="generic")
        db.add_all([lm_a, lm_b, generic])
        await db.flush()
        ua = User(company_id=lm_a.id, name="Mahmoud", email="m@example.com", role=UserRole.ceo)
        ub = User(company_id=lm_b.id, name="Other", email="o@example.com", role=UserRole.ceo)
        ug = User(company_id=generic.id, name="Gen", email="g@example.com", role=UserRole.ceo)
        db.add_all([ua, ub, ug])
        await db.flush()
        a_id, b_id, g_id = lm_a.id, lm_b.id, generic.id
        tok = {
            "a": create_access_token({"sub": ua.email, "user_id": ua.id,
                                       "company_id": a_id, "role": "ceo", "name": ua.name}),
            "b": create_access_token({"sub": ub.email, "user_id": ub.id,
                                       "company_id": b_id, "role": "ceo", "name": ub.name}),
            "g": create_access_token({"sub": ug.email, "user_id": ug.id,
                                       "company_id": g_id, "role": "ceo", "name": ug.name}),
        }
        await db.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("contacts.txt", SAMPLE, "text/plain")}

        print("\n== A. auth gate ==")
        res = await client.post("/internal/import-contacts",
                                 data={"dry_run": True}, files=files)
        check("A1 no token -> 401/403", res.status_code in (401, 403), str(res.status_code))

        res = await client.post("/internal/import-contacts", data={"dry_run": True},
                                 files=files, headers=auth(tok["g"]))
        check("A2 generic-vertical company -> 404 (vertical gate, fails closed)",
              res.status_code == 404, str(res.status_code))

        print("\n== B. dry run then real ==")
        res = await client.post("/internal/import-contacts", data={"dry_run": True},
                                 files=files, headers=auth(tok["a"]))
        check("B1 dry run -> 200", res.status_code == 200, res.text[:200])
        check("B2 dry run reports imported=1, no_area=1",
              res.json()["imported"] == 1 and res.json()["skipped_no_area"] == 1, res.text[:200])
        check("B3 dry run wrote nothing", len(await rows_for(a_id)) == 0)

        res = await client.post("/internal/import-contacts", data={"dry_run": False},
                                 files=files, headers=auth(tok["a"]))
        check("B4 real run reports imported=1", res.json()["imported"] == 1, res.text[:200])
        check("B5 exactly 1 row created", len(await rows_for(a_id)) == 1)
        check("B6 response carries no phone field", all("phone" not in r for r in res.json()["results"]))

        res = await client.post("/internal/import-contacts", data={"dry_run": False},
                                 files=files, headers=auth(tok["a"]))
        check("B7 re-run imports 0 (idempotent)",
              res.json()["imported"] == 0 and res.json()["skipped_duplicate"] == 1, res.text[:200])

        print("\n== C. tenant scoping — the reason this variant was chosen ==")
        res = await client.post("/internal/import-contacts", data={"dry_run": False},
                                 files=files, headers=auth(tok["b"]))
        check("C1 company B's token imports into B, not A", res.json()["company_id"] == b_id,
              res.text[:200])
        check("C2 company A still has exactly its own 1 row", len(await rows_for(a_id)) == 1)
        check("C3 company B has its own separate row", len(await rows_for(b_id)) == 1)

        # An attacker-style attempt to aim at another tenant via a form field:
        # company_id is not a parameter at all, so it must be ignored.
        res = await client.post("/internal/import-contacts",
                                 data={"dry_run": False, "company_id": a_id},
                                 files={"file": ("c.txt", FALLBACK_SAMPLE, "text/plain")},
                                 headers=auth(tok["b"]))
        check("C4 a company_id form field cannot redirect the import",
              res.status_code == 200 and res.json()["company_id"] == b_id, res.text[:200])
        check("C5 company A unchanged after that attempt", len(await rows_for(a_id)) == 1)

        print("\n== D. the newly-confirmed Dubai fallback words import correctly ==")
        res = await client.post("/internal/import-contacts", data={"dry_run": False},
                                 files={"file": ("c.txt", FALLBACK_SAMPLE, "text/plain")},
                                 headers=auth(tok["a"]))
        body = res.json()
        check("D1 both fallback contacts imported", body["imported"] == 2, res.text[:300])
        check("D2 both resolved to Dubai with no area",
              all(r["emirate"] == "Dubai" and r["area"] is None
                  for r in body["results"] if r["status"] == "imported"), res.text[:300])

        res = await client.get("/openapi.json")
        check("E1 route hidden from the OpenAPI schema",
              "/internal/import-contacts" not in res.json().get("paths", {}))

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
        for _s, name, detail in failed:
            print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
