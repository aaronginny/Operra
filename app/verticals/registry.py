"""Shared vertical registry — the pluggable-modes seam for the platform.

Each client company has exactly one `companies.vertical` string (see
app.models.company). Historically, adding a vertical meant hand-writing a new
check against that string in the inbound webhook pipeline
(app.services.webhook_service), the reminder scheduler's daily tick
(app.services.reminder_service), and a FastAPI auth dependency
(app.dependencies) — three separate places, each a copy-pasted variant of the
last. This module replaces "copy the last vertical's check" with "register a
Vertical": a vertical's own package declares what it needs, once, and the
generic dispatchers below do the same lookup for every vertical uniformly.

Nothing here knows what a vertical's handlers actually do — it only stores
callables and hands them back by name. Zero dependency on SQLAlchemy models,
FastAPI, or any specific vertical's code, specifically so that importing this
module can never create an import cycle with the verticals that register into
it.

A company's vertical is assigned once, deliberately, by the platform
operator — never a self-serve toggle a client can flip. This registry mirrors
that: registration happens at process start (see app.verticals.bootstrap),
not per-request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

# (db, company_id, sender, text) -> result dict. Called only after the
# registry has already matched the sender's company to this vertical, so the
# handler never needs to re-derive company_id itself.
InboundHandler = Callable[[AsyncSession, int, str, str], Awaitable[dict]]

# (db, company_id) -> anything (return value is never inspected by the
# dispatcher; existing hooks like send_broker_pulse return an int count and
# are registered unmodified rather than wrapped just to satisfy a stricter
# signature).
DailyHook = Callable[[AsyncSession, int], Awaitable[Any]]


@dataclass(frozen=True)
class Vertical:
    """One vertical's pluggable hooks. Every field but `name` is optional —
    a vertical with no proactive message (launch_matcher today) simply
    doesn't set `daily`; a vertical with no inbound WhatsApp intent
    (real_estate today) doesn't set `inbound`.

    persist_inbound: when False, a message this vertical's `inbound` handler
    claims must never reach the generic pipeline's own logging/auto-register
    writes (message_logs, employees) — see the ordering guarantee documented
    on app.services.webhook_service.dispatch_inbound and enforced by its
    structure, not by this flag. The flag itself is read by nothing yet; it
    exists so a vertical's PII policy is declared as data next to its
    registration rather than only as a comment, and so a future dispatcher
    change has something concrete to assert against instead of re-deriving
    the policy from prose.
    """

    name: str
    inbound: Optional[InboundHandler] = None
    daily: Optional[DailyHook] = None
    persist_inbound: bool = True


_REGISTRY: dict[str, Vertical] = {}


def register_vertical(vertical: Vertical) -> None:
    """Register a vertical. Called once, at import time, by the vertical's
    own module (see app.verticals.bootstrap for why that import is
    guaranteed to happen before any dispatch can occur).

    Raises on a duplicate name rather than silently overwriting — two
    verticals racing to register the same name is a bug worth failing loudly
    on, not something to paper over.
    """
    if vertical.name in _REGISTRY:
        raise ValueError(f"vertical already registered: {vertical.name!r}")
    _REGISTRY[vertical.name] = vertical


def get_vertical(name: str) -> Vertical | None:
    """Look up a vertical by its companies.vertical value. None for
    "generic" and for any name nothing has registered — the same fail-safe
    default as the rest of the platform: unrecognised means invisible, not
    an error.
    """
    return _REGISTRY.get(name)


def all_verticals() -> list[Vertical]:
    """Every registered vertical, for the scheduler's daily-hook sweep."""
    return list(_REGISTRY.values())


def _reset_registry_for_tests() -> None:
    """Test-only escape hatch. Production code never calls this — the
    registry is populated once at import time and stays populated for the
    life of the process."""
    _REGISTRY.clear()
