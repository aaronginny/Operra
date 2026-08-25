"""Orchestration: inbound message in, WhatsApp reply out.

    source -> parser -> matcher -> formatter -> provider

Each stage is injectable so tests drive the whole path with a recording
provider and no credentials.

Two deliberate properties of this module:

  * Nothing is persisted. The forwarded launch text is parsed in memory,
    answered, and dropped. Broadcasts routinely carry another agent's name and
    number in the footer, so not storing them is the only way to guarantee that
    footer never lands in a table. It also means this feature's only table is
    investor_criteria.

  * It runs BEFORE the generic inbound pipeline. app.services.webhook_service
    logs sender and raw text to message_logs for the task product; routing a
    launch-matcher company through that would write a phone number and the
    forwarded text to a table on this feature's path. So the dispatcher below
    is called first and returns without falling through.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User
from app.services.launch_matcher.formatter import format_reply
from app.services.launch_matcher.matcher import MatchOutcome, match_launch
from app.services.launch_matcher.parser import LaunchParser, parse_launch
from app.services.launch_matcher.providers import (
    InboundMessage,
    WhatsAppProvider,
    get_provider,
)
from app.services.launch_matcher.sources import resolve_source

logger = logging.getLogger(__name__)

LAUNCH_MATCHER_VERTICAL = "launch_matcher"

# Sent when a message arrives that we cannot read as a launch at all.
UNREADABLE_REPLY = (
    "I couldn't read that as a project launch.\n\n"
    "Forward the launch broadcast as text and I'll match it against your "
    "investors."
)


async def resolve_launch_matcher_company(
    db: AsyncSession, sender: str
) -> int | None:
    """Resolve a sender's phone to a launch-matcher company_id, or None.

    Reads the existing users table to identify which tenant is messaging —
    unavoidable for multi-tenancy and the same lookup every inbound message
    does. It is a read: nothing here writes the number anywhere, and the number
    never reaches this feature's own table.
    """
    from app.services.ceo_command_service import get_ceo_user

    user: User | None = await get_ceo_user(db, sender)
    if not user:
        return None

    company = await db.get(Company, user.company_id)
    if company is None or company.vertical != LAUNCH_MATCHER_VERTICAL:
        return None
    return company.id


async def build_reply(
    db: AsyncSession,
    company_id: int,
    message: InboundMessage,
    parser: LaunchParser | None = None,
) -> tuple[str, MatchOutcome | None]:
    """Run the pipeline and return (reply_body, outcome).

    Split out from sending so tests can assert the exact reply text without a
    provider, and so a future dashboard preview could reuse it.
    """
    source = resolve_source(message)
    if source is None:
        return UNREADABLE_REPLY, None

    text = await source.extract_text(message)
    if not text:
        return UNREADABLE_REPLY, None

    launch = parse_launch(text, parser=parser)
    outcome = await match_launch(db, company_id, launch)

    logger.info(
        "Launch matched: company=%s source=%s emirate=%s considered=%d matched=%d",
        company_id, source.name, launch.emirate, outcome.considered,
        len(outcome.matches),
    )
    return format_reply(outcome), outcome


async def handle_launch_message(
    db: AsyncSession,
    company_id: int,
    message: InboundMessage,
    provider: WhatsAppProvider | None = None,
    parser: LaunchParser | None = None,
) -> dict:
    """Parse, match, and reply to the advisor. Never messages an investor."""
    reply, outcome = await build_reply(db, company_id, message, parser=parser)

    provider = provider or get_provider()
    result = await provider.send_text(message.sender, reply)
    if not result.ok:
        logger.warning(
            "Launch reply not delivered: company=%s provider=%s error=%s",
            company_id, provider.name, result.error,
        )

    return {
        "status": "launch_matcher",
        "matched": bool(outcome and outcome.matched),
        "match_count": len(outcome.matches) if outcome else 0,
        "considered": outcome.considered if outcome else 0,
        "delivered": result.ok,
        "reply": reply,
    }


async def try_handle_launch_matcher(
    db: AsyncSession, sender: str, text: str
) -> dict | None:
    """Entry point for the inbound webhook.

    Returns a result dict when this sender belongs to a launch-matcher company
    (meaning the message is fully handled and must not fall through to the
    generic pipeline), or None when it doesn't and normal processing should
    continue untouched.

    Returning None for everyone else is what keeps every existing tenant —
    Lenin's included — on exactly the path they are on today.
    """
    company_id = await resolve_launch_matcher_company(db, sender)
    if company_id is None:
        return None

    message = InboundMessage(sender=sender, text=text)
    return await handle_launch_message(db, company_id, message)
