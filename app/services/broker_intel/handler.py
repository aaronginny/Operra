"""broker_intel — inbound handling, the daily nudge, and registration.

The vertical for a Dubai real-estate broker working from WhatsApp. Two
features:

  1. Lead intel on demand. She forwards or types a project/area and gets a
     scannable bulleted briefing — market context, why it appeals,
     appreciation in qualitative terms, developer reputation, landmarks. She
     is asked which format she wants first (a quick read for herself, or
     polished text she can forward to a client verbatim) unless her message
     already said.
  2. A daily content nudge. Once a day she is offered an ARTICLE or a FUN
     FACT; whichever she picks comes back as a ready-to-post caption.

Registered with persist_inbound=False, like launch_matcher and for the same
reason: what she forwards is lead material and can carry a third party's
name and number, so it must not reach the generic pipeline's message_logs
write or its Employee auto-registration. That is guaranteed structurally by
dispatch_inbound returning this handler's result before _run_generic_pipeline
is reachable — see app.services.webhook_service, and the session-spy checks
in test_broker_intel.py that fail if the split is undone.

No content this module produces may read as an official Dubai Land
Department figure; formatter.py enforces that on every content-bearing
reply.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.services.broker_intel import formatter, intents, state
from app.services.broker_intel.content import ContentGenerator, get_generator
from app.verticals.registry import Vertical, register_vertical

logger = logging.getLogger(__name__)

BROKER_INTEL_VERTICAL = "broker_intel"


async def _recipients(db: AsyncSession, company_id: int) -> list[str]:
    """Numbers to send this company's proactive messages to.

    Same shape as the real-estate pulse's recipient lookup: the company's
    CEO users with a WhatsApp number on file.
    """
    stmt = select(User).where(
        User.company_id == company_id,
        User.role == UserRole.ceo,
        User.whatsapp_number.isnot(None),
    )
    users = (await db.execute(stmt)).scalars().all()
    return [u.whatsapp_number for u in users if u.whatsapp_number]


async def build_reply(
    company_id: int,
    sender: str,
    text: str,
    generator: ContentGenerator | None = None,
) -> str:
    """Work out the reply for one inbound message.

    Pure with respect to the database — it reads no tables and writes none,
    which is what lets this vertical be stateless. `generator` is injected
    by the tests; production resolves it per call so a key added to the
    environment takes effect without a redeploy of this module's import.
    """
    gen = generator or get_generator()
    intent = intents.parse(text)

    # Small talk. Answered before anything reads the text as a project name.
    if intent.kind == "greeting":
        return formatter.render_greeting()

    # She confirmed a subject we flagged as unrecognised. Proceed with the
    # subject she originally sent, now with her explicit go-ahead.
    if intent.kind == "confirm":
        pending = state.take_pending(company_id, sender)
        if pending is None or pending.kind != "confirm_subject":
            return formatter.render_forgot_context()
        state.set_pending(company_id, sender, "audience", pending.subject)
        return formatter.render_format_question(pending.subject)

    # She answered ME / LEAD to a question we asked earlier.
    if intent.kind == "audience":
        pending = state.take_pending(company_id, sender)
        if pending is None:
            return formatter.render_forgot_context()
        lines = await gen.lead_intel(pending.subject, intent.value or "self")
        if not lines:
            return formatter.render_unavailable()
        return formatter.render_lead_intel(pending.subject, lines, intent.value or "self")

    # She picked ARTICLE / FUN FACT — either answering the daily nudge or
    # asking cold. Both are handled identically, which is why losing the
    # nudge's state on a restart costs nothing here.
    if intent.kind == "content":
        kind = "article" if intent.value == "article" else "fun_fact"
        lines = await gen.social_caption(kind)
        if not lines:
            return formatter.render_unavailable()
        state.clear(company_id, sender)
        return formatter.render_social_caption(kind, lines)

    if intent.kind == "lead_intel" and intent.subject:
        # Nothing in the curated geography tables corroborates this name, so
        # confirm before briefing — see Intent.confidence for why a question
        # beats a confident answer here.
        if intent.confidence == "low":
            state.set_pending(company_id, sender, "confirm_subject", intent.subject)
            return formatter.render_confirm_subject(intent.subject)

        # Format already stated in the same message — no need to ask.
        if intent.audience:
            lines = await gen.lead_intel(intent.subject, intent.audience)
            if not lines:
                return formatter.render_unavailable()
            return formatter.render_lead_intel(intent.subject, lines, intent.audience)

        state.set_pending(company_id, sender, "audience", intent.subject)
        return formatter.render_format_question(intent.subject)

    return formatter.render_unreadable()


async def handle_broker_message(
    db: AsyncSession, company_id: int, sender: str, text: str
) -> dict:
    """Inbound entry point. Sends the reply and reports what happened."""
    from app.services.launch_matcher.providers import get_provider

    reply = await build_reply(company_id, sender, text)
    result = await get_provider().send_text(sender, reply)

    # Logged without the message body or the reply: both can carry a lead's
    # personal details, and application logs have broader retention and
    # access than any table this vertical declines to write to.
    logger.info(
        "broker_intel inbound handled: company=%s sent=%s", company_id, bool(result.ok)
    )
    return {"status": "broker_intel", "sent": bool(result.ok), "reply": reply}


async def send_daily_nudge(db: AsyncSession, company_id: int) -> int:
    """Daily hook: offer today's content choice.

    Same contract as real_estate's send_broker_pulse — "what to do for one
    company" — with company enumeration, the per-company pulse toggle and
    the per-company try/except all handled generically by
    _send_vertical_daily_hooks in reminder_service.
    """
    from app.services.launch_matcher.providers import get_provider

    numbers = await _recipients(db, company_id)
    if not numbers:
        logger.info("broker_intel daily nudge: no recipients for company=%s", company_id)
        return 0

    body = formatter.render_daily_nudge()
    provider = get_provider()
    sent = 0
    for number in numbers:
        result = await provider.send_text(number, body)
        if result.ok:
            sent += 1
    logger.info("broker_intel daily nudge sent to %s recipient(s) for company=%s",
                sent, company_id)
    return sent


async def _registry_inbound(
    db: AsyncSession, company_id: int, sender: str, text: str
) -> dict:
    return await handle_broker_message(db, company_id, sender, text)


register_vertical(
    Vertical(
        name=BROKER_INTEL_VERTICAL,
        inbound=_registry_inbound,
        daily=send_daily_nudge,
        # Forwarded lead material can carry a third party's name and phone;
        # none of it may reach message_logs or auto-register an Employee.
        persist_inbound=False,
    )
)
