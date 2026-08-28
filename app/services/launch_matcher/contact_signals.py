"""Shared text-classification signals for parsing raw contact data.

Used by both bulk-import features that turn someone else's contact export
into rows here: the investor_criteria importer (app/services/launch_matcher/
importer.py — a contact's free-text tag) and the contact_lookup importer
(app/services/launch_matcher/contact_lookup_importer.py — a contact's name
itself, since that export has no separate tag field). Both need the same
two judgements on the same kind of short, curated text — "is this contact
worth keeping at all" and "what emirate/area does it hint at" — so the logic
lives once here rather than drifting into two copies.

REUSE OF THE LAUNCH PARSER'S TABLES: EMIRATES and AREA_TO_EMIRATE (imported
from parser.py) are reused as-is — already the vetted, deployed keyword
tables for exactly this job. They are NOT reused via parser.py's own
_extract_emirate_and_area function, because this module also folds in
SUPPLEMENTARY_AREAS and SHORT_CODE_EMIRATES below, both kept deliberately
separate from parser.py's own tables — see the comments on each for why.
"""

from __future__ import annotations

import re

from app.services.launch_matcher.parser import AREA_DISPLAY, AREA_TO_EMIRATE, EMIRATES

# Substrings marking a contact as not worth keeping, regardless of anything
# else in the text — checked case-insensitively, and checked before
# area/emirate detection, so "wrong number, was asking about Dubai" is still
# rejected rather than kept because "Dubai" also appears.
SKIP_PHRASES = (
    "wrong number", "blocked me", "blocked", "no response", "not responding",
    "unresponsive", "don't send", "dont send", "do not send", "not interested",
    "spam", "do not contact", "dnc", "invalid number", "duplicate",
    "unsubscribe", "switched off", "no res", "cnt reach", "not working",
    "no budget", "not in service",
)

# Development/area names not yet in parser.py's own AREA_TO_EMIRATE. Kept
# separate for the same reason as the short emirate codes below: unverified
# against the deployed launch-broadcast parser's false-positive risk profile,
# whereas the short, curated text this module reads (a contact tag or name)
# has a much lower risk of an incidental match.
#
# "la foret" (Abu Dhabi) and "al barari"/"barari" (Dubai — not Sharjah as
# first described; Al Barari is the well-known villa community off Al Ain
# Road) were both confirmed explicitly by Aaron.
#
# "alfurjan" and "jlt" are not new geography claims — they're variants of
# areas already in parser.py's own AREA_TO_EMIRATE ("al furjan" with the
# space; "jvc"/"jvt"/"jbr" as the precedent for a well-established 3-letter
# Dubai acronym) that its word-boundary matching doesn't catch: "alfurjan"
# has no space to match "al furjan", and "jlt" (Jumeirah Lake Towers) simply
# isn't in that table yet. Surfaced by the real import run against Mahmoud's
# actual contact list, not guessed.
SUPPLEMENTARY_AREAS = {
    "masaar": "Sharjah",
    "la foret": "Abu Dhabi",
    "al barari": "Dubai",
    "barari": "Dubai",
    "alfurjan": "Dubai",
    "jlt": "Dubai",
}

SUPPLEMENTARY_AREA_DISPLAY = {
    "alfurjan": "Al Furjan",
    "jlt": "JLT",
}

# Contact-tag/contact-name shorthand for an emirate ("DXB investor", "Ahmed
# SHJ"), as opposed to how an emirate would be named in full-sentence launch
# broadcast prose. Deliberately NOT merged into parser.py's own EMIRATES
# table: that table backs the already-deployed launch-broadcast parser, where
# a bare 2-3 letter code risks matching inside unrelated prose. AUH, RAK and
# UAQ are omitted here because parser.py's own EMIRATES already recognises
# them.
SHORT_CODE_EMIRATES = {
    "DXB": "Dubai",
    "SHJ": "Sharjah",
    "AJM": "Ajman",
    "FUJ": "Fujairah",
    # 2 letters and far too generic to trust case-insensitively (would match
    # inside "ad campaign", "add", ...). Matched literal-uppercase only.
    "AD": "Abu Dhabi",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")
BARE_PHONE_RE = re.compile(r"^[\d\s\-+()]{7,}$")


def guess_emirate_and_area(text: str) -> tuple[str | None, str | None]:
    """Best-effort emirate/area guess from a short piece of contact text (a
    tag or a contact name).

    Area-level signals always win over emirate-only ones, regardless of which
    table they came from: first a known area name (parser.py's own table,
    longest first), then SUPPLEMENTARY_AREAS (also area-level) — only after
    both of those fail to match does an emirate-only signal get to decide
    anything, from EMIRATES then SHORT_CODE_EMIRATES. Without this ordering,
    a text containing both an emirate code and a more specific area name
    (e.g. "AUH" and "La Foret" together) would report the emirate and lose
    the area, since a naive first-match-wins scan hits the emirate table
    first. Returns (emirate, area) — area is None only when no area-level
    signal, from either table, was found.
    """
    lowered = text.lower()

    for name in sorted(AREA_TO_EMIRATE, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return AREA_TO_EMIRATE[name], AREA_DISPLAY.get(name, name.title())

    for name, canonical in sorted(SUPPLEMENTARY_AREAS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return canonical, SUPPLEMENTARY_AREA_DISPLAY.get(name, name.title())

    for name, canonical in sorted(EMIRATES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return canonical, None

    for code, canonical in SHORT_CODE_EMIRATES.items():
        if len(code) == 2:
            if re.search(rf"\b{code}\b", text):  # case-sensitive on purpose
                return canonical, None
        elif re.search(rf"\b{code}\b", text, re.I):
            return canonical, None

    return None, None


def skip_phrase(text: str) -> str | None:
    """The first SKIP_PHRASES entry found in text, or None."""
    lowered = text.lower()
    for phrase in SKIP_PHRASES:
        if phrase in lowered:
            return phrase
    return None
