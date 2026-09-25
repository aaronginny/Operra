"""Orchestrates a sourced briefing end to end: search -> extract -> assemble
-> render -> caveat.

This is what handler.py calls for single-area lead intel, multi-area
comparisons, and the daily brief (build_daily_brief). search.py and extraction.py stay agnostic of
WhatsApp formatting so they can be unit-tested without a rendered message
in view; formatter.py still owns the one caveat-attachment chokepoint
(_sourced_reply) for the same reason it always has — see formatter.py's
docstring.

search and extractor are accepted as parameters (defaulting to the real
providers) so tests can inject stubs, the same pattern content.py's
ContentGenerator uses.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from app.services.broker_intel import focus as focus_topics
from app.services.broker_intel import formatter
from app.services.broker_intel.content import ContentGenerator, get_generator
from app.services.broker_intel.extraction import (
    _DIGIT,
    MAX_QUALITATIVE_COMPARISON,
    MAX_QUALITATIVE_FOCUSED,
    MAX_QUALITATIVE_FOCUSED_COMPARISON,
    MAX_QUALITATIVE_SINGLE,
    Claim,
    ExtractionProvider,
    RangeFact,
    assemble_ranges,
    get_extraction_provider,
    remap_claims,
    render_bullets,
    render_comparison_bullets,
    render_comparison_sections,
)
from app.services.broker_intel.search import (
    SearchProvider,
    SourceResult,
    get_search_provider,
)

logger = logging.getLogger(__name__)

# Comparison layout. False = one interleaved list, metric by metric across
# both areas; True = a block per area under its own sub-header. Both are
# built and tested; this flag is the single place the default is chosen.
COMPARISON_GROUPED = True


def _focus_kw(focus: tuple[str, ...]) -> dict:
    """`focus=` for search/extraction only when there is one, so a plain
    briefing makes exactly the calls it always made."""
    return {"focus": focus} if focus else {}


async def build_lead_intel_reply(
    subject: str,
    audience: str,
    search: SearchProvider | None = None,
    extractor: ExtractionProvider | None = None,
    focus: tuple[str, ...] = (),
) -> str:
    """`focus` is what she asked about the subject (see focus.py): it steers
    the search, tells the extractor what to look for, and decides what the
    reply leads with. Empty means the plain briefing, unchanged."""
    search = search or get_search_provider()
    extractor = extractor or get_extraction_provider()

    sources = await search.search_area(subject, **_focus_kw(focus))
    if not sources:
        return formatter.render_thin_sources(subject, focus)

    claims = await extractor.extract_claims(subject, sources, **_focus_kw(focus))
    if claims is None:
        return formatter.render_unavailable()

    ranges, qualitative = assemble_ranges(claims, subject)
    ranges, qualitative, places_first = focus_topics.narrow(ranges, qualitative, focus)
    if not ranges and not qualitative:
        return formatter.render_thin_sources(subject, focus)
    missing = focus_topics.unanswered(focus, ranges, qualitative)
    answered = tuple(k for k in focus if k not in missing)

    bullets = render_bullets(
        subject, ranges, qualitative, audience,
        max_qualitative=MAX_QUALITATIVE_FOCUSED if places_first else MAX_QUALITATIVE_SINGLE,
        places_first=places_first,
    )
    # Cite only what reached a bullet: the caps above can leave facts out,
    # and a source listed under Sources: must have a marker in the reply.
    cited_sources = _cited(sources, *_shown([("", bullets)], ranges, qualitative))
    return formatter.render_lead_intel(subject, bullets, audience, cited_sources,
                                       answered, missing)


async def build_comparison_reply(
    subjects: list[str],
    audience: str,
    search: SearchProvider | None = None,
    extractor: ExtractionProvider | None = None,
    grouped: bool = COMPARISON_GROUPED,
    focus: tuple[str, ...] = (),
) -> str:
    search = search or get_search_provider()
    extractor = extractor or get_extraction_provider()

    per_area_sources: dict[str, list[SourceResult]] = {}
    for area in subjects:
        per_area_sources[area] = await search.search_area(area, **_focus_kw(focus))

    if not any(per_area_sources.values()):
        return formatter.render_thin_sources(" vs ".join(subjects), focus)

    combined_sources: list[SourceResult] = []
    combined_claims: list[Claim] = []
    offset = 0
    for area in subjects:
        srcs = per_area_sources[area]
        if not srcs:
            continue
        claims = await extractor.extract_claims(area, srcs, **_focus_kw(focus))
        if claims:
            combined_claims.extend(remap_claims(claims, offset))
        combined_sources.extend(srcs)
        offset += len(srcs)

    per_area_facts: dict[str, tuple[list, list]] = {}
    places_first = focus_topics.asks_about_places(focus)
    for area in subjects:
        ranges, qualitative = assemble_ranges(combined_claims, area)
        ranges, qualitative, _ = focus_topics.narrow(ranges, qualitative, focus)
        if ranges or qualitative:
            per_area_facts[area] = (ranges, qualitative)

    if not per_area_facts:
        return formatter.render_thin_sources(" vs ".join(subjects), focus)
    max_qual = MAX_QUALITATIVE_FOCUSED_COMPARISON if places_first else MAX_QUALITATIVE_COMPARISON

    all_ranges = [r for ranges, _q in per_area_facts.values() for r in ranges]
    all_qual = [q for _r, qualitative in per_area_facts.values() for q in qualitative]
    missing = focus_topics.unanswered(focus, all_ranges, all_qual)
    answered = tuple(k for k in focus if k not in missing)

    if grouped:
        sections = render_comparison_sections(
            per_area_facts, audience,
            max_qualitative_per_area=max_qual, places_first=places_first,
        )
        # Only the facts that actually made it into a section may be cited.
        shown = _shown(sections, all_ranges, all_qual)
        cited_sources = _cited(combined_sources, *shown)
        return formatter.render_comparison(
            subjects, [], audience, cited_sources, sections=sections,
            focus=answered, unanswered=missing,
        )

    bullets = render_comparison_bullets(
        per_area_facts, audience, max_qualitative_per_area=max_qual
    )
    cited_sources = _cited(combined_sources, all_ranges, all_qual)
    return formatter.render_comparison(subjects, bullets, audience, cited_sources,
                                       focus=answered, unanswered=missing)


def _shown(sections, all_ranges, all_qual):
    """Narrow the citation list to the markers that actually appear in the
    rendered sections — a source that got trimmed by a per-area cap must not
    still be listed under Sources:. A single-area briefing passes its
    bullets as one unnamed section."""
    rendered = " ".join(line for _name, lines in sections for line in lines)
    used = {int(n) for n in re.findall(r"\[(\d+)\]", rendered)}
    return (
        [r for r in all_ranges if set(r.source_indices) & used],
        [q for q in all_qual if q.source_index in used],
    )


def _cited(sources: list[SourceResult], ranges, qualitative) -> list[tuple[int, SourceResult]]:
    used = sorted(
        {i for r in ranges for i in r.source_indices} | {q.source_index for q in qualitative}
    )
    return [(i, sources[i - 1]) for i in used if 1 <= i <= len(sources)]


# ── The daily brief ─────────────────────────────────────────────────────
#
# Three parts, each dropped rather than faked when nothing good was found:
#
#   🔥 one headline — the publisher's own title, verbatim, from an
#      allowlisted source. No model rewrites it, so nothing in it is ours.
#   📊 one market data point — the exact search -> extract -> assemble path
#      a briefing uses, for one area per day (DAILY_AREAS, rotating). Going
#      through assemble_ranges for a named area keeps both structural
#      guarantees: no mixed units, and no citywide figure passed off as the
#      area's.
#   💡 one post idea — the only unsourced line; a hook, not a script, with
#      any figure in it rejected outright (see _clean_idea).
#
# If neither sourced part found anything, build_daily_brief returns None and
# the handler sends the old ARTICLE / FUN FACT offer instead — an idea with
# no news or data under it isn't a brief.

# Where the data point rotates, one area per day. Areas her clients actually
# ask about first, then the other high-volume Dubai communities.
DAILY_AREAS: tuple[str, ...] = (
    "JVC", "Arjan", "Business Bay", "Dubai Marina", "Downtown Dubai",
    "Dubai Hills Estate", "JLT", "Al Furjan", "Dubai South", "Palm Jumeirah",
)
# Areas tried per morning before giving up on the data point — bounds the
# search/extraction spend of a quiet day.
_DAILY_AREA_ATTEMPTS = 2

# Which figure to lead with when an area turns up several. Movement first
# (the brief is a daily, so change is the news), then the headline price.
_DATA_POINT_PRIORITY = (
    "yoy_change_pct", "price_per_sqft", "rental_yield_pct", "annual_rent",
    "transaction_count", "total_price",
)

# Headlines older than this lose out to fresher ones when both are found.
_HEADLINE_FRESH_DAYS = 3

_DUBAI_TZ = timezone(timedelta(hours=4))  # UAE has no DST


def dubai_today() -> date:
    return datetime.now(_DUBAI_TZ).date()


def area_for(day: date) -> str:
    return DAILY_AREAS[day.toordinal() % len(DAILY_AREAS)]


def _published(s: SourceResult) -> datetime | None:
    raw = (s.published_date or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def clean_headline(title: str, domain: str) -> str:
    """The title as published, minus the site-name suffix portals and papers
    append ("... | Khaleej Times", "... - Gulf News"). Only a suffix that
    spells the source's own domain is removed, so a headline that merely
    contains a dash is left alone."""
    title = " ".join((title or "").split())
    stem = domain.split(".")[0].lower()
    for sep in (" | ", " - ", " – ", " — "):
        head, found, tail = title.rpartition(sep)
        squashed = re.sub(r"[^a-z]", "", tail.lower())
        if found and head and squashed and (stem.startswith(squashed) or squashed.startswith(stem)):
            title = head
            break
    return title.strip()


def pick_headline(news: list[SourceResult], today: date) -> SourceResult | None:
    """The first titled result (search already ranked them) published within
    _HEADLINE_FRESH_DAYS; failing that, the first titled result at all."""
    titled = [s for s in news if clean_headline(s.title, s.domain)]
    if not titled:
        return None
    cutoff = today - timedelta(days=_HEADLINE_FRESH_DAYS)
    for s in titled:
        dt = _published(s)
        if dt is not None and dt.astimezone(_DUBAI_TZ).date() >= cutoff:
            return s
    return titled[0]


def pick_data_point(ranges: list[RangeFact]) -> RangeFact | None:
    """One RangeFact to show: highest-priority metric, preferring the
    general (unqualified) figure and then one corroborated by more sources."""
    rank = {m: i for i, m in enumerate(_DATA_POINT_PRIORITY)}
    candidates = [r for r in ranges if r.metric in rank]
    if not candidates:
        return None
    return min(candidates, key=lambda r: (rank[r.metric], bool(r.qualifier), r.single_source))


_MAX_IDEA_WORDS = 25
_IDEA_STRIP = "\"'“”‘’ "


def clean_idea(raw: str | None) -> str | None:
    """Accept the model's idea only if it is one short, figure-free line.
    Same rule as a qualitative claim: a digit here would be an uncited
    number in a sourced message, so the line is dropped, never edited."""
    idea = " ".join((raw or "").split()).strip(_IDEA_STRIP)
    if not idea or _DIGIT.search(idea) or len(idea.split()) > _MAX_IDEA_WORDS:
        return None
    return idea


async def build_daily_brief(
    search: SearchProvider | None = None,
    extractor: ExtractionProvider | None = None,
    generator: ContentGenerator | None = None,
    today: date | None = None,
) -> str | None:
    """The morning brief, or None when nothing sourced was found (the
    caller then falls back to the ARTICLE / FUN FACT offer)."""
    search = search or get_search_provider()
    extractor = extractor or get_extraction_provider()
    generator = generator or get_generator()
    today = today or dubai_today()

    sources: list[SourceResult] = []

    headline_src = pick_headline(await search.search_news(), today)
    headline = news_line = None
    if headline_src is not None:
        sources.append(headline_src)
        headline = clean_headline(headline_src.title, headline_src.domain)
        news_line = f"{headline} [1]"

    # Data point: today's area, then the next one along if it came up empty.
    data_area = data_line = None
    fact = None
    start = DAILY_AREAS.index(area_for(today))
    for step in range(_DAILY_AREA_ATTEMPTS):
        area = DAILY_AREAS[(start + step) % len(DAILY_AREAS)]
        area_sources = await search.search_area(area)
        if not area_sources:
            continue
        claims = await extractor.extract_claims(area, area_sources)
        if not claims:
            continue
        # Shift into the brief's shared numbering, after the headline, so
        # "[1]" can never mean two different sources in the same message.
        ranges, _qualitative = assemble_ranges(remap_claims(claims, len(sources)), area)
        fact = pick_data_point(ranges)
        if fact is not None:
            sources.extend(area_sources)
            data_area = area
            data_line = render_bullets(area, [fact], [], "self", max_bullets=1)[0]
            break

    if news_line is None and data_line is None:
        logger.info("broker_intel daily brief: nothing sourced found for %s", today)
        return None

    topic = headline or f"the {data_area} property market"
    idea_line = clean_idea(await generator.post_idea(topic))

    cited = _cited(sources, [fact] if fact is not None else [], [])
    if headline_src is not None:
        cited = [(1, headline_src)] + cited

    return formatter.render_daily_brief(
        date_label=f"{today.day} {today:%b %Y}",
        news_line=news_line,
        data_area=data_area,
        data_line=data_line,
        idea_line=idea_line,
        cited_sources=cited,
    )
