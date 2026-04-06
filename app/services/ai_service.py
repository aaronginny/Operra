"""AI service ??? extract structured task data from raw message text."""

import json
import logging
import re
from datetime import datetime, timedelta

import httpx

from app.config import settings

logger = logging.getLogger(__name__)



SYSTEM_PROMPT = (
    "You are a task-extraction assistant. "
    "Given a raw WhatsApp message, extract a structured task.\n"
    "Return ONLY valid JSON with these keys:\n"
    '  "title": short task title,\n'
    '  "description": fuller description or null,\n'
    '  "owner": name of the person responsible or null,\n'
    '  "due_date": ISO-8601 datetime string or null\n'
    "If the message does not contain a task, return "
    '{"title": null, "description": null, "owner": null, "due_date": null}.'
)


async def extract_task_from_message(
    text: str, known_employee_names: list[str] | None = None
) -> dict:
    """Call the LLM to extract task fields from a chat message.

    Falls back to a rule-based parser if no API key is configured so the
    app can run without an OpenAI account during development.

    Args:
        text: raw message text
        known_employee_names: optional list of employee names from the DB
            for more accurate name matching in rule-based mode.
    """
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        logger.info("Using rule-based extraction (no OpenAI key).")
        return _rule_based_extract(text, known_employee_names or [])

    return await _openai_extract(text)


async def _openai_extract(text: str) -> dict:
    """Real OpenAI chat-completion call."""
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("LLM returned non-JSON: %s", content)
        return {"title": None, "description": None, "owner": None, "due_date": None}


# ---------------------------------------------------------------------------
# Rule-based fallback parser
# ---------------------------------------------------------------------------

_EMPTY_RESULT = {"title": None, "description": None, "owner": None, "due_date": None}

# Casual / greeting messages that should NEVER create a task
_CASUAL_MESSAGES = {
    "hello", "hi", "hey", "helo", "hii", "hiii",
    "ok", "okay", "okk", "okkk", "k", "kk",
    "yes", "yeah", "yep", "yup", "no", "nah", "nope",
    "thanks", "thank you", "thankyou", "thx", "ty",
    "good", "great", "nice", "cool", "fine", "awesome", "perfect",
    "good morning", "good night", "good evening", "good afternoon",
    "gm", "gn",
    "bye", "goodbye", "see you", "later",
    "lol", "haha", "hehe", "ha",
    "good job", "well done", "nice work", "great work",
    "hmm", "hmm ok", "alright",
    "what", "why", "how", "when", "where", "who",
    "sure", "np", "no problem",
}

# Action verbs that indicate an actionable instruction
_ACTION_VERBS = {
    "pack", "send", "finish", "complete", "do", "make", "get", "call",
    "check", "reply", "update", "submit", "prepare", "deliver",
    "dispatch", "ship", "order", "buy", "fix", "clean", "arrange",
    "schedule", "confirm", "follow", "contact", "email", "message",
    "write", "print", "scan", "upload", "download", "install",
    "remove", "delete", "move", "transfer", "pick", "drop",
    "set", "create", "build", "organize", "sort", "count",
    "verify", "review", "approve", "reject", "cancel",
    "collect", "return", "refund", "pay", "invoice",
    "remind", "notify", "inform", "tell", "ask",
    "open", "close", "start", "stop", "run", "test",
    "book", "reserve", "plan", "assign", "delegate",
    "load", "unload", "stock", "restock", "inventory",
    "wrap", "label", "tag", "seal", "tape",
    "wash", "iron", "fold", "stitch", "cut", "sew",
    "give", "bring", "take", "put", "place", "keep",
}

# Common non-name capitalised words to skip during name extraction
_SKIP_WORDS = {
    "Please", "Kindly", "Hey", "Hi", "Hello", "Dear", "The", "This",
    "That", "Send", "Finish", "Complete", "Do", "Make", "Pack", "Get",
    "Check", "Call", "Reply", "Update", "Submit", "Prepare", "I", "We",
    "You", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "Today", "Tomorrow", "Diwali", "Christmas",
}

# Patterns that indicate a deadline
_DEADLINE_PATTERN = re.compile(
    r"(?:by|before|until|due)\s+"
    r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)|"
    r"today|tonight|tomorrow|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    re.IGNORECASE,
)

# Simple time pattern to convert "5pm" ??? hours/minutes
_TIME_PATTERN = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    re.IGNORECASE,
)


def _parse_deadline(text: str) -> str | None:
    """Try to extract a deadline datetime string from the message."""
    match = _DEADLINE_PATTERN.search(text)
    if not match:
        return None

    raw = match.group(1).strip().lower()
    now = datetime.now()

    # Relative days
    day_map = {
        "today": 0, "tonight": 0, "tomorrow": 1,
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }

    if raw in day_map:
        if raw in ("today", "tonight", "tomorrow"):
            target = now + timedelta(days=day_map[raw])
            target = target.replace(hour=17, minute=0, second=0, microsecond=0)
        else:
            # Next occurrence of that weekday
            target_wd = day_map[raw]
            days_ahead = (target_wd - now.weekday()) % 7 or 7
            target = now + timedelta(days=days_ahead)
            target = target.replace(hour=17, minute=0, second=0, microsecond=0)
        return target.isoformat()

    # Explicit time like "5pm" or "3:30pm"
    tm = _TIME_PATTERN.search(raw)
    if tm:
        hour = int(tm.group(1))
        minute = int(tm.group(2) or 0)
        ampm = tm.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target.isoformat()

    return None


def _match_known_employee(text: str, known_names: list[str]) -> str | None:
    """Try to match a known employee name anywhere in the message (case-insensitive).

    Checks longest names first so 'Ravi Kumar' matches before 'Ravi'.
    """
    if not known_names:
        return None

    text_lower = text.lower()
    # Sort by length descending so multi-word names match first
    for name in sorted(known_names, key=len, reverse=True):
        if name.lower() in text_lower:
            return name
    return None


def _extract_name(text: str) -> str | None:
    """Extract the first word that looks like a person's name.

    Checks capitalised words first (strongest signal), then falls back to
    any alphabetic word ???3 chars that isn't a known verb, filler, or stop word.
    """
    # Build a lowercase skip set for fallback matching
    _skip_lower = {w.lower() for w in _SKIP_WORDS} | _ACTION_VERBS | {
        "please", "kindly", "the", "and", "for", "task", "with", "from",
        "boxes", "order", "items", "pieces", "units",
    }

    words = text.split()

    # Pass 1: capitalised words (strongest signal)
    for word in words:
        clean = re.sub(r"[,.:;!?]", "", word)
        if (
            clean
            and clean[0].isupper()
            and clean.isalpha()
            and len(clean) >= 2
            and clean not in _SKIP_WORDS
            and clean.lower() not in _ACTION_VERBS
        ):
            return clean

    # Pass 2: any word that could be a name (not a verb/filler, ???3 chars)
    for word in words:
        clean = re.sub(r"[,.:;!?]", "", word)
        if (
            clean
            and clean.isalpha()
            and len(clean) >= 3
            and clean.lower() not in _skip_lower
        ):
            return clean.capitalize()

    return None


def _build_title(text: str, name: str | None) -> str:
    """Build a short task title by stripping the name and deadline parts."""
    title = text
    # Remove the name (case-insensitive)
    if name:
        title = re.sub(rf"(?i)\b{re.escape(name)}\b", "", title, count=1)
    # Remove deadline clause
    title = _DEADLINE_PATTERN.sub("", title)
    # Remove filler words/phrases at the start
    title = re.sub(
        r"^[\s,]*(?:please|kindly|hey|hi|hello|dear|task\s+for|for)[\s,]*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Remove trailing filler like 'for' left after name removal
    title = re.sub(
        r"\s+(?:for|to)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = title.strip(" ,.")
    # Capitalise first letter
    if title:
        title = title[0].upper() + title[1:]
    return title[:120] if title else text[:80]


def _is_actionable(text: str) -> bool:
    """Return True only if the message looks like an actionable task instruction.

    Filters out greetings, acknowledgements, and other casual chatter.
    Requires at least one recognised action verb OR a deadline expression.
    """
    cleaned = text.strip().lower().rstrip(".!?,")

    # Reject known casual messages
    if cleaned in _CASUAL_MESSAGES:
        return False

    # Reject very short messages (1-2 words with no verb)
    words = cleaned.split()
    if len(words) <= 2:
        has_verb = any(w.rstrip("s") in _ACTION_VERBS or w in _ACTION_VERBS for w in words)
        if not has_verb:
            return False

    # For longer messages, require at least one action verb OR a deadline
    has_verb = any(
        w.rstrip("s") in _ACTION_VERBS or w in _ACTION_VERBS
        for w in words
    )
    has_deadline = bool(_DEADLINE_PATTERN.search(text))

    return has_verb or has_deadline


def _rule_based_extract(text: str, known_names: list[str] | None = None) -> dict:
    """Rule-based fallback when no OpenAI key is available.

    Extracts:
      - owner  (matched against known employees first, then heuristic)
      - due_date (deadline expression like 'by 5pm')
      - title  (remaining text, cleaned up)

    Returns title=None for non-actionable messages (greetings, etc.).
    """
    # Gate: reject casual / non-actionable messages
    if not _is_actionable(text):
        logger.info("Message rejected as non-actionable: %r", text)
        return _EMPTY_RESULT

    # Try DB-backed name match first, then fall back to heuristic
    owner = _match_known_employee(text, known_names or [])
    if not owner:
        owner = _extract_name(text)

    due_date = _parse_deadline(text)
    title = _build_title(text, owner)

    logger.info(
        "Extraction result ??? employee: %s | title: %s | deadline: %s",
        owner or "(none)",
        title or "(none)",
        due_date or "(none)",
    )

    return {
        "title": title,
        "description": text,
        "owner": owner,
        "due_date": due_date,
    }
import json
from app.config import settings
import httpx


import json
from app.config import settings
import httpx
import re

async def analyze_progress_update(text: str, task_title: str) -> dict:        
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        text_lower = text.lower()
        if "done" in text_lower or "completed" in text_lower:
            return {"type": "task_completion", "progress_percent": 100}
        
        # Rule based fallback for UPDATE <progress>
        match = re.search(r"update\s+(\d+)\s*%?", text_lower)
        if match:
            return {"type": "progress_update", "progress_percent": int(match.group(1))}
        return {"type": "no_progress", "progress_percent": None}

    sys_prompt = f"""You are analyzing an employee's progress update for the task: '{task_title}'.
Parse the message and return ONLY valid JSON with keys:
  "type": one of ["progress_update", "task_completion", "no_progress"]
  "progress_percent": an integer from 0 to 100, or null if no progress or completion
"""
    payload = {
        "model": getattr(settings, 'openai_model', 'gpt-4o-mini'),
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        
        j = json.loads(response.json()["choices"][0]["message"]["content"])     
        return j
    except Exception:
        return {"type": "no_progress", "progress_percent": None}
