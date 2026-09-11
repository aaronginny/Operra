"""Orchestrates a sourced briefing end to end: search -> extract -> assemble
-> render -> caveat.

This is what handler.py calls for BOTH single-area lead intel and
multi-area comparisons. search.py and extraction.py stay agnostic of
WhatsApp formatting so they can be unit-tested without a rendered message
in view; formatter.py still owns the one caveat-attachment chokepoint
(_sourced_reply) for the same reason it always has — see formatter.py's
docstring.

search and extractor are accepted as parameters (defaulting to the real
providers) so tests can inject stubs, the same pattern content.py's
ContentGenerator uses.
"""

from __future__ import annotations

from app.services.broker_intel import formatter
from app.services.broker_intel.extraction import (
    Claim,
    ExtractionProvider,
    assemble_ranges,
    get_extraction_provider,
    remap_claims,
    render_bullets,
    render_comparison_bullets,
)
from app.services.broker_intel.search import (
    SearchProvider,
    SourceResult,
    get_search_provider,
)


async def build_lead_intel_reply(
    subject: str,
    audience: str,
    search: SearchProvider | None = None,
    extractor: ExtractionProvider | None = None,
) -> str:
    search = search or get_search_provider()
    extractor = extractor or get_extraction_provider()

    sources = await search.search_area(subject)
    if not sources:
        return formatter.render_thin_sources(subject)

    claims = await extractor.extract_claims(subject, sources)
    if claims is None:
        return formatter.render_unavailable()

    ranges, qualitative = assemble_ranges(claims, subject)
    if not ranges and not qualitative:
        return formatter.render_thin_sources(subject)

    bullets = render_bullets(subject, ranges, qualitative, audience)
    cited_sources = _cited(sources, ranges, qualitative)
    return formatter.render_lead_intel(subject, bullets, audience, cited_sources)


async def build_comparison_reply(
    subjects: list[str],
    audience: str,
    search: SearchProvider | None = None,
    extractor: ExtractionProvider | None = None,
) -> str:
    search = search or get_search_provider()
    extractor = extractor or get_extraction_provider()

    per_area_sources: dict[str, list[SourceResult]] = {}
    for area in subjects:
        per_area_sources[area] = await search.search_area(area)

    if not any(per_area_sources.values()):
        return formatter.render_thin_sources(" vs ".join(subjects))

    combined_sources: list[SourceResult] = []
    combined_claims: list[Claim] = []
    offset = 0
    for area in subjects:
        srcs = per_area_sources[area]
        if not srcs:
            continue
        claims = await extractor.extract_claims(area, srcs)
        if claims:
            combined_claims.extend(remap_claims(claims, offset))
        combined_sources.extend(srcs)
        offset += len(srcs)

    per_area_facts: dict[str, tuple[list, list]] = {}
    for area in subjects:
        ranges, qualitative = assemble_ranges(combined_claims, area)
        if ranges or qualitative:
            per_area_facts[area] = (ranges, qualitative)

    if not per_area_facts:
        return formatter.render_thin_sources(" vs ".join(subjects))

    bullets = render_comparison_bullets(per_area_facts, audience)
    all_ranges = [r for ranges, _q in per_area_facts.values() for r in ranges]
    all_qual = [q for _r, qualitative in per_area_facts.values() for q in qualitative]
    cited_sources = _cited(combined_sources, all_ranges, all_qual)
    return formatter.render_comparison(subjects, bullets, audience, cited_sources)


def _cited(sources: list[SourceResult], ranges, qualitative) -> list[tuple[int, SourceResult]]:
    used = sorted(
        {i for r in ranges for i in r.source_indices} | {q.source_index for q in qualitative}
    )
    return [(i, sources[i - 1]) for i in used if 1 <= i <= len(sources)]
