"""WhatsApp webhook routes.

Dev / testing (JSON body):
  GET  /webhook      — verification handshake
  POST /webhook      — receive message → handle reply OR extract task → save

Meta Cloud API (real webhook):
  GET  /webhook/whatsapp  — Meta verification handshake (hub.mode / hub.challenge)
  POST /webhook/whatsapp  — Real Meta payload; extracts sender + text and processes
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.messaging_service import subscribe_waba_webhook
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


# ---------------------------------------------------------------------------
# Meta Cloud API webhook — real production endpoints
# ---------------------------------------------------------------------------

@router.get("/resubscribe", tags=["WhatsApp"])
async def resubscribe_waba():
    """Manually re-subscribe this app to the WABA webhook.

    Hit this after changing the production phone number or WABA.
    """
    import asyncio as _asyncio
    ok, msg = await _asyncio.to_thread(subscribe_waba_webhook)
    return {"success": ok, "detail": msg}


@router.get("/whatsapp")
async def meta_verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    """Meta webhook verification handshake (GET /webhook/whatsapp).

    Meta sends hub.mode="subscribe" plus the token you configured in the
    Meta developer portal.  We echo back hub.challenge as plain text.
    """
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Meta webhook verified successfully.")
        return PlainTextResponse(hub_challenge)
    logger.warning("Meta webhook verification failed: mode=%r token=%r", hub_mode, hub_verify_token)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp")
async def meta_receive_message(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive a real Meta Cloud API webhook payload (POST /webhook/whatsapp).

    Meta payload structure::

        {
          "entry": [{
            "changes": [{
              "value": {
                "messages": [{
                  "from": "919876543210",
                  "text": {"body": "DONE"}
                }]
              }
            }]
          }]
        }

    Non-message events (status updates, read receipts, etc.) are silently
    ignored so Meta doesn't retry them.
    """
    import json as _json
    raw_bytes = await request.body()
    logger.info("=== META WEBHOOK HIT === method=POST path=/webhook/whatsapp")
    logger.info("=== HEADERS === %s", dict(request.headers))
    logger.info("=== RAW BODY === %s", raw_bytes.decode("utf-8", errors="replace"))

    try:
        body = _json.loads(raw_bytes)
    except Exception:
        logger.warning("Meta webhook: could not parse JSON body")
        return {"status": "ok"}

    logger.info("=== PARSED BODY === %s", body)

    # Surface Meta delivery status updates so silent drops are visible
    try:
        statuses = body["entry"][0]["changes"][0]["value"].get("statuses") or []
    except (KeyError, IndexError, TypeError):
        statuses = []
    for s in statuses:
        status = s.get("status")
        recipient = s.get("recipient_id")
        msg_id = s.get("id")
        errors = s.get("errors") or []
        if status == "failed" or errors:
            err_summary = "; ".join(
                f"code={e.get('code')} title={e.get('title')!r} detail={(e.get('error_data') or {}).get('details') or e.get('message')!r}"
                for e in errors
            )
            logger.error(
                "=== META DELIVERY FAILED === to=%s msg_id=%s status=%s errors=[%s]",
                recipient, msg_id, status, err_summary,
            )
        else:
            logger.info("=== META DELIVERY === to=%s msg_id=%s status=%s", recipient, msg_id, status)

    try:
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")
    except (KeyError, IndexError, TypeError):
        # Status updates, delivery receipts, etc. — not actionable
        logger.debug("Meta webhook: no message in payload, skipping")
        return {"status": "ok"}

    if not sender or not text:
        return {"status": "ok"}

    # Normalise sender to E.164 format (Meta omits the leading +)
    if not sender.startswith("+"):
        sender = f"+{sender}"

    logger.info("Meta webhook: message from %s", sender)
    await process_incoming_message(db=db, sender=sender, text=text)
    return {"status": "ok"}
