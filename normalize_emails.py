"""One-off data migration: normalize every User.email to lowercase.

Fixes the case-sensitivity auth bug. Signup used to store whatever casing the
user typed, but Postgres text equality is case-sensitive — so a later login
typed with different casing (e.g. mobile auto-capitalization) missed the row,
while a retry signup with the original casing still matched and was blocked.

SAFE BY DEFAULT — this runs as a DRY RUN and only reports. Pass --apply to
write. It never merges or deletes: if two rows would collide once lowercased
(e.g. "Lenin@x.com" and "lenin@x.com" both exist), it flags both and changes
NEITHER, leaving that decision to a human.

Order of operations for a DB that might contain case-variant duplicates:
    1. python normalize_emails.py            # dry run — see what would change
    2. resolve any flagged collisions by hand (pick which row survives)
    3. python normalize_emails.py --apply     # lowercase rows + create the
                                              #   ux_users_email_lower index

Usage (from the repo root, with the app venv active):
    python normalize_emails.py                     # dry run, report only
    python normalize_emails.py --apply             # commit the changes
    python normalize_emails.py --highlight lenin   # spotlight one customer

Runs against whatever DATABASE_URL points at (SQLite dev / Postgres prod).
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

RULE = "-" * 64


def _norm(email: str) -> str:
    """Match the app's canonical form (auth_routes._normalize_email)."""
    return email.strip().lower()


async def main(apply: bool, highlight: str) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    print(f"DB dialect : {engine.dialect.name}")
    print(f"Mode       : {'APPLY (writing changes)' if apply else 'DRY RUN (no changes)'}")
    print(RULE)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT id, name, email FROM users WHERE email IS NOT NULL")
            )
        ).all()

    # Group every row by its normalized email. Any group with 2+ members is a
    # case-collision cluster — the whole point of grouping is that a size-1
    # group's normalized value is unique across the table, so lowercasing it
    # can never create a duplicate.
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(_norm(r.email), []).append(r)

    collisions = {k: v for k, v in groups.items() if len(v) > 1}
    to_change = [
        r
        for k, members in groups.items()
        if len(members) == 1
        for r in members
        if r.email != k
    ]

    print(f"Users with an email      : {len(rows)}")
    print(f"Rows needing lowercasing : {len(to_change)}")
    print(f"Case-collision clusters  : {len(collisions)}")
    print(RULE)

    if collisions:
        print("!!  COLLISIONS — 2+ rows map to the same lowercased email.")
        print("    These are NOT changed. Resolve by hand, then re-run:")
        for norm_email, members in collisions.items():
            print(f"\n  -> all collapse to {norm_email!r}:")
            for m in members:
                print(f"       id={m.id}  name={m.name!r}  email={m.email!r}")
        print(RULE)

    if to_change:
        print("Rows that will be lowercased (old -> new):")
        for r in to_change:
            print(f"  id={r.id}  {r.email!r} -> {_norm(r.email)!r}")
        print(RULE)

    # Spotlight one customer (default: lenin) so their corrected value is
    # unambiguous in the output.
    hl = highlight.lower()
    matches = [
        r for r in rows
        if hl in (r.email or "").lower() or hl in (r.name or "").lower()
    ]
    if matches:
        print(f"Spotlight — rows matching {highlight!r}:")
        for r in matches:
            new = _norm(r.email)
            if len(groups[new]) > 1:
                tail = "   [IN A COLLISION — unchanged, see above]"
            elif new == r.email:
                tail = "   [already normalized — no change]"
            else:
                tail = ""
            arrow = f"{r.email!r} -> {new!r}" if new != r.email else f"{r.email!r}"
            print(f"  id={r.id}  name={r.name!r}  email {arrow}{tail}")
        print(RULE)
    else:
        print(f"Spotlight — no rows matched {highlight!r}.")
        print(RULE)

    if not apply:
        print("DRY RUN — nothing written. Re-run with --apply to commit.")
        await engine.dispose()
        return

    # ---- APPLY ------------------------------------------------------------
    if to_change:
        async with engine.begin() as conn:
            for r in to_change:
                await conn.execute(
                    text("UPDATE users SET email = :new WHERE id = :id"),
                    {"new": _norm(r.email), "id": r.id},
                )
        print(f"OK: lowercased {len(to_change)} row(s).")
    else:
        print("OK: no rows needed lowercasing.")

    # Create the case-insensitive unique index — only once the data is clean.
    if collisions:
        print(
            "SKIP: not creating ux_users_email_lower while collisions remain. "
            "Resolve them and re-run."
        )
    else:
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower "
                        "ON users (lower(email))"
                    )
                )
            print("OK: ensured case-insensitive unique index ux_users_email_lower.")
        except Exception as exc:  # noqa: BLE001 — report, don't crash
            print(f"WARN: could not create unique index: {exc}")

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize User.email to lowercase (safe, dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write changes (default: dry run, report only)",
    )
    parser.add_argument(
        "--highlight",
        default="lenin",
        help="spotlight rows whose email/name contains this substring (default: lenin)",
    )
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply, highlight=args.highlight))
