"""Short-lived conversation state for broker_intel — in process, never in
the database.

DESIGN NOTE — persistence (design question 2).

broker_intel is registered persist_inbound=False and ships stateless for
v1: nothing she sends is written to any table. That is the safer default
for the same reason launch_matcher chose it — what she forwards is lead
material, so it can carry a third party's name and phone number, and the
generic pipeline's message_logs write would capture that verbatim for a
person who never contacted this product. Not storing it is both simpler to
ship correctly and impossible to get wrong later.

But both features are two-step conversations ("which format?" / "article or
fun fact?"), so something has to bridge one message to the next. That
bridge is this module: a process-local dict with a short TTL, holding only
what she typed as the subject and which question is outstanding. It never
touches the DB, so "stateless" stays true of persistence, which is the part
that carries the PII risk.

Two consequences, both accepted deliberately for v1:

  * A restart (every deploy) drops any pending question. The handler treats
    a missing entry as "ask again" rather than as an error — see
    render_forgot_context — and the ARTICLE / FUN FACT keywords are
    self-describing, so the daily-nudge reply still works with no state at
    all. Only the ME / LEAD follow-up genuinely needs the bridge.
  * It is per-process. Render runs this on a single instance today; on
    several, a follow-up could land on a worker that never asked the
    question, degrading to the same "ask again" path.

The upgrade path, if she finds the re-asking annoying or the dashboard
should show her history, is a small table keyed by (company_id, phone) —
which is then a deliberate decision to persist lead text, made on its own
merits rather than inherited by accident from a caching choice.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Long enough to answer a question mid-call, short enough that a stale
# subject never attaches itself to an unrelated later message.
TTL_SECONDS = 30 * 60


@dataclass
class Pending:
    """The outstanding question for one phone number.

    kind: "audience" — she has been asked ME/LEAD about `subject`.
    """

    kind: str
    subject: str
    created_at: float


_PENDING: dict[tuple[int, str], Pending] = {}


def _key(company_id: int, phone: str) -> tuple[int, str]:
    return (company_id, phone)


def set_pending(company_id: int, phone: str, kind: str, subject: str) -> None:
    _PENDING[_key(company_id, phone)] = Pending(
        kind=kind, subject=subject, created_at=time.time()
    )


def take_pending(company_id: int, phone: str) -> Pending | None:
    """Return the outstanding question and clear it. Expired entries are
    dropped and read as absent, so a question answered an hour later is
    treated as a fresh start rather than silently reusing a stale subject."""
    key = _key(company_id, phone)
    pending = _PENDING.get(key)
    if pending is None:
        return None
    if time.time() - pending.created_at > TTL_SECONDS:
        _PENDING.pop(key, None)
        return None
    _PENDING.pop(key, None)
    return pending


def clear(company_id: int, phone: str) -> None:
    _PENDING.pop(_key(company_id, phone), None)


def _reset_for_tests() -> None:
    _PENDING.clear()
