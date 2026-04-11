"""Messaging service — WhatsApp (Twilio) and Email (SMTP) delivery.

Falls back to console logging when credentials are not configured,
so the app can run in development without external accounts.
"""

import asyncio
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from twilio.rest import Client as TwilioClient

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
# WhatsApp via Twilio
# ---------------------------------------------------------------------------

def _twilio_configured() -> bool:
    """Return True if all Twilio credentials are present."""
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_number)


def _normalize_whatsapp_phone(phone_number: str) -> str:
    """Normalize user-entered WhatsApp numbers to Twilio-friendly E.164 format."""
    cleaned = phone_number.strip()
    if cleaned.lower().startswith("whatsapp:"):
        cleaned = cleaned.split(":", 1)[1]

    cleaned = re.sub(r"[\s\-()]", "", cleaned)
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"

    # Warn when a number looks like a bare 10-digit Indian mobile (6–9 prefix)
    # that is missing the +91 country code — e.g. "+9876543210" instead of "+919876543210".
    digits_only = cleaned.lstrip("+")
    if len(digits_only) == 10 and digits_only[0] in "6789":
        logger.warning(
            "=== PHONE FORMAT WARNING === %r looks like an Indian mobile number "
            "without country code. Expected +91XXXXXXXXXX but got %s. "
            "Message will be sent to %s — update the employee's phone number if delivery fails.",
            phone_number, cleaned, cleaned,
        )

    return cleaned


async def send_whatsapp_message(phone_number: str, message: str) -> bool:
    """Send a WhatsApp message via the Twilio API.

    If Twilio credentials are not configured the message is logged to the
    console instead so the scheduler never crashes.
    """
    if not _twilio_configured():
        logger.error(
            "=== TWILIO NOT CONFIGURED === "
            "SID=%s  TOKEN=%s  NUMBER=%s — message to %r NOT sent.",
            "set" if settings.twilio_account_sid else "MISSING",
            "set" if settings.twilio_auth_token else "MISSING",
            "set" if settings.twilio_whatsapp_number else "MISSING",
            phone_number,
        )
        return False

    clean_phone = _normalize_whatsapp_phone(phone_number)
    from_number = _normalize_whatsapp_phone(settings.twilio_whatsapp_number)

    logger.info(
        "=== TWILIO SEND ATTEMPT === raw_to=%r  normalized_to=%s  from=whatsapp:%s  to=whatsapp:%s",
        phone_number, clean_phone, from_number, clean_phone,
    )

    try:
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)

        # Twilio's WhatsApp API is synchronous; run in a thread to keep the
        # event loop unblocked.
        sent = await asyncio.to_thread(
            client.messages.create,
            body=message,
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{clean_phone}",
        )

        if sent.status in ("failed", "undelivered"):
            logger.error(
                "=== TWILIO DELIVERY FAILED === to=%s SID=%s status=%s error_code=%s",
                clean_phone, sent.sid, sent.status, sent.error_code,
            )
            return False

        logger.info(
            "=== TWILIO SENT OK === to=%s SID=%s status=%s",
            clean_phone, sent.sid, sent.status,
        )
        return True

    except Exception as exc:
        # Extract Twilio error code if present (TwilioRestException has .code)
        error_code = getattr(exc, "code", None)
        error_msg = getattr(exc, "msg", None) or str(exc)
        logger.error(
            "=== TWILIO SEND FAILED === to=%s error_code=%s msg=%s",
            clean_phone, error_code, error_msg,
        )
        logger.error("=== TWILIO EXCEPTION TRACEBACK ===", exc_info=True)
        return False


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

