"""WhatsApp webhook route — JSON-based (for Swagger / curl testing).

GET  /webhook  — verification handshake
POST /webhook  — receive message → handle reply OR extract task → save
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.webhook_service import process_incoming_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["WhatsApp"])

VERIFY_TOKEN: str = settings.whatsapp_verify_token


# ---------------------------------------------------------------------------
# Request schema (simplified dev payload — also powers the Swagger "Try it out")
# ---------------------------------------------------------------------------
class WebhookPayload(BaseModel):
    """Simplified payload for local testing via Swagger / curl."""

    company_id: int = 1
    sender: str = "unknown"
    message: str


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    """WhatsApp webhook verification (GET)."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def receive_message(
    payload: WebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """Receive a WhatsApp message, handle reply commands OR extract a task.

    Send a JSON body like::

        {
          "company_id": 1,
          "sender": "+919876543210",
          "message": "Ravi please finish the invoice by Friday"
        }

    Or a reply command::

        {
          "company_id": 1,
          "sender": "+919876543210",
          "message": "DONE"
        }
    """
    return await process_incoming_message(
        db=db,
        sender=payload.sender,
        text=payload.message,
        force_company_id=payload.company_id,
    )
