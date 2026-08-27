"""One-off production account provisioning — run in Render's shell, then delete.

Creates two accounts directly in the database, bypassing the public signup flow:

  1. An admin account, whose email you should make match FOUNDER_EMAIL so the
     billing/trial founder bypass recognises it (see the note below).
  2. A client account with company.vertical = 'launch_matcher', which no API
     endpoint can set — signup always creates 'generic'.

Passwords are generated here with `secrets` and printed once to stdout. They are
never written to disk. Capture them from the shell output before you close it —
they are bcrypt-hashed into the database and cannot be recovered afterwards.

SAFETY
------
This runs against the live database, so it is written to be safe to run twice:

  * It never creates a user whose email already exists — it reports and skips.
  * It never modifies or deletes an existing row, with one deliberate
    exception: if the launch-matcher company exists but its vertical is wrong,
    it fixes that one column and says so.
  * Everything happens in a single transaction. Any error rolls the whole thing
    back, so a half-created account is not a possible outcome.
  * It prints what it is about to do, and what it did, in full.

USAGE
-----
    python create_accounts.py --admin-email you@example.com \\
                             --mahmoud-email mahmoud@example.com

Optional: --admin-name, --mahmoud-name, --admin-company, --mahmoud-company,
          --admin-phone, --mahmoud-phone   (phones are optional; see note)
          --dry-run   show what would happen, write nothing
"""

import argparse
import asyncio
import secrets
import string
import sys

# Import the application's own modules so hashing, models and the database URL
# all come from the running service's configuration — not a reimplementation.
from sqlalchemy import select

from app.database import async_session
from app.models.company import Company
from app.models.user import User, UserRole
from app.services.auth_service import get_password_hash

PASSWORD_LENGTH = 20
# Ambiguous characters removed: a password that gets read aloud or retyped
# shouldn't hinge on telling l from 1 or O from 0.
ALPHABET = (
    "".join(c for c in string.ascii_letters + string.digits if c not in "lIO01")
    + "!@#$%^&*-_=+"
)


def generate_password() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(PASSWORD_LENGTH))


def normalize_email(email: str) -> str:
    """Match what auth_routes does, so login finds the row we create."""
    return email.strip().lower()


def normalize_phone(number: str | None) -> str | None:
    if not number:
        return None
    cleaned = "".join(ch for ch in number if ch.isdigit() or ch == "+").strip()
    if cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned or None


async def provision(
    db,
    *,
    company_name: str,
    vertical: str,
    user_name: str,
    email: str,
    phone: str | None,
    dry_run: bool,
) -> dict:
    """Create one company + one CEO user, or report why it was skipped."""
    email = normalize_email(email)
    phone = normalize_phone(phone)

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalars().first()
    if existing:
        company = await db.get(Company, existing.company_id)
        note = ""
        # The one mutation this script will make to pre-existing data, because
        # a launch_matcher account with the wrong vertical is silently broken.
        if company and vertical != "generic" and company.vertical != vertical:
            if dry_run:
                note = (
                    f" WOULD FIX vertical: {company.vertical!r} -> {vertical!r}"
                )
            else:
                old = company.vertical
                company.vertical = vertical
                note = f" FIXED vertical: {old!r} -> {vertical!r}"
        return {
            "status": "exists",
            "email": email,
            "password": None,
            "company_id": existing.company_id,
            "company_name": company.name if company else "?",
            "vertical": company.vertical if company else "?",
            "user_id": existing.id,
            "note": note,
        }

    password = generate_password()

    if dry_run:
        return {
            "status": "would_create",
            "email": email,
            "password": password,
            "company_id": None,
            "company_name": company_name,
            "vertical": vertical,
            "user_id": None,
            "note": "",
        }

    company = Company(name=company_name, vertical=vertical)
    db.add(company)
    await db.flush()  # assigns company.id

    user = User(
        company_id=company.id,
        name=user_name,
        email=email,
        password_hash=get_password_hash(password),
        role=UserRole.ceo,
        whatsapp_number=phone,
        is_verified=True,  # no OTP step exists any more; unverified can't log in
    )
    db.add(user)
    await db.flush()

    return {
        "status": "created",
        "email": email,
        "password": password,
        "company_id": company.id,
        "company_name": company.name,
        "vertical": company.vertical,
        "user_id": user.id,
        "note": "",
    }


def report(title: str, r: dict) -> None:
    print(f"\n=== {title} ===")
    print(f"  status       : {r['status']}{r['note']}")
    print(f"  company      : {r['company_name']} (id={r['company_id']})")
    print(f"  vertical     : {r['vertical']}")
    print(f"  user_id      : {r['user_id']}")
    print(f"  LOGIN EMAIL  : {r['email']}")
    if r["password"]:
        print(f"  LOGIN PASSWORD: {r['password']}")
    else:
        print("  LOGIN PASSWORD: (unchanged — account already existed, "
              "password not reset)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    # Defaults are the real addresses for this provisioning run. The admin email
    # MUST stay equal to FOUNDER_EMAIL in Render (currently
    # aaronginnycodes@gmail.com) — that env-var match is the only thing that
    # grants the billing/trial founder bypass. Comparison is case-insensitive on
    # both sides, so the stored lowercase form still matches.
    ap.add_argument("--admin-email", default="aaronginnycodes@gmail.com",
                    help="must match FOUNDER_EMAIL in Render for founder bypass")
    ap.add_argument("--mahmoud-email", default="Mahmoudmousa291@gmail.com")
    ap.add_argument("--admin-name", default="Aaron")
    ap.add_argument("--mahmoud-name", default="Mahmoud")
    ap.add_argument("--admin-company", default="PhantomPilot HQ")
    ap.add_argument("--mahmoud-company", default="Mahmoud Advisory")
    ap.add_argument("--admin-phone", default=None,
                    help="optional; matching FOUNDER_PHONE also grants bypass")
    ap.add_argument("--mahmoud-phone", default=None,
                    help="optional, but required later for the WhatsApp flow — "
                         "the launch matcher resolves his tenant by this number")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 68)
    print("  PhantomPilot — production account provisioning")
    if args.dry_run:
        print("  DRY RUN — nothing will be written")
    print("=" * 68)

    # Founder bypass is an env-var identity match evaluated per request, not a
    # database flag — so creating the row proves nothing on its own. Check the
    # match here, on the server, where FOUNDER_EMAIL is actually readable.
    from app.config import settings

    founder_email = (settings.founder_email or "").strip().lower()
    admin_email = normalize_email(args.admin_email)
    print("\n-- founder bypass --")
    if not founder_email:
        print("  FOUNDER_EMAIL is NOT SET in this environment.")
        print("  -> the admin account will have NO founder bypass until it is set.")
    elif founder_email == admin_email:
        print(f"  FOUNDER_EMAIL matches the admin email ({admin_email})")
        print("  -> founder bypass WILL apply to this account.")
    else:
        print(f"  MISMATCH: FOUNDER_EMAIL is {founder_email!r}")
        print(f"            admin email is  {admin_email!r}")
        print("  -> founder bypass will NOT apply. Fix one of them to match.")

    # One transaction for both accounts: a failure leaves nothing behind.
    async with async_session() as db:
        try:
            admin = await provision(
                db,
                company_name=args.admin_company,
                vertical="generic",
                user_name=args.admin_name,
                email=args.admin_email,
                phone=args.admin_phone,
                dry_run=args.dry_run,
            )
            mahmoud = await provision(
                db,
                company_name=args.mahmoud_company,
                vertical="launch_matcher",
                user_name=args.mahmoud_name,
                email=args.mahmoud_email,
                phone=args.mahmoud_phone,
                dry_run=args.dry_run,
            )

            if args.dry_run:
                await db.rollback()
                print("\n(dry run — rolled back, nothing written)")
            else:
                await db.commit()
        except Exception:
            await db.rollback()
            print("\nERROR — rolled back, no accounts were created.")
            raise

    report("ADMIN ACCOUNT (yours)", admin)
    report("MAHMOUD'S ACCOUNT (launch_matcher)", mahmoud)

    print("\n" + "=" * 68)
    print("  CAPTURE THE PASSWORDS ABOVE NOW — they are bcrypt-hashed in the")
    print("  database and cannot be recovered once this output is gone.")
    print("=" * 68)

    if mahmoud["vertical"] != "launch_matcher":
        print("\nWARNING: Mahmoud's vertical is not 'launch_matcher'. The launch")
        print("matcher routes will 404 for him until that column is corrected.")

    if not args.dry_run:
        print("\nReminder: delete this script from the server when you are done.")


if __name__ == "__main__":
    asyncio.run(main())
