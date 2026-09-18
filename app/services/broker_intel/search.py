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
_MAX_RESULTS_HEADLINES = 8

# Every domain a source may come from, with the trust tier it is shown
# under. This one table is both the allowlist (REPUTABLE_DOMAINS is derived
# from it, below) and the tier map, so a domain cannot be allowed in without
# also being given a tier. No social platforms — see the module docstring.
#
#   verified — official government/regulatory data (DLD and its data
#              properties). Shown 🟢.
#   market   — established portals, and agencies/analytics firms with
#              research desks. Shown 🟡.
#   news     — general news and business press. Shown 🔴.
TIER_VERIFIED, TIER_MARKET, TIER_NEWS = "verified", "market", "news"

DOMAIN_TIERS: dict[str, str] = {
    "dubailand.gov.ae": TIER_VERIFIED, "dubaipulse.gov.ae": TIER_VERIFIED,
    "dxbinteract.com": TIER_VERIFIED,
    "bayut.com": TIER_MARKET, "propertyfinder.ae": TIER_MARKET,
    "dubizzle.com": TIER_MARKET, "propertymonitor.ae": TIER_MARKET,
    "knightfrank.ae": TIER_MARKET, "knightfrank.com": TIER_MARKET,
    "cbre.ae": TIER_MARKET, "cbre.com": TIER_MARKET, "jll-mena.com": TIER_MARKET,
    "savills.ae": TIER_MARKET, "corelogic.com": TIER_MARKET,
    "engelvoelkers.com": TIER_MARKET, "betterhomes.ae": TIER_MARKET,
    "arabianbusiness.com": TIER_NEWS, "thenationalnews.com": TIER_NEWS,
    "thenational.ae": TIER_NEWS, "gulfnews.com": TIER_NEWS,
    "khaleejtimes.com": TIER_NEWS, "zawya.com": TIER_NEWS,
    "reuters.com": TIER_NEWS, "bloomberg.com": TIER_NEWS,
}

REPUTABLE_DOMAINS: tuple[str, ...] = tuple(DOMAIN_TIERS)

# Any UAE government host (e.g. a RERA or ministry page) is both allowed and
# 🟢, without having to be listed one by one.
_GOV_SUFFIX = ".gov.ae"

TIER_EMOJI: dict[str, str] = {
    TIER_VERIFIED: "🟢", TIER_MARKET: "🟡", TIER_NEWS: "🔴",
}


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


def _listed_as(domain: str) -> str | None:
    """The DOMAIN_TIERS key `domain` falls under (itself, or a parent of a
    subdomain), or None."""
    for d in DOMAIN_TIERS:
        if domain == d or domain.endswith("." + d):
            return d
    return None


def on_allowlist(url: str) -> bool:
    domain = domain_of(url)
    return _listed_as(domain) is not None or domain.endswith(_GOV_SUFFIX)


def tier_of(domain: str) -> str:
    """The trust tier a cited source is shown under.

    A domain with no tier falls back to TIER_MARKET rather than failing or
    going unlabelled — but logs a warning, so a new domain that somehow
    reaches a reply gets noticed and categorised properly. (With the
    allowlist derived from DOMAIN_TIERS that should not happen through
    search; the fallback is for anything that bypasses it.)
    """
    domain = (domain or "").lower().removeprefix("www.")
    listed = _listed_as(domain)
    if listed is not None:
        return DOMAIN_TIERS[listed]
    if domain.endswith(_GOV_SUFFIX):
        return TIER_VERIFIED
    logger.warning("broker_intel: source domain %r has no trust tier — showing as market data", domain)
    return TIER_MARKET


def tier_emoji(domain: str) -> str:
    return TIER_EMOJI[tier_of(domain)]


class SearchProvider(Protocol):
    async def search_area(self, area: str) -> list[SourceResult]: ...

    async def search_news(self) -> list[SourceResult]: ...


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

    async def search_news(self) -> list[SourceResult]:
        """This week's Dubai property headlines, for the daily brief. One
        news-topic call, allowlist-filtered like every other result."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                    json={
                        "query": "Dubai real estate property market news",
                        "search_depth": "advanced",
                        "max_results": _MAX_RESULTS_HEADLINES,
                        "topic": "news",
                        "time_range": "week",
                        "include_domains": list(REPUTABLE_DOMAINS),
                    },
                )
        except Exception:
            logger.exception("broker_intel news search errored")
            return []
        if resp.status_code != 200:
            logger.warning("broker_intel news search HTTP %s", resp.status_code)
            return []
        return _dedup_and_filter(resp.json().get("results", []))


class StubSearchProvider:
    """Deterministic stand-in for tests. Constructed with canned results
    per area (case-insensitive); an area with no entry returns none, which
    is exactly the "nothing found" case the pipeline must handle honestly."""

    def __init__(
        self,
        by_area: dict[str, list[SourceResult]] | None = None,
        news: list[SourceResult] | None = None,
    ) -> None:
        self._by_area = {k.lower(): v for k, v in (by_area or {}).items()}
        self._news = list(news or [])
        self.calls: list[str] = []

    async def search_area(self, area: str) -> list[SourceResult]:
        self.calls.append(area)
        return list(self._by_area.get(area.lower(), []))

    async def search_news(self) -> list[SourceResult]:
        self.calls.append("<news>")
        return list(self._news)


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
