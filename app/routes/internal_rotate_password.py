"""TEMPORARY — one-time password rotation for Mahmoud's account.

There is no in-app way to change a password: signup only creates, and
PATCH /auth/profile covers name and WhatsApp number only. Mahmoud's current
password was generated during provisioning and appeared in tool output at
the time, and its punctuation makes it awkward to hand over, so it is being
rotated to a clean alphanumeric one.

Auth is the ordinary login gate and the rotation applies to the CALLER'S OWN
user row — the account is identified by the token, never by a parameter — so
this cannot be aimed at another user even with a valid login. The caller
must also supply their current password, so a borrowed token alone is not
enough to lock someone out of their own account.

DELETE once the rotation is done:
  1. Delete this file.
  2. Remove its import/include_router lines in app/main.py.
  3. Delete test_internal_rotate_password.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import (
    get_current_user,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

MIN_PASSWORD_LENGTH = 12


class RotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


@router.post("/rotate-password")
async def rotate_password(
    payload: RotateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set a new password on the caller's own account."""
    if not current_user.password_hash or not verify_password(
        payload.current_password, current_user.password_hash
    ):
        # Deliberately vague, same as the login route.
        raise HTTPException(status_code=403, detail="Incorrect password")

    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=400, detail="New password must differ from the current one"
        )

    current_user.password_hash = get_password_hash(payload.new_password)
    await db.flush()

    # Never log the password itself, only that a rotation happened.
    logger.info(
        "Password rotated for user_id=%s company_id=%s",
        current_user.id, current_user.company_id,
    )
    return {"success": True, "user_id": current_user.id,
            "company_id": current_user.company_id}
