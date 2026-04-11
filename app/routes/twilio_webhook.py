"""Twilio WhatsApp webhook — receives real Twilio form-data POSTs.

POST /whatsapp/webhook  — Twilio sends incoming messages here
"""

import logging

from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.webhook_service import process_incoming_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["Twilio WhatsApp"])


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
    Body: str = Form(""),
    From: str = Form(""),
    To: str = Form(""),
    MessageSid: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Receive an incoming WhatsApp message from Twilio.

    Twilio sends form-encoded data with fields like Body, From, To, etc.
    This endpoint processes the message and returns a TwiML XML reply.
    """
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

    return _twiml_response("Message received by Foreman AI.")
