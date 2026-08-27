"""TEMPORARY one-off account provisioning endpoint. DELETE AFTER USE.

Exists only because Render's shell is gated behind a paid plan, so the
equivalent script (create_accounts.py) cannot be run on the server. This
does the same work over HTTP, guarded by a shared secret.

REMOVAL (do this immediately after the accounts are created):
  1. delete this file
  2. remove the two `internal_provision` lines from app/main.py
  3. remove `provision_secret` from app/config.py
  4. delete PROVISION_SECRET from the Render environment
  5. redeploy

WHY IT IS BUILT THE WAY IT IS
-----------------------------
An endpoint that mints accounts — including one that receives the founder
bypass — is the most dangerous surface in this codebase while it exists. So:

  * It FAILS CLOSED. With PROVISION_SECRET unset or too short, every request
    is refused. A deploy that forgets the env var leaves the route inert
    rather than wide open, which is the failure mode that actually matters.
  * The secret is compared with secrets.compare_digest, not ==, so response
    timing does not leak how much of a guess was correct.
  * The secret travels in a header on a POST, never in the URL. Query strings
    end up in access logs, proxy logs and browser history; headers on a POST
    do not. This is why it cannot be triggered by pasting a URL in a browser.
  * It is hidden from the OpenAPI schema, so it is not advertised at /docs.
  * It is idempotent: an existing email is reported and skipped, never
    overwritten, and no password is ever reset.
  * Neither the secret nor any generated password is logged. They appear only
    in the HTTP response body, once.
"""

import logging
import secrets
import string

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.company import Company
from app.models.user import User, UserRole
from app.services.auth_service import get_password_hash

logger = logging.getLogger(__name__)

# No prefix collision with anything real; hidden from the schema regardless.
router = APIRouter(prefix="/internal", tags=["Internal"])

# A short secret is worse than no secret, because it invites guessing at an
# endpoint that creates privileged accounts.
MIN_SECRET_LENGTH = 32

PASSWORD_LENGTH = 20
# Ambiguous glyphs removed: these get read aloud and retyped.
ALPHABET = (
    "".join(c for c in string.ascii_letters + string.digits if c not in "lIO01")
    + "!@#$%^&*-_=+"
)


def _generate_password() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(PASSWORD_LENGTH))


def _normalize_email(email: str) -> str:
    """Match auth_routes._normalize_email so login finds the row we create."""
    return email.strip().lower()


def _normalize_phone(number: str | None) -> str | None:
    if not number:
        return None
    cleaned = "".join(ch for ch in number if ch.isdigit() or ch == "+").strip()
    if cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned or None


def _authorize(provided: str | None) -> None:
    """Refuse unless the caller presents the configured secret.

    Fails closed on a missing or weak configured secret — that ordering
    matters, because the dangerous case is a deploy where PROVISION_SECRET
    was never set.
    """
    configured = (settings.provision_secret or "").strip()

    if not configured:
        logger.warning("provision endpoint called but PROVISION_SECRET is not set")
        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    if len(configured) < MIN_SECRET_LENGTH:
        logger.error(
            "provision endpoint refused: PROVISION_SECRET is shorter than %d chars",
            MIN_SECRET_LENGTH,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"PROVISION_SECRET must be at least {MIN_SECRET_LENGTH} characters. "
                "Set a longer one and redeploy."
            ),
        )

    if not provided or not secrets.compare_digest(provided.strip(), configured):
        logger.warning("provision endpoint: bad or missing secret")
        raise HTTPException(status_code=401, detail="Unauthorized")


class ProvisionRequest(BaseModel):
    admin_email: str = "aaronginnycodes@gmail.com"
    mahmoud_email: str = "Mahmoudmousa291@gmail.com"
    admin_name: str = "Aaron"
    mahmoud_name: str = "Mahmoud"
    admin_company: str = "PhantomPilot HQ"
    mahmoud_company: str = "Mahmoud Advisory"
    admin_phone: str | None = None
    # Optional here, but the launch matcher resolves Mahmoud's tenant by phone
    # on inbound WhatsApp, so his account is not usable end-to-end without it.
    mahmoud_phone: str | None = None
    dry_run: bool = False


async def _provision(
    db,
    *,
    company_name: str,
    vertical: str,
    user_name: str,
    email: str,
    phone: str | None,
    dry_run: bool,
) -> dict:
    """Create one company + CEO user, or report why it was skipped."""
    email = _normalize_email(email)
    phone = _normalize_phone(phone)

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalars().first()
    if existing:
        company = await db.get(Company, existing.company_id)
        note = ""
        # The only mutation to pre-existing data: a launch_matcher company
        # sitting on the wrong vertical is silently broken, so fix that column.
        if company and vertical != "generic" and company.vertical != vertical:
            if dry_run:
                note = f" WOULD FIX vertical: {company.vertical!r} -> {vertical!r}"
            else:
                old = company.vertical
                company.vertical = vertical
                note = f" FIXED vertical: {old!r} -> {vertical!r}"
        return {
            "status": "exists",
            "email": email,
            "password": None,
            "company_id": existing.company_id,
            "company_name": company.name if company else None,
            "vertical": company.vertical if company else None,
            "user_id": existing.id,
            "note": note or "account already existed; password NOT reset",
        }

    password = _generate_password()

    if dry_run:
        return {
            "status": "would_create",
            "email": email,
            "password": password,
            "company_id": None,
            "company_name": company_name,
            "vertical": vertical,
            "user_id": None,
            "note": "dry run — nothing written",
        }

    company = Company(name=company_name, vertical=vertical)
    db.add(company)
    await db.flush()

    user = User(
        company_id=company.id,
        name=user_name,
        email=email,
        password_hash=get_password_hash(password),
        role=UserRole.ceo,
        whatsapp_number=phone,
        is_verified=True,  # no OTP step exists; unverified accounts can't log in
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


@router.post("/provision-accounts", include_in_schema=False)
async def provision_accounts(
    payload: ProvisionRequest,
    x_provision_secret: str | None = Header(default=None, alias="X-Provision-Secret"),
):
    """Create the admin and launch-matcher accounts. One-time use."""
    _authorize(x_provision_secret)

    founder_email = (settings.founder_email or "").strip().lower()
    admin_email = _normalize_email(payload.admin_email)

    # Founder bypass is an env-var identity match evaluated per request, not a
    # column — so creating the row proves nothing. Report the match from here,
    # where FOUNDER_EMAIL is actually readable.
    if not founder_email:
        founder_status = ("FOUNDER_EMAIL is NOT SET — the admin account will "
                          "have no founder bypass until it is.")
    elif founder_email == admin_email:
        founder_status = (f"FOUNDER_EMAIL matches admin email ({admin_email}) "
                          "— founder bypass WILL apply.")
    else:
        founder_status = (f"MISMATCH: FOUNDER_EMAIL is {founder_email!r} but admin "
                          f"email is {admin_email!r} — bypass will NOT apply.")

    # One transaction for both accounts: a failure leaves nothing behind.
    async with async_session() as db:
        try:
            admin = await _provision(
                db,
                company_name=payload.admin_company,
                vertical="generic",
                user_name=payload.admin_name,
                email=payload.admin_email,
                phone=payload.admin_phone,
                dry_run=payload.dry_run,
            )
            mahmoud = await _provision(
                db,
                company_name=payload.mahmoud_company,
                vertical="launch_matcher",
                user_name=payload.mahmoud_name,
                email=payload.mahmoud_email,
                phone=payload.mahmoud_phone,
                dry_run=payload.dry_run,
            )
            if payload.dry_run:
                await db.rollback()
            else:
                await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("provisioning failed; rolled back")
            raise HTTPException(
                status_code=500,
                detail="Provisioning failed and was rolled back. No accounts created.",
            )

    # Logged by status only — never the passwords.
    logger.info(
        "provisioning run: admin=%s mahmoud=%s dry_run=%s",
        admin["status"], mahmoud["status"], payload.dry_run,
    )

    warnings = []
    if mahmoud["vertical"] and mahmoud["vertical"] != "launch_matcher":
        warnings.append(
            "Mahmoud's vertical is not 'launch_matcher' — the launch matcher "
            "routes will 404 for him."
        )
    if not _normalize_phone(payload.mahmoud_phone) and mahmoud["status"] == "created":
        warnings.append(
            "No mahmoud_phone was supplied. The launch matcher resolves his "
            "tenant by phone number on inbound WhatsApp, so forwarding a launch "
            "will not reach his account until it is set."
        )

    return {
        "dry_run": payload.dry_run,
        "founder_bypass": founder_status,
        "admin": admin,
        "mahmoud": mahmoud,
        "warnings": warnings,
        "capture_now": (
            "Copy the passwords from this response now — they are bcrypt-hashed "
            "in the database and cannot be recovered."
        ),
        "next_step": (
            "Delete app/routes/internal_provision.py, its two lines in "
            "app/main.py, provision_secret from app/config.py, and the "
            "PROVISION_SECRET env var in Render. Then redeploy."
        ),
    }
