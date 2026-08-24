"""Where launch text comes from — the seam OCR slots into later.

Today a launch arrives as a forwarded WhatsApp text message and the text is
already there. Tomorrow it may arrive as a poster or a PDF, and the text will
have to be extracted first. That difference belongs here and nowhere else: a
source turns an `InboundMessage` into plain text, and the parser downstream
neither knows nor cares which source produced it.

Adding OCR later is therefore a new class in this module plus one line in
`resolve_source`, with no change to the parser, matcher, formatter, or handler:

    class ImageLaunchSource:
        name = "image"
        def can_handle(self, message): return message.has_image
        async def extract_text(self, message): return await ocr(message.image)

OCR is explicitly NOT built now — this only makes sure nothing blocks it.
"""

from __future__ import annotations

from typing import Protocol

from app.services.launch_matcher.providers import InboundMessage


class LaunchSource(Protocol):
    """Turns an inbound message into launch text, or declines it."""

    name: str

    def can_handle(self, message: InboundMessage) -> bool: ...

    async def extract_text(self, message: InboundMessage) -> str | None: ...


class TextMessageSource:
    """A forwarded text message — the text is the launch."""

    name = "text"

    def can_handle(self, message: InboundMessage) -> bool:
        return bool(message.text and message.text.strip())

    async def extract_text(self, message: InboundMessage) -> str | None:
        return message.text.strip() if message.text else None


# Ordered by specificity. An image source would go before the text source so a
# flyer with a one-word caption is read as a flyer, not as its caption.
_SOURCES: list[LaunchSource] = [TextMessageSource()]


def resolve_source(message: InboundMessage) -> LaunchSource | None:
    """First source that can handle this message, or None."""
    for source in _SOURCES:
        if source.can_handle(message):
            return source
    return None
