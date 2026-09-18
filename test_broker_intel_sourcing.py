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
  K  source trust tiers — the tier map, the fallback, the Sources line
  L  the daily brief — drop-if-nothing, scope, numbering, the post idea
"""

from __future__ import annotations

import asyncio
import math
import sys

from app.services.broker_intel import briefing, formatter
from app.services.broker_intel.extraction import (
    MAX_QUALITATIVE_SINGLE,
    Claim,
    QualitativeFact,
    StubExtractionProvider,
    _parse_claims,
    assemble_ranges,
    is_plausible,
    is_substantive_note,
    remap_claims,
    render_bullets,
    render_comparison_bullets,
    render_comparison_sections,
)
from app.services.broker_intel.search import (
    DOMAIN_TIERS,
    REPUTABLE_DOMAINS,
    TIER_EMOJI,
    TIER_MARKET,
    TIER_NEWS,
    TIER_VERIFIED,
    SourceResult,
    StubSearchProvider,
    domain_of,
    on_allowlist,
    tier_emoji,
    tier_of,
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
    check("G7 a qualifier-heavy area is capped at VARIANTS_PER_METRIC "
          "bullets for one metric, not one per qualifier variant "
          "(4 variants in, at most 2 out)",
          sum(1 for b in comp if "*Arjan*" in b and "Price/sqft" in b) <= 2, str(comp))
    check("G8 ...so the other area's DIFFERENT metric still makes it into "
          "the comparison rather than being crowded out",
          any("*JVC*" in b and "Rental yield" in b for b in comp), str(comp))
    check("G9 the unqualified figure is preferred over a unit-type variant, "
          "so the general area number is never the one dropped",
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


# ── J. substance pass: plausibility, filler filter, layout ───

def run_substance_checks() -> None:
    """Client feedback: the briefings read thin next to plain ChatGPT, and
    some bullets were marketing filler. These cover the three fixes."""
    print("\n== J. substance pass — plausibility, filler filter, layouts ==")

    # 1. Metric mislabelling. Live testing produced "Typical unit prices run
    #    AED 693 for studio units" — a price/sqft figure filed as a total
    #    price. Grouping can't catch that; the plausibility bound must.
    mislabelled = ('{"claims": [{"metric": "total_price", "scope_area": "JVC", '
                    '"value": 693, "qualifier": "studio", "note": "", '
                    '"source_index": 1}]}')
    check("J1 a price/sqft value mislabelled as total_price is dropped",
          _parse_claims(mislabelled, 3) == [], str(_parse_claims(mislabelled, 3)))
    check("J2 the SAME value is kept when filed under the right metric",
          len(_parse_claims(mislabelled.replace("total_price", "price_per_sqft"), 3)) == 1)

    for metric, bad in (("rental_yield_pct", 400), ("down_payment_pct", 900),
                         ("days_on_market", 99999), ("service_charge", 50000),
                         ("annual_rent", 12), ("price_per_sqft", 1)):
        raw = ('{"claims": [{"metric": "%s", "scope_area": "X", "value": %s, '
               '"qualifier": "", "note": "", "source_index": 1}]}' % (metric, bad))
        check(f"J3 an impossible {metric} ({bad}) is dropped",
              _parse_claims(raw, 3) == [])

    check("J4 plausible values for every metric survive",
          all(is_plausible(m, v) for m, v in (
              ("price_per_sqft", 1568), ("total_price", 1_000_000),
              ("rental_yield_pct", 8.4), ("annual_rent", 66_531),
              ("yoy_change_pct", 4.1), ("transaction_count", 135),
              ("days_on_market", 45), ("service_charge", 11),
              ("down_payment_pct", 20))))

    # 2. The filler filter — her actual complaint, verbatim.
    check("J5 'JVC is popular for strong rental yields' is rejected as filler",
          not is_substantive_note("JVC is popular for strong rental yields"))
    for filler in ("A vibrant community with modern amenities",
                    "A sought-after area for investors",
                    "Ideal for families and young professionals",
                    "An excellent investment opportunity",
                    "Accessible community with growing amenities"):
        check(f"J6 filler rejected: {filler[:40]!r}", not is_substantive_note(filler))

    for real in ("Circle Mall and Al Khail Road sit inside the community",
                  "Served by the Dubai Metro red line at Mall of the Emirates",
                  "Developed by Nakheel with handover scheduled for phase two",
                  "Arjan offers full freehold ownership rights"):
        check(f"J7 substantive kept: {real[:40]!r}", is_substantive_note(real))

    check("J8 filler is dropped at parse time, not just at render time",
          _parse_claims('{"claims": [{"metric": "qualitative", "scope_area": "JVC", '
                         '"value": null, "qualifier": "", "note": "a vibrant community", '
                         '"source_index": 1}]}', 3) == [])

    # 3. Numeric facts always outrank colour commentary for the budget.
    ranges, _ = assemble_ranges(
        [Claim("price_per_sqft", "JVC", 1500, "", "", 1),
         Claim("rental_yield_pct", "JVC", 7.5, "", "", 1)], "JVC")
    many_qual = [QualitativeFact(f"Circle Mall sits in district {i}", 1) for i in range(5)]
    bullets = render_bullets("JVC", ranges, many_qual, "self", max_bullets=10)
    check("J9 qualitative bullets are capped so numbers dominate",
          sum(1 for b in bullets if "Circle Mall" in b) <= MAX_QUALITATIVE_SINGLE,
          str(bullets))
    check("J10 ...and every numeric fact still made it in",
          sum(1 for b in bullets if "AED" in b or "%" in b) == 2, str(bullets))

    # 4. New metrics render with the right units.
    for metric, value, expect in (
        ("transaction_count", 135, "135"),
        ("days_on_market", 45, "45 days"),
        ("service_charge", 11, "AED 11/sqft/yr"),
        ("down_payment_pct", 20, "20%"),
    ):
        r, _ = assemble_ranges([Claim(metric, "JVC", value, "", "", 1)], "JVC")
        line = render_bullets("JVC", r, [], "self")[0]
        check(f"J11 {metric} renders with its unit ({expect})", expect in line, line)

    # 5. The grouped layout.
    per_area = {
        "Arjan": assemble_ranges([
            Claim("price_per_sqft", "Arjan", 1568, "", "", 1),
            Claim("rental_yield_pct", "Arjan", 8.4, "", "", 2)], "Arjan"),
        "JVC": assemble_ranges([
            Claim("service_charge", "JVC", 11, "", "", 3)], "JVC"),
    }
    sections = render_comparison_sections(per_area, "self")
    check("J12 grouped layout returns one section per area, in order",
          [name for name, _ in sections] == ["Arjan", "JVC"], str(sections))
    check("J13 bullets under a sub-header don't repeat the area name",
          all("Arjan" not in ln for ln in dict(sections)["Arjan"]), str(sections))

    lead_sections = render_comparison_sections(per_area, "lead")
    lead_lines = dict(lead_sections)["Arjan"]
    check("J14 LEAD bullets under a sub-header read as whole phrases, "
          "not sentences beginning mid-clause (the 'is currently trading' bug)",
          not any(ln[0].islower() for ln in lead_lines), str(lead_lines))
    check("J15 price/sqft is not double-united ('AED 1,568/sqft per square foot')",
          not any("/sqft per square" in ln for ln in lead_lines), str(lead_lines))


# ── K. source trust tiers ─────────────────────────────────────

def run_tier_checks() -> None:
    print("\n== K. source trust tiers ==")
    import logging

    check("K1 DLD is 🟢 verified", tier_of("dubailand.gov.ae") == TIER_VERIFIED)
    check("K2 DXBinteract is 🟢 verified", tier_of("dxbinteract.com") == TIER_VERIFIED)
    check("K3 any other UAE government host is 🟢 verified, and allowed",
          tier_of("rera.gov.ae") == TIER_VERIFIED
          and on_allowlist("https://www.rera.gov.ae/x"))
    for d in ("propertyfinder.ae", "bayut.com", "dubizzle.com", "engelvoelkers.com"):
        check(f"K4 {d} is 🟡 market data", tier_of(d) == TIER_MARKET)
    for d in ("gulfnews.com", "khaleejtimes.com", "arabianbusiness.com", "thenational.ae"):
        check(f"K5 {d} is 🔴 news/opinion", tier_of(d) == TIER_NEWS)
    check("K6 subdomains and www. inherit their parent's tier",
          tier_of("www.gulfnews.com") == TIER_NEWS
          and tier_of("blog.propertyfinder.ae") == TIER_MARKET)
    check("K7 every allowlisted domain has a tier — the allowlist IS the tier map",
          set(REPUTABLE_DOMAINS) == set(DOMAIN_TIERS)
          and set(DOMAIN_TIERS.values()) <= set(TIER_EMOJI), str(set(DOMAIN_TIERS.values())))
    check("K8 no social platform crept in via the tier map",
          not any(d in DOMAIN_TIERS for d in ("instagram.com", "linkedin.com", "facebook.com")))

    # Unknown domain: 🟡 fallback, never a crash, and a warning is logged.
    records: list[logging.LogRecord] = []

    class _Grab(logging.Handler):
        def emit(self, record):
            records.append(record)

    lg = logging.getLogger("app.services.broker_intel.search")
    grab = _Grab(level=logging.WARNING)
    lg.addHandler(grab)
    try:
        tier = tier_of("some-new-portal.ae")
    finally:
        lg.removeHandler(grab)
    check("K9 an uncategorised domain falls back to 🟡 market data",
          tier == TIER_MARKET and tier_emoji("some-new-portal.ae") == "🟡")
    check("K10 ...and logs a warning naming it, so it gets categorised",
          any("some-new-portal.ae" in r.getMessage() for r in records),
          str([r.getMessage() for r in records]))

    # The Sources line format, exactly as specified.
    body = formatter.render_lead_intel(
        "Arjan", ["Price/sqft: AED 1,500 [1][2][8]"], "self",
        [(1, src("propertyfinder.ae")), (2, src("dubailand.gov.ae")), (8, src("gulfnews.com"))],
    )
    check("K11 Sources line shows each source's tier emoji",
          "Sources: [1] 🟡 propertyfinder.ae  [2] 🟢 dubailand.gov.ae  [8] 🔴 gulfnews.com" in body,
          body)
    check("K12 SOURCED_CAVEAT carries the legend for all three tiers",
          all(s in formatter.SOURCED_CAVEAT
              for s in ("🟢 official", "🟡 market data", "🔴 news/opinion")))
    check("K13 ...and still says anything not 🟢 is not official DLD data",
          "not 🟢 is not official DLD data" in formatter.SOURCED_CAVEAT)


# ── L. the daily brief's honesty rules ────────────────────────

async def run_daily_brief_checks() -> None:
    print("\n== L. daily brief: drop-if-nothing, scope, numbering, idea ==")
    from datetime import date

    day = date(2026, 9, 18)
    area = briefing.area_for(day)
    nxt = briefing.DAILY_AREAS[(briefing.DAILY_AREAS.index(area) + 1) % len(briefing.DAILY_AREAS)]

    class Gen:
        def __init__(self, idea):
            self.idea, self.topics = idea, []

        async def post_idea(self, topic):
            self.topics.append(topic)
            return self.idea

    news = [SourceResult(url="https://gulfnews.com/a", domain="gulfnews.com",
                         title="Dubai rents cool in prime areas | Gulf News", content="",
                         published_date="Wed, 17 Sep 2026 08:00:00 GMT")]

    # Nothing sourced anywhere -> None (handler falls back to the offer),
    # and no idea is even asked for.
    gen = Gen("Talk about the market.")
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({}), extractor=StubExtractionProvider(claims=[]),
        generator=gen, today=day)
    check("L1 nothing sourced found -> no brief at all (None), not an idea alone",
          r is None and gen.topics == [], repr(r))

    # News only: brief without a data section; not fabricated.
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({}, news=news), extractor=StubExtractionProvider(claims=[]),
        generator=Gen("Ask followers where they would rent next."), today=day)
    check("L2 news but no data -> brief with news, and NO data section",
          r is not None and "🔥 Top news" in r and "📊" not in r, r)
    check("L3 the headline is verbatim with the ' | Gulf News' suffix trimmed",
          r is not None and "Dubai rents cool in prime areas [1]" in r
          and "| Gulf News" not in r, r)

    # Data only, and scope isolation: a citywide claim for today's area is
    # dropped, so a data point only appears from an area-scoped claim.
    citywide_only = StubExtractionProvider(claims=lambda s, srcs: [
        Claim("price_per_sqft", "citywide", 1700, "", "", 1)])
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({area: [src("bayut.com")], nxt: [src("bayut.com")]}),
        extractor=citywide_only, generator=Gen("x"), today=day)
    check("L4 a Dubai-wide figure never becomes an area's data point",
          r is None, repr(r))

    # Today's area has nothing; the next area in the rotation is tried.
    second = StubExtractionProvider(claims=lambda s, srcs: [
        Claim("rental_yield_pct", s, 7.2, "", "", 1)] if s == nxt else [])
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({area: [src("bayut.com")], nxt: [src("propertyfinder.ae")]}),
        extractor=second, generator=Gen("Break down what landlords earn here."), today=day)
    check("L5 an empty day's area falls through to the next area in the rotation",
          r is not None and f"📊 Market data — {nxt}" in r and "7.2%" in r, r)
    check("L6 with no headline, the data point is [1] and cites its own source",
          r is not None and "[1] 🟡 propertyfinder.ae" in r and "[1]" in r.split("Sources:")[0], r)

    # Mixed units: the data point is one metric, chosen by priority.
    mixed = StubExtractionProvider(claims=lambda s, srcs: [
        Claim("total_price", s, 1_000_000, "", "", 1),
        Claim("price_per_sqft", s, 1_564, "", "", 1),
        Claim("yoy_change_pct", s, 9.5, "", "", 2)])
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({area: [src("bayut.com"), src("dubailand.gov.ae")]}, news=news),
        extractor=mixed, generator=Gen("x"), today=day)
    data_line = next((ln for ln in (r or "").splitlines() if ln.startswith("• ") and "%" in ln), "")
    check("L7 the data point prefers price movement, and is a single metric",
          "YoY change: 9.5% [3]" in data_line and "1,564" not in (r or "")
          and "1,000,000" not in (r or ""), r)
    check("L8 area sources are numbered after the headline, each with its tier",
          r is not None and "[1] 🔴 gulfnews.com" in r and "[3] 🟢 dubailand.gov.ae" in r
          and "bayut.com" not in r, r)

    # The post idea: dropped, never edited, if it smuggles in a figure.
    for bad in ("Explain why JVC rents rose 12% this year.", "", None,
                " ".join(["word"] * 40)):
        r = await briefing.build_daily_brief(
            search=StubSearchProvider({}, news=news), extractor=StubExtractionProvider(claims=[]),
            generator=Gen(bad), today=day)
        check(f"L9 an unusable idea ({(bad or 'empty')[:25]!r}) is dropped, brief still sent",
              r is not None and "💡" not in r and "🔥 Top news" in r, r)
    gen = Gen('"Ask your followers: rent or buy in this market?"')
    r = await briefing.build_daily_brief(
        search=StubSearchProvider({}, news=news), extractor=StubExtractionProvider(claims=[]),
        generator=gen, today=day)
    check("L10 a clean idea is kept (quotes stripped) and seeded from the headline",
          r is not None and "• Ask your followers: rent or buy in this market? " not in r
          and "• Ask your followers: rent or buy in this market?" in r
          and gen.topics == ["Dubai rents cool in prime areas"], f"{gen.topics} {r}")

    # Headline picking and cleaning.
    old = SourceResult(url="https://gulfnews.com/o", domain="gulfnews.com",
                       title="Old story", content="", published_date="2026-08-01")
    fresh = SourceResult(url="https://khaleejtimes.com/f", domain="khaleejtimes.com",
                         title="Fresh story - Khaleej Times", content="",
                         published_date="2026-09-17T09:00:00Z")
    check("L11 a fresh headline beats a higher-ranked stale one",
          briefing.pick_headline([old, fresh], day) is fresh)
    check("L12 with nothing fresh, the top-ranked titled result is used",
          briefing.pick_headline([old], day) is old)
    check("L13 a dash that isn't the site name is left alone",
          briefing.clean_headline("Dubai Hills - a decade on", "gulfnews.com")
          == "Dubai Hills - a decade on")
    check("L14 the rotation moves day to day",
          briefing.area_for(day) != briefing.area_for(date(2026, 9, 19)))


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
    run_substance_checks()
    await run_briefing_checks()
    run_tier_checks()
    await run_daily_brief_checks()

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
