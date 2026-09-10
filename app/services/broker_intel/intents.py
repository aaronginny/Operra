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

# Greetings and small talk. Checked before project extraction, because
# extract_project below will happily treat "hello" as a project name — it has
# no vocabulary of real projects to check against, only a shape. That
# produced "Got it — *hello*. ME or LEAD?", which is the kind of reply that
# makes a tool feel broken on first contact.
_GREETINGS = (
    "hi", "hii", "hiii", "hey", "hello", "helo", "yo",
    "good morning", "good afternoon", "good evening", "gm", "ga",
    "salam", "salaam", "assalam", "assalamualaikum", "as salam alaikum",
    "namaste", "hola", "morning", "evening",
    "thanks", "thank you", "thx", "ty", "shukran",
    "ok", "okay", "k", "cool", "great", "nice", "done",
    "test", "testing",
)

# Confirms a low-confidence subject the bot asked about (see Intent.confidence).
_CONFIRM_WORDS = ("yes", "yep", "yeah", "yup", "correct", "confirm", "go ahead", "proceed", "y")

# Signals that she is asking about more than one place. Used two ways: to
# decide a multi-area message is a comparison, and — the case that actually
# bit her — to notice that a message MEANT to name several areas when only
# one was recognised, so the bot says so instead of silently answering half.
_COMPARISON_MARKERS = (
    "compare", "comparison", "versus", "vs", "against",
    "difference", "differences", "better",
)

# She asked "I need data backed reply, with numbers". The bot has no live
# transaction data — briefings are AI-generated general context — so an
# explicit request for real figures must be answered honestly rather than
# mis-parsed. Matched only when no area/project is present, so "compare
# Arjan and JVC in terms of rates and ROI" stays a comparison: mentioning
# rates while naming places is not the same as asking what the tool is.
_DATA_REQUEST_PHRASES = (
    "data backed", "data-backed", "backed by data", "with numbers",
    "actual numbers", "real numbers", "give me numbers", "need numbers",
    "hard numbers", "exact figures", "real data", "actual data", "live data",
    "official data", "dld data", "transaction data", "statistics", "stats",
    "source", "sourced", "citation", "citations", "evidence",
)

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
      greeting  — small talk, not a query
      confirm   — she confirmed a subject the bot was unsure about
      comparison — two or more recognised areas (subjects holds all of them)
      partial_comparison — one area recognised, but the wording meant more
      data_request — an explicit ask for real figures / sourced data
      content   — she picked ARTICLE / FUN FACT (value holds which)
      audience  — she picked ME / LEAD (value holds "self" / "lead")
      lead_intel — she named a project/area (subject holds it; audience may
                   already be set if she said both in one message)
      unknown   — nothing usable

    confidence, for lead_intel only:
      "high" — the subject matched the curated UAE geography tables, so it
               is definitely a real place.
      "low"  — the subject is a best-effort name lifted from her text with
               nothing to corroborate it. It might be a genuine new launch
               the tables don't list, or it might be a typo or a stray
               sentence. The handler asks rather than briefing on it, since
               a confident briefing about a project that does not exist is
               worse than a question — especially under the forwardable
               format, where she might send it to a client before noticing.
    """

    kind: str
    value: str | None = None
    subject: str | None = None
    audience: str | None = None
    emirate: str | None = None
    area: str | None = None
    confidence: str | None = None
    # comparison only: every recognised area, in the order she wrote them.
    subjects: list[str] | None = None
    emirates: list[str] | None = None


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


def find_all_areas(text: str) -> list[tuple[str, str]]:
    """Every distinct known area in the text, as (emirate, display name), in
    the order they appear.

    find_area below returns only the first match, which is what silently
    dropped "JVC" from "Compare Arjan and JVC" — the caller had no way to
    know a second area was even present. This returns all of them so the
    handler can compare rather than quietly pick one.

    Longest name first, and matched spans are consumed, so "sobha hartland"
    is one area rather than also counting as "hartland".
    """
    lowered = text.lower()
    consumed: list[tuple[int, int]] = []
    found: list[tuple[int, str, str]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in consumed)

    for name in sorted(AREA_TO_EMIRATE, key=len, reverse=True):
        for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", lowered):
            if overlaps(m.start(), m.end()):
                continue
            consumed.append((m.start(), m.end()))
            found.append((m.start(), AREA_TO_EMIRATE[name],
                           AREA_DISPLAY.get(name, name.title())))

    # De-duplicate by display name, keeping first appearance order.
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for _pos, emirate, display in sorted(found, key=lambda t: t[0]):
        if display not in seen:
            seen.add(display)
            ordered.append((emirate, display))
    return ordered


def wants_comparison(text: str) -> bool:
    """True when the wording implies more than one place, whether or not we
    recognised them all.

    "and"/"&" are deliberately NOT treated as markers on their own in a long
    sentence: "tell me about JVC and the market there" is one area with an
    incidental conjunction, not a comparison. They only count in a short
    message, where "Arjan and Nakheel Heights" really is a list of two —
    which is the case worth catching, since the second name may be a project
    the curated tables don't know and so can't be detected directly.
    """
    lowered = text.lower()
    for marker in _COMPARISON_MARKERS:
        if _has_word(lowered, marker.strip()):
            return True
    if len(text.split()) <= 6 and (_has_word(lowered, "and") or "&" in text):
        return True
    return False


def wants_real_data(text: str) -> bool:
    """True when she is explicitly asking for real figures / sourced data."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _DATA_REQUEST_PHRASES)


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

    # Greetings / small talk, before anything tries to read the text as a
    # project name. Only for a short message carrying no geography, so
    # "hi, what about JVC" is still a briefing request.
    stripped = lowered.strip(" .!?,")
    if emirate is None and len(text.split()) <= 3:
        if stripped in _GREETINGS or any(
            stripped == g or stripped.startswith(g + " ") for g in _GREETINGS
        ):
            return Intent(kind="greeting")

        if stripped in _CONFIRM_WORDS:
            return Intent(kind="confirm")

    # An explicit ask for real figures, when nothing here names a place.
    # Checked BEFORE the keyword replies below because a phrasing like "give
    # me actual numbers" contains "me", which the bare-audience matcher would
    # otherwise claim as a ME/LEAD format choice.
    if emirate is None and not find_all_areas(text) and wants_real_data(text):
        return Intent(kind="data_request")

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

    # Two or more recognised areas -> a genuine side-by-side, not a silent
    # pick of whichever matched first.
    all_areas = find_all_areas(text)
    if len(all_areas) >= 2:
        return Intent(
            kind="comparison",
            subjects=[display for _em, display in all_areas],
            emirates=[em for em, _display in all_areas],
            audience=audience,
            confidence="high",
        )

    # Exactly one area, but the wording clearly meant several. Say so rather
    # than answering half the question — the case that prompted this fix.
    if len(all_areas) == 1 and wants_comparison(text):
        return Intent(
            kind="partial_comparison",
            subject=all_areas[0][1],
            emirate=all_areas[0][0],
            area=all_areas[0][1],
            audience=audience,
            confidence="high",
        )

    # An explicit ask for real figures, and nothing here names a place —
    # answer honestly about what this tool has rather than trying to read
    # "I need data backed reply, with numbers" as a project name. Checked
    # after the area paths on purpose: naming rates/ROI alongside real areas
    # is a briefing request, not a question about the tool's sourcing.
    if not all_areas and emirate is None and wants_real_data(text):
        return Intent(kind="data_request")

    # An area or emirate came from the curated tables, so it is definitely
    # real. Anything else is a shape-based guess from her wording.
    if area or emirate:
        subject, confidence = (area or emirate), "high"
    else:
        subject, confidence = extract_project(text), "low"

    if subject:
        return Intent(
            kind="lead_intel",
            subject=subject,
            audience=audience,
            emirate=emirate,
            area=area,
            confidence=confidence,
        )

    return Intent(kind="unknown")
