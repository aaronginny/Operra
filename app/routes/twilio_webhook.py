"""Twilio WhatsApp webhook — receives real Twilio form-data POSTs.

POST /whatsapp/webhook  — Twilio sends incoming messages here
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator

from app.config import settings
from app.database import get_db
from app.services.webhook_service import process_incoming_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["Twilio WhatsApp"])


async def _verify_twilio_signature(request: Request) -> None:
    """Reject the request unless X-Twilio-Signature is valid for our auth_token.

    Skipped only if TWILIO_AUTH_TOKEN isn't configured (dev/sandbox).
    """
    auth_token = settings.twilio_auth_token
    if not auth_token:
        # Dev fallback — log loudly so this isn't silently disabled in prod.
        logger.warning("Twilio webhook: signature check skipped (TWILIO_AUTH_TOKEN unset)")
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio signs against the full public URL; behind Render's proxy the
    # request scheme/host appear as the proxied values, which is what we want.
    url = str(request.url)
    form = await request.form()
    params = {k: v for k, v in form.items()}

    validator = RequestValidator(auth_token)
    if not validator.validate(url, params, signature):
        logger.warning("Twilio webhook: invalid signature for url=%s", url)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _twiml_response(text: str) -> Response:
    """Return a TwiML XML response that sends a reply message."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{text}</Message>"
        "</Response>"
    )
    return Response(content=xml, media_type="application/xml")


@router.post("/webhook")
async def twilio_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive an incoming WhatsApp message from Twilio.

    Twilio sends form-encoded data with fields like Body, From, To, etc.
    This endpoint processes the message and returns a TwiML XML reply.
    """
    await _verify_twilio_signature(request)

    form = await request.form()
    Body = (form.get("Body") or "")
    From = (form.get("From") or "")
    To = (form.get("To") or "")
    MessageSid = (form.get("MessageSid") or "")

    # Strip the "whatsapp:" prefix Twilio adds to numbers
    sender = From.replace("whatsapp:", "").strip()
    message = Body.strip()

    logger.info(
        "=== TWILIO WEBHOOK === Raw From=%r | Stripped sender=%r | Body=%r | To=%r | SID=%s",
        From, sender, Body, To, MessageSid,
    )

    if not message:
        return _twiml_response("No message received.")

    # Delegate all processing to the shared webhook service
    result = await process_incoming_message(
        db=db,
        sender=sender,
        text=message,
    )

    # Build a user-friendly TwiML reply based on what happened
    status = result.get("status", "")

    if status == "ceo_command":
        return _twiml_response(result.get("reply", "Command processed."))

    if status == "task_updated":
        task_title = result.get("task_title", "")
        new_status = result.get("new_status", "")
        return _twiml_response(f'Task "{task_title}" updated to {new_status}.')

    if status == "task_created":
        task_title = result.get("task_title", "")
        return _twiml_response(f'Task created: "{task_title}".')

    if status == "usage_hint":
        return _twiml_response(result.get("detail", "Command processed."))

    if status == "error":
        return _twiml_response(result.get("detail", "Something went wrong. Please try again."))

    return _twiml_response("Message received by PhantomPilot.")
