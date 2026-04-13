import ast
import httpx
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from database.redis_client import get_redis

logger = logging.getLogger(__name__)

POLYMARKET_BASE = "https://gamma-api.polymarket.com"

# ── IPL keyword patterns (word-boundary safe) ─────────────────────────────────
_IPL_RE = [re.compile(p, re.IGNORECASE) for p in [
    r"\bIPL\b", r"\bIndian Premier League\b", r"\bIPLT20\b",
    r"\bcricket\b",
    r"\bMumbai Indians\b", r"\bChennai Super Kings\b", r"\bCSK\b",
    r"\bRCB\b", r"\bRoyal Challengers\b",
    r"\bKKR\b", r"\bKolkata Knight Riders\b",
    r"\bSunRisers\b", r"\bSRH\b",
    r"\bDelhi Capitals\b", r"\bDelhi Daredevils\b",
    r"\bGujarat Titans\b",
    r"\bLucknow Super Giants\b",
    r"\bPunjab Kings\b", r"\bPBKS\b",
    r"\bRajasthan Royals\b",
    r"\bRohit Sharma\b", r"\bVirat Kohli\b",
    r"\bMS Dhoni\b", r"\bDhoni\b", r"\bBumrah\b",
    r"\bT20\b",
    r"\bWankhede\b", r"\bEden Gardens\b", r"\bChinnaswamy\b",
]]


def _is_ipl(question: str) -> bool:
    return any(p.search(question) for p in _IPL_RE)


def classify_market(question: str) -> Optional[str]:
    """Classify a market question into 'ipl' or 'geopolitics'. Returns None if neither."""
    if _is_ipl(question):
        return "ipl"
    return None  # geopolitics tag markets are classified directly


# ── Events-based fetching ─────────────────────────────────────────────────────

def _extract_markets_from_events(events: List[Dict]) -> List[Tuple[Dict, str]]:
    """
    Flatten events → markets.  Returns list of (market_dict, category) tuples.
    """
    result = []
    for event in events:
        for market in event.get("markets", []):
            # Inherit endDate from event if market doesn't have one
            if not market.get("endDate") and event.get("endDate"):
                market["endDate"] = event["endDate"]
            result.append(market)
    return result


async def _fetch_events(tag_slug: str) -> List[Dict]:
    """Fetch events for a tag slug from Polymarket Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{POLYMARKET_BASE}/events",
                params={
                    "tag_slug": tag_slug,
                    "active": "true",
                    "closed": "false",
                    "limit": 100,
                },
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Polymarket /events?tag_slug={tag_slug} returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Polymarket events fetch for tag={tag_slug} failed: {e}")
    return []


async def fetch_markets_by_category() -> List[Tuple[Dict, str]]:
    """
    Fetches markets from Polymarket using the tagged events API.
    Returns list of (market_dict, category_str) tuples.

    Sports tag  → filter for IPL/cricket keywords → category = 'ipl'
    Geopolitics tag → all markets → category = 'geopolitics'
    """
    redis = get_redis()
    cache_key = "polymarket:tagged_markets"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return [(m, c) for m, c in json.loads(cached)]
        except Exception:
            pass

    sports_events = await _fetch_events("sports")
    geo_events = await _fetch_events("geopolitics")

    results: List[Tuple[Dict, str]] = []

    # Sports → only IPL / cricket
    for market in _extract_markets_from_events(sports_events):
        if _is_ipl(market.get("question", "")):
            results.append((market, "ipl"))

    # Geopolitics → everything with a valid question
    for market in _extract_markets_from_events(geo_events):
        if market.get("question"):
            results.append((market, "geopolitics"))

    logger.info(
        f"Polymarket tagged fetch: {sum(1 for _, c in results if c == 'ipl')} IPL, "
        f"{sum(1 for _, c in results if c == 'geopolitics')} geopolitics markets"
    )

    if redis:
        try:
            serialisable = [(m, c) for m, c in results]
            await redis.setex(cache_key, 300, json.dumps(serialisable))
        except Exception:
            pass

    return results


# ── Kept for backwards compatibility ─────────────────────────────────────────

async def fetch_polymarket_markets() -> List[Dict[str, Any]]:
    """Legacy: fetch all markets (used by market_fetcher fallback)."""
    redis = get_redis()
    cache_key = "polymarket:all_markets"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{POLYMARKET_BASE}/markets",
                params={"active": "true", "limit": 200, "closed": "false"},
            )
            if resp.status_code == 200:
                markets = resp.json()
                if redis:
                    await redis.setex(cache_key, 300, json.dumps(markets))
                return markets
    except Exception as e:
        logger.error(f"Polymarket /markets fetch failed: {e}")
    return []


async def get_market_by_id(market_id: str) -> Optional[Dict[str, Any]]:
    redis = get_redis()
    if redis:
        try:
            cached = await redis.get(f"market:{market_id}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{POLYMARKET_BASE}/markets/{market_id}")
            if resp.status_code == 200:
                market = resp.json()
                if redis:
                    await redis.setex(f"market:{market_id}", 300, json.dumps(market))
                return market
    except Exception as e:
        logger.error(f"Polymarket single market fetch failed: {e}")
    return None
