"""Read one inbound WhatsApp message into a broker_intel intent.

DESIGN NOTE — how she names a project or area (design question 1).

She does not learn a command syntax. She forwards or types naturally, the
same way launch_matcher's advisor forwards a launch broadcast, and this
module works out what she meant. Three signals, in priority order:

  1. A known UAE area name, from app.services.geo.uae — the same curated
     table the launch parser matches against, extracted to a shared module
     in the platform refactor precisely so a second vertical could use it
     without importing a launch-broadcast parser.
  2. A known emirate name.
  3. Otherwise, a best-effort project name lifted from the message text —
     because most of what she forwards is a specific project ("Sobha
     Hartland II"), and the area table cannot list every launch.

If none of the three yield anything, the handler asks rather than guessing.
A wrong guess here is worse than a question: it would produce a confident
briefing about the wrong community, and under the 'lead' format she might
forward it to a client before noticing.

Keyword intents (ARTICLE / FUN FACT / ME / LEAD) are checked before any of
that, and are matched as whole words so a project called "Article Living"
does not read as a content request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.geo.uae import AREA_DISPLAY, AREA_TO_EMIRATE, EMIRATES

# Two vocabularies, deliberately different.
#
# _BARE_AUDIENCE is only consulted for a short standalone reply — she is
# answering the ME/LEAD question and nothing else.
#
# _INLINE_AUDIENCE is what may be read out of a longer sentence, and every
# entry is a phrase rather than a bare word. This matters: "tell me about
# Sobha Hartland" contains the standalone word "me", so a bare-word list
# would silently classify the most natural phrasing she could possibly use
# as a format choice and skip the question entirely. Only an explicit "for
# me" / "for the lead" counts inside a sentence.
_BARE_AUDIENCE = {
    "self": ("me", "mine", "myself", "quick", "read"),
    "lead": ("lead", "client", "send", "forward", "polished"),
}

_INLINE_AUDIENCE = {
    "self": ("for me", "for myself", "for my own", "just for me"),
    "lead": ("for the lead", "for lead", "for the client", "for client",
              "to forward", "to send", "ready to send", "send to lead",
              "send to the lead", "polished"),
}

_CONTENT_WORDS = {
    "article": ("article", "insight", "post"),
    "fun_fact": ("fun fact", "funfact", "fact", "trivia"),
}

# Stripped before project-name extraction so "tell me about Sobha Hartland"
# yields "Sobha Hartland" rather than the whole sentence. Ordered longest
# first so the longer phrasings win.
_LEAD_PREFIXES = (
    "can you tell me about", "tell me more about", "what do you know about",
    "give me info on", "give me details on", "tell me about", "info on",
    "details on", "brief me on", "what about", "how about", "look up",
    "anything on", "intel on", "about",
)

_NOISE = re.compile(r"[‘’“”\"'`*_~]+")


def _has_word(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


@dataclass
class Intent:
    """What the message asked for.

    kind is one of:
      content   — she picked ARTICLE / FUN FACT (value holds which)
      audience  — she picked ME / LEAD (value holds "self" / "lead")
      lead_intel — she named a project/area (subject holds it; audience may
                   already be set if she said both in one message)
      unknown   — nothing usable
    """

    kind: str
    value: str | None = None
    subject: str | None = None
    audience: str | None = None
    emirate: str | None = None
    area: str | None = None


def _match_audience(lowered: str, *, bare: bool) -> str | None:
    """bare=True for a short standalone reply (the ME/LEAD answer);
    bare=False for a hint embedded in a longer sentence, where only explicit
    phrases count — see the comment on the two tables above."""
    table = _BARE_AUDIENCE if bare else _INLINE_AUDIENCE
    for audience, words in table.items():
        for w in words:
            if _has_word(lowered, w):
                return audience
    return None


def _match_content(lowered: str) -> str | None:
    # fun fact before article: "fun fact article" should read as the fact.
    for kind in ("fun_fact", "article"):
        for w in _CONTENT_WORDS[kind]:
            if _has_word(lowered, w):
                return kind
    return None


def find_area(text: str) -> tuple[str | None, str | None]:
    """(emirate, area display name) from known UAE geography, longest match
    first so "sobha hartland" beats "hartland". Same approach as the launch
    parser, against the same shared table."""
    lowered = text.lower()
    for name in sorted(AREA_TO_EMIRATE, key=len, reverse=True):
        if _has_word(lowered, name):
            return AREA_TO_EMIRATE[name], AREA_DISPLAY.get(name, name.title())
    for name, canonical in sorted(EMIRATES.items(), key=lambda kv: -len(kv[0])):
        if _has_word(lowered, name):
            return canonical, None
    return None, None


def extract_project(text: str) -> str | None:
    """Best-effort project name from free text.

    Takes the first substantive line, strips a leading question phrasing,
    and cuts at the first separator — the same shape as the launch parser's
    own project extraction, kept local because the goal differs: this wants
    a label to brief on, not a field to match against.
    """
    for raw in (text or "").splitlines():
        line = _NOISE.sub("", raw).strip()
        if not line:
            continue
        lowered = line.lower()
        for prefix in _LEAD_PREFIXES:
            if lowered.startswith(prefix):
                line = line[len(prefix):].strip(" ,:?-")
                break
        # Drop a trailing question mark and any separator tail.
        line = re.split(r"\s*[|·•\n]\s*|\s+[-–—]\s+", line)[0].strip(" ?.,:-")
        if len(line) < 3:
            continue
        # A line that is only digits/punctuation is not a name.
        if re.fullmatch(r"[\d\s.,/%-]+", line):
            continue
        return line[:80]
    return None


def parse(text: str) -> Intent:
    """Read a message into an Intent. Never raises."""
    text = (text or "").strip()
    if not text:
        return Intent(kind="unknown")

    lowered = text.lower()
    emirate, area = find_area(text)

    # A bare keyword reply. Checked first, and only when the message carries
    # no geography — "article about JVC" is a briefing request, not a post.
    content = _match_content(lowered)
    if content and emirate is None and len(text.split()) <= 4:
        return Intent(kind="content", value=content)

    if emirate is None and len(text.split()) <= 4:
        bare_audience = _match_audience(lowered, bare=True)
        if bare_audience:
            return Intent(kind="audience", value=bare_audience)

    # Inside a longer message only an explicit phrase counts.
    audience = _match_audience(lowered, bare=False)

    subject = area or extract_project(text) or emirate
    if subject:
        return Intent(
            kind="lead_intel",
            subject=subject,
            audience=audience,
            emirate=emirate,
            area=area,
        )

    return Intent(kind="unknown")
