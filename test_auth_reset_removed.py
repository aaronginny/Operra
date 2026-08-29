"""Regression guard: the /auth/reset database-wipe route must stay gone.

That route deleted every row from users and companies. It was a development
convenience that a security pass hardened (founder + ADMIN_RESET_TOKEN, 404
when unset) instead of removing, and the token was in fact set in
production, leaving a single request able to destroy the live database.
It has since been removed outright.

This test exists so that reintroducing it — or a route like it — fails
visibly rather than passing unnoticed. It is deliberately cheap: no network,
no fixtures, just the app's own route table plus a live request.

    python test_auth_reset_removed.py
"""

import asyncio
import os
import sys

TEST_DB_PATH = "_test_auth_reset_removed.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"

import httpx  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.database as _db_module  # noqa: E402

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db_module.engine = engine
_db_module.async_session = SessionLocal

from app.main import app  # noqa: E402
import app.routes.auth_routes as auth_routes  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


async def main() -> None:
    print("=" * 68)
    print("  /auth/reset removal — regression guard")
    print("=" * 68)

    paths = [r.path for r in app.routes]
    check("1 /auth/reset is not registered on the app", "/auth/reset" not in paths)

    check("2 auth_routes exposes no reset handler",
          not hasattr(auth_routes, "reset_users") and not hasattr(auth_routes, "ResetRequest"))

    src_path = auth_routes.__file__
    src = open(src_path, encoding="utf-8").read()
    check("3 no ADMIN_RESET_TOKEN reference remains", "ADMIN_RESET_TOKEN" not in src)
    check("4 auth_routes issues no bulk delete", "delete(User)" not in src and "delete(Company)" not in src)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/auth/reset", json={"confirm": "anything"})
        # 404 (route absent), not 401 — an existing protected route would
        # challenge for auth before it 404'd.
        check("5 POST /auth/reset -> 404, not an auth challenge",
              r.status_code == 404, str(r.status_code))

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    passed = sum(1 for x in results if x[0] == PASS)
    failed = [x for x in results if x[0] == FAIL]
    print("\n" + "=" * 68)
    print(f"  {passed}/{len(results)} checks passed")
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
