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
    """Real OpenAI chat-completion call — falls back to rule-based on any failure."""
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

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if not response.is_success:
                logger.error(
                    "OpenAI task extraction HTTP %s — body: %s",
                    response.status_code,
                    response.text[:300],
                )
                return _rule_based_extract(text)
            content = response.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error("OpenAI returned non-JSON: %s", content[:200])
                return _rule_based_extract(text)
    except Exception as exc:
        logger.error("OpenAI task extraction failed (%s) — falling back to rule-based", exc)
        return _rule_based_extract(text)


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

# ---------------------------------------------------------------------------
# Progress-update analyser
# ---------------------------------------------------------------------------

_PROGRESS_SYSTEM_PROMPT = """You are analyzing an employee's WhatsApp message about their task: '{task_title}'.

Determine if this is a progress update, task completion, or unrelated message.
Return ONLY valid JSON with these keys:
  "type": one of ["progress_update", "task_completion", "no_progress"]
  "progress_percent": integer 0-100 (estimate from context clues — e.g. "almost done" ≈ 85, "just started" ≈ 10, "halfway" ≈ 50). Use 100 for completions. null if no_progress.
  "summary": a short one-line summary of the update for the manager's dashboard (e.g. "70% complete - finishing final details"). null if no_progress.

Examples:
- "almost done, just finishing the corners" → {{"type":"progress_update","progress_percent":85,"summary":"85% — finishing corners"}}
- "done with everything" → {{"type":"task_completion","progress_percent":100,"summary":"Completed"}}
- "having trouble with the paint" → {{"type":"progress_update","progress_percent":null,"summary":"Blocked — issue with paint"}}
- "ok thanks" → {{"type":"no_progress","progress_percent":null,"summary":null}}
"""

# Simple keyword→percent map for the rule-based fallback
_PROGRESS_KEYWORDS = [
    ({"done", "completed", "finished", "all done"}, 100, "task_completion"),
    ({"almost done", "nearly done", "almost finished", "nearly finished", "almost complete"}, 85, "progress_update"),
    ({"halfway", "half done", "50%", "half way"}, 50, "progress_update"),
    ({"just started", "starting now", "beginning"}, 10, "progress_update"),
    ({"working on it", "in progress", "on it"}, 30, "progress_update"),
    ({"mostly done", "most of it"}, 75, "progress_update"),
]


async def analyze_progress_update(text: str, task_title: str) -> dict:
    """Analyze a free-text message to extract progress info and a short summary.

    Returns dict with keys: type, progress_percent, summary.
    """
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        return _rule_based_progress(text)

    return await _openai_progress(text, task_title)


def _rule_based_progress(text: str) -> dict:
    """Fallback when no OpenAI key is set."""
    text_lower = text.lower().strip()

    # Explicit UPDATE <number> command
    match = re.search(r"update\s+(\d+)\s*%?", text_lower)
    if match:
        pct = min(int(match.group(1)), 100)
        if pct >= 100:
            return {"type": "task_completion", "progress_percent": 100, "summary": "Completed"}
        return {"type": "progress_update", "progress_percent": pct, "summary": f"{pct}% complete"}

    # Keyword matching
    for keywords, pct, update_type in _PROGRESS_KEYWORDS:
        if any(kw in text_lower for kw in keywords):
            summary = "Completed" if update_type == "task_completion" else f"{pct}% — {text_lower[:60]}"
            return {"type": update_type, "progress_percent": pct, "summary": summary}

    return {"type": "no_progress", "progress_percent": None, "summary": None}


# ---------------------------------------------------------------------------
# Enquiry extraction
# ---------------------------------------------------------------------------

_ENQUIRY_SYSTEM_PROMPT = (
    "You are analyzing a WhatsApp message to determine if it's a client enquiry.\n"
    "A client enquiry is when someone reports a new potential client or customer asking about services.\n"
    "Examples: 'new client enquiry from John for painting', 'got a new client Raj wants plumbing work',\n"
    "'ENQUIRY Priya needs electrical work for her shop'\n\n"
    "Return ONLY valid JSON with these keys:\n"
    '  "is_enquiry": true/false,\n'
    '  "client_name": name of the potential client or null,\n'
    '  "service_requested": what service they want or null,\n'
    '  "notes": any extra details or null\n'
    "If this is NOT an enquiry, return "
    '{"is_enquiry": false, "client_name": null, "service_requested": null, "notes": null}.'
)

_ENQUIRY_EMPTY = {"is_enquiry": False, "client_name": None, "service_requested": None, "notes": None}

# Regex for explicit ENQUIRY command
_ENQUIRY_COMMAND_PATTERN = re.compile(
    r"^ENQUIRY\s+(.+)", re.IGNORECASE
)

# Keywords that suggest an enquiry in natural language
_ENQUIRY_KEYWORDS = {"enquiry", "enquire", "new client", "got a new client", "client asking", "customer asking", "new customer"}


def _is_enquiry_message(text: str) -> bool:
    """Quick check if a message might be an enquiry."""
    text_lower = text.lower().strip()
    if text_lower.startswith("enquiry"):
        return True
    return any(kw in text_lower for kw in _ENQUIRY_KEYWORDS)


async def extract_enquiry_from_message(text: str) -> dict:
    """Extract enquiry details from a message.

    Returns dict with: is_enquiry, client_name, service_requested, notes.
    """
    if not _is_enquiry_message(text):
        return _ENQUIRY_EMPTY

    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        return _rule_based_enquiry(text)

    return await _openai_enquiry(text)


def _rule_based_enquiry(text: str) -> dict:
    """Fallback enquiry extraction without OpenAI."""
    # Try explicit ENQUIRY command first
    match = _ENQUIRY_COMMAND_PATTERN.match(text.strip())
    if match:
        rest = match.group(1).strip()
        # Try to parse "ClientName for/wants/needs Service"
        parts = re.split(r'\s+(?:for|wants|needs|requesting|about)\s+', rest, maxsplit=1, flags=re.IGNORECASE)
        client_name = parts[0].strip() if parts else rest
        service = parts[1].strip() if len(parts) > 1 else None
        return {
            "is_enquiry": True,
            "client_name": client_name,
            "service_requested": service,
            "notes": text,
        }

    # Natural language: try to extract client name after trigger keywords
    text_lower = text.lower()
    for kw in ["new client", "got a new client", "new customer"]:
        if kw in text_lower:
            after = text[text_lower.index(kw) + len(kw):].strip().lstrip("- :,")
            parts = re.split(r'\s+(?:for|wants|needs|requesting|about)\s+', after, maxsplit=1, flags=re.IGNORECASE)
            client_name = parts[0].strip() if parts else after
            service = parts[1].strip() if len(parts) > 1 else None
            if client_name:
                return {
                    "is_enquiry": True,
                    "client_name": client_name[:100],
                    "service_requested": service,
                    "notes": text,
                }

    # Generic enquiry keyword match — mark as enquiry but with minimal extraction
    return {
        "is_enquiry": True,
        "client_name": "Unknown Client",
        "service_requested": None,
        "notes": text,
    }


async def _openai_enquiry(text: str) -> dict:
    """Call OpenAI to extract enquiry details."""
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": _ENQUIRY_SYSTEM_PROMPT},
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

        result = json.loads(response.json()["choices"][0]["message"]["content"])
        return {
            "is_enquiry": result.get("is_enquiry", False),
            "client_name": result.get("client_name"),
            "service_requested": result.get("service_requested"),
            "notes": result.get("notes"),
        }
    except Exception:
        logger.exception("OpenAI enquiry extraction failed — falling back to rule-based")
        return _rule_based_enquiry(text)


# ---------------------------------------------------------------------------
# CEO command intent parser
# ---------------------------------------------------------------------------

_CEO_SYSTEM_PROMPT = """You are parsing a CEO's WhatsApp message to determine what action they want to take on their team's tasks.

The CEO manages employees and tasks. Parse their natural language into a structured command.

## CRITICAL RULES FOR employee_name
- The employee_name is always a PERSON'S NAME (e.g. "Ryan", "Aaron", "Priya").
- Month names (January, February, March, April, May, June, July, August, September, October, November, December) are NEVER employee names.
- When the message starts with "Tell [name]" or "Ask [name]" or "Message [name]", the employee_name is the word immediately after "Tell"/"Ask"/"Message" — NOT any word that appears later in the sentence.
- If the message contains "Tell Aaron the deadline for X is April 25th", employee_name="Aaron" (first word after Tell), NOT "April".
- Cross-check against Known employees list when possible; if the name appears in that list, prefer the match.

## Possible intents (pick the BEST match):
1. "update_task" — CEO wants to change a task's deadline, description, or other field.
   Triggers: words like "deadline", "due date", "is now [date]", "change", "update [task field]", "extend", "move the deadline".
   Examples:
     "Tell Ryan the deadline for the plumbing job is now April 20th" → update_task, employee=Ryan, keyword=plumbing, due_date=2025-04-20
     "Tell aaron the deadline for the plumbing task is now April 25th" → update_task, employee=aaron, keyword=plumbing, due_date=2025-04-25
     "Update Ryan's task description to use copper pipes instead" → update_task, employee=Ryan, keyword=null, description="use copper pipes instead"
2. "check_status" — CEO wants a status report on a task or employee.
   Triggers: "how is", "how's", "status", "progress", "doing on", "update on".
   Examples: "How is Ryan doing on the plumbing task?" → check_status, employee=Ryan, keyword=plumbing
3. "complete_task" — CEO wants to mark a task as completed.
   Triggers: "mark as complete", "close", "finish".
   Examples: "Mark Ryan's bedroom task as complete" → complete_task, employee=Ryan, keyword=bedroom
4. "send_message" — CEO wants to send a short freeform message to an employee (NO deadline/task field change).
   Triggers: "tell [name] to [action]", "let [name] know", "message [name]".
   Examples: "Tell Ryan to call me" → send_message, employee=Ryan, message="call me"
5. "unknown" — Cannot determine intent.

## Priority when "Tell" appears:
- If the sentence contains "deadline", "due date", "is now [date/time]", "description", or "change" → intent is "update_task".
- Otherwise if it is just "Tell [name] to [do something]" → intent is "send_message".

## Date parsing for due_date:
- Convert human dates to ISO-8601 (YYYY-MM-DD). Use the current year (2025) unless another year is mentioned.
- "April 25th" → "2025-04-25", "April 20th" → "2025-04-20", "next Monday" → nearest upcoming Monday.

Known employees: {employee_names}

Return ONLY valid JSON with these keys:
  "intent": one of ["update_task", "check_status", "complete_task", "send_message", "unknown"]
  "employee_name": PERSON name only — never a month or date word (or null)
  "task_keyword": keyword(s) to identify the task (e.g. "plumbing", "bedroom painting") or null
  "changes": object with fields to update, only for update_task intent:
    - "due_date": ISO-8601 date string if a deadline/date is mentioned, else null
    - "description": new description text if mentioned, else null
    - "title": new title if mentioned, else null
  "message": the message to relay to the employee (for send_message intent), or null
  "summary": a short human-readable summary of what the CEO wants (always fill this)
"""


async def parse_ceo_command(text: str, employee_names: list[str]) -> dict:
    """Parse a CEO's natural-language WhatsApp command into a structured intent.

    Falls back to rule-based parsing if OpenAI is unavailable.
    """
    if not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
        return _rule_based_ceo_parse(text, employee_names)

    return await _openai_ceo_parse(text, employee_names)


async def _openai_ceo_parse(text: str, employee_names: list[str]) -> dict:
    """Use OpenAI to parse CEO command intent."""
    names_str = ", ".join(employee_names) if employee_names else "(none known)"
    sys_prompt = _CEO_SYSTEM_PROMPT.format(employee_names=names_str)

    payload = {
        "model": settings.openai_model,
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
            if not response.is_success:
                logger.error(
                    "OpenAI CEO parse HTTP %s — body: %s",
                    response.status_code, response.text[:300],
                )
                return _rule_based_ceo_parse(text, employee_names)

            content = response.json()["choices"][0]["message"]["content"]
            try:
                result = json.loads(content)
                return {
                    "intent": result.get("intent", "unknown"),
                    "employee_name": result.get("employee_name"),
                    "task_keyword": result.get("task_keyword"),
                    "changes": result.get("changes") or {},
                    "message": result.get("message"),
                    "summary": result.get("summary", ""),
                }
            except json.JSONDecodeError:
                logger.error("OpenAI CEO parse returned non-JSON: %s", content[:200])
                return _rule_based_ceo_parse(text, employee_names)
    except Exception as exc:
        logger.error("OpenAI CEO parse failed (%s) — falling back to rule-based", exc)
        return _rule_based_ceo_parse(text, employee_names)


# Month names that must never be treated as employee names
_MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}

# Regex to extract "Tell/Ask/Message <Name>" — captures the first word after the verb
_TELL_NAME_RE = re.compile(
    r"(?:tell|ask|message|notify|inform)\s+([A-Za-z][A-Za-z'-]{1,30})",
    re.IGNORECASE,
)

# Regex to extract a date phrase like "April 25th", "25 April", "April 25", "Apr 20th"
_DATE_PHRASE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
    re.IGNORECASE,
)

_MONTH_TO_NUM = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _extract_date_from_text(text: str) -> str | None:
    """Extract a human date phrase and convert to ISO-8601 YYYY-MM-DD."""
    match = _DATE_PHRASE_RE.search(text)
    if not match:
        return None
    raw = match.group(0).strip()
    # Normalise: remove ordinal suffixes
    cleaned = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", raw, flags=re.IGNORECASE).strip()
    parts = cleaned.split()
    if not parts:
        return None
    try:
        # "April 25" or "25 April"
        if parts[0].isdigit():
            day = int(parts[0])
            month = _MONTH_TO_NUM.get(parts[1].lower()) if len(parts) > 1 else None
        else:
            month = _MONTH_TO_NUM.get(parts[0].lower())
            day = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        if month and day:
            return f"2025-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        pass
    return None


def _rule_based_ceo_parse(text: str, employee_names: list[str]) -> dict:
    """Fallback rule-based CEO command parser."""
    text_lower = text.lower().strip()
    result = {
        "intent": "unknown",
        "employee_name": None,
        "task_keyword": None,
        "changes": {},
        "message": None,
        "summary": text[:100],
    }

    # ── Step 1: Extract employee name ────────────────────────────
    # Priority: known DB names first (longest match wins)
    for name in sorted(employee_names, key=len, reverse=True):
        if name.lower() in text_lower and name.lower() not in _MONTH_NAMES:
            result["employee_name"] = name
            break

    # If still no name, try "Tell/Ask/Message <Name>" pattern
    if not result["employee_name"]:
        m = _TELL_NAME_RE.search(text)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in _MONTH_NAMES:
                result["employee_name"] = candidate.capitalize()

    # ── Step 2: Extract due date ──────────────────────────────────
    due_date_iso = _extract_date_from_text(text)
    if due_date_iso:
        result["changes"]["due_date"] = due_date_iso

    # ── Step 3: Detect intent (order matters) ────────────────────
    has_deadline_kw = any(kw in text_lower for kw in [
        "deadline", "due date", "is now", "by", "extend", "move the deadline",
    ])
    has_desc_kw = "description" in text_lower
    has_update_kw = any(kw in text_lower for kw in ["change", "update"])

    if any(kw in text_lower for kw in ["how is", "how's", "status", "progress", "doing on", "update on"]):
        result["intent"] = "check_status"
        result["summary"] = f"Check status for {result['employee_name'] or 'unknown employee'}"

    elif any(kw in text_lower for kw in ["mark", "complete", "close", "finish"]) and "done" not in text_lower[:6]:
        result["intent"] = "complete_task"
        result["summary"] = f"Complete task for {result['employee_name'] or 'unknown employee'}"

    elif has_deadline_kw or (has_desc_kw and has_update_kw) or due_date_iso:
        # "Tell Aaron the deadline … is now April 25th" → update_task, not send_message
        result["intent"] = "update_task"
        if has_desc_kw:
            # Extract everything after "description to"
            m = re.search(r"description\s+to\s+(.+)", text, re.IGNORECASE)
            if m:
                result["changes"]["description"] = m.group(1).strip()
        result["summary"] = f"Update task for {result['employee_name'] or 'unknown employee'}"

    elif any(kw in text_lower for kw in ["tell", "message", "notify", "inform", "let"]):
        result["intent"] = "send_message"
        result["message"] = text
        result["summary"] = f"Send message to {result['employee_name'] or 'unknown employee'}"

    return result


async def _openai_progress(text: str, task_title: str) -> dict:
    """Call OpenAI to interpret the progress update."""
    sys_prompt = _PROGRESS_SYSTEM_PROMPT.format(task_title=task_title)
    payload = {
        "model": settings.openai_model,
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
            if not response.is_success:
                logger.error(
                    "OpenAI progress analysis HTTP %s — body: %s",
                    response.status_code,
                    response.text[:300],
                )
                return _rule_based_progress(text)
            result = json.loads(response.json()["choices"][0]["message"]["content"])
        return {
            "type": result.get("type", "no_progress"),
            "progress_percent": result.get("progress_percent"),
            "summary": result.get("summary"),
        }
    except Exception as exc:
        logger.error("OpenAI progress analysis failed (%s) — falling back to rule-based", exc)
        return _rule_based_progress(text)
