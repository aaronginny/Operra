"""Parse a forwarded UAE project-launch broadcast into structured fields.

Approach: deterministic regex plus curated keyword tables, not an LLM. Launch
broadcasts are highly templated ("Sobha Hartland II | 1BR from AED 1.4M |
60/40 | EOI Thursday"), so pattern matching handles them accurately, and it is
free, offline, instant, and — unlike an LLM call — never ships the forwarded
message to a third party, which matters when forwarded broadcasts can carry
other people's contact details in the footer.

`LaunchParser` is a Protocol, so an LLM-backed parser can be dropped in later
for messages this one cannot read. The matcher only ever sees `ParsedLaunch`,
so nothing downstream depends on how the text was interpreted.

Nothing in this module extracts, stores, or returns a person's name, phone
number, or email — forwarded broadcasts often contain an agent's number in the
footer, and it is deliberately left on the floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

# ── Reference data ───────────────────────────────────────────

EMIRATES = {
    "dubai": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "abudhabi": "Abu Dhabi",
    "auh": "Abu Dhabi",
    "ras al khaimah": "RAK",
    "rak": "RAK",
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "fujairah": "Fujairah",
    "umm al quwain": "UAQ",
    "uaq": "UAQ",
}

# Areas we can recognise, mapped to their emirate. Used both to pull the area
# out of the text and to infer the emirate when the broadcast doesn't say it
# outright — which is common, because everyone in the group already knows.
AREA_TO_EMIRATE = {
    # ── Dubai ──
    "sobha hartland": "Dubai", "hartland": "Dubai", "meydan": "Dubai",
    "mbr city": "Dubai", "mohammed bin rashid city": "Dubai",
    "downtown": "Dubai", "downtown dubai": "Dubai", "business bay": "Dubai",
    "dubai marina": "Dubai", "marina": "Dubai", "jbr": "Dubai",
    "palm jumeirah": "Dubai", "bluewaters": "Dubai", "city walk": "Dubai",
    "jvc": "Dubai", "jumeirah village circle": "Dubai",
    "jvt": "Dubai", "jumeirah village triangle": "Dubai",
    "dubai hills": "Dubai", "dubai hills estate": "Dubai",
    "creek harbour": "Dubai", "dubai creek harbour": "Dubai",
    "damac hills": "Dubai", "damac lagoons": "Dubai",
    "arjan": "Dubai", "al furjan": "Dubai", "dubai south": "Dubai",
    "emaar beachfront": "Dubai", "dubai islands": "Dubai",
    "expo city": "Dubai", "the valley": "Dubai", "emaar south": "Dubai",
    "town square": "Dubai", "dubailand": "Dubai", "silicon oasis": "Dubai",
    "sports city": "Dubai", "motor city": "Dubai", "discovery gardens": "Dubai",
    "international city": "Dubai", "al barsha": "Dubai", "tilal al ghaf": "Dubai",
    "rashid yachts": "Dubai", "mina rashid": "Dubai", "za'abeel": "Dubai",
    "zabeel": "Dubai", "jumeirah garden city": "Dubai", "barsha heights": "Dubai",
    # ── Abu Dhabi ──
    "yas island": "Abu Dhabi", "saadiyat": "Abu Dhabi",
    "saadiyat island": "Abu Dhabi", "al reem": "Abu Dhabi",
    "reem island": "Abu Dhabi", "al maryah": "Abu Dhabi",
    "maryah island": "Abu Dhabi", "al raha": "Abu Dhabi",
    "masdar city": "Abu Dhabi", "khalifa city": "Abu Dhabi",
    "al ghadeer": "Abu Dhabi", "zayed city": "Abu Dhabi",
    # ── Ras Al Khaimah ──
    "al marjan": "RAK", "al marjan island": "RAK", "mina al arab": "RAK",
    "hayat island": "RAK", "al hamra": "RAK",
    # ── Sharjah ──
    "aljada": "Sharjah", "al jada": "Sharjah", "maryam island": "Sharjah",
    "sharjah waterfront": "Sharjah",
}

# Areas whose display form isn't just .title() — acronyms and stylised names.
AREA_DISPLAY = {
    "jvc": "JVC", "jvt": "JVT", "jbr": "JBR",
    "mbr city": "MBR City", "damac hills": "DAMAC Hills",
    "damac lagoons": "DAMAC Lagoons", "za'abeel": "Za'abeel",
    "al maryah": "Al Maryah", "aljada": "Aljada",
}

DEVELOPERS = [
    "Sobha", "Emaar", "Damac", "DAMAC", "Nakheel", "Meraas", "Aldar", "Danube",
    "Binghatti", "Azizi", "Ellington", "Omniyat", "Select Group", "Samana",
    "Deyaar", "Union Properties", "Wasl", "Dubai Properties", "MAG", "Tiger",
    "Object 1", "Reportage", "Nshama", "Arada", "Eagle Hills", "Bloom",
    "Imkan", "Modon", "Q Properties", "RAK Properties", "Sol Properties",
    "Prestige One ", "Vincitore", "Danube Properties", "LEOS", "Majid Al Futtaim",
]

# Unit types, normalised. Order matters: longer patterns first so "studio"
# isn't shadowed and "1.5BR" style variants resolve sensibly.
UNIT_PATTERNS = [
    (r"\bstudios?\b", "studio"),
    (r"\b([1-9])\s*(?:-|\s)?\s*(?:br|bhk|bed(?:room)?s?)\b", "{n}BR"),
    # Enumerated mixes share one trailing unit word: "1 & 2 bedroom",
    # "1, 2 & 3 BR", "2/3 bed". Handled by _expand_unit_runs below, which
    # needs the whole run rather than a single digit.
    (r"\b([1-9](?:\s*(?:,|&|and|/|\+)\s*[1-9])+)\s*(?:-|\s)?\s*(?:br|bhk|bed(?:room)?s?)\b", "{run}"),
    (r"\btownhouses?\b", "townhouse"),
    (r"\bvillas?\b", "villa"),
    (r"\bpenthouses?\b", "penthouse"),
    (r"\bduplex(?:es)?\b", "duplex"),
]

_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "mn": 1_000_000, "b": 1_000_000_000}


@dataclass
class ParsedLaunch:
    """A launch broadcast reduced to the fields matching cares about.

    Every field is optional: broadcasts vary wildly and a half-read message
    still matches usefully on what it did yield. `emirate` is the exception in
    practice — matching refuses to guess without it (see matcher.py).
    """

    developer: str | None = None
    project: str | None = None
    emirate: str | None = None
    area: str | None = None
    unit_types: list[str] = field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    payment_plan: str | None = None
    launch_date: str | None = None
    # off_plan / ready — a launch is off-plan unless it says otherwise.
    completion_status: str = "off_plan"
    # Kept only for the reply header, never persisted.
    raw_text: str = ""

    @property
    def headline(self) -> str:
        """'Sobha Hartland II — Dubai' style header for the reply."""
        name = self.project or self.developer or "Launch"
        return f"{name} — {self.emirate}" if self.emirate else name


class LaunchParser(Protocol):
    """Anything that can turn launch text into a ParsedLaunch.

    Implemented here by TextLaunchParser. An LLM-backed parser could implement
    the same call for messages the regex parser reads poorly; the matcher and
    everything downstream would not change.
    """

    def parse(self, text: str) -> ParsedLaunch: ...


# ── Field extractors ─────────────────────────────────────────

def _parse_amount(number: str, suffix: str | None) -> float | None:
    """Turn ('1.4', 'M') or ('1,400,000', None) into a float."""
    try:
        value = float(number.replace(",", "").strip())
    except ValueError:
        return None
    if suffix:
        value *= _MULTIPLIERS.get(suffix.lower().rstrip("."), 1)
    return value


# A money token: optional AED/Dhs, digits with optional separators, optional
# K/M/B suffix. Requires either a suffix or 6+ digits, so "60/40" and "2BR"
# can't be mistaken for prices.
_MONEY = r"(?:aed|dhs?|د\.إ)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m|mn|b)?\b"


def _extract_prices(text: str) -> tuple[float | None, float | None]:
    """Pull a price or price range out of the message.

    Handles 'from AED 1.4M', '1.2M - 1.8M', 'starting 850K', '1,400,000'.
    Returns (min, max); a single 'from X' price yields (X, None).
    """
    lowered = text.lower()

    # A range: "1.2M - 1.8M", "1.2M to 1.8M", "AED 900K – 1.3M"
    range_re = re.compile(_MONEY + r"\s*(?:-|–|—|to|until)\s*" + _MONEY, re.I)
    for m in range_re.finditer(lowered):
        low = _parse_amount(m.group(1), m.group(2))
        high = _parse_amount(m.group(3), m.group(4))
        # A bare lower bound inherits the upper bound's scale: "1.2 - 1.8M".
        if low is not None and high is not None and m.group(2) is None and m.group(4):
            low = _parse_amount(m.group(1), m.group(4))
        if low and high and low <= high and _plausible(low) and _plausible(high):
            return low, high

    # A single anchored price: "from 1.4M", "starting at AED 850K", "@ 1.4M"
    single_re = re.compile(
        r"(?:from|starting(?:\s+(?:at|from))?|start|prices?\s+from|@)\s*" + _MONEY, re.I
    )
    for m in single_re.finditer(lowered):
        value = _parse_amount(m.group(1), m.group(2))
        if value and _plausible(value):
            return value, None

    # Last resort: any plausible standalone money token.
    for m in re.finditer(_MONEY, lowered, re.I):
        if not m.group(2) and len(m.group(1).replace(",", "")) < 6:
            continue  # "60/40" and friends
        value = _parse_amount(m.group(1), m.group(2))
        if value and _plausible(value):
            return value, None

    return None, None


def _plausible(value: float) -> bool:
    """UAE property prices sit between 100k and 500m; anything else is noise."""
    return 100_000 <= value <= 500_000_000


def _extract_emirate_and_area(text: str) -> tuple[str | None, str | None]:
    """Find the area, and the emirate either stated or implied by that area."""
    lowered = text.lower()

    area = None
    # Longest area name first so "sobha hartland" beats "hartland".
    for name in sorted(AREA_TO_EMIRATE, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            area = name
            break

    emirate = None
    for name, canonical in sorted(EMIRATES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            emirate = canonical
            break

    # An unstated emirate is implied by a known area — broadcasts routinely
    # say "Hartland" and assume you know that means Dubai.
    if emirate is None and area:
        emirate = AREA_TO_EMIRATE[area]

    return emirate, (AREA_DISPLAY.get(area, area.title()) if area else None)


def _extract_unit_types(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for pattern, template in UNIT_PATTERNS:
        for m in re.finditer(pattern, lowered, re.I):
            if template == "{run}":
                labels = [f"{d}BR" for d in re.findall(r"[1-9]", m.group(1))]
            elif "{n}" in template:
                labels = [template.format(n=m.group(1))]
            else:
                labels = [template]
            for label in labels:
                if label not in found:
                    found.append(label)
    # studio, 1BR, 2BR … reads better than discovery order.
    def sort_key(u: str):
        return (0, 0) if u == "studio" else (1, int(u[0])) if u[:1].isdigit() else (2, 0)
    return sorted(found, key=sort_key)


def _extract_payment_plan(text: str) -> str | None:
    """'60/40', '1% monthly', 'post-handover 40%'."""
    m = re.search(r"\b(\d{2})\s*/\s*(\d{2})\b", text)
    if m and int(m.group(1)) + int(m.group(2)) in range(95, 106):
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:per\s+)?month(?:ly)?\b", text, re.I)
    if m:
        return f"{m.group(1)}% monthly"
    if re.search(r"post[\s-]?handover", text, re.I):
        return "post-handover"
    return None


_DAYS = r"(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?"
_MONTHS = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
           r"(?:uary|ruary|ch|il|e|y|ust|ember|ober|tember)?")


def _extract_launch_date(text: str) -> str | None:
    """The EOI or launch date, as written — kept as text, not a real date.

    Broadcasts say 'EOI Thursday' or 'launch 12 March'. Normalising that to a
    timestamp would need a reference date and a timezone assumption, and the
    value is only ever echoed back to the advisor, so the words are enough.
    """
    patterns = [
        rf"\b(?:eoi|expression of interest)\b[^.\n]{{0,24}}?\b({_DAYS}|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}|\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?)",
        rf"\blaunch(?:es|ing|ed)?\b[^.\n]{{0,24}}?\b({_DAYS}|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}|\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?)",
        rf"\b(?:eoi|launch)\b[^.\n]{{0,16}}?\b(today|tomorrow|this\s+week|next\s+week)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip().title()
    return None


def _extract_developer(text: str) -> str | None:
    for dev in sorted(DEVELOPERS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(dev)}\b", text, re.I):
            return dev.strip()
    return None


def _extract_project(text: str, developer: str | None, area: str | None) -> str | None:
    """Best-effort project name from the first substantive line.

    Broadcasts lead with the project ("Sobha Hartland II — Dubai", "🔥 NEW
    LAUNCH: Bayview by Address"). Take the first line that isn't pure hype,
    strip decoration, and cut at the first separator.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip emoji/decoration and common shout-y prefixes.
        line = re.sub(r"[^\w\s&'’\-–—|,:.()]+", " ", line).strip()
        line = re.sub(
            r"^\s*(?:new\s+launch|launch(?:ing)?|just\s+launched|exclusive|"
            r"breaking|announcement|pre[\s-]?launch|now\s+live)\s*[:\-–—|]*\s*",
            "", line, flags=re.I,
        ).strip()
        if not line or len(line) < 3:
            continue
        # Cut at the first separator: "Bayview | 1BR from 1.4M" -> "Bayview".
        candidate = re.split(r"\s*[|·•]\s*|\s+[-–—]\s+|\s*,\s*", line)[0].strip(" :-–—")
        if not candidate:
            continue
        # A line that's only a price/plan/date isn't a name.
        if re.fullmatch(r"[\d\s.,/%kmbaed-]+", candidate, re.I):
            continue
        if area and candidate.lower() == area.lower():
            continue
        return candidate[:120]
    return developer


def _extract_completion_status(text: str) -> str:
    """Ready only when the message says so; a launch is off-plan by default."""
    if re.search(r"\b(ready|handed\s*over|handover\s+complete|move[\s-]?in\s+now|"
                 r"ready\s+to\s+move)\b", text, re.I):
        return "ready"
    return "off_plan"


# ── The parser ───────────────────────────────────────────────

class TextLaunchParser:
    """Regex/keyword parser for forwarded launch broadcasts."""

    def parse(self, text: str) -> ParsedLaunch:
        text = text or ""
        emirate, area = _extract_emirate_and_area(text)
        developer = _extract_developer(text)
        price_min, price_max = _extract_prices(text)

        return ParsedLaunch(
            developer=developer,
            project=_extract_project(text, developer, area),
            emirate=emirate,
            area=area,
            unit_types=_extract_unit_types(text),
            price_min=price_min,
            price_max=price_max,
            payment_plan=_extract_payment_plan(text),
            launch_date=_extract_launch_date(text),
            completion_status=_extract_completion_status(text),
            raw_text=text,
        )


def parse_launch(text: str, parser: LaunchParser | None = None) -> ParsedLaunch:
    """Parse launch text with the default parser unless another is supplied."""
    return (parser or TextLaunchParser()).parse(text)
