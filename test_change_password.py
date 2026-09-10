"""Verification for POST /auth/change-password.

Until this shipped there was no in-app way to change a password — signup
only creates, and PATCH /auth/profile covers name and WhatsApp number only —
so every rotation needed a temporary secret-gated endpoint deployed and then
removed again. This is the permanent replacement, so it needs to hold up on
its own.

Plain asyncio script, no pytest — same convention as every other suite here.

    python test_change_password.py
    TEST_DATABASE_URL=postgresql+asyncpg://... python test_change_password.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_change_password.db"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
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
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import (  # noqa: E402
    create_access_token,
    get_password_hash,
    verify_password,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

OLD_PW = "OriginalPass123"
NEW_PW = "BrandNewPass456"
URL = "/auth/change-password"


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


async def hash_for(email: str) -> str:
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalars().first()
        return u.password_hash


async def main() -> None:
    print("=" * 68)
    print(f"  change-password  (DB: {TEST_DB_URL})")
    print("=" * 68)

    if IS_SQLITE and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        if not IS_SQLITE:
            await conn.execute(sa_text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa_text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with SessionLocal() as db:
        co_a = Company(name="Co A", vertical="generic")
        co_b = Company(name="Co B", vertical="broker_intel")
        db.add_all([co_a, co_b])
        await db.flush()
        ua = User(company_id=co_a.id, name="Alice", email="alice@example.com",
                   role=UserRole.ceo, password_hash=get_password_hash(OLD_PW))
        ub = User(company_id=co_b.id, name="Bob", email="bob@example.com",
                   role=UserRole.ceo, password_hash=get_password_hash(OLD_PW))
        db.add_all([ua, ub])
        await db.flush()
        tok_a = create_access_token({"sub": ua.email, "user_id": ua.id,
                                      "company_id": co_a.id, "role": "ceo", "name": ua.name})
        tok_b = create_access_token({"sub": ub.email, "user_id": ub.id,
                                      "company_id": co_b.id, "role": "ceo", "name": ub.name})
        bob_id = ub.id
        await db.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n== A. rejections ==")
        r = await client.post(URL, json={"current_password": OLD_PW, "new_password": NEW_PW})
        check("A1 no token -> 401/403", r.status_code in (401, 403), str(r.status_code))

        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": "wrong-password", "new_password": NEW_PW})
        check("A2 wrong current password -> 403", r.status_code == 403, str(r.status_code))

        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": OLD_PW, "new_password": "short"})
        check("A3 too-short new password -> 422", r.status_code == 422, str(r.status_code))

        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": OLD_PW, "new_password": ""})
        check("A4 empty new password -> 422", r.status_code == 422, str(r.status_code))

        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": OLD_PW, "new_password": OLD_PW})
        check("A5 reusing the same password -> 400", r.status_code == 400, str(r.status_code))

        r = await client.post(URL, headers=auth(tok_a), json={"new_password": NEW_PW})
        check("A6 missing current_password -> 422", r.status_code == 422, str(r.status_code))

        # Cannot be aimed at another account.
        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": OLD_PW, "new_password": NEW_PW,
                                     "user_id": bob_id, "email": "bob@example.com"})
        check("A7 extra fields naming another user -> 422 (extra=forbid)",
              r.status_code == 422, str(r.status_code))

        check("A8 the stored hash is untouched after every rejection",
              verify_password(OLD_PW, await hash_for("alice@example.com")))

        print("\n== B. the change itself ==")
        r = await client.post(URL, headers=auth(tok_a),
                               json={"current_password": OLD_PW, "new_password": NEW_PW})
        check("B1 valid change -> 200", r.status_code == 200, r.text[:150])
        check("B2 response leaks no password material",
              "password" not in r.text.lower() or "Password updated" in r.text, r.text[:120])

        h = await hash_for("alice@example.com")
        check("B3 new password verifies", verify_password(NEW_PW, h))
        check("B4 old password no longer works", not verify_password(OLD_PW, h))
        check("B5 stored as a bcrypt hash, not plaintext",
              h.startswith("$2") and NEW_PW not in h, h[:12])

        print("\n== C. end to end through the real login route ==")
        r = await client.post("/auth/login",
                               json={"email": "alice@example.com", "password": NEW_PW})
        check("C1 login with the NEW password succeeds",
              r.status_code == 200 and bool(r.json().get("access_token")), r.text[:120])
        r = await client.post("/auth/login",
                               json={"email": "alice@example.com", "password": OLD_PW})
        check("C2 login with the OLD password is rejected",
              not r.json().get("access_token"), r.text[:120])

        print("\n== D. it only ever touches the caller's own account ==")
        check("D1 the other user's password is untouched",
              verify_password(OLD_PW, await hash_for("bob@example.com")))
        r = await client.post(URL, headers=auth(tok_b),
                               json={"current_password": OLD_PW, "new_password": "BobsOwnPass789"})
        check("D2 that user changes their own password fine", r.status_code == 200, r.text[:120])
        check("D3 and the first user's new password still stands",
              verify_password(NEW_PW, await hash_for("alice@example.com")))

        print("\n== E. available to every vertical ==")
        # Company B is broker_intel; the route is not vertical-gated, so a
        # non-generic tenant must be able to use it too (D2 above already
        # exercised it — assert the intent explicitly).
        async with SessionLocal() as db:
            bob = await db.get(User, bob_id)
            co = await db.get(Company, bob.company_id)
        check("E1 a broker_intel-vertical user could change their password",
              co.vertical == "broker_intel" and verify_password(
                  "BobsOwnPass789", await hash_for("bob@example.com")),
              f"vertical={co.vertical}")

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
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
