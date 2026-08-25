"""Turn a match outcome into the WhatsApp reply body.

Written for a phone screen: short lines, no markdown tables, no wide columns.
The header restates what we understood from the launch so the advisor can spot
a misparse immediately rather than trusting a wrong match.

When nothing matches, the reply says so plainly. It never pads the list with
near-misses — the advisor acts on this by forwarding to a real person, so a
false positive costs them credibility.

Only investor labels appear here. No names, phones, or emails, by construction:
the matcher has none to give.
"""

from __future__ import annotations

from app.services.launch_matcher.matcher import MatchOutcome, _fmt_money


def _launch_detail_line(outcome: MatchOutcome) -> str:
    """'1BR from 1.4M · 60/40 · EOI Thursday' — whatever we actually read."""
    launch = outcome.launch
    parts: list[str] = []

    units = ", ".join(launch.unit_types[:4]) if launch.unit_types else ""
    if launch.price_min is not None:
        if launch.price_max:
            price = f"{_fmt_money(launch.price_min)}–{_fmt_money(launch.price_max)}"
        else:
            price = f"from {_fmt_money(launch.price_min)}"
        parts.append(f"{units} {price}".strip())
    elif units:
        parts.append(units)

    if launch.payment_plan:
        parts.append(launch.payment_plan)
    if launch.launch_date:
        parts.append(f"EOI {launch.launch_date}")

    return " · ".join(parts)


def format_reply(outcome: MatchOutcome) -> str:
    """Build the full reply text for a parsed-and-matched launch."""
    launch = outcome.launch

    # Emirate unreadable — the top-level filter can't run, so we ask instead of
    # guessing. Asking costs one message; a wrong emirate costs a bad forward.
    if outcome.blocked_reason == "emirate":
        name = launch.project or launch.developer
        subject = f'"{name}"' if name else "that message"
        return (
            f"I couldn't tell which emirate {subject} is in, so I haven't "
            f"matched it.\n\n"
            f"Reply with the emirate (Dubai, Abu Dhabi, RAK…) and forward it "
            f"again."
        )

    header = launch.headline
    detail = _launch_detail_line(outcome)
    lines = [header]
    if detail:
        lines.append(detail)

    if not outcome.matched:
        lines.append("")
        if outcome.considered == 0:
            lines.append(
                f"No investors on file for {launch.emirate} yet — nothing to match against."
            )
        else:
            plural = "investor" if outcome.considered == 1 else "investors"
            lines.append(
                f"No matches. Checked {outcome.considered} {launch.emirate} "
                f"{plural}; none fit on budget, area or unit type."
            )
        return "\n".join(lines)

    count = len(outcome.matches)
    lines.append("")
    lines.append(f"Matches {count} investor{'' if count == 1 else 's'}:")
    for match in outcome.matches:
        lines.append(f"- {match.summary}")

    return "\n".join(lines)
