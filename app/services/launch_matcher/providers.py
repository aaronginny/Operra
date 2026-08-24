"""The WhatsApp seam — the only place in this feature that knows about WhatsApp.

Everything upstream (sources, parser, matcher, formatter) works on plain text
and our own `InboundMessage`, never on a provider's payload shape. Swapping
Meta for another provider means writing one class that satisfies
`WhatsAppProvider` and changing what `get_provider()` returns; no parsing or
matching code moves.

Currently backed by the existing Meta Cloud API integration in
app.services.messaging_service — reused rather than rebuilt, so retries, phone
normalisation and Meta's error taxonomy stay in one place.

Phase 1 only ever *replies* to a message the advisor sent us, inside WhatsApp's
24-hour session window, to exactly one recipient. There is no
business-initiated send here and no fan-out; the advisor forwards to investors
themselves. Nothing in this module can send to an investor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InboundMessage:
    """A received message, normalised away from any provider's payload shape.

    `sender` is the advisor's own number, used solely to resolve which tenant
    they are. It is never written to any table this feature owns.
    """

    sender: str
    text: str
    provider_message_id: str | None = None


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None


class WhatsAppProvider(Protocol):
    """Send a plain-text WhatsApp message to one recipient."""

    name: str

    async def send_text(self, to: str, body: str) -> SendResult: ...


class MetaCloudProvider:
    """Meta Cloud API, via the existing messaging_service sender."""

    name = "meta_cloud"

    async def send_text(self, to: str, body: str) -> SendResult:
        # Imported lazily so tests can use RecordingProvider without pulling in
        # the requests/Meta stack at all.
        from app.services.messaging_service import send_whatsapp_message_detailed

        ok, error = await send_whatsapp_message_detailed(to, body)
        return SendResult(ok=ok, error=error)


class RecordingProvider:
    """Records instead of sending. For tests and dry runs.

    Also what makes the whole flow testable without live credentials: the
    handler is exercised end to end and the exact reply body is asserted.
    """

    name = "recording"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> SendResult:
        self.sent.append((to, body))
        return SendResult(ok=True)


def get_provider() -> WhatsAppProvider:
    """The provider this deployment sends through.

    Meta is the only functional integration in this codebase today, so it is
    the default and the only wiring. Migrating providers is deliberately out of
    scope for Phase 1; this function is the single place that choice lives when
    it is made.
    """
    return MetaCloudProvider()
