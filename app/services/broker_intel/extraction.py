"""Structured fact extraction for broker_intel's sourced briefings — the
half of the pipeline that turns raw search text into reply content, without
ever letting free-text generation decide what counts as a number.

WHY THIS MODULE EXISTS. An earlier prototype asked the model to read search
results and write bullet points directly. It read well right up until it
silently merged a total apartment price (AED 1,000,000) with a
price-per-square-foot figure (AED 1,564) from the same source page into one
nonsense "range" — confidently formatted, correctly cited, and meaningless.
Free-text generation has no seam at which that mistake can be caught, and a
prompt instruction not to do it did not reliably hold.

So the model's job here is narrowed to EXTRACTION ONLY: read each source and
report typed claims (Claim, below) — a metric, a scope, a number, which
source it came from. Nothing downstream trusts the model's arithmetic or its
sense of which numbers belong together. assemble_ranges() groups claims by
(metric, scope, qualifier) in plain Python, so a price-per-sqft claim and a
total-price claim can never land in the same bucket — the grouping key does
not let it happen, regardless of what the model returns. See
test_broker_intel_sourcing.py for the direct regression test built from the
bug this replaced.

The same narrowing fixes two smaller bugs found alongside it: a single
source's figure no longer gets phrased as if it were a market consensus
(single_source is tracked explicitly), and a Dubai-wide statistic can no
longer attach itself to an area-specific briefing (assemble_ranges drops
any claim whose scope_area does not match the area actually asked about).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from typing import Protocol

import httpx

from app.config import settings
from app.services.broker_intel.search import SourceResult

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0
_MAX_TOKENS = 1500

# Bullet budgets. Deliberately NOT content.py's MAX_BULLETS: that one sizes
# a social caption, which wants to be short, while a briefing she is reading
# mid-call wants to be substantial. Client feedback on the first sourced
# build was that six bullets read thin next to just asking ChatGPT, so the
# numeric budget roughly doubled — see the docstrings on the renderers for
# how the space is apportioned when there is more data than budget.
MAX_BRIEFING_BULLETS = 10       # single-area briefing
MAX_COMPARISON_BULLETS = 12     # interleaved comparison (both areas)
MAX_COMPARISON_PER_AREA = 5     # per-area block in the grouped comparison
MAX_QUALITATIVE_SINGLE = 2      # colour commentary never dominates a briefing
MAX_QUALITATIVE_COMPARISON = 1
VARIANTS_PER_METRIC = 2         # per area, in a comparison — see _representative_facts

# The only metric types a claim may carry. assemble_ranges groups on this
# field, so two claims can only ever combine if they share one of these —
# a price-per-sqft figure and a total price differ on metric and so can
# never merge, by construction rather than by prompt wording.
METRICS: tuple[str, ...] = (
    "price_per_sqft",     # AED per square foot
    "total_price",        # AED, a whole-unit sale price
    "rental_yield_pct",   # gross rental yield, percent
    "annual_rent",        # AED per year, a rented unit
    "yoy_change_pct",     # year-over-year price/value change, percent
    "transaction_count",  # registered transactions in a stated period
    "days_on_market",     # average days to sell/let
    "service_charge",     # AED per sqft per year
    "down_payment_pct",   # payment-plan down payment, percent
    "qualitative",        # no number — context, amenities, landmarks
)

_PCT_METRICS = {"rental_yield_pct", "yoy_change_pct", "down_payment_pct"}
_AED_METRICS = {"price_per_sqft", "total_price", "annual_rent", "service_charge"}
_PLAIN_METRICS = {"transaction_count", "days_on_market"}

# Plausibility bounds per metric, as (low, high) inclusive.
#
# These catch the one error class the deterministic assembly cannot: the
# model MISLABELLING a metric. Live testing produced "Typical unit prices
# run AED 693 for studio units" — a price-per-sqft figure tagged as
# total_price. Nothing downstream could tell: 693 is a perfectly good
# number, correctly cited, in the wrong bucket. Grouping only guarantees
# that different metrics never MERGE; it cannot know a value was filed
# under the wrong one.
#
# Bounds are deliberately wide — they are an absurdity filter, not a
# market view — and a claim outside them is DROPPED, never rescaled or
# reassigned, on the same principle as every other check here: a source
# that produced something impossible contributes nothing.
_PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "price_per_sqft": (150, 15_000),
    "total_price": (100_000, 500_000_000),
    "rental_yield_pct": (0.5, 25),
    "annual_rent": (5_000, 50_000_000),
    "yoy_change_pct": (-60, 150),
    "transaction_count": (1, 1_000_000),
    "days_on_market": (1, 1_000),
    "service_charge": (1, 300),
    "down_payment_pct": (1, 100),
}


def is_plausible(metric: str, value: float) -> bool:
    low, high = _PLAUSIBLE_RANGE.get(metric, (float("-inf"), float("inf")))
    return low <= value <= high

# Scope labels that never count as area-specific, however they're spelled.
_CITYWIDE_LABELS = {"citywide", "city-wide", "city wide", "dubai", "dubai-wide",
                     "dubai wide", "uae", "national", ""}

_DIGIT = re.compile(r"\d")

# ── Qualitative substance filter ─────────────────────────────────────────
#
# Client feedback on the first sourced build: the briefings read thin, and
# some bullets were marketing filler -- "JVC is popular for strong rental
# yields" sitting directly under a bullet that already gave the actual
# yield figure. A qualitative claim earns its place only when it tells her
# something a numeric bullet cannot, so it has to clear two tests:
#
#   1. it must not be generic agent-speak (the blocklist below), and
#   2. it must name something concrete -- a road, a mall, a metro station, a
#      school, a developer, a handover date -- detected either as a proper
#      noun or as one of the concrete nouns below.
#
# Both are deliberately conservative: dropping a borderline-useful line
# costs her nothing (the numeric bullets carry the value), while keeping a
# vague one is exactly the "this is just ChatGPT" problem she raised.
_MARKETING_PHRASES = (
    "popular", "sought after", "sought-after", "highly desirable", "desirable",
    "vibrant", "thriving", "booming", "bustling", "charming", "prestigious",
    "luxurious lifestyle", "strong demand", "high demand", "growing demand",
    "strong rental yields", "attractive returns", "attractive yields",
    "excellent investment", "great investment", "solid investment",
    "promising", "lucrative", "ideal for families", "perfect for families",
    "family-friendly community", "well-established community",
    "accessible community", "growing amenities", "modern amenities",
    "world-class amenities", "strong investor interest", "investor favourite",
    "investor favorite", "good value", "value for money", "up and coming",
    "up-and-coming", "rapidly developing", "hidden gem",
)

# Concrete things worth a bullet when named. A note mentioning one of these
# is saying something checkable, not selling.
_CONCRETE_NOUNS = (
    "metro", "tram", "station", "mall", "school", "nursery", "hospital",
    "clinic", "mosque", "park", "beach", "marina", "highway", "road",
    "interchange", "boulevard", "handover", "completion", "completed",
    "under construction", "off-plan", "freehold", "leasehold", "developer",
    "master plan", "masterplan", "phase", "tower", "community centre",
    "community center", "golf", "lagoon", "airport", "university", "campus",
)

# A capitalised word that is not the first word of the note -- a decent
# proxy for "names an actual place, road, developer or project".
_PROPER_NOUN = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-zA-Z]{2,}")


def is_substantive_note(note: str) -> bool:
    """True when a qualitative claim says something concrete enough to be
    worth one of her bullets. See the comment block above for why this is
    two-sided rather than a simple blocklist."""
    text = (note or "").strip()
    if len(text) < 12:
        return False
    lowered = text.lower()
    if any(phrase in lowered for phrase in _MARKETING_PHRASES):
        return False
    if any(noun in lowered for noun in _CONCRETE_NOUNS):
        return True
    return bool(_PROPER_NOUN.search(text))


@dataclass(frozen=True)
class Claim:
    """One fact, from one source, with nothing implied beyond what the
    source actually said."""

    metric: str            # one of METRICS
    scope_area: str        # e.g. "Arjan", or a citywide label — see above
    value: float | None    # None only when metric == "qualitative"
    qualifier: str          # short lowercase tag, e.g. "studio"; "" if none
    note: str               # the qualitative text; "" for numeric claims
    source_index: int       # 1-based index into the source list given to the model


@dataclass(frozen=True)
class RangeFact:
    """One or more same-metric, same-scope, same-qualifier claims, reduced
    to a display-ready range. Built entirely in Python by assemble_ranges,
    so it cannot mix units regardless of what the model returned."""

    metric: str
    scope_area: str
    qualifier: str
    low: float
    high: float
    source_indices: tuple[int, ...]
    single_source: bool


@dataclass(frozen=True)
class QualitativeFact:
    note: str
    source_index: int


class ExtractionProvider(Protocol):
    async def extract_claims(
        self, subject: str, sources: list[SourceResult]
    ) -> list[Claim] | None: ...


_SYSTEM = (
    "You extract structured facts about Dubai real estate from numbered "
    "source excerpts. Output ONLY a JSON object of the shape "
    '{"claims": [{"metric": "...", "scope_area": "...", "value": ..., '
    '"qualifier": "...", "note": "...", "source_index": ...}]}.\n'
    "Rules, all mandatory:\n"
    f"- metric must be exactly one of: {', '.join(METRICS)}.\n"
    "- value is a plain number with no currency symbol, no percent sign, "
    "no thousands separator — for every metric except qualitative, where "
    "value must be null.\n"
    "- scope_area is the specific area or project the claim is actually "
    "about. If a source states a Dubai-wide or generic figure that is not "
    "specific to the area you were asked about, set scope_area to "
    '"citywide" — never attribute a citywide figure to a specific area.\n'
    "- qualifier is a short lowercase tag when the source ties the figure "
    'to a unit type ("studio", "1-bed", "villa", "townhouse"), otherwise '
    "an empty string.\n"
    "- note is a short (under 20 words) qualitative observation, ONLY for "
    "metric=qualitative, and must contain NO digits. If it needs a number "
    "to make its point, extract that number as its own numeric claim "
    "instead; do not smuggle a figure into a qualitative note.\n"
    "- A qualitative note must NAME SOMETHING CONCRETE AND CHECKABLE: a "
    "road, metro station, mall, school, hospital, park, the developer, the "
    "master plan, handover status. Generic agent-speak is worthless here "
    "and will be discarded — never write things like 'popular with "
    "investors', 'strong rental yields', 'vibrant community', 'great "
    "investment' or 'family-friendly'. 'Circle Mall and Al Khail Road sit "
    "inside the community' is useful; 'a sought-after area' is not.\n"
    "- Extract EVERY metric the sources support, not just prices and "
    "yields. Actively look for transaction_count (how many deals "
    "registered in a period), days_on_market, service_charge (AED per sqft "
    "per year) and down_payment_pct (payment-plan terms) — these are "
    "frequently present and are more useful to a working broker than "
    "another price figure.\n"
    "- source_index must be one of the numbers given in the source list "
    "below, referring to the source the claim actually came from.\n"
    "- Extract only what a source explicitly states. Never compute, "
    "average, convert between units, or infer a figure that is not written "
    "in the source text — if a source's number is ambiguous (e.g. unclear "
    "whether a percentage is a yield or a payment-plan discount), leave it "
    "out rather than guess which metric it is.\n"
    "- If a source has no usable claims, contribute nothing from it.\n"
    "- At most 20 claims total."
)


# How much of each source's text the model gets to read. Raised from 600
# after measuring the real bottleneck behind "the briefings feel thin": it
# was never the bullet cap (12 bullets rendered the same 8 as 6 did) but how
# few claims came back per source. More text in, more extractable facts out.
_SOURCE_CHARS = 1400


def _source_block(sources: list[SourceResult]) -> str:
    lines = []
    for i, s in enumerate(sources, start=1):
        date = s.published_date or "undated"
        lines.append(f"[{i}] {s.domain} ({date}): {s.content[:_SOURCE_CHARS]}")
    return "\n\n".join(lines)


def _parse_claims(raw: str, max_index: int) -> list[Claim]:
    """Turn the model's JSON into validated Claims, DROPPING — never
    repairing — anything malformed. Repairing a bad claim would mean the
    code deciding what the model meant; dropping it means a source that
    produced garbage simply contributes nothing, which is always safe."""
    try:
        data = json.loads(raw)
        raw_claims = data.get("claims", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []

    out: list[Claim] = []
    for c in raw_claims if isinstance(raw_claims, list) else []:
        if not isinstance(c, dict):
            continue
        metric = c.get("metric")
        if metric not in METRICS:
            continue
        try:
            idx = int(c.get("source_index"))
        except (TypeError, ValueError):
            continue
        if not (1 <= idx <= max_index):
            continue
        scope = str(c.get("scope_area") or "").strip()
        qualifier = str(c.get("qualifier") or "").strip().lower()

        if metric == "qualitative":
            note = str(c.get("note") or "").strip()
            # A qualitative claim carrying a digit is exactly the ambiguity
            # this schema exists to prevent — drop it rather than let an
            # uncited-looking figure slip through as prose.
            if not note or _DIGIT.search(note):
                continue
            # ...and a claim that is just agent-speak earns no bullet at all.
            if not is_substantive_note(note):
                continue
            out.append(Claim(metric=metric, scope_area=scope or "citywide",
                              value=None, qualifier=qualifier, note=note,
                              source_index=idx))
            continue

        try:
            value = float(c.get("value"))
        except (TypeError, ValueError):
            continue
        if value != value or value in (float("inf"), float("-inf")):  # NaN/inf guard
            continue
        # A value impossible for its metric means the model filed it under
        # the wrong one — see _PLAUSIBLE_RANGE. Drop it.
        if not is_plausible(metric, value):
            logger.info("broker_intel: dropped implausible %s=%s", metric, value)
            continue
        out.append(Claim(metric=metric, scope_area=scope or "citywide",
                          value=value, qualifier=qualifier, note="",
                          source_index=idx))
    return out


class OpenAIExtractionProvider:
    """Real extraction via the same chat-completions endpoint the rest of
    the app uses, in JSON mode."""

    async def extract_claims(self, subject: str, sources: list[SourceResult]) -> list[Claim] | None:
        if not sources:
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM},
                            {"role": "user", "content":
                                f"Area/subject: {subject}\n\nSources:\n{_source_block(sources)}"},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": _MAX_TOKENS,
                        "temperature": 0.1,
                    },
                )
            if resp.status_code != 200:
                logger.warning("broker_intel extraction failed: HTTP %s", resp.status_code)
                return None
            raw = resp.json()["choices"][0]["message"]["content"]
            return _parse_claims(raw, max_index=len(sources))
        except Exception:
            logger.exception("broker_intel extraction errored")
            return None


class StubExtractionProvider:
    """Deterministic stand-in for tests — no network call. Returns a fixed
    claims list (or the result of a callable, for per-call variation)."""

    def __init__(self, claims=None) -> None:
        self._claims = claims
        self.calls: list[tuple[str, int]] = []

    async def extract_claims(self, subject: str, sources: list[SourceResult]) -> list[Claim] | None:
        self.calls.append((subject, len(sources)))
        result = self._claims(subject, sources) if callable(self._claims) else self._claims
        return list(result) if result is not None else []


def extraction_configured() -> bool:
    """Mirrors content.py's ai_configured() — the extraction step uses the
    same OpenAI key and the same placeholder check."""
    key = settings.openai_api_key
    return bool(key) and not key.startswith("sk-your")


def get_extraction_provider() -> ExtractionProvider:
    if extraction_configured():
        return OpenAIExtractionProvider()
    logger.warning("broker_intel: no usable OpenAI key — sourced extraction unavailable.")
    return StubExtractionProvider(claims=[])


def remap_claims(claims: list[Claim], offset: int) -> list[Claim]:
    """Shift source_index by `offset`. Used when combining two areas' own
    independently-indexed claims (each extracted against its own source
    list, both starting at 1) into one shared numbering for a comparison,
    so "[1]" can never mean two different sources in the same reply."""
    return [replace(c, source_index=c.source_index + offset) for c in claims]


# ── Deterministic assembly ───────────────────────────────────────────────

def _area_matches(scope_area: str, target: str) -> bool:
    scope = scope_area.strip().lower()
    if scope in _CITYWIDE_LABELS:
        return False
    t = target.strip().lower()
    return scope == t or t in scope or scope in t


def assemble_ranges(
    claims: list[Claim], target_area: str
) -> tuple[list[RangeFact], list[QualitativeFact]]:
    """Group claims scoped to `target_area` into RangeFacts, plus the
    qualitative claims scoped to it, in that priority order (METRICS order).

    THE INVARIANT THIS FUNCTION HOLDS: two claims combine into one RangeFact
    only when they share metric AND scope_area AND qualifier. A
    price_per_sqft claim and a total_price claim differ on metric, so they
    can never appear in the same RangeFact — nothing in the grouping key
    lets it happen, independent of what the model extracted.

    Claims scoped outside target_area (including anything citywide) are
    dropped entirely — see the module docstring on the Dubai-wide-yield-in-
    a-JVC-briefing bug this closes.
    """
    numeric: dict[tuple[str, str, str], list[Claim]] = {}
    qualitative: list[QualitativeFact] = []

    for c in claims:
        if not _area_matches(c.scope_area, target_area):
            continue
        if c.metric == "qualitative":
            qualitative.append(QualitativeFact(note=c.note, source_index=c.source_index))
            continue
        key = (c.metric, c.scope_area.strip().lower(), c.qualifier)
        numeric.setdefault(key, []).append(c)

    order = {m: i for i, m in enumerate(METRICS)}
    ranges: list[RangeFact] = []
    for (metric, _scope, qualifier), group in numeric.items():
        values = [c.value for c in group if c.value is not None]
        if not values:
            continue
        indices = tuple(sorted({c.source_index for c in group}))
        ranges.append(RangeFact(
            metric=metric, scope_area=group[0].scope_area, qualifier=qualifier,
            low=min(values), high=max(values),
            source_indices=indices, single_source=len(indices) == 1,
        ))
    ranges.sort(key=lambda r: order.get(r.metric, 99))
    return ranges, qualitative


# ── Deterministic rendering (no LLM involved past this point) ───────────

_ME_LABEL = {
    "price_per_sqft": "Price/sqft",
    "total_price": "Price",
    "rental_yield_pct": "Rental yield",
    "annual_rent": "Annual rent",
    "yoy_change_pct": "YoY change",
    "transaction_count": "Transactions",
    "days_on_market": "Days on market",
    "service_charge": "Service charge",
    "down_payment_pct": "Down payment",
}


def _fmt_amount(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def _fmt_pct(v: float) -> str:
    return f"{v:g}"


def _fmt_value(metric: str, v: float) -> str:
    return _fmt_pct(v) if metric in _PCT_METRICS else _fmt_amount(v)


def _range_str(fact: RangeFact, bare: bool = False) -> str:
    """`bare=True` omits the unit suffix, for the LEAD templates that spell
    the unit out in words — otherwise they read "AED 1,568/sqft per square
    foot"."""
    lo, hi = _fmt_value(fact.metric, fact.low), _fmt_value(fact.metric, fact.high)
    body = lo if fact.low == fact.high else f"{lo}-{hi}"
    unit = "%" if fact.metric in _PCT_METRICS else ""
    prefix = "AED " if fact.metric in _AED_METRICS else ""
    if bare:
        suffix = ""
    elif fact.metric == "price_per_sqft":
        suffix = "/sqft"
    elif fact.metric == "service_charge":
        suffix = "/sqft/yr"
    elif fact.metric == "days_on_market":
        suffix = " days"
    else:
        suffix = ""
    return f"{prefix}{body}{unit}{suffix}"


def _markers(indices: tuple[int, ...]) -> str:
    return "".join(f"[{i}]" for i in indices)


def _me_line(area: str, fact: RangeFact) -> str:
    label = _ME_LABEL.get(fact.metric, fact.metric)
    qual = f" ({fact.qualifier})" if fact.qualifier else ""
    return f"{label}{qual}: {_range_str(fact)}"


_LEAD_TEMPLATES = {
    "price_per_sqft": lambda area, fact, qual: (
        f"{area} is currently trading around {_range_str(fact, bare=True)} "
        f"per square foot{qual}"
    ),
    "total_price": lambda area, fact, qual: (
        f"Typical unit prices in {area} run {_range_str(fact)}{qual}"
    ),
    "rental_yield_pct": lambda area, fact, qual: (
        f"Rental yields in {area} are running around {_range_str(fact)}{qual}"
    ),
    "annual_rent": lambda area, fact, qual: (
        f"Annual rent in {area} runs around {_range_str(fact)}{qual}"
    ),
    "yoy_change_pct": lambda area, fact, qual: (
        f"{area} has seen a {_range_str(fact)} year-on-year change{qual}"
    ),
    "transaction_count": lambda area, fact, qual: (
        f"{_range_str(fact)} transactions were registered in {area}{qual}"
    ),
    "days_on_market": lambda area, fact, qual: (
        f"Property in {area} is taking around {_range_str(fact)} to sell{qual}"
    ),
    "service_charge": lambda area, fact, qual: (
        f"Service charges in {area} run {_range_str(fact)}{qual}"
    ),
    "down_payment_pct": lambda area, fact, qual: (
        f"Payment plans in {area} start from {_range_str(fact)} down{qual}"
    ),
}

# Used under a per-area sub-header, where the area name is already stated
# above the bullet. These are written as standalone fragments rather than
# derived from _LEAD_TEMPLATES by string surgery — stripping the area name
# out of a finished sentence produced bullets like "is currently trading
# around AED 1,568 per square foot", which starts mid-clause.
_LEAD_BARE_TEMPLATES = {
    "price_per_sqft": lambda fact, qual: (
        f"Trading around {_range_str(fact, bare=True)} per square foot{qual}"
    ),
    "total_price": lambda fact, qual: f"Typical unit prices run {_range_str(fact)}{qual}",
    "rental_yield_pct": lambda fact, qual: (
        f"Rental yields are running around {_range_str(fact)}{qual}"
    ),
    "annual_rent": lambda fact, qual: f"Annual rent runs around {_range_str(fact)}{qual}",
    "yoy_change_pct": lambda fact, qual: (
        f"Values have moved {_range_str(fact)} year on year{qual}"
    ),
    "transaction_count": lambda fact, qual: (
        f"{_range_str(fact)} transactions registered{qual}"
    ),
    "days_on_market": lambda fact, qual: (
        f"Taking around {_range_str(fact)} to sell{qual}"
    ),
    "service_charge": lambda fact, qual: f"Service charges run {_range_str(fact)}{qual}",
    "down_payment_pct": lambda fact, qual: (
        f"Payment plans start from {_range_str(fact)} down{qual}"
    ),
}


def _lead_line(area: str, fact: RangeFact) -> str:
    qual = f" for {fact.qualifier} units" if fact.qualifier else ""
    template = _LEAD_TEMPLATES.get(fact.metric)
    if template is None:
        return f"{area}: {_range_str(fact)}{qual}"
    return template(area, fact, qual)


def _lead_bare_line(fact: RangeFact) -> str:
    qual = f" for {fact.qualifier} units" if fact.qualifier else ""
    template = _LEAD_BARE_TEMPLATES.get(fact.metric)
    if template is None:
        return f"{_range_str(fact)}{qual}"
    return template(fact, qual)


def render_bullets(
    subject: str,
    ranges: list[RangeFact],
    qualitative: list[QualitativeFact],
    audience: str,
    max_bullets: int = MAX_BRIEFING_BULLETS,
    max_qualitative: int = MAX_QUALITATIVE_SINGLE,
) -> list[str]:
    """Single-area bullets. ME is terse with inline citation markers; LEAD
    reads as complete sentences naming the area, since it may be forwarded
    to a client verbatim. Both are built purely from RangeFact/
    QualitativeFact — no free-text generation happens after assemble_ranges,
    so a bullet's numbers are exactly what a source stated.

    Numeric facts are laid down first and qualitative ones only fill what
    budget is left, capped separately: a briefing that is mostly colour
    commentary is the thin-feeling output the client complained about, so
    real figures always get first claim on the space.
    """
    lines: list[str] = []
    for fact in ranges[:max_bullets]:
        body = _me_line(subject, fact) if audience != "lead" else _lead_line(subject, fact)
        lines.append(f"{body} {_markers(fact.source_indices)}".rstrip())
    remaining = min(max_qualitative, max_bullets - len(lines))
    for q in qualitative[:max(0, remaining)]:
        lines.append(f"{q.note} [{q.source_index}]")
    return lines[:max_bullets]


def _representative_facts(
    per_area: dict[str, tuple[list[RangeFact], list[QualitativeFact]]],
    per_metric: int = VARIANTS_PER_METRIC,
) -> list[tuple[str, RangeFact]]:
    """Up to `per_metric` RangeFacts per (area, metric), unqualified first.

    Strictly one-per-metric was the original fix for one area's unit-type
    variants crowding the other out of a comparison. It over-corrected: with
    only four distinct metrics found per area, a comparison had nothing left
    to say and raising the bullet cap changed nothing. Two keeps the
    crowding bounded (the cap is per area, so neither can run away) while
    letting a second genuinely different figure — a 1-bed price next to the
    area average — earn its place.
    """
    grouped: dict[tuple[str, str], list[RangeFact]] = {}
    for area, (ranges, _qualitative) in per_area.items():
        for fact in ranges:
            grouped.setdefault((area, fact.metric), []).append(fact)

    out: list[tuple[str, RangeFact]] = []
    for (area, _metric), facts in grouped.items():
        # Unqualified (the general area figure) first, then the rest as found.
        facts.sort(key=lambda f: bool(f.qualifier))
        for fact in facts[:per_metric]:
            out.append((area, fact))
    return out


def render_comparison_sections(
    per_area: dict[str, tuple[list[RangeFact], list[QualitativeFact]]],
    audience: str,
    max_per_area: int = MAX_COMPARISON_PER_AREA,
    max_qualitative_per_area: int = MAX_QUALITATIVE_COMPARISON,
) -> list[tuple[str, list[str]]]:
    """A comparison grouped under one sub-header per area, as
    [(area, [bullet, ...]), ...].

    The alternative shape to render_comparison_bullets' single interleaved
    list. Grouping trades the direct metric-for-metric adjacency for the
    ability to carry more figures per area without the reader losing track
    of which area a bullet belongs to — with a sub-header above each block,
    the bullets no longer each have to name their own area, so they read
    shorter even as there are more of them.
    """
    order = {m: i for i, m in enumerate(METRICS)}
    representative = _representative_facts(per_area)

    sections: list[tuple[str, list[str]]] = []
    for area, (_ranges, qualitative) in per_area.items():
        facts = [f for a, f in representative if a == area]
        facts.sort(key=lambda f: order.get(f.metric, 99))
        lines: list[str] = []
        for fact in facts[:max_per_area]:
            # Under a sub-header the area name is already stated, so both
            # voices use their area-free phrasing.
            body = _lead_bare_line(fact) if audience == "lead" else _me_line(area, fact)
            lines.append(f"{body} {_markers(fact.source_indices)}".rstrip())
        for q in qualitative[:max_qualitative_per_area]:
            if len(lines) >= max_per_area + max_qualitative_per_area:
                break
            lines.append(f"{q.note} [{q.source_index}]")
        if lines:
            sections.append((area, lines))
    return sections


def render_comparison_bullets(
    per_area: dict[str, tuple[list[RangeFact], list[QualitativeFact]]],
    audience: str,
    max_bullets: int = MAX_COMPARISON_BULLETS,
    max_qualitative_per_area: int = MAX_QUALITATIVE_COMPARISON,
) -> list[str]:
    """One bullet list spanning every area, grouped by metric so the same
    kind of figure sits next to its counterpart for each area — the actual
    point of a comparison. Each bullet names its own area, so nothing here
    relies on the areas being read in order.

    At most ONE bullet per (area, metric) — preferring the unqualified
    figure over a unit-type-specific one (studio/1-bed/villa...) when both
    exist. Found in live testing: one area's sources broke price-per-sqft
    out by unit type while the other's didn't, so that area alone produced
    four price_per_sqft bullets against the comparison's MAX_BULLETS cap —
    crowding the other area almost entirely out of its own comparison. A
    single-area briefing (render_bullets) still shows every qualifier
    variant; only the cross-area contrast needs one representative number
    per area per metric to stay fair between the areas being compared.
    """
    order = {m: i for i, m in enumerate(METRICS)}
    representative = _representative_facts(per_area)

    by_metric: dict[str, list[tuple[str, RangeFact]]] = {}
    for area, fact in representative:
        by_metric.setdefault(fact.metric, []).append((area, fact))

    qual_lines = [
        f"{area}: {q.note} [{q.source_index}]"
        for area, (_ranges, qualitative) in per_area.items()
        for q in qualitative[:max_qualitative_per_area]
    ]

    lines: list[str] = []
    for metric in sorted(by_metric, key=lambda m: order.get(m, 99)):
        for area, fact in by_metric[metric]:
            if audience == "lead":
                body = _lead_line(area, fact)
            else:
                body = f"*{area}* {_me_line(area, fact)}"
            lines.append(f"{body} {_markers(fact.source_indices)}".rstrip())

    lines = lines[:max_bullets]
    if len(lines) < max_bullets:
        lines.extend(qual_lines[: max_bullets - len(lines)])
    return lines[:max_bullets]
