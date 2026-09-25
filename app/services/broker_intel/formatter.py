"""Reply formatting for broker_intel — and the two places its sourcing
caveats are enforced.

HARD REQUIREMENT, made structural. Every reply that carries market
commentary must say so, and must never let a figure read as an official
Dubai Land Department number. That promise is kept here rather than in the
generator or the handler, because both of those have many code paths and
this module has exactly two entry points for it:

  * `_content_reply` — for reply content that is PURELY AI-generated, with
    no search behind it (the daily nudge's article/fun-fact captions).
    Appends MARKET_CAVEAT.
  * `_sourced_reply` — for reply content built from real web search results
    via extraction.py's structured pipeline (lead intel, comparisons, the
    daily brief). Appends SOURCED_CAVEAT, and also lists which sources were
    actually cited, each with its trust tier (search.DOMAIN_TIERS).

Both take the caller's text and append their caveat unconditionally, with
no parameter to switch it off — so a new content feature cannot ship an
uncaveated reply by forgetting a flag. It can only do so by adding a THIRD
bullets-to-body function somewhere else, which is a visible edit, and
test_broker_intel.py asserts the caveat property over every reply-producing
entry point in this module, so a third path fails the suite rather than
passing quietly.

The wording of both caveats is deliberately readable in both audiences. The
lead-ready format is forwarded to a client verbatim, so neither caveat may
read like an internal note to the broker.
"""

from __future__ import annotations

from app.services.broker_intel import focus as focus_topics
from app.services.broker_intel.search import tier_emoji

# Appended to replies with NO search behind them — currently only the
# ARTICLE / FUN FACT captions, which remain general AI commentary by
# design (see content.py's docstring on the sourcing policy for those).
MARKET_CAVEAT = (
    "_General market context, AI-generated — indicative only, "
    "not official DLD data._"
)

# Appended to replies built from real web search results (lead intel,
# comparisons). Deliberately does NOT say "AI-generated" — the figures in
# these replies come from cited sources, not from the model's own
# knowledge — but is equally explicit that only 🟢-tier sources are
# official: search mostly surfaces portal LISTING prices, which run above
# what a unit actually sells for, and nothing here is guaranteed current.
#
# It opens with the tier legend for the emoji on the Sources line. That is
# permanent rather than a one-time explainer on purpose: this vertical keeps
# no conversation history (see state.py), so "first time she sees it" isn't
# knowable — and the LEAD format is forwarded to a client, who has never
# seen the legend and needs it in the message itself.
SOURCED_CAVEAT = (
    "_🟢 official/registry · 🟡 market data (portals, agencies) · "
    "🔴 news/opinion. Anything not 🟢 is not official DLD data — often "
    "listing prices, which run above sale prices. Not guaranteed current "
    "— verify before quoting a client._"
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
    """Bullets-to-body path for PURELY AI-generated content (no search
    behind it). Always caveated with MARKET_CAVEAT — see module docstring.
    """
    parts = [p for p in (header, _bullets(lines)) if p]
    return "\n\n".join(parts) + f"\n\n{MARKET_CAVEAT}"


def _sourced_reply(
    header: str,
    lines: list[str],
    cited_sources: list[tuple[int, object]],
    sections: list[tuple[str, list[str]]] | None = None,
    footnote: str = "",
) -> str:
    """Bullets-to-body path for content built from real search results —
    the counterpart to _content_reply. Always caveated with SOURCED_CAVEAT,
    and lists exactly which sources were actually cited (each `[n]` marker
    that reached this reply's bullets, resolved to its domain) — never the
    full search result set, only what got used.

    `sections` renders a grouped body (a bold sub-header per area, its own
    bullets beneath) instead of one flat list; `lines` is used when it is
    absent. Both shapes are assembled HERE rather than by the caller, so
    there is still exactly one function in this package that turns sourced
    content into a message body, and it still appends the caveat with no
    way to switch it off.

    Each cited source is shown with its trust-tier emoji (see
    search.DOMAIN_TIERS; unknown domains fall back to 🟡 with a logged
    warning), and SOURCED_CAVEAT opens with the legend for those emoji.

    `footnote` is a line to her under the body (see _gap_note) — it adds to
    the message; nothing about it can remove the caveat below.
    """
    if sections:
        body_parts = [f"*{name}*\n{_bullets(section_lines)}"
                      for name, section_lines in sections if section_lines]
        body = "\n\n".join(body_parts)
    else:
        body = _bullets(lines)
    parts = [p for p in (header, body, footnote) if p]
    if cited_sources:
        parts.append("Sources: " + "  ".join(
            f"[{i}] {tier_emoji(s.domain)} {s.domain}" for i, s in cited_sources
        ))
    parts.append(SOURCED_CAVEAT)
    return "\n\n".join(parts)


# ── Feature 1: lead intel ────────────────────────────────────

def _about(subject: str, focus: tuple[str, ...]) -> str:
    """"*JVC*", or "*JVC* — nearby landmarks" for a focused question, so she
    can see the question she asked was the one understood."""
    label = focus_topics.label(focus)
    return f"*{subject}* — {label}" if label else f"*{subject}*"


def _gap_note(subject: str, unanswered: tuple[str, ...], audience: str) -> str:
    """Names the part of a multi-part question that nothing sourced
    answered, so half an answer never passes for a whole one. Only in her
    own format: the LEAD one is forwarded, and its header already lists only
    what the message covers."""
    if not unanswered or audience == "lead":
        return ""
    return f"_Couldn't find anything sourced on {focus_topics.label(unanswered)} for {subject}._"


def render_format_question(subject: str, focus: tuple[str, ...] = ()) -> str:
    """Asked before generating, when she hasn't already said which format."""
    return f"Got it — {_about(subject, focus)}.\n\n{_FORMAT_PROMPT}"


def render_lead_intel(
    subject: str,
    lines: list[str],
    audience: str,
    cited_sources: list[tuple[int, object]] | None = None,
    focus: tuple[str, ...] = (),
    unanswered: tuple[str, ...] = (),
) -> str:
    """The briefing itself, built from real search results — see
    briefing.py. cited_sources defaults to empty so existing direct callers
    (tests probing the caveat property) still work without threading it.

    The 'lead' audience gets no header naming the broker or the request,
    because the whole message is forwarded to the client as-is; a header
    like "Here's your briefing on X" would read as addressed to her, not to
    them. A focused answer does get a header in both formats — just the
    place and the topic, "*JVC* — nearby landmarks" — because its bullets
    are named places that don't say which community they surround, and that
    header reads as naturally to a client as to her.

    `focus` is what the reply answers; `unanswered`, what she also asked
    that nothing sourced covered (see _gap_note).
    """
    if focus:
        header = _about(subject, focus)
    else:
        header = "" if audience == "lead" else f"*{subject}*"
    return _sourced_reply(header, lines, cited_sources or [],
                          footnote=_gap_note(subject, unanswered, audience))


# ── Feature 2: the daily brief ──────────────────────────────

DAILY_BRIEF_TITLE = "🏠 *UAE PROPERTY INTELLIGENCE*"
IDEA_SECTION = "💡 Post idea (AI suggestion)"


def render_daily_brief(
    date_label: str,
    news_line: str | None,
    data_area: str | None,
    data_line: str | None,
    idea_line: str | None,
    cited_sources: list[tuple[int, object]],
) -> str:
    """The proactive morning brief — see briefing.build_daily_brief.

    Any section that found nothing is left out, never filled with a
    placeholder. Built through _sourced_reply like every other sourced
    reply, so the tiered Sources line and SOURCED_CAVEAT cannot be skipped.
    The post idea is the one unsourced part; its section header says so
    outright, since SOURCED_CAVEAT deliberately doesn't say AI-generated.
    """
    sections: list[tuple[str, list[str]]] = []
    if news_line:
        sections.append(("🔥 Top news", [news_line]))
    if data_line:
        sections.append((f"📊 Market data — {data_area}", [data_line]))
    if idea_line:
        sections.append((IDEA_SECTION, [idea_line]))
    header = f"{DAILY_BRIEF_TITLE} — {date_label}"
    return _sourced_reply(header, [], cited_sources, sections=sections)


def render_daily_nudge() -> str:
    """The fallback morning message, sent when the daily brief found nothing
    sourced to report (see briefing.build_daily_brief). Carries no generated
    content itself, so it needs no caveat — it only offers a choice."""
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

def render_comparison(
    subjects: list[str],
    lines: list[str],
    audience: str,
    cited_sources: list[tuple[int, object]] | None = None,
    sections: list[tuple[str, list[str]]] | None = None,
    focus: tuple[str, ...] = (),
    unanswered: tuple[str, ...] = (),
) -> str:
    """A genuine side-by-side, built from real search results per area —
    see briefing.py. Goes through _sourced_reply like render_lead_intel, so
    the caveat and source list still cannot be skipped.

    `sections` selects the grouped layout (a block per area) over the flat
    interleaved one; the header is dropped in grouped mode because each
    block already names its area — unless the question had a focus, when
    the header carries what was compared ("*Arjan vs JVC* — schools").
    """
    compared = " vs ".join(subjects)
    if focus:
        header = _about(compared, focus)
    elif sections:
        header = ""
    else:
        header = "" if audience == "lead" else f"*{compared}*"
    footnote = _gap_note(compared, unanswered, audience)
    if sections:
        return _sourced_reply(header, [], cited_sources or [], sections=sections,
                              footnote=footnote)
    return _sourced_reply(header, lines, cited_sources or [], footnote=footnote)


def render_partial_comparison(found: str, original: str) -> str:
    """One area recognised where the wording meant several.

    This is the reply for the bug she actually hit: the bot answered about
    Arjan alone and gave no sign it had dropped "JVC" or that she'd asked to
    compare. Saying what was understood — and what wasn't — is the whole
    point, so it names the one it found rather than asking a blank question.
    """
    return (
        f"I could only pick out *{found}* in that.\n\n"
        "Did you mean to compare it with somewhere else? Send both areas "
        "and I'll do a side-by-side — e.g. \"Arjan vs JVC\"."
    )


def render_no_live_data() -> str:
    """She asked for real figures with no area or project named — nothing
    to search on yet. Now that briefings ARE search-backed (see
    briefing.py), the honest answer is to say what's still true (no
    official DLD transaction data) and point her at what actually gets
    real numbers: naming a subject."""
    return (
        "I don't have official DLD transaction data — but I can search "
        "real published sources (portals, agencies, press) for a specific "
        "area or project.\n\n"
        "Tell me which one — e.g. *Arjan* or *JVC* — and I'll pull current "
        "figures with sources attached.\n\n"
        "Worth knowing: those are listing/asking prices, not registered "
        "sale prices, so they can run above what a unit actually sells for."
    )


def render_thin_sources(subject: str, focus: tuple[str, ...] = ()) -> str:
    """Search ran for `subject` but turned up nothing usable — distinct
    from render_unavailable (a hard failure of search or extraction) and
    render_no_live_data (no subject was even given). Same principle as
    both: no data beats invented data, said plainly rather than papered
    over with vague market commentary.

    For a focused question it names the topic that came up empty, and
    points at the general briefing rather than at "the area it's in"."""
    if focus:
        return (
            f"I searched, but couldn't find good sourced information on "
            f"{focus_topics.label(focus)} for *{subject}* right now.\n\n"
            f"Send just *{subject}* on its own for the general briefing "
            "instead, or check back later as more gets published."
        )
    return (
        f"I searched, but couldn't find good sourced information on "
        f"*{subject}* right now.\n\n"
        "That can happen for a very new or small project that hasn't been "
        "written about yet. Try the area it's in instead, or check back "
        "later as more gets published."
    )


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


def render_confirm_subject(subject: str, focus: tuple[str, ...] = ()) -> str:
    """Asked when the subject is a low-confidence guess (see Intent.confidence).

    Deliberately offers to proceed rather than refusing: it may well be a
    genuine new launch the curated tables don't list yet. It just must not
    silently produce a confident briefing about something that might not
    exist.
    """
    label = focus_topics.label(focus)
    then = f"look up {label} for it anyway" if label else "brief you on it anyway"
    return (
        f"I don't recognise *{subject}* as a project or area I know.\n\n"
        f"If that's right, reply *YES* and I'll {then}.\n"
        "Otherwise send the area — e.g. \"JVC\" or \"Sobha Hartland\"."
    )


def render_need_subject(focus: tuple[str, ...]) -> str:
    """She asked about a topic without naming a place ("what are the
    rental yields?"). Says what was understood and asks where — nothing is
    held in state, so the example shows sending both together."""
    label = focus_topics.label(focus)
    return (
        f"Happy to look up {label} — for which area or project?\n\n"
        f"Send it with the place, e.g. \"{label} in JVC\"."
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
