"""Web search for broker_intel — the retrieval half of sourced briefings.

Same shape as content.py's ContentGenerator seam: a Protocol, a real
implementation, and a deterministic stand-in, so the pipeline is testable
without a Tavily key and swapping providers later touches one class.

Two queries per area, not one: a "general" search (best for hard figures —
prices, yields) and a "news" search (Tavily's own dating is reliable there,
where it comes back null on most general-topic results). Both are filtered
to REPUTABLE_DOMAINS before anything downstream sees them.

WHY THE ALLOWLIST IS ENFORCED HERE, NOT TRUSTED TO TAVILY. An early probe
against the real API cited an Instagram post and a LinkedIn post as market
sources — unusable, and actively bad once a reply gets forwarded to a
client. Tavily's own `include_domains` parameter turned out to be a soft
preference rather than a hard filter (an unlisted domain still came back in
testing despite it being passed), so every result is re-checked against the
allowlist in Python before it can reach a Claim, a bullet, or a citation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 45.0
_MAX_RESULTS_GENERAL = 8
_MAX_RESULTS_NEWS = 6

# Portals with real listing inventory, international agencies with research
# desks, the DLD's own data properties, and mainstream UAE/regional business
# press. No social platforms — see the module docstring.
REPUTABLE_DOMAINS: tuple[str, ...] = (
    "bayut.com", "propertyfinder.ae", "dubizzle.com", "propertymonitor.ae",
    "dxbinteract.com", "dubailand.gov.ae", "dubaipulse.gov.ae",
    "knightfrank.ae", "knightfrank.com", "cbre.ae", "cbre.com", "jll-mena.com",
    "savills.ae", "corelogic.com", "engelvoelkers.com", "betterhomes.ae",
    "arabianbusiness.com", "thenationalnews.com", "gulfnews.com",
    "khaleejtimes.com", "zawya.com", "reuters.com", "bloomberg.com",
)


@dataclass(frozen=True)
class SourceResult:
    """One search hit, already known to be on the allowlist."""

    url: str
    domain: str
    title: str
    content: str
    published_date: str | None = None


def domain_of(url: str) -> str:
    try:
        return url.split("/")[2].removeprefix("www.")
    except IndexError:
        return url


def on_allowlist(url: str) -> bool:
    domain = domain_of(url)
    return any(domain == d or domain.endswith("." + d) for d in REPUTABLE_DOMAINS)


class SearchProvider(Protocol):
    async def search_area(self, area: str) -> list[SourceResult]: ...


def _dedup_and_filter(payloads: list[dict]) -> list[SourceResult]:
    results: list[SourceResult] = []
    seen: set[str] = set()
    for r in payloads:
        url = r.get("url") or ""
        if not url or url in seen or not on_allowlist(url):
            continue
        seen.add(url)
        results.append(SourceResult(
            url=url,
            domain=domain_of(url),
            title=r.get("title") or "",
            content=r.get("content") or "",
            published_date=r.get("published_date") or None,
        ))
    return results


class TavilySearchProvider:
    """Real search via the Tavily API."""

    async def search_area(self, area: str) -> list[SourceResult]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                headers = {"Authorization": f"Bearer {settings.tavily_api_key}"}
                general, news = await asyncio.gather(
                    client.post(
                        "https://api.tavily.com/search",
                        headers=headers,
                        json={
                            "query": f"{area} Dubai apartment price per sqft rental yield 2026",
                            "search_depth": "advanced",
                            "max_results": _MAX_RESULTS_GENERAL,
                            "topic": "general",
                            "include_domains": list(REPUTABLE_DOMAINS),
                        },
                    ),
                    client.post(
                        "https://api.tavily.com/search",
                        headers=headers,
                        json={
                            "query": f"{area} Dubai property market",
                            "search_depth": "advanced",
                            "max_results": _MAX_RESULTS_NEWS,
                            "topic": "news",
                            "time_range": "month",
                            "include_domains": list(REPUTABLE_DOMAINS),
                        },
                    ),
                    return_exceptions=True,
                )
        except Exception:
            logger.exception("broker_intel search errored for area=%s", area)
            return []

        payloads: list[dict] = []
        for resp in (general, news):
            if isinstance(resp, BaseException):
                logger.warning("broker_intel search leg failed for area=%s: %s", area, resp)
                continue
            if resp.status_code != 200:
                logger.warning("broker_intel search HTTP %s for area=%s", resp.status_code, area)
                continue
            payloads.extend(resp.json().get("results", []))
        return _dedup_and_filter(payloads)


class StubSearchProvider:
    """Deterministic stand-in for tests. Constructed with canned results
    per area (case-insensitive); an area with no entry returns none, which
    is exactly the "nothing found" case the pipeline must handle honestly."""

    def __init__(self, by_area: dict[str, list[SourceResult]] | None = None) -> None:
        self._by_area = {k.lower(): v for k, v in (by_area or {}).items()}
        self.calls: list[str] = []

    async def search_area(self, area: str) -> list[SourceResult]:
        self.calls.append(area)
        return list(self._by_area.get(area.lower(), []))


def search_configured() -> bool:
    """True when a usable Tavily key is configured."""
    key = settings.tavily_api_key
    return bool(key) and not key.startswith("tvly-your")


def get_search_provider() -> SearchProvider:
    """The provider for this process. Falls back to the stub — which
    returns no results rather than inventing any — when no key is set."""
    if search_configured():
        return TavilySearchProvider()
    logger.warning("broker_intel: no usable TAVILY_API_KEY — sourced search unavailable.")
    return StubSearchProvider()
