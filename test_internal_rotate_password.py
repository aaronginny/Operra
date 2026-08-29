"""Verification for the TEMPORARY /internal/rotate-password endpoint, plus a
permanent check that the /auth/reset database-wipe route is really gone.

Delete the rotation sections with the endpoint. Section D (auth/reset is
absent) is worth keeping wherever auth tests live — it guards against that
capability being reintroduced.

    python test_internal_rotate_password.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_rotate_password.db"
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
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import (  # noqa: E402
    create_access_token,
    get_password_hash,
    verify_password,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

OLD_PW = "-WWLagG3nHPTVCfmHX25"
NEW_PW = "Rk7mTqPw4ZbnYx82Hs6V"


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
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    async with SessionLocal() as db:
        co = Company(name="Mahmoud Advisory", vertical="launch_matcher")
        other_co = Company(name="Other Co")
        db.add_all([co, other_co])
        await db.flush()
        target = User(company_id=co.id, name="Mahmoud", email="m@example.com",
                       role=UserRole.ceo, password_hash=get_password_hash(OLD_PW))
        bystander = User(company_id=other_co.id, name="Other", email="o@example.com",
                          role=UserRole.ceo, password_hash=get_password_hash(OLD_PW))
        db.add_all([target, bystander])
        await db.flush()
        tok = create_access_token({"sub": target.email, "user_id": target.id,
                                    "company_id": co.id, "role": "ceo", "name": target.name})
        other_tok = create_access_token({"sub": bystander.email, "user_id": bystander.id,
                                          "company_id": other_co.id, "role": "ceo",
                                          "name": bystander.name})
        bystander_id = bystander.id
        await db.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    URL = "/internal/rotate-password"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n== A. auth + input gates ==")
        r = await client.post(URL, json={"current_password": OLD_PW, "new_password": NEW_PW})
        check("A1 no token -> 401/403", r.status_code in (401, 403), str(r.status_code))

        r = await client.post(URL, headers=auth(tok),
                               json={"current_password": "wrong", "new_password": NEW_PW})
        check("A2 wrong current password -> 403", r.status_code == 403, str(r.status_code))

        r = await client.post(URL, headers=auth(tok),
                               json={"current_password": OLD_PW, "new_password": "short"})
        check("A3 too-short new password -> 422", r.status_code == 422, str(r.status_code))

        r = await client.post(URL, headers=auth(tok),
                               json={"current_password": OLD_PW, "new_password": OLD_PW})
        check("A4 reusing the same password -> 400", r.status_code == 400, str(r.status_code))

        r = await client.post(URL, headers=auth(tok),
                               json={"current_password": OLD_PW, "new_password": NEW_PW,
                                     "user_id": 999, "email": "victim@example.com"})
        check("A5 extra fields rejected — cannot name another account",
              r.status_code == 422, str(r.status_code))

        check("A6 password still unchanged after every rejected attempt",
              verify_password(OLD_PW, await hash_for("m@example.com")))

        print("\n== B. the rotation itself ==")
        r = await client.post(URL, headers=auth(tok),
                               json={"current_password": OLD_PW, "new_password": NEW_PW})
        check("B1 rotation succeeds", r.status_code == 200, r.text[:200])
        h = await hash_for("m@example.com")
        check("B2 new password verifies", verify_password(NEW_PW, h))
        check("B3 old password no longer works", not verify_password(OLD_PW, h))
        check("B4 stored as a bcrypt hash, not plaintext",
              h.startswith("$2") and NEW_PW not in h, h[:12])
        check("B5 response echoes no password material",
              "password" not in r.text.lower(), r.text[:200])

        print("\n== C. it only ever touches the caller's own row ==")
        check("C1 the other user's password is untouched",
              verify_password(OLD_PW, await hash_for("o@example.com")))
        OTHER_NEW = "Zq5wRt9mKp3xLn74Bd"
        r = await client.post(URL, headers=auth(other_tok),
                               json={"current_password": OLD_PW, "new_password": OTHER_NEW})
        check("C2 that user's rotation reports their OWN user_id",
              r.status_code == 200 and r.json()["user_id"] == bystander_id,
              f"{r.status_code} {r.text[:120]} expected user_id={bystander_id}")
        check("C3 the other user's new password took effect",
              verify_password(OTHER_NEW, await hash_for("o@example.com")))
        check("C4 first user's password survived the second user's rotation",
              verify_password(NEW_PW, await hash_for("m@example.com")))

        print("\n== D. the /auth/reset database-wipe route is gone ==")
        paths = [r_.path for r_ in app.routes]
        check("D1 /auth/reset not registered on the app", "/auth/reset" not in paths)
        r = await client.post("/auth/reset", headers=auth(tok), json={"confirm": "anything"})
        check("D2 POST /auth/reset -> 404", r.status_code == 404, str(r.status_code))
        async with SessionLocal() as db:
            n_users = len((await db.execute(select(User))).scalars().all())
            n_cos = len((await db.execute(select(Company))).scalars().all())
        check("D3 users/companies still present (nothing wiped)",
              n_users == 2 and n_cos == 2, f"users={n_users} companies={n_cos}")

        r = await client.get("/openapi.json")
        check("D4 rotate-password hidden from OpenAPI",
              URL not in r.json().get("paths", {}))

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    print("\n" + "=" * 68)
    passed = sum(1 for x in results if x[0] == PASS)
    failed = [x for x in results if x[0] == FAIL]
    print(f"  {passed}/{len(results)} checks passed")
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
