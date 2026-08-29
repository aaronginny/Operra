"""TEMPORARY — second contact_lookup import pass for Mahmoud's account.

The first pass (358 rows) ran through a shared-secret variant of this
endpoint, which has since been removed. This pass exists to pick up the ~108
contacts that the newly-confirmed Dubai keywords (Astro / Shomous / Aludra /
Kawther — see FALLBACK_EMIRATE_HINTS in contact_signals.py) now recognise.

Auth is the ordinary login + `require_launch_matcher_company` gate rather
than a shared secret this time, which is strictly tighter: the import target
is taken from the authenticated user's own token, so this physically cannot
write into another tenant, and no static cross-tenant secret has to exist in
production for the duration.

Still not a permanent feature — nothing in the product asks users to upload
contact files, and this ships no UI. DELETE once the pass is done:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
  3. Delete test_internal_import_contacts.py.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_launch_matcher_company
from app.schemas.auth_schema import CurrentUser
from app.services.launch_matcher.contact_lookup_importer import (
    import_contact_lookup,
    parse_contacts_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.post("/import-contacts")
async def import_contacts_endpoint(
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_launch_matcher_company),
):
    """Import a contact export into the CALLER'S OWN company_lookup rows.

    company_id is deliberately not a parameter — it comes from the token, so
    there is no way to aim this at another tenant even with a valid login.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    is_csv = (file.filename or "").lower().endswith(".csv")
    contacts = parse_contacts_text(text, is_csv=is_csv)

    company_id = current_user.company_id
    summary = await import_contact_lookup(db, company_id, contacts, dry_run=dry_run)

    logger.info(
        "Contact import (%s): company=%s total=%s imported=%s",
        "dry_run" if dry_run else "real", company_id, summary.total, summary.imported,
    )

    return {
        "company_id": company_id,
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
