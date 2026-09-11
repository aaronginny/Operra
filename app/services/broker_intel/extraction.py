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
from app.services.broker_intel.content import MAX_BULLETS
from app.services.broker_intel.search import SourceResult

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0
_MAX_TOKENS = 900

# The only metric types a claim may carry. assemble_ranges groups on this
# field, so two claims can only ever combine if they share one of these —
# a price-per-sqft figure and a total price differ on metric and so can
# never merge, by construction rather than by prompt wording.
METRICS: tuple[str, ...] = (
    "price_per_sqft",    # AED per square foot
    "total_price",       # AED, a whole-unit sale price
    "rental_yield_pct",  # gross rental yield, percent
    "annual_rent",       # AED per year, a rented unit
    "yoy_change_pct",    # year-over-year price/value change, percent
    "qualitative",       # no number — context, amenities, reputation, etc.
)

_PCT_METRICS = {"rental_yield_pct", "yoy_change_pct"}
_AED_METRICS = {"price_per_sqft", "total_price", "annual_rent"}

# Scope labels that never count as area-specific, however they're spelled.
_CITYWIDE_LABELS = {"citywide", "city-wide", "city wide", "dubai", "dubai-wide",
                     "dubai wide", "uae", "national", ""}

_DIGIT = re.compile(r"\d")


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
    "metric=qualitative — market context, amenities, developer reputation, "
    "landmarks — and must contain NO digits. If it needs a number to make "
    "its point, extract that number as its own numeric claim instead; do "
    "not smuggle a figure into a qualitative note.\n"
    "- source_index must be one of the numbers given in the source list "
    "below, referring to the source the claim actually came from.\n"
    "- Extract only what a source explicitly states. Never compute, "
    "average, convert between units, or infer a figure that is not written "
    "in the source text — if a source's number is ambiguous (e.g. unclear "
    "whether a percentage is a yield or a payment-plan discount), leave it "
    "out rather than guess which metric it is.\n"
    "- If a source has no usable claims, contribute nothing from it.\n"
    "- At most 12 claims total."
)


def _source_block(sources: list[SourceResult]) -> str:
    lines = []
    for i, s in enumerate(sources, start=1):
        date = s.published_date or "undated"
        lines.append(f"[{i}] {s.domain} ({date}): {s.content[:600]}")
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
}


def _fmt_amount(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def _fmt_pct(v: float) -> str:
    return f"{v:g}"


def _fmt_value(metric: str, v: float) -> str:
    return _fmt_pct(v) if metric in _PCT_METRICS else _fmt_amount(v)


def _range_str(fact: RangeFact) -> str:
    lo, hi = _fmt_value(fact.metric, fact.low), _fmt_value(fact.metric, fact.high)
    body = lo if fact.low == fact.high else f"{lo}-{hi}"
    unit = "%" if fact.metric in _PCT_METRICS else ""
    prefix = "AED " if fact.metric in _AED_METRICS else ""
    suffix = "/sqft" if fact.metric == "price_per_sqft" else ""
    return f"{prefix}{body}{unit}{suffix}"


def _markers(indices: tuple[int, ...]) -> str:
    return "".join(f"[{i}]" for i in indices)


def _me_line(area: str, fact: RangeFact) -> str:
    label = _ME_LABEL.get(fact.metric, fact.metric)
    qual = f" ({fact.qualifier})" if fact.qualifier else ""
    return f"{label}{qual}: {_range_str(fact)}"


_LEAD_TEMPLATES = {
    "price_per_sqft": lambda area, fact, qual: (
        f"{area} is currently trading around {_range_str(fact)} per square foot{qual}"
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
}


def _lead_line(area: str, fact: RangeFact) -> str:
    qual = f" for {fact.qualifier} units" if fact.qualifier else ""
    template = _LEAD_TEMPLATES.get(fact.metric)
    if template is None:
        return f"{area}: {_range_str(fact)}{qual}"
    return template(area, fact, qual)


def render_bullets(
    subject: str,
    ranges: list[RangeFact],
    qualitative: list[QualitativeFact],
    audience: str,
) -> list[str]:
    """Single-area bullets. ME is terse with inline citation markers; LEAD
    reads as complete sentences naming the area, since it may be forwarded
    to a client verbatim. Both are built purely from RangeFact/
    QualitativeFact — no free-text generation happens after assemble_ranges,
    so a bullet's numbers are exactly what a source stated."""
    lines: list[str] = []
    for fact in ranges[:MAX_BULLETS]:
        body = _me_line(subject, fact) if audience != "lead" else _lead_line(subject, fact)
        lines.append(f"{body} {_markers(fact.source_indices)}".rstrip())
    remaining = MAX_BULLETS - len(lines)
    for q in qualitative[:max(0, remaining)]:
        lines.append(f"{q.note} [{q.source_index}]")
    return lines[:MAX_BULLETS]


def render_comparison_bullets(
    per_area: dict[str, tuple[list[RangeFact], list[QualitativeFact]]],
    audience: str,
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

    representative: dict[tuple[str, str], RangeFact] = {}
    for area, (ranges, _qualitative) in per_area.items():
        for fact in ranges:
            key = (area, fact.metric)
            current = representative.get(key)
            # Prefer no qualifier (the general area figure); otherwise keep
            # whichever came first.
            if current is None or (current.qualifier and not fact.qualifier):
                representative[key] = fact

    by_metric: dict[str, list[tuple[str, RangeFact]]] = {}
    for (area, _metric), fact in representative.items():
        by_metric.setdefault(fact.metric, []).append((area, fact))

    qual_lines = [
        f"{area}: {q.note} [{q.source_index}]"
        for area, (_ranges, qualitative) in per_area.items()
        for q in qualitative[:1]
    ]

    lines: list[str] = []
    for metric in sorted(by_metric, key=lambda m: order.get(m, 99)):
        for area, fact in by_metric[metric]:
            if audience == "lead":
                body = _lead_line(area, fact)
            else:
                body = f"*{area}* {_me_line(area, fact)}"
            lines.append(f"{body} {_markers(fact.source_indices)}".rstrip())

    lines = lines[:MAX_BULLETS]
    if len(lines) < MAX_BULLETS:
        lines.extend(qual_lines[: MAX_BULLETS - len(lines)])
    return lines[:MAX_BULLETS]
