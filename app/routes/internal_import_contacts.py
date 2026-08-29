"""TEMPORARY — one-time contact_lookup import for Mahmoud's production account.

Same hardening pattern as the earlier, now-removed /internal/provision-
accounts endpoint (see git history: 94e00d7, 2cf84bc): a shared-secret
header checked with a constant-time comparison, fails closed as a 404 (not
401/403) so a wrong or missing secret looks identical to the route not
existing at all, and hidden from the OpenAPI schema for the same reason.

This exists because Render's free tier has no Shell access, so there's no
way to run import_contact_lookup.py directly against production — this
endpoint is the same script's logic, reachable over plain HTTPS instead.

DO NOT leave this in the codebase permanently. Once the real import is done:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
  3. Remove `import_secret` from app/config.py.
  4. Delete the IMPORT_SECRET env var from Render.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.services.launch_matcher.contact_lookup_importer import (
    import_contact_lookup,
    parse_contacts_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _check_secret(provided: str | None) -> None:
    # Both sides are stripped: pasting a value into a hosting provider's env
    # var field routinely picks up a trailing newline or space, which would
    # otherwise fail compare_digest against a byte-identical-looking secret.
    expected = (settings.import_secret or "").strip()
    supplied = (provided or "").strip()
    # Same failure for "not configured", "no header sent", and "wrong
    # value" -- a 404, indistinguishable from the route not existing.
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=404)


@router.get("/import-secret-diag")
async def import_secret_diag(x_import_secret: str | None = Header(default=None)):
    """TEMPORARY diagnostic — deleted with the rest of this file.

    Reports only lengths and truncated SHA-256 fingerprints, never any secret
    value, so a mismatch between the env var and the caller's header can be
    identified without either being exposed. Unauthenticated on purpose: the
    thing being diagnosed is precisely whether the secret check can pass, so
    gating this on that same check would make it useless.
    """
    configured = (settings.import_secret or "").strip()
    supplied = (x_import_secret or "").strip()

    def fingerprint(value: str) -> str | None:
        return hashlib.sha256(value.encode()).hexdigest()[:12] if value else None

    return {
        "configured": bool(configured),
        "configured_len": len(configured),
        "configured_fp": fingerprint(configured),
        "raw_configured_len": len(settings.import_secret or ""),
        "received": bool(supplied),
        "received_len": len(supplied),
        "received_fp": fingerprint(supplied),
        "match": bool(configured) and configured == supplied,
    }


@router.post("/import-contacts")
async def import_contacts_endpoint(
    company_id: int = Form(...),
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
    x_import_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    _check_secret(x_import_secret)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    is_csv = (file.filename or "").lower().endswith(".csv")
    contacts = parse_contacts_text(text, is_csv=is_csv)

    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=400, detail=f"No company with id={company_id}")
    if company.vertical != "launch_matcher":
        raise HTTPException(
            status_code=400,
            detail=f"Company {company_id} ({company.name!r}) has "
                   f"vertical={company.vertical!r}, not 'launch_matcher'. Refusing.",
        )
    # Captured now, as plain values: import_contact_lookup's dry-run path
    # calls db.rollback() per row, which expires every ORM object on this
    # session -- company included -- so company.name below would otherwise
    # trigger an implicit reload outside an awaited context.
    company_name, company_id_val = company.name, company.id

    summary = await import_contact_lookup(db, company_id, contacts, dry_run=dry_run)

    logger.info(
        "Contact import (%s): company=%s total=%s imported=%s",
        "dry_run" if dry_run else "real", company_id, summary.total, summary.imported,
    )

    return {
        "company": company_name,
        "company_id": company_id_val,
        "dry_run": dry_run,
        "total": summary.total,
        "imported": summary.imported,
        "skipped_no_area": summary.count("skipped_no_area"),
        "skipped_bad_phrase": summary.count("skipped_bad_phrase"),
        "skipped_duplicate": summary.count("skipped_duplicate"),
        "skipped_invalid": summary.count("skipped_invalid"),
        # Never phone -- ContactImportResult doesn't carry one at all.
        "results": [
            {
                "name": r.name, "status": r.status, "reason": r.reason,
                "emirate": r.emirate, "area": r.area,
            }
            for r in summary.results
        ],
    }
