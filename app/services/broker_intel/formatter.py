"""Reply formatting for broker_intel — and the one place the sourcing
caveat is enforced.

HARD REQUIREMENT, made structural. Every reply that carries AI-generated
market commentary must say so, and must never let a figure read as an
official Dubai Land Department number. That promise is kept here rather than
in the generator or the handler, because both of those have many code paths
and this has one: `_content_reply` is the only function in the package that
turns generated bullets into a message body, and it appends the caveat
unconditionally, after the caller's text, with no parameter to switch it off.

So a new content feature cannot ship an uncaveated reply by forgetting a
flag. It can only do so by adding a second bullets-to-body function
somewhere else, which is a visible edit — and test_broker_intel.py asserts
the property over every reply-producing entry point in this module, so a
second path fails the suite rather than passing quietly.

The wording is deliberately readable in both audiences. The lead-ready
format is forwarded to a client verbatim, so the caveat cannot read like an
internal note to the broker; "indicative market context" works in front of
a client, "FYI these numbers are AI-generated, don't quote them" would not.
"""

from __future__ import annotations

# Appended to every content-bearing reply. Short enough not to dominate a
# phone screen, explicit enough that no figure above it can be mistaken for
# an official registry number.
MARKET_CAVEAT = (
    "_General market context, AI-generated — indicative only, "
    "not official DLD data._"
)

_FORMAT_PROMPT = (
    "How do you want it?\n\n"
    "- *ME* — quick read for you\n"
    "- *LEAD* — polished, ready to forward\n\n"
    "Reply ME or LEAD."
)


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"• {line}" for line in lines)


def _content_reply(header: str, lines: list[str]) -> str:
    """The ONLY bullets-to-body path in this package. Always caveated.

    Every content-bearing renderer below routes through here. See this
    module's docstring for why that matters and what enforces it.
    """
    parts = [p for p in (header, _bullets(lines)) if p]
    return "\n\n".join(parts) + f"\n\n{MARKET_CAVEAT}"


# ── Feature 1: lead intel ────────────────────────────────────

def render_format_question(subject: str) -> str:
    """Asked before generating, when she hasn't already said which format."""
    return f"Got it — *{subject}*.\n\n{_FORMAT_PROMPT}"


def render_lead_intel(subject: str, lines: list[str], audience: str) -> str:
    """The briefing itself.

    The 'lead' audience gets no header naming the broker or the request,
    because the whole message is forwarded to the client as-is; a header
    like "Here's your briefing on X" would read as addressed to her, not to
    them.
    """
    header = "" if audience == "lead" else f"*{subject}*"
    return _content_reply(header, lines)


# ── Feature 2: daily content nudge ───────────────────────────

def render_daily_nudge() -> str:
    """The proactive morning message. Carries no generated content itself,
    so it needs no caveat — it only offers a choice."""
    return (
        "Morning! Want something to post today?\n\n"
        "- *ARTICLE* — a short market insight\n"
        "- *FUN FACT* — a bit of Dubai trivia\n\n"
        "Reply ARTICLE or FUN FACT."
    )


def render_social_caption(kind: str, lines: list[str]) -> str:
    label = "Article" if kind == "article" else "Fun fact"
    return _content_reply(f"*{label} — ready to post*", lines)


# ── Non-content replies (no generated market claims, so no caveat) ──

def render_greeting() -> str:
    """Replied to small talk. Doubles as the de-facto welcome message, since
    "hi" is what a new user sends first — so it says what this can actually
    do rather than just greeting back."""
    return (
        "Hello! 👋\n\n"
        "Send me a project or area and I'll put together a briefing — "
        "market context, why it appeals, developer, nearby landmarks.\n\n"
        "- e.g. *Sobha Hartland* or *tell me about JVC*\n"
        "- or reply *ARTICLE* / *FUN FACT* for something to post today"
    )


def render_confirm_subject(subject: str) -> str:
    """Asked when the subject is a low-confidence guess (see Intent.confidence).

    Deliberately offers to proceed rather than refusing: it may well be a
    genuine new launch the curated tables don't list yet. It just must not
    silently produce a confident briefing about something that might not
    exist.
    """
    return (
        f"I don't recognise *{subject}* as a project or area I know.\n\n"
        "If that's right, reply *YES* and I'll brief you on it anyway.\n"
        "Otherwise send the area — e.g. \"JVC\" or \"Sobha Hartland\"."
    )


def render_unreadable() -> str:
    return (
        "I couldn't tell which project or area you meant.\n\n"
        "Send me the project name or area — e.g. \"Sobha Hartland\" or "
        "\"tell me about JVC\" — and I'll pull a briefing together."
    )


def render_unavailable() -> str:
    """Used when generation failed. Deliberately says nothing about the
    market: a failed generation must never be papered over with filler that
    could be mistaken for a briefing."""
    return (
        "I couldn't generate that just now — the content service didn't "
        "respond.\n\nTry again in a moment."
    )


def render_forgot_context() -> str:
    """She answered ME/LEAD but the pending question is gone (see state.py —
    the cache is in-process and short-lived, so a restart drops it)."""
    return (
        "Sorry — I've lost track of which project that was for.\n\n"
        "Send me the project or area again and I'll pick it straight back up."
    )
