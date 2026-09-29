"""One WhatsApp number, one user.

Inbound WhatsApp is routed by the sender's number (ceo_command_service.
get_ceo_user): on this platform the number IS the identity. Two users
holding one number is therefore not a data-quality nit, it is a routing
fault — the message can only go to one of them, and nothing about the
message says which was meant.

That fault has now bitten twice. On 2026-09-07 a generic row sharing the
broker_intel client's number won an unordered lookup; the fix was a
tie-break (non-generic first, then lowest id). On 2026-09-25 the same client
lost to a lower-id real_estate row: real_estate is non-generic, so it won the
tie-break, but it has no inbound WhatsApp handler, so the generic pipeline
answered her. A tie-break cannot be right, because it is guessing which of
two accounts a handset belongs to. The only correct state is that it never
has to guess.

So the rule is enforced at three layers:

  1. The database. A unique index (UNIQUE_INDEX, created by migration 037)
     on each number's routing key. This is the structural guarantee: no code
     path — signup, profile edit, a future provisioning endpoint, a script,
     raw SQL — can create a second holder once it exists.
  2. The write points. Signup and PATCH /auth/profile call find_holder
     first, so a person gets a readable message rather than an
     IntegrityError, and catch the IntegrityError anyway for the race.
  3. Every boot. A unique index cannot be CREATED while a duplicate
     already exists, and run_migrations logs-and-continues on a failed
     statement — so on a database that still holds a duplicate, layer 1
     would be silently absent. check_uniqueness runs after migrations and
     logs CRITICAL when the index is missing or a duplicate remains, and
     its result is reported on /health as `whatsapp_unique`, so the state
     is visible from outside without a diagnostic endpoint.

The routing key is the number's last 10 digits: the same key
get_ceo_user's suffix fallback matches on, so "+919150390233" and
"+9150390233" are one number here exactly as they are to the resolver. A
key on the raw string would let those two coexist, and the exact-match step
would then route to whichever held the full form without ever reaching the
tie-break.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

UNIQUE_INDEX = "uq_users_whatsapp_key"

NUMBER_IN_USE = (
    "This WhatsApp number is already linked to another PhantomPilot account. "
    "Each account needs its own number."
)

# Set by check_uniqueness at boot; read by /health. None until it has run.
_last_check: dict | None = None


def routing_key(number: str | None) -> str | None:
    """The last 10 digits of a number — its identity for routing."""
    digits = re.sub(r"\D", "", number or "")
    return digits[-10:] or None


async def find_holder(
    db: AsyncSession, number: str | None, exclude_user_id: int | None = None
) -> User | None:
    """The user (other than `exclude_user_id`) already holding `number`'s
    routing key, or None. The SQL is only a coarse prefilter on the last four
    characters; equality is decided on routing_key in Python, so a stored
    number with stray formatting still counts as the same number."""
    key = routing_key(number)
    if key is None:
        return None
    stmt = select(User).where(User.whatsapp_number.like(f"%{key[-4:]}")).order_by(User.id)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    for user in (await db.execute(stmt)).scalars():
        if routing_key(user.whatsapp_number) == key:
            return user
    return None


async def _index_present(conn) -> bool:
    if conn.dialect.name == "sqlite":
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :n"
    else:
        sql = "SELECT 1 FROM pg_indexes WHERE tablename = 'users' AND indexname = :n"
    return (await conn.execute(text(sql), {"n": UNIQUE_INDEX})).first() is not None


async def _duplicate_groups(conn) -> int:
    rows = await conn.execute(text(
        "SELECT whatsapp_number FROM users "
        "WHERE whatsapp_number IS NOT NULL AND whatsapp_number <> ''"
    ))
    seen: dict[str, int] = {}
    for (number,) in rows:
        key = routing_key(number)
        if key:
            seen[key] = seen.get(key, 0) + 1
    return sum(1 for n in seen.values() if n > 1)


async def check_uniqueness(engine: AsyncEngine) -> dict:
    """Boot-time proof that layer 1 is actually in force. Never raises: a
    failed check must not take the whole platform down, so it reports
    instead — CRITICAL in the log, and `whatsapp_unique: false` on /health.
    Only counts are logged, never numbers."""
    global _last_check
    async with engine.connect() as conn:
        present = await _index_present(conn)
        groups = await _duplicate_groups(conn)
    result = {"index_present": present, "duplicate_groups": groups,
              "ok": present and groups == 0}
    if groups:
        logger.critical(
            "WhatsApp routing: %d number(s) are held by more than one user. Inbound "
            "messages from those handsets can reach the wrong account, and the unique "
            "index %s cannot be created until every one is resolved.", groups, UNIQUE_INDEX,
        )
    elif not present:
        logger.critical(
            "WhatsApp routing: unique index %s is missing, so nothing at the database "
            "level stops two users sharing a number. Check migration 037's log line.",
            UNIQUE_INDEX,
        )
    else:
        logger.info("WhatsApp routing: one number per user, enforced by %s.", UNIQUE_INDEX)
    _last_check = result
    return result


def last_check_ok() -> bool | None:
    return None if _last_check is None else _last_check["ok"]
