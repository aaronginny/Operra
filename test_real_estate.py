"""End-to-end verification for the real-estate vertical (DealKnot merge).

Runs against a throwaway SQLite database and the real FastAPI app via ASGI —
real routes, real auth dependency, real JWTs, real matching engine. WhatsApp is
the only thing stubbed, since there are no live Meta credentials in a test
environment; the stub records every message that *would* have been sent so the
notification content can still be asserted.

Follows the convention of the other test scripts in this repo: a plain asyncio
script with its own engine, run directly (no pytest).

    python test_real_estate.py
"""

import asyncio
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./_test_real_estate.db")

import httpx  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

TEST_DB_PATH = "_test_real_estate.db"
TEST_DB_URL = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"

# Point the app's db module at the test engine BEFORE anything imports it.
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
from app.models.employee import Employee  # noqa: E402
from app.models.enquiry import Enquiry  # noqa: E402
from app.models.task import Task, TaskStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.auth_service import create_access_token  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    mark = "  [ok]" if condition else "  [XX]"
    print(f"{mark} {name}" + (f"  -- {detail}" if detail and not condition else ""))


# ── WhatsApp stub ────────────────────────────────────────────
# Records instead of sending. Patched into every module that imported the
# sender by name, since `from ... import send_whatsapp_message` binds a
# module-level reference that patching the source module alone would miss.
sent_messages: list[tuple[str, str]] = []


async def fake_send_whatsapp_message(phone_number: str, message: str) -> bool:
    sent_messages.append((phone_number, message))
    return True


def install_whatsapp_stub() -> None:
    import app.services.messaging_service as messaging
    import app.services.real_estate_notifications as re_notify
    import app.routes.enquiries as enq_routes
    import app.services.reminder_service as reminder

    messaging.send_whatsapp_message = fake_send_whatsapp_message
    re_notify.send_whatsapp_message = fake_send_whatsapp_message
    enq_routes.send_whatsapp_message = fake_send_whatsapp_message
    reminder.send_whatsapp_message = fake_send_whatsapp_message


# ── Fixtures ─────────────────────────────────────────────────

async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def setup_db() -> dict:
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)

    ctx: dict = {}
    async with SessionLocal() as db:
        # Lenin — an existing, non-real-estate customer. Left at the default
        # vertical on purpose: the point is that an untouched account stays
        # untouched.
        lenin_co = Company(name="Lenin Logistics")
        db.add(lenin_co)
        await db.flush()

        lenin = User(
            company_id=lenin_co.id, name="Lenin", email="lenin@example.com",
            role=UserRole.ceo, whatsapp_number="+919000000001",
        )
        db.add(lenin)

        # Some ordinary generic-product data so "no behaviour change" is
        # actually measurable rather than vacuously true on an empty account.
        emp = Employee(
            name="Ravi", phone_number="+919000000009",
            company_id=lenin_co.id, gender="neutral",
        )
        db.add(emp)
        await db.flush()
        db.add(Task(
            company_id=lenin_co.id, title="Deliver container",
            status=TaskStatus.pending, assigned_employee_id=emp.id,
        ))
        db.add(Enquiry(company_id=lenin_co.id, client_name="Walk-in client"))

        # The real-estate broker.
        broker_co = Company(name="Chennai Realty", vertical="real_estate")
        db.add(broker_co)
        await db.flush()
        broker = User(
            company_id=broker_co.id, name="Priya", email="priya@example.com",
            role=UserRole.ceo, whatsapp_number="+919000000002",
        )
        db.add(broker)
        await db.flush()

        ctx["lenin_company_id"] = lenin_co.id
        ctx["broker_company_id"] = broker_co.id
        ctx["lenin_token"] = create_access_token({
            "sub": lenin.email, "user_id": lenin.id,
            "company_id": lenin_co.id, "role": "ceo", "name": lenin.name,
        })
        ctx["broker_token"] = create_access_token({
            "sub": broker.email, "user_id": broker.id,
            "company_id": broker_co.id, "role": "ceo", "name": broker.name,
        })
        await db.commit()
    return ctx


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── A. Isolation: Lenin's generic account is untouched ───────

async def test_generic_isolation(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- A. Generic account (vertical='generic') sees nothing --")
    h = auth(ctx["lenin_token"])

    gated = [
        ("GET", "/real-estate/buyers"), ("GET", "/real-estate/sellers"),
        ("GET", "/real-estate/listings"), ("GET", "/real-estate/matches"),
        ("GET", "/real-estate/commissions"), ("GET", "/real-estate/constants"),
        ("GET", "/real-estate/summary"), ("POST", "/real-estate/matches/run"),
    ]
    blocked = []
    for method, path in gated:
        r = await client.request(method, path, headers=h, json={})
        if r.status_code != 404:
            blocked.append(f"{path} -> {r.status_code}")
    check("A1. every real-estate route 404s for a generic company",
          not blocked, "; ".join(blocked))

    r = await client.post(
        "/real-estate/buyers", headers=h,
        json={"name": "Sneaky", "areas": "Velachery", "budget_min": 1, "budget_max": 2},
    )
    check("A2. generic company cannot create real-estate records",
          r.status_code == 404, f"got {r.status_code}")

    r = await client.get("/real-estate/status", headers=h)
    check("A3. status endpoint reports the vertical off",
          r.status_code == 200 and r.json() == {"vertical": "generic", "enabled": False},
          str(r.json() if r.status_code == 200 else r.status_code))

    # His existing product still behaves exactly as before.
    r = await client.get("/api/dashboard/tasks", headers=h)
    tasks_ok = r.status_code == 200 and len(r.json()) == 1
    check("A4. existing tasks endpoint unchanged", tasks_ok,
          f"status={r.status_code}")

    r = await client.get("/enquiries", headers=h)
    enq = r.json() if r.status_code == 200 else []
    check("A5. existing enquiries endpoint unchanged",
          r.status_code == 200 and len(enq) == 1, f"status={r.status_code}")
    check("A6. enquiry payload carries null real-estate links (additive only)",
          bool(enq) and enq[0].get("buyer_id") is None and enq[0].get("seller_id") is None,
          str(enq[:1]))

    r = await client.get("/api/dashboard/employees", headers=h)
    check("A7. existing employees endpoint unchanged",
          r.status_code == 200 and len(r.json()) == 1, f"status={r.status_code}")


# ── B. Matching engine end to end ────────────────────────────

async def test_matching(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- B. Buyer + seller in the same area produce a match --")
    h = auth(ctx["broker_token"])
    sent_messages.clear()

    r = await client.post("/real-estate/buyers", headers=h, json={
        "name": "Arun Kumar", "phone": "+919000000011", "areas": "Velachery",
        "property_type": "apt_resale", "division": "sales", "currency": "INR",
        "budget_min": 5000000, "budget_max": 8000000, "radius_km": 5,
    })
    check("B1. buyer created", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
    if r.status_code != 201:
        return

    check("B2. no match yet (no sellers on the books)",
          not [m for m in sent_messages], f"{len(sent_messages)} messages")

    r = await client.post("/real-estate/sellers", headers=h, json={
        "name": "Meena Rao", "phone": "+919000000012", "areas": "Velachery",
        "property_type": "apt_resale", "division": "sales", "currency": "INR",
        "price": 6500000,
    })
    check("B3. seller created", r.status_code == 201, f"{r.status_code} {r.text[:160]}")

    r = await client.get("/real-estate/matches", headers=h)
    matches = r.json() if r.status_code == 200 else []
    check("B4. a match was created", len(matches) == 1, f"{len(matches)} matches")
    if not matches:
        return

    m = matches[0]
    check("B5. match is an exact area match", m["match_type"] == "exact", m["match_type"])
    check("B6. distance is 0 km for an exact area match",
          float(m["distance_km"]) == 0.0, str(m["distance_km"]))
    check("B7. price is inside budget", m["price_match_kind"] == "exact", m["price_match_kind"])
    check("B8. match links the right buyer and seller",
          m["buyer_name"] == "Arun Kumar" and m["seller_name"] == "Meena Rao",
          f"{m['buyer_name']} / {m['seller_name']}")
    check("B9. score matches the ported formula (98)", m["score"] == 98, str(m["score"]))

    # WhatsApp notification
    broker_msgs = [msg for phone, msg in sent_messages if phone == "+919000000002"]
    check("B10. a WhatsApp notification fired for the new match",
          len(broker_msgs) == 1, f"{len(broker_msgs)} messages to the broker")
    if broker_msgs:
        body = broker_msgs[0]
        check("B11. notification names both parties",
              "Arun Kumar" in body and "Meena Rao" in body, body[:120])
        check("B12. notification is the new-match alert",
              "new match" in body.lower(), body[:120])

    # Idempotence: re-running must not re-notify.
    sent_messages.clear()
    r = await client.post("/real-estate/matches/run", headers=h)
    check("B13. re-running finds no new matches",
          r.status_code == 200 and r.json()["new_matches"] == 0, r.text[:120])
    check("B14. re-running does not re-notify (notified_at respected)",
          not sent_messages, f"{len(sent_messages)} duplicate messages")


async def test_proximity_and_exclusions(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- C. Proximity matching and the exclusion gates --")
    h = auth(ctx["broker_token"])
    sent_messages.clear()

    # Anna Nagar is ~12.1km from Velachery. A buyer with a 15km radius should
    # proximity-match the existing Velachery seller.
    r = await client.post("/real-estate/buyers", headers=h, json={
        "name": "Divya S", "phone": "+919000000013", "areas": "Anna Nagar",
        "property_type": "apt_resale", "division": "sales", "currency": "INR",
        "budget_min": 6000000, "budget_max": 7000000, "radius_km": 15,
    })
    check("C1. proximity buyer created", r.status_code == 201, r.text[:160])

    r = await client.get("/real-estate/matches", headers=h)
    matches = r.json() if r.status_code == 200 else []
    prox = [m for m in matches if m["buyer_name"] == "Divya S"]
    check("C2. proximity match found", len(prox) == 1, f"{len(prox)}")
    if prox:
        check("C3. flagged as proximity, not exact",
              prox[0]["match_type"] == "proximity", prox[0]["match_type"])
        check("C4. carries the 12.1 km distance badge",
              abs(float(prox[0]["distance_km"]) - 12.1) < 0.05,
              str(prox[0]["distance_km"]))

    # Same area and budget, but a villa — must not match the apartment seller.
    r = await client.post("/real-estate/buyers", headers=h, json={
        "name": "Wrong Type", "areas": "Velachery", "property_type": "villa_resale",
        "division": "sales", "currency": "INR",
        "budget_min": 5000000, "budget_max": 8000000, "radius_km": 5,
    })
    check("C5. mismatched-type buyer created", r.status_code == 201, r.text[:120])

    # Same area/type but a different currency — must not match.
    r = await client.post("/real-estate/buyers", headers=h, json={
        "name": "Wrong Currency", "areas": "Velachery", "property_type": "apt_resale",
        "division": "sales", "currency": "USD",
        "budget_min": 5000000, "budget_max": 8000000, "radius_km": 5,
    })
    check("C6. mismatched-currency buyer created", r.status_code == 201, r.text[:120])

    r = await client.get("/real-estate/matches", headers=h)
    matches = r.json() if r.status_code == 200 else []
    names = {m["buyer_name"] for m in matches}
    check("C7. villa buyer does not match an apartment seller",
          "Wrong Type" not in names, str(names))
    check("C8. USD buyer does not match an INR seller",
          "Wrong Currency" not in names, str(names))


# ── D. Enquiry pipeline + commissions ────────────────────────

async def test_enquiry_and_commission(client: httpx.AsyncClient, ctx: dict) -> None:
    print("\n-- D. Enquiry stages and commissions --")
    h = auth(ctx["broker_token"])

    r = await client.get("/real-estate/buyers", headers=h)
    buyers = r.json()
    buyer_id = next(b["id"] for b in buyers if b["name"] == "Arun Kumar")

    r = await client.post("/enquiries", headers=h, json={
        "client_name": "Arun Kumar", "service_requested": "2BHK in Velachery",
        "buyer_id": buyer_id,
    })
    check("D1. enquiry created with a buyer link",
          r.status_code == 201 and r.json()["buyer_id"] == buyer_id, r.text[:160])
    enquiry_id = r.json()["id"] if r.status_code == 201 else None

    sent_messages.clear()
    r = await client.post(f"/enquiries/{enquiry_id}/advance-stage", headers=h)
    check("D2. enquiry advances to Follow Up",
          r.status_code == 200 and r.json()["stage"] == "follow_up", r.text[:160])
    broker_msgs = [m for p, m in sent_messages if p == "+919000000002"]
    check("D3. broker notified of the stage change", len(broker_msgs) >= 1,
          f"{len(broker_msgs)} messages")
    if broker_msgs:
        check("D4. stage alert names the stage and the client",
              "Follow Up" in broker_msgs[0] and "Arun Kumar" in broker_msgs[0],
              broker_msgs[0][:120])

    r = await client.post("/real-estate/commissions", headers=h, json={
        "enquiry_id": enquiry_id, "deal_value": 6500000,
        "commission_percent": 2, "split_percent": 50,
        "source": "both_sides", "status": "Received", "currency": "INR",
    })
    check("D5. commission booked", r.status_code == 201, r.text[:160])
    if r.status_code == 201:
        c = r.json()
        check("D6. commission amount derived from value x percent",
              abs(c["commission_amount"] - 130000) < 0.01, str(c["commission_amount"]))

    r = await client.get("/real-estate/summary", headers=h)
    summary = r.json() if r.status_code == 200 else {}
    check("D7. summary reports the booked commission",
          summary.get("commission_received_total") == 130000.0, str(summary))


# ── E. Morning pulse ─────────────────────────────────────────

async def test_morning_pulse(ctx: dict) -> None:
    print("\n-- E. Morning pulse is real-estate only --")
    from app.services.real_estate_notifications import build_broker_pulse

    async with SessionLocal() as db:
        generic_pulse = await build_broker_pulse(db, ctx["lenin_company_id"])
        check("E1. generic company produces no broker pulse",
              generic_pulse is None, repr(generic_pulse))

        broker_pulse = await build_broker_pulse(db, ctx["broker_company_id"])
        check("E2. real-estate company produces a pulse",
              broker_pulse is not None, repr(broker_pulse))
        if broker_pulse:
            check("E3. pulse reports new leads",
                  "New leads:" in broker_pulse, broker_pulse)
            check("E4. pulse reports matches found overnight",
                  "Matches found:" in broker_pulse, broker_pulse)
            check("E5. pulse reports enquiry stage counts",
                  "Pipeline" in broker_pulse and "Follow Up" in broker_pulse,
                  broker_pulse)
            print("\n     Broker pulse preview:")
            for line in broker_pulse.split("\n"):
                print(f"       {line}")

    # The scheduler sweep must never touch a generic company.
    from app.services.reminder_service import _send_real_estate_pulses
    sent_messages.clear()
    async with SessionLocal() as db:
        await _send_real_estate_pulses(db)
    recipients = {p for p, _ in sent_messages}
    check("E6. scheduler sweep messages only the broker, never Lenin",
          recipients == {"+919000000002"}, str(recipients))


# ── Runner ───────────────────────────────────────────────────

async def main() -> None:
    print("=" * 64)
    print("  Real-estate vertical — end-to-end verification")
    print("=" * 64)

    install_whatsapp_stub()
    ctx = await setup_db()
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await test_generic_isolation(client, ctx)
        await test_matching(client, ctx)
        await test_proximity_and_exclusions(client, ctx)
        await test_enquiry_and_commission(client, ctx)
        await test_morning_pulse(ctx)

    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print("\n" + "=" * 64)
    print(f"  Results: {passed}/{len(results)} passed  |  {failed} failed")
    print("=" * 64)

    if failed:
        print("\nFailed:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"  [XX] {name}" + (f"\n       {detail}" if detail else ""))
        sys.exit(1)
    print("\nAll real-estate tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
