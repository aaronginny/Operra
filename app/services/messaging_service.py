"""Messaging service — WhatsApp (Meta Cloud API) and Email (SMTP) delivery.

Falls back to console logging when credentials are not configured,
so the app can run in development without external accounts.

WhatsApp provider: Meta Cloud API (migrated from Twilio).
Twilio code is kept below but commented out until Meta is confirmed working.
"""

import asyncio
import logging
import os
import re
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
# from twilio.rest import Client as TwilioClient  # kept for rollback

from app.config import settings

logger = logging.getLogger(__name__)


def format_reminder(employee_name: str, task_title: str, deadline: str | None) -> str:
    """Build a conversational reminder message with reply instructions."""
    deadline_line = f"\nDeadline: {deadline}" if deadline else ""

    return (
        f"Hi {employee_name},\n"
        f"\n"
        f"Reminder:\n"
        f'Please complete task "{task_title}"\n'
        f"{deadline_line}\n"
        f"\n"
        f"Reply with:\n"
        f"  DONE\n"
        f"  STARTED\n"
        f"  HELP"
    )


# ---------------------------------------------------------------------------
# WhatsApp via Meta Cloud API
# ---------------------------------------------------------------------------

def _normalize_whatsapp_phone(phone_number: str) -> str:
    """Normalize a phone number to digits-only (no + prefix) for Meta API."""
    cleaned = phone_number.strip()
    if cleaned.lower().startswith("whatsapp:"):
        cleaned = cleaned.split(":", 1)[1]

    cleaned = re.sub(r"[\s\-()]", "", cleaned)
    # Meta wants no leading +
    cleaned = cleaned.lstrip("+")

    # Warn when a number looks like a bare 10-digit Indian mobile (6–9 prefix)
    # missing the 91 country code — e.g. "9876543210" instead of "919876543210".
    if len(cleaned) == 10 and cleaned[0] in "6789":
        logger.warning(
            "=== PHONE FORMAT WARNING === %r looks like an Indian mobile number "
            "without country code. Expected 91XXXXXXXXXX but got %s. "
            "Message will be sent to %s — update the employee's phone number if delivery fails.",
            phone_number, cleaned, cleaned,
        )

    return cleaned


def _send_via_meta(to_clean: str, body: str) -> bool:
    """Synchronous Meta Cloud API call (run inside asyncio.to_thread)."""
    phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
    access_token = os.getenv("META_ACCESS_TOKEN")

    if not phone_number_id or not access_token:
        logger.error("=== META NOT CONFIGURED === META_PHONE_NUMBER_ID or META_ACCESS_TOKEN missing")
        return False

    url = f"https://graph.facebook.com/v25.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "text",
        "text": {"body": body},
    }

    response = requests.post(url, headers=headers, json=payload, timeout=10)
    if response.status_code == 200:
        logger.info("=== META SENT OK === to %s", to_clean)
        return True
    else:
        logger.error("=== META SEND FAILED === %s: %s", response.status_code, response.text)
        return False


async def send_whatsapp_message(phone_number: str, message: str) -> bool:
    """Send a WhatsApp message via the Meta Cloud API.

    requests.post is synchronous; it runs inside asyncio.to_thread so the
    event loop stays unblocked.  Falls back gracefully when env vars are absent.
    """
    to_clean = _normalize_whatsapp_phone(phone_number)
    logger.info("=== META SEND ATTEMPT === raw_to=%r  normalized_to=%s", phone_number, to_clean)
    return await asyncio.to_thread(_send_via_meta, to_clean, message)


# ---------------------------------------------------------------------------
# TWILIO — kept for rollback, not active
# ---------------------------------------------------------------------------
# def _twilio_configured() -> bool:
#     return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_number)
#
# async def _send_via_twilio(phone_number: str, message: str) -> bool:
#     if not _twilio_configured():
#         logger.error("=== TWILIO NOT CONFIGURED ===")
#         return False
#     clean_phone = _normalize_whatsapp_phone_e164(phone_number)
#     from_number = _normalize_whatsapp_phone_e164(settings.twilio_whatsapp_number)
#     try:
#         client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
#         sent = await asyncio.to_thread(
#             client.messages.create,
#             body=message,
#             from_=f"whatsapp:{from_number}",
#             to=f"whatsapp:{clean_phone}",
#         )
#         if sent.status in ("failed", "undelivered"):
#             logger.error("=== TWILIO DELIVERY FAILED === SID=%s status=%s", sent.sid, sent.status)
#             return False
#         logger.info("=== TWILIO SENT OK === SID=%s status=%s", sent.sid, sent.status)
#         return True
#     except Exception as exc:
#         logger.error("=== TWILIO SEND FAILED === %s", exc, exc_info=True)
#         return False


# ---------------------------------------------------------------------------
# Email via SMTP (Gmail / configurable)
# ---------------------------------------------------------------------------

def _email_configured() -> bool:
    """Return True if SMTP credentials are present."""
    return bool(settings.email_user and settings.email_password)


async def send_email(email: str, message: str, subject: str = "Task Reminder") -> None:
    """Send an email via SMTP (async).

    If email credentials are not configured the message is logged to the
    console instead so the scheduler never crashes.
    """
    if not _email_configured():
        logger.warning(
            "Email credentials not configured — logging message instead.\n"
            "[Email → %s]\n%s",
            email,
            message,
        )
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.email_user
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        await aiosmtplib.send(
            msg,
            hostname=settings.email_host,
            port=settings.email_port,
            username=settings.email_user,
            password=settings.email_password,
            start_tls=True,
        )

        logger.info("Email sent to %s (subject: %s)", email, subject)
    except Exception:
        logger.exception("Failed to send email to %s", email)


# ---------------------------------------------------------------------------
# Welcome message for newly registered employees
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "Welcome to PhantomPilot.\n"
    "\n"
    "You will receive task reminders here.\n"
    "\n"
    "Reply commands:\n"
    "DONE → mark task complete\n"
    "STARTED → mark task in progress\n"
    "HELP → request assistance"
)


async def send_welcome_message(phone_number: str) -> None:
    """Send a welcome WhatsApp message to a newly registered employee."""
    await send_whatsapp_message(phone_number, WELCOME_TEXT)


# ---------------------------------------------------------------------------
# Smart follow-up message templates
# ---------------------------------------------------------------------------

def format_progress_check(employee_name: str, task_title: str, deadline: str, next_checkpoint: str | None = None) -> str:
    """60-minute follow-up — friendly progress check.

    If a next_checkpoint is provided, includes a question about it.
    """
    checkpoint_line = ""
    if next_checkpoint:
        checkpoint_line = f"\nAlso, did you manage to {next_checkpoint} yet?\n"

    return (
        f"Hi {employee_name} 👋\n\n"
        f"Checking in on your task:\n"
        f'"{task_title}"\n\n'
        f"Deadline: {deadline}\n"
        f"{checkpoint_line}\n"
        f"Have you started?\n\n"
        f"Reply:\n"
        f"STARTED\n"
        f"DONE\n"
        f"HELP"
    )


def format_urgent_reminder(task_title: str) -> str:
    """30-minute follow-up — urgency reminder."""
    return (
        f"Reminder: 30 minutes left.\n\n"
        f"Task: {task_title}\n\n"
        f"Please update status:\n"
        f"DONE\n"
        f"STARTED\n"
        f"HELP"
    )


def format_deadline_alert(task_title: str) -> str:
    """Deadline reached — final alert."""
    return (
        f"PhantomPilot - Deadline Reached\n\n"
        f"Task: {task_title}\n\n"
        f"Please reply with:\n"
        f"DONE - mark complete\n"
        f"HELP - request assistance"
    )

