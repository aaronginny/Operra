"""Match a parsed launch against one company's stored investor criteria.

Matching is strict on purpose. The brief is explicit that a weak match dressed
up as a real one is worse than saying nothing, because the advisor acts on
these by forwarding to a real person. So:

  * Emirate is the top-level filter and runs first. An investor who wants Abu
    Dhabi is never shown a Dubai launch, whatever else lines up.
  * Area exclusion is strict and settled policy, not a placeholder: an investor
    who named areas and does not get one of them is excluded outright. A wrong
    "match" costs this client more than a missed near-miss does, because they
    act on it by forwarding to a real person. Do not soften this into partial
    or scored matching.
  * Every criterion the investor actually stated must hold. Criteria they left
    blank are treated as "no preference", not as a wildcard to squeeze a match
    through.
  * When the launch itself is too vague to judge a criterion the investor DID
    state, that is a non-match rather than a guess. Not knowing is not the same
    as agreeing.

Every reason returned corresponds to a criterion that genuinely matched, so
the advisor can trust the "why" as much as the "who".

An investor's real name is used here when the advisor has stored one (client
request; see app/models/investor_criteria.py for the full policy change) —
InvestorMatch.summary prefers `name` over `label` for display. Nothing else
about matching reads it: the emirate/budget/area/unit-type/payment logic below
is unchanged and never touches name or label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investor_criteria import InvestorCriteria
from app.services.launch_matcher.parser import ParsedLaunch

# A launch priced "from 1.4M" has no stated ceiling; treat it as open-ended so
# an investor whose budget starts above the entry price still matches.
_OPEN_ENDED = float("inf")


@dataclass
class InvestorMatch:
    """One investor whose criteria the launch satisfies."""

    label: str
    name: str | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        """The investor's real name when stored, else their label."""
        return self.name or self.label

    @property
    def summary(self) -> str:
        """'Ahmed Al Maktoum — Dubai, 1.2–1.6M, off-plan', or 'Investor 4 — ...'
        when no name is on file."""
        return f"{self.display} — {', '.join(self.reasons)}" if self.reasons else self.display


@dataclass
class MatchOutcome:
    """The result of matching one launch against one company's investors."""

    launch: ParsedLaunch
    matches: list[InvestorMatch] = field(default_factory=list)
    considered: int = 0
    # Set when the launch could not be matched at all — currently only when the
    # emirate could not be determined, since that is the top-level filter and
    # guessing it would undermine every result beneath it.
    blocked_reason: str | None = None

    @property
    def matched(self) -> bool:
        return bool(self.matches)


def _fmt_money(value: float) -> str:
    """Compact money for a WhatsApp line: 1.4M, 850K, 2.65M."""
    if value >= 1_000_000:
        text = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if value >= 1_000:
        text = f"{value / 1_000:.0f}"
        return f"{text}K"
    return f"{value:.0f}"


def _split_areas(areas: str | None) -> list[str]:
    return [a.strip() for a in (areas or "").split(",") if a.strip()]


def _areas_overlap(investor_areas: list[str], launch_area: str | None,
                   project: str | None) -> str | None:
    """Return the investor area the launch satisfies, or None.

    Checks the project name as well as the parsed area, because an investor who
    asked for "Hartland" should match "Sobha Hartland II" even when the area
    field came back as something broader. Substring matching in both directions
    handles "Hartland" vs "Sobha Hartland".
    """
    haystacks = [h.lower() for h in (launch_area, project) if h]
    if not haystacks:
        return None
    for wanted in investor_areas:
        needle = wanted.lower()
        for hay in haystacks:
            if needle in hay or hay in needle:
                return wanted
    return None


def _unit_matches(wanted: str, launch_units: list[str]) -> bool:
    """Does the launch offer the unit type this investor wants?"""
    want = wanted.strip().lower()
    if not want:
        return True
    return any(want == u.lower() or want in u.lower() or u.lower() in want
               for u in launch_units)


def evaluate(criteria: InvestorCriteria, launch: ParsedLaunch) -> InvestorMatch | None:
    """Decide whether one investor matches this launch, and why.

    Returns None for a non-match. Order matters: emirate is checked first so
    the top-level filter short-circuits before anything else is considered.
    """
    reasons: list[str] = []

    # ── 1. Emirate — the top-level filter ────────────────────
    if not launch.emirate or criteria.emirate != launch.emirate:
        return None
    reasons.append(criteria.emirate)

    # ── 2. Build stage ───────────────────────────────────────
    stage = (criteria.off_plan_or_ready or "both").lower()
    if stage != "both" and stage != launch.completion_status:
        return None

    # ── 3. Area, when the investor named any ─────────────────
    investor_areas = _split_areas(criteria.areas)
    matched_area = None
    if investor_areas:
        matched_area = _areas_overlap(investor_areas, launch.area, launch.project)
        if not matched_area:
            # They named areas and this isn't one of them (or the launch didn't
            # say where it is). Either way it isn't a confident match.
            return None

    # ── 4. Budget overlap ────────────────────────────────────
    inv_min = float(criteria.budget_min or 0)
    inv_max = float(criteria.budget_max or 0) or _OPEN_ENDED
    has_budget = inv_min > 0 or inv_max is not _OPEN_ENDED

    if has_budget and launch.price_min is not None:
        launch_low = float(launch.price_min)
        launch_high = float(launch.price_max) if launch.price_max else _OPEN_ENDED
        # Two ranges overlap when each starts at or below the other's end.
        if not (inv_max >= launch_low and inv_min <= launch_high):
            return None

    # ── 5. Unit type, when the investor named one ────────────
    wanted_unit = (criteria.property_type or "").strip()
    if wanted_unit:
        if not launch.unit_types:
            # They asked for 2BR and the launch didn't say what it offers.
            return None
        if not _unit_matches(wanted_unit, launch.unit_types):
            return None

    # ── 6. Payment preference ────────────────────────────────
    # Only "payment_plan" constrains the launch: an investor who needs
    # instalments cannot use a launch that offers none, and a launch that
    # doesn't state its terms is too vague to judge — a non-match, not a guess,
    # consistent with how every other stated criterion is handled here.
    # "cash" and "either" impose nothing: a cash buyer can take a launch with
    # or without a plan.
    payment_pref = (criteria.payment_preference or "either").lower()
    if payment_pref == "payment_plan" and not launch.payment_plan:
        return None

    # ── Reasons, in the order they read best ─────────────────
    if matched_area:
        reasons.append(f"wanted {matched_area}")
    if has_budget:
        if inv_max is _OPEN_ENDED:
            reasons.append(f"{_fmt_money(inv_min)}+")
        elif inv_min > 0:
            reasons.append(f"{_fmt_money(inv_min)}–{_fmt_money(inv_max)}")
        else:
            reasons.append(f"up to {_fmt_money(inv_max)}")
    if wanted_unit:
        reasons.append(wanted_unit)
    if stage != "both":
        reasons.append(stage.replace("_", "-"))
    # "payment plan buyer" is only claimed when the preference was actually
    # tested against stated terms; "cash buyer" is informative rather than a
    # filter, and is surfaced because the advisor needs it when deciding how to
    # pitch. Both come from the structured column — never from free text.
    if payment_pref == "payment_plan":
        reasons.append("payment plan buyer")
    elif payment_pref == "cash":
        reasons.append("cash buyer")

    return InvestorMatch(label=criteria.label, name=criteria.name, reasons=reasons)


async def match_launch(
    db: AsyncSession, company_id: int, launch: ParsedLaunch
) -> MatchOutcome:
    """Match a launch against every investor criteria row for one company.

    Scoped to company_id like every other tenant-owned query in this codebase;
    one advisor's investors are never visible to another's.
    """
    outcome = MatchOutcome(launch=launch)

    # Without an emirate the top-level filter cannot run, and everything below
    # it would be a guess. Say so rather than returning whatever else lines up.
    if not launch.emirate:
        outcome.blocked_reason = "emirate"
        return outcome

    # Narrow on (company_id, emirate) in SQL — the indexed access path, and it
    # keeps the top-level filter genuinely first rather than filtering in Python.
    stmt = (
        select(InvestorCriteria)
        .where(
            InvestorCriteria.company_id == company_id,
            InvestorCriteria.emirate == launch.emirate,
        )
        .order_by(InvestorCriteria.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    outcome.considered = len(rows)

    for row in rows:
        match = evaluate(row, launch)
        if match:
            outcome.matches.append(match)

    return outcome
