"""Verification for broker_intel's sourced-briefing pipeline: search.py,
extraction.py, and briefing.py.

Pure unit tests, no DB and no app harness — these three modules take
SourceResult/Claim/RangeFact values in and values out, so they're tested
directly, the same "plain asyncio script, no pytest" convention as the rest
of this repo's test files.

Sections:
  A  the mixed-unit regression — the actual bug this pipeline replaced
  B  single-source vs multi-source disclosure
  C  scope isolation — citywide and other-area claims never leak in
  D  qualifier splits groups (studio rent vs villa rent, etc.)
  E  defensive parsing of the model's JSON — malformed input is dropped,
     never repaired or guessed at
  F  remap_claims — the comparison multi-area indexing math
  G  audience-differentiated rendering (ME vs LEAD)
  H  the allowlist — search.py's domain filter
  I  briefing.py end to end, with stub search/extraction — thin/failed
     cases answer honestly, partial-area comparisons degrade gracefully
"""

from __future__ import annotations

import asyncio
import math
import sys

from app.services.broker_intel import briefing, formatter
from app.services.broker_intel.extraction import (
    Claim,
    StubExtractionProvider,
    _parse_claims,
    assemble_ranges,
    remap_claims,
    render_bullets,
    render_comparison_bullets,
)
from app.services.broker_intel.search import (
    REPUTABLE_DOMAINS,
    SourceResult,
    StubSearchProvider,
    domain_of,
    on_allowlist,
)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(("  [ok] " if condition else "  [XX] ") + name
          + (f"  -- {detail}" if detail and not condition else ""))


def src(domain: str, content: str = "", date: str | None = None) -> SourceResult:
    return SourceResult(url=f"https://{domain}/x", domain=domain, title="x",
                         content=content, published_date=date)


# ── A. the mixed-unit regression ─────────────────────────────

def run_mixed_unit_checks() -> None:
    """THE bug: a total apartment price (AED 1,000,000) and a
    price-per-square-foot figure (AED 1,564) came from the same source page
    and got merged by free-text generation into one nonsense "range" —
    AED 1,000,000 to AED 1,564/sqft. This is the direct regression test,
    built to reproduce that exact pair of numbers."""
    print("\n== A. the mixed-unit regression (the actual live bug) ==")

    claims = [
        Claim(metric="total_price", scope_area="Arjan", value=1_000_000,
              qualifier="", note="", source_index=1),
        Claim(metric="price_per_sqft", scope_area="Arjan", value=1_564,
              qualifier="", note="", source_index=1),
    ]
    ranges, qualitative = assemble_ranges(claims, "Arjan")

    check("A1 both claims survive assembly", len(ranges) == 2, str(ranges))
    metrics = {r.metric for r in ranges}
    check("A2 they land in TWO separate RangeFacts, not one",
          metrics == {"total_price", "price_per_sqft"}, str(metrics))

    for r in ranges:
        check(f"A3 {r.metric} RangeFact carries only its own metric's value",
              (r.low, r.high) == (1_000_000, 1_000_000) if r.metric == "total_price"
              else (r.low, r.high) == (1_564, 1_564),
              f"{r.metric}: {r.low}-{r.high}")

    bullets = render_bullets("Arjan", ranges, qualitative, "self")
    check("A4 rendered bullets: no single line contains both figures",
          not any("1,000,000" in b and "1,564" in b for b in bullets),
          str(bullets))
    check("A5 both figures appear, each in its own bullet",
          any("1,000,000" in b for b in bullets) and any("1,564" in b for b in bullets),
          str(bullets))
    check("A6 the price/sqft bullet carries the /sqft unit; the total price does not",
          any("1,564" in b and "/sqft" in b for b in bullets)
          and not any("1,000,000" in b and "/sqft" in b for b in bullets),
          str(bullets))

    # Same check the other way round: many claims of both metrics, still
    # never cross-contaminate regardless of how many there are.
    many = [
        Claim("total_price", "Arjan", 900_000, "", "", 1),
        Claim("total_price", "Arjan", 1_100_000, "", "", 2),
        Claim("price_per_sqft", "Arjan", 1_400, "", "", 1),
        Claim("price_per_sqft", "Arjan", 1_600, "", "", 3),
        Claim("price_per_sqft", "Arjan", 1_650, "", "", 4),
    ]
    ranges2, _ = assemble_ranges(many, "Arjan")
    by_metric = {r.metric: r for r in ranges2}
    check("A7 grouping holds with several claims per metric: total_price range",
          (by_metric["total_price"].low, by_metric["total_price"].high) == (900_000, 1_100_000))
    check("A8 ...and price_per_sqft range, independently",
          (by_metric["price_per_sqft"].low, by_metric["price_per_sqft"].high) == (1_400, 1_650))
    check("A9 total_price cites sources [1][2] only",
          by_metric["total_price"].source_indices == (1, 2))
    check("A10 price_per_sqft cites sources [1][3][4] only",
          by_metric["price_per_sqft"].source_indices == (1, 3, 4))


# ── B. single-source vs multi-source disclosure ──────────────

def run_disclosure_checks() -> None:
    print("\n== B. single-source vs multi-source disclosure ==")

    single = [Claim("rental_yield_pct", "JVC", 7.2, "", "", 5)]
    ranges, _ = assemble_ranges(single, "JVC")
    check("B1 one source -> single_source=True", ranges[0].single_source is True)
    check("B2 one source -> exactly one citation marker",
          ranges[0].source_indices == (5,))

    multi = [
        Claim("rental_yield_pct", "JVC", 6.5, "", "", 1),
        Claim("rental_yield_pct", "JVC", 8.1, "", "", 2),
    ]
    ranges2, _ = assemble_ranges(multi, "JVC")
    check("B3 two sources -> single_source=False", ranges2[0].single_source is False)
    check("B4 two sources -> both markers present",
          ranges2[0].source_indices == (1, 2))

    bullets_single = render_bullets("JVC", ranges, [], "self")
    bullets_multi = render_bullets("JVC", ranges2, [], "self")
    check("B5 single-source bullet has exactly one bracket",
          bullets_single[0].count("[") == 1, bullets_single[0])
    check("B6 multi-source bullet has two brackets",
          bullets_multi[0].count("[") == 2, bullets_multi[0])


# ── C. scope isolation ────────────────────────────────────────

def run_scope_checks() -> None:
    """The other live bug: a Dubai-wide yield figure attached itself to a
    JVC-specific briefing. assemble_ranges must drop anything not scoped
    to the area actually being briefed."""
    print("\n== C. scope isolation — citywide and other-area claims excluded ==")

    claims = [
        Claim("rental_yield_pct", "JVC", 7.5, "", "", 1),
        Claim("rental_yield_pct", "citywide", 6.68, "", "", 2),
        Claim("price_per_sqft", "Arjan", 1500, "", "", 3),  # wrong area entirely
        Claim("qualitative", "citywide", None, "", "Dubai overall demand is strong", 4),
    ]
    ranges, qualitative = assemble_ranges(claims, "JVC")

    check("C1 only the JVC-scoped yield claim survives",
          len(ranges) == 1 and ranges[0].metric == "rental_yield_pct", str(ranges))
    check("C2 the citywide yield figure (6.68) never appears in JVC's ranges",
          not any(r.low == 6.68 or r.high == 6.68 for r in ranges), str(ranges))
    check("C3 the Arjan price claim never appears in JVC's ranges",
          not any(r.metric == "price_per_sqft" for r in ranges), str(ranges))
    check("C4 the citywide qualitative claim is also excluded",
          qualitative == [], str(qualitative))

    # Various spellings of "not this area" all excluded, not just "citywide".
    for label in ("Dubai", "dubai-wide", "UAE", "", "Dubai wide"):
        c = [Claim("rental_yield_pct", label, 6.0, "", "", 1)]
        r, _ = assemble_ranges(c, "JVC")
        check(f"C5 scope_area={label!r} excluded from a JVC briefing",
              r == [], f"got {r}")

    # Leniency: a slightly different rendering of the SAME area still matches.
    c = [Claim("price_per_sqft", "JVC, Dubai", 1500, "", "", 1)]
    r, _ = assemble_ranges(c, "JVC")
    check("C6 'JVC, Dubai' still matches a request for 'JVC' (substring leniency)",
          len(r) == 1, str(r))


# ── D. qualifier splits groups ────────────────────────────────

def run_qualifier_checks() -> None:
    print("\n== D. qualifier splits groups (studio vs villa, etc.) ==")

    claims = [
        Claim("annual_rent", "JVC", 45_000, "studio", "", 1),
        Claim("annual_rent", "JVC", 50_000, "studio", "", 2),
        Claim("annual_rent", "JVC", 130_000, "villa", "", 3),
    ]
    ranges, _ = assemble_ranges(claims, "JVC")
    check("D1 studio and villa rents produce TWO separate RangeFacts",
          len(ranges) == 2, str(ranges))
    by_qual = {r.qualifier: r for r in ranges}
    check("D2 studio range never absorbs the villa figure",
          by_qual["studio"].high == 50_000 and by_qual["villa"].low == 130_000,
          str(ranges))

    bullets = render_bullets("JVC", ranges, [], "lead")
    check("D3 rendered LEAD bullets name each qualifier distinctly",
          any("studio" in b for b in bullets) and any("villa" in b for b in bullets),
          str(bullets))


# ── E. defensive parsing ──────────────────────────────────────

def run_parsing_checks() -> None:
    """_parse_claims must DROP anything malformed rather than repair or
    guess at it — a source that produced garbage should simply contribute
    nothing, which is always the safe outcome."""
    print("\n== E. defensive parsing of the model's JSON ==")

    good = ('{"claims": [{"metric": "price_per_sqft", "scope_area": "Arjan", '
            '"value": 1500, "qualifier": "", "note": "", "source_index": 1}]}')
    check("E1 well-formed JSON parses to one claim", len(_parse_claims(good, 3)) == 1)

    check("E2 not valid JSON at all -> dropped entirely", _parse_claims("not json {{{", 3) == [])
    check("E3 JSON with no 'claims' key -> dropped entirely", _parse_claims("{}", 3) == [])
    check("E4 a JSON array instead of an object -> dropped entirely",
          _parse_claims("[1,2,3]", 3) == [])

    unknown_metric = ('{"claims": [{"metric": "made_up_metric", "scope_area": "X", '
                       '"value": 1, "qualifier": "", "note": "", "source_index": 1}]}')
    check("E5 an unrecognised metric is dropped", _parse_claims(unknown_metric, 3) == [])

    bad_index = ('{"claims": [{"metric": "total_price", "scope_area": "X", '
                 '"value": 1, "qualifier": "", "note": "", "source_index": 99}]}')
    check("E6 a source_index outside the given range is dropped",
          _parse_claims(bad_index, 3) == [])

    non_numeric = ('{"claims": [{"metric": "total_price", "scope_area": "X", '
                    '"value": "expensive", "qualifier": "", "note": "", "source_index": 1}]}')
    check("E7 a non-numeric value for a numeric metric is dropped",
          _parse_claims(non_numeric, 3) == [])

    digit_note = ('{"claims": [{"metric": "qualitative", "scope_area": "X", '
                   '"value": null, "qualifier": "", "note": "yields 8% here", '
                   '"source_index": 1}]}')
    check("E8 a qualitative note smuggling in a digit is dropped",
          _parse_claims(digit_note, 3) == [])

    empty_note = ('{"claims": [{"metric": "qualitative", "scope_area": "X", '
                   '"value": null, "qualifier": "", "note": "", "source_index": 1}]}')
    check("E9 an empty qualitative note is dropped",
          _parse_claims(empty_note, 3) == [])

    not_a_dict = '{"claims": ["just a string", 42, null]}'
    check("E10 non-dict entries in the claims array are dropped",
          _parse_claims(not_a_dict, 3) == [])

    nan_value = ('{"claims": [{"metric": "total_price", "scope_area": "X", '
                 '"value": NaN, "qualifier": "", "note": "", "source_index": 1}]}')
    # Python's json module accepts bare NaN as an extension and parses it to
    # float('nan'); the NaN/inf guard in _parse_claims must catch it there
    # rather than let a NaN "value" reach a RangeFact.
    check("E11 a NaN value is dropped, not passed through",
          _parse_claims(nan_value, 3) == [])

    inf_value = ('{"claims": [{"metric": "total_price", "scope_area": "X", '
                 '"value": Infinity, "qualifier": "", "note": "", "source_index": 1}]}')
    check("E11b an Infinity value is dropped, not passed through",
          _parse_claims(inf_value, 3) == [])

    mixed = ('{"claims": ['
             '{"metric": "price_per_sqft", "scope_area": "Arjan", "value": 1500, '
             '"qualifier": "", "note": "", "source_index": 1},'
             '{"metric": "made_up", "scope_area": "Arjan", "value": 1, '
             '"qualifier": "", "note": "", "source_index": 1},'
             '{"metric": "qualitative", "scope_area": "Arjan", "value": null, '
             '"qualifier": "", "note": "Has 5 towers", "source_index": 1}'
             ']}')
    parsed = _parse_claims(mixed, 3)
    check("E12 a mixed batch keeps only the valid claim, drops the other two",
          len(parsed) == 1 and parsed[0].metric == "price_per_sqft", str(parsed))


# ── F. remap_claims — comparison multi-area indexing ──────────

def run_remap_checks() -> None:
    print("\n== F. remap_claims — multi-area source indexing ==")

    claims = [
        Claim("price_per_sqft", "JVC", 1500, "", "", 1),
        Claim("rental_yield_pct", "JVC", 7.0, "", "", 2),
    ]
    remapped = remap_claims(claims, offset=5)
    check("F1 source_index shifts by the offset",
          [c.source_index for c in remapped] == [6, 7], str(remapped))
    check("F2 every other field is preserved exactly",
          all(a.metric == b.metric and a.scope_area == b.scope_area and a.value == b.value
              for a, b in zip(claims, remapped)))
    check("F3 the original claims are untouched (immutable dataclass)",
          [c.source_index for c in claims] == [1, 2])


# ── G. audience-differentiated rendering ──────────────────────

def run_audience_checks() -> None:
    print("\n== G. ME vs LEAD render differently from the same facts ==")

    ranges, qualitative = assemble_ranges(
        [Claim("price_per_sqft", "Arjan", 1500, "", "", 1),
         Claim("price_per_sqft", "Arjan", 1600, "", "", 2)],
        "Arjan",
    )
    me = render_bullets("Arjan", ranges, qualitative, "self")
    lead = render_bullets("Arjan", ranges, qualitative, "lead")
    check("G1 ME and LEAD produce different wording from identical facts",
          me != lead, f"me={me} lead={lead}")
    check("G2 both still carry the same underlying figures (1,500-1,600)",
          all("1,500" in b or "1,600" in b for b in me) and
          all("1,500" in b or "1,600" in b for b in lead), f"me={me} lead={lead}")
    check("G3 ME reads terse (short label form)", me[0].startswith("Price/sqft"), me[0])
    check("G4 LEAD reads as a sentence naming the area", "Arjan" in lead[0], lead[0])

    per_area = {
        "Arjan": assemble_ranges([Claim("price_per_sqft", "Arjan", 1500, "", "", 1)], "Arjan"),
        "JVC": assemble_ranges([Claim("price_per_sqft", "JVC", 1469, "", "", 2)], "JVC"),
    }
    comp_me = render_comparison_bullets(per_area, "self")
    comp_lead = render_comparison_bullets(per_area, "lead")
    check("G5 comparison bullets name both areas (ME)",
          any("Arjan" in b for b in comp_me) and any("JVC" in b for b in comp_me), str(comp_me))
    check("G6 comparison bullets name both areas (LEAD)",
          any("Arjan" in b for b in comp_lead) and any("JVC" in b for b in comp_lead), str(comp_lead))

    # Found in live testing: one area's sources broke price_per_sqft into
    # unit-type variants (studio/1-bed/2-bed) while the other area's didn't,
    # so that area alone produced 4 bullets against the 6-bullet cap and
    # crowded the other area almost entirely out of its own comparison.
    crowded = {
        "Arjan": assemble_ranges([
            Claim("price_per_sqft", "Arjan", 1500, "", "", 1),
            Claim("price_per_sqft", "Arjan", 1700, "studio", "", 1),
            Claim("price_per_sqft", "Arjan", 1600, "1-bed", "", 1),
            Claim("price_per_sqft", "Arjan", 1550, "2-bed", "", 1),
        ], "Arjan"),
        "JVC": assemble_ranges([
            Claim("price_per_sqft", "JVC", 1469, "", "", 1),
            Claim("rental_yield_pct", "JVC", 7.5, "", "", 1),
        ], "JVC"),
    }
    comp = render_comparison_bullets(crowded, "self")
    check("G7 a qualifier-heavy area contributes at most ONE bullet per "
          "metric to a comparison, not one per qualifier variant",
          sum(1 for b in comp if "*Arjan*" in b and "Price/sqft" in b) == 1, str(comp))
    check("G8 ...so the other area's DIFFERENT metric still makes it into "
          "the comparison rather than being crowded out",
          any("*JVC*" in b and "Rental yield" in b for b in comp), str(comp))
    check("G9 the representative Arjan figure is the unqualified one, "
          "not an arbitrary unit-type variant",
          any("*Arjan*" in b and "Price/sqft:" in b and "1,500" in b for b in comp), str(comp))


# ── H. the allowlist ──────────────────────────────────────────

def run_allowlist_checks() -> None:
    print("\n== H. search.py's domain allowlist ==")

    check("H1 a reputable domain is accepted", on_allowlist("https://www.bayut.com/some/page"))
    check("H2 a subdomain of a reputable domain is accepted",
          on_allowlist("https://blog.propertyfinder.ae/x"))
    check("H3 Instagram is rejected", not on_allowlist("https://www.instagram.com/p/xyz"))
    check("H4 LinkedIn is rejected", not on_allowlist("https://www.linkedin.com/posts/xyz"))
    check("H5 an unrelated random domain is rejected",
          not on_allowlist("https://maphomesrealestate.com/x"))
    check("H6 domain_of strips 'www.'", domain_of("https://www.bayut.com/x") == "bayut.com")
    check("H7 REPUTABLE_DOMAINS carries no social platform",
          not any(d in REPUTABLE_DOMAINS for d in
                  ("instagram.com", "linkedin.com", "facebook.com", "x.com", "tiktok.com")))


# ── I. briefing.py end to end, with stub providers ────────────

async def run_briefing_checks() -> None:
    print("\n== I. briefing.py end to end (stub search + extraction) ==")

    # Nothing found at all -> honest thin-sources reply, no fabrication.
    empty_search = StubSearchProvider({})
    r = await briefing.build_lead_intel_reply(
        "Nonexistent Project", "self", search=empty_search,
        extractor=StubExtractionProvider(claims=[]),
    )
    check("I1 zero search results -> render_thin_sources, not a briefing",
          "couldn't find" in r.lower() and "•" not in r, r[:80])

    # Search found sources, but extraction hard-failed -> render_unavailable.
    has_sources = StubSearchProvider({"Arjan": [src("bayut.com", "some content")]})

    class DeadExtractor:
        async def extract_claims(self, subject, sources):
            return None

    r = await briefing.build_lead_intel_reply(
        "Arjan", "self", search=has_sources, extractor=DeadExtractor()
    )
    check("I2 extraction failure -> render_unavailable, not a briefing",
          "couldn't generate" in r.lower() and "•" not in r, r[:80])

    # Search found sources, extraction ran but found nothing usable -> thin.
    r = await briefing.build_lead_intel_reply(
        "Arjan", "self", search=has_sources, extractor=StubExtractionProvider(claims=[])
    )
    check("I3 sources found but nothing extractable -> render_thin_sources",
          "couldn't find" in r.lower(), r[:80])

    # A real success case, end to end, with the caveat and a source list.
    real_search = StubSearchProvider({"Arjan": [src("bayut.com", "..."), src("propertyfinder.ae", "...")]})
    real_extractor = StubExtractionProvider(claims=[
        Claim("price_per_sqft", "Arjan", 1500, "", "", 1),
        Claim("price_per_sqft", "Arjan", 1650, "", "", 2),
    ])
    r = await briefing.build_lead_intel_reply("Arjan", "self", search=real_search, extractor=real_extractor)
    check("I4 a real success case carries SOURCED_CAVEAT",
          formatter.SOURCED_CAVEAT in r, r[-100:])
    check("I5 ...and a Sources: line naming the actual domains cited",
          "Sources:" in r and "bayut.com" in r and "propertyfinder.ae" in r, r)
    check("I6 ...and MARKET_CAVEAT (the old, ungrounded caveat) is NOT present",
          formatter.MARKET_CAVEAT not in r, r)

    # Comparison: one area has sources, the other has none at all —
    # must degrade to covering just the one area, not fail outright.
    partial = StubSearchProvider({"Arjan": [src("bayut.com", "...")]})  # JVC absent
    partial_extractor = StubExtractionProvider(claims=lambda subject, sources: (
        [Claim("price_per_sqft", "Arjan", 1500, "", "", 1)] if subject == "Arjan" else []
    ))
    r = await briefing.build_comparison_reply(
        ["Arjan", "JVC"], "self", search=partial, extractor=partial_extractor
    )
    check("I7 comparison degrades gracefully when one area has no sources",
          "Arjan" in r and "•" in r, r[:100])
    check("I8 ...and fabricates no JVC-labeled bullet (only the header names it)",
          "*JVC*" not in r, r)

    # Comparison: NEITHER area has sources -> thin-sources, not a crash.
    r = await briefing.build_comparison_reply(
        ["Ghost Town", "Nowhere"], "self",
        search=StubSearchProvider({}), extractor=StubExtractionProvider(claims=[]),
    )
    check("I9 comparison with zero sources anywhere -> honest thin reply",
          "couldn't find" in r.lower(), r[:80])

    # search_area is actually called with the right area names.
    tracked = StubSearchProvider({"Arjan": [src("bayut.com")], "JVC": [src("bayut.com")]})
    tracked_extractor = StubExtractionProvider(claims=[
        Claim("price_per_sqft", "Arjan", 1500, "", "", 1),
    ])
    await briefing.build_comparison_reply(["Arjan", "JVC"], "self",
                                           search=tracked, extractor=tracked_extractor)
    check("I10 both areas are actually searched, not just the first",
          tracked.calls == ["Arjan", "JVC"], str(tracked.calls))


async def main() -> None:
    print("=" * 68)
    print("  broker_intel sourcing pipeline verification")
    print("=" * 68)

    run_mixed_unit_checks()
    run_disclosure_checks()
    run_scope_checks()
    run_qualifier_checks()
    run_parsing_checks()
    run_remap_checks()
    run_audience_checks()
    run_allowlist_checks()
    await run_briefing_checks()

    print("\n" + "=" * 68)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = [r for r in results if r[0] == FAIL]
    print(f"  {passed}/{len(results)} checks passed")
    for _s, name, detail in failed:
        print(f"    - {name}: {detail}")
    print("=" * 68)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
