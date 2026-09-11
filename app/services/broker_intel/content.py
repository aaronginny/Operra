"""Content generation for broker_intel — the AI seam for its ungrounded
content: the daily nudge's article/fun-fact captions.

Same shape as launch_matcher's WhatsAppProvider: a Protocol, a real
implementation, and a deterministic stand-in, so the whole vertical is
testable without an API key and swapping the model later touches one class.

SOURCING POLICY. Everything here is AI-generated general commentary, with
no search behind it — appropriate for a social caption, which isn't making
a factual claim a client would rely on. Lead intel and comparisons, which
ARE claims a client might rely on, no longer go through this module at all:
they're built by briefing.py from real web search results via
extraction.py's structured pipeline, precisely because free-text AI
commentary about prices and yields turned out not to be trustworthy enough
(see extraction.py's docstring for the bug that prompted the split).

This module is deliberately NOT where the caveat promise is kept — see
formatter.py, which appends MARKET_CAVEAT to every reply built from
`social_caption` regardless of what came back from here. A generator that
forgot to caveat itself still cannot produce an uncaveated reply.

The prompt below asks the model to avoid stating precise figures as fact and
to stay qualitative, which reduces how often a hard number shows up at all.
That is a second line of defence, not the primary one.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Bullet counts tuned for a phone screen mid-call, not for completeness.
MAX_BULLETS = 6
_TIMEOUT = 45.0

_SHARED_RULES = (
    "Rules you must follow:\n"
    "- Output ONLY bullet lines, each starting with '- '. No preamble, no headings, "
    "no closing paragraph.\n"
    f"- At most {MAX_BULLETS} bullets. Each under 20 words.\n"
    "- Do NOT invent precise statistics, prices, percentages or transaction volumes. "
    "Speak qualitatively ('has seen strong investor interest'), never "
    "'prices rose 12.4% in Q2'.\n"
    "- Never claim a figure comes from the Dubai Land Department or any official "
    "registry.\n"
    "- No emoji.\n"
)

_ARTICLE_SYSTEM = (
    "You are a social-media copywriter for a Dubai real-estate broker.\n"
    "Write a short, punchy, ready-to-post social caption on a general Dubai "
    "real-estate topic — the kind of insight that makes a follower stop "
    "scrolling.\n" + _SHARED_RULES
)

_FUN_FACT_SYSTEM = (
    "You are a social-media copywriter for a Dubai real-estate broker.\n"
    "Write a short, punchy, ready-to-post social caption built around one "
    "genuinely interesting fact about Dubai real estate or the city itself.\n"
    + _SHARED_RULES
)


class ContentGenerator(Protocol):
    """Anything that can produce bullet lines for broker_intel's ungrounded
    content. lead_intel/compare_areas used to live here too; they moved to
    briefing.py's search-backed pipeline — see this module's docstring."""

    async def social_caption(self, kind: str) -> list[str] | None: ...


def _clean_bullets(raw: str) -> list[str]:
    """Model output -> bullet strings, stripped of markers and truncated."""
    out: list[str] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        for marker in ("- ", "* ", "• "):
            if line.startswith(marker):
                line = line[len(marker):].strip()
                break
        else:
            # Numbered lists sometimes slip through despite the prompt.
            if len(line) > 2 and line[0].isdigit() and line[1] in ".)":
                line = line[2:].strip()
        if line:
            out.append(line)
    return out[:MAX_BULLETS]


class OpenAIContentGenerator:
    """Real generation via the same OpenAI chat-completions endpoint and
    settings the rest of the app already uses (see ai_service.py)."""

    async def _complete(self, system: str, user: str) -> list[str] | None:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_tokens": 400,
                        "temperature": 0.8,
                    },
                )
            if resp.status_code != 200:
                logger.warning("broker_intel generation failed: HTTP %s", resp.status_code)
                return None
            bullets = _clean_bullets(resp.json()["choices"][0]["message"]["content"])
            return bullets or None
        except Exception:
            # Never surface a stack trace as a WhatsApp reply — the caller
            # turns None into an honest "couldn't generate" message.
            logger.exception("broker_intel generation errored")
            return None

    async def social_caption(self, kind: str) -> list[str] | None:
        system = _ARTICLE_SYSTEM if kind == "article" else _FUN_FACT_SYSTEM
        return await self._complete(system, "Write today's caption.")


class StubContentGenerator:
    """Deterministic stand-in used by the tests, and by any environment
    without a usable OpenAI key.

    It deliberately produces obviously-generic copy with no numbers in it.
    That is the safe failure mode: if this ever runs in front of the client
    by accident, she gets bland text, never invented statistics.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def social_caption(self, kind: str) -> list[str] | None:
        self.calls.append(("social_caption", kind))
        if kind == "article":
            return [
                "Location still decides most of a Dubai property's long-term story.",
                "Communities with schools and transport nearby hold demand best.",
                "Ask what a building will feel like to live in years from now.",
            ]
        return [
            "Dubai's skyline has reshaped itself within a single generation.",
            "Neighbourhoods planned around walkability keep drawing families.",
            "The city keeps rewarding people who look one district ahead.",
        ]


def ai_configured() -> bool:
    """True when a usable OpenAI key is configured.

    Mirrors ai_service.py's own guard: the repo ships a literal
    'sk-your-...here' placeholder in .env.example, and treating that as a
    real key would mean every generation attempt burns a 45s timeout before
    failing.
    """
    key = settings.openai_api_key
    return bool(key) and not key.startswith("sk-your")


def get_generator() -> ContentGenerator:
    """The generator for this process. Falls back to the stub — never to
    invented specifics — when no usable key is configured."""
    if ai_configured():
        return OpenAIContentGenerator()
    logger.warning("broker_intel: no usable OpenAI key — using StubContentGenerator.")
    return StubContentGenerator()
