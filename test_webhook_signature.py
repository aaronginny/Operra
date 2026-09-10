"""Verification for Meta webhook signature checking.

POST /webhook/whatsapp was unauthenticated: anyone who knew the URL could
post a payload naming any sender and have it processed as a genuine inbound
WhatsApp message. Meta signs every webhook with HMAC-SHA256 over the raw
body, keyed on the App Secret, so checking that is what separates a real
delivery from a forgery.

The skip-when-unset behaviour is tested as deliberately as the rejection
paths: shipping this must not sever inbound delivery on an environment that
hasn't been given META_APP_SECRET yet, which is exactly the state production
is in until Aaron supplies it.

    python test_webhook_signature.py
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys

TEST_DB_PATH = "_test_webhook_signature.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"

import httpx  # noqa: E402
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

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

SECRET = "test_app_secret_value"
URL = "/webhook/whatsapp"

PAYLOAD = {
    "entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "messages": [{"from": "919990001111", "id": "wamid.SIGTEST",
                       "text": {"body": "hi"}, "type": "text"}],
    }}]}]
}
RAW = json.dumps(PAYLOAD).encode()


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def main() -> None:
    print("=" * 68)
    print("  Meta webhook signature verification")
    print("=" * 68)

    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    original_secret = settings.meta_app_secret

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── secret unset: must stay permissive, or shipping this breaks prod ──
        print("\n== A. META_APP_SECRET unset (current production state) ==")
        settings.meta_app_secret = None
        r = await client.post(URL, content=RAW, headers={"Content-Type": "application/json"})
        check("A1 unsigned request is still accepted while the secret is unset",
              r.status_code == 200, f"{r.status_code} {r.text[:80]}")
        check("A2 ...and is actually processed, not silently dropped",
              r.json().get("status") == "ok", r.text[:80])

        # ── secret set: verification is live ──
        print("\n== B. META_APP_SECRET set ==")
        settings.meta_app_secret = SECRET

        r = await client.post(URL, content=RAW,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": sign(RAW, SECRET)})
        check("B1 correctly signed request -> 200", r.status_code == 200,
              f"{r.status_code} {r.text[:80]}")

        r = await client.post(URL, content=RAW, headers={"Content-Type": "application/json"})
        check("B2 NO signature header -> 403", r.status_code == 403, str(r.status_code))

        r = await client.post(URL, content=RAW,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": sign(RAW, "wrong_secret")})
        check("B3 signature from the WRONG secret -> 403", r.status_code == 403, str(r.status_code))

        r = await client.post(URL, content=RAW,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": "garbage"})
        check("B4 malformed signature header -> 403", r.status_code == 403, str(r.status_code))

        r = await client.post(URL, content=RAW,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": sign(RAW, SECRET).replace("sha256=", "")})
        check("B5 signature missing the sha256= prefix -> 403", r.status_code == 403,
              str(r.status_code))

        # The signature must cover the body, so a tampered body must fail even
        # with an otherwise-valid signature for the ORIGINAL body.
        tampered = json.dumps({
            "entry": [{"changes": [{"value": {
                "messaging_product": "whatsapp",
                "messages": [{"from": "919999999999", "id": "wamid.FORGED",
                               "text": {"body": "hi"}, "type": "text"}],
            }}]}]
        }).encode()
        r = await client.post(URL, content=tampered,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": sign(RAW, SECRET)})
        check("B6 body tampered after signing (sender swapped) -> 403",
              r.status_code == 403, str(r.status_code))

        r = await client.post(URL, content=tampered,
                               headers={"Content-Type": "application/json",
                                        "X-Hub-Signature-256": sign(tampered, SECRET)})
        check("B7 ...but correctly re-signed tampered body is accepted "
              "(signature proves origin, not intent)", r.status_code == 200,
              str(r.status_code))

        # ── the forgery this closes ──
        print("\n== C. the actual attack this prevents ==")
        settings.meta_app_secret = SECRET
        forged = json.dumps({
            "entry": [{"changes": [{"value": {
                "messaging_product": "whatsapp",
                "messages": [{"from": "919150390233", "id": "wamid.IMPERSONATE",
                               "text": {"body": "hi"}, "type": "text"}],
            }}]}]
        }).encode()
        r = await client.post(URL, content=forged,
                               headers={"Content-Type": "application/json"})
        check("C1 an unsigned payload impersonating a real client is rejected",
              r.status_code == 403, str(r.status_code))

    settings.meta_app_secret = original_secret

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
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
