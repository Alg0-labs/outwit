import httpx
import json
import logging
from typing import List, Dict, Any, Optional
from config import settings
from database.redis_client import get_redis

logger = logging.getLogger(__name__)

# Fallback mock news when API is unavailable or key not set
MOCK_NEWS: Dict[str, List[Dict]] = {
    "ipl": [
        {"headline": "Mumbai Indians win toss, elect to bat first against CSK", "source": "CricInfo", "published": "2025-04-12T14:00:00Z", "url": "#"},
        {"headline": "Rohit Sharma returns to form with 78-run knock in last match", "source": "ESPN Cricinfo", "published": "2025-04-11T20:00:00Z", "url": "#"},
        {"headline": "CSK's Jadeja ruled fit for today's match after shoulder scare", "source": "NDTV Sports", "published": "2025-04-12T10:00:00Z", "url": "#"},
        {"headline": "Wankhede pitch expected to assist spinners in evening conditions", "source": "Cricbuzz", "published": "2025-04-12T09:00:00Z", "url": "#"},
        {"headline": "MS Dhoni confirms he will bat lower order despite CSK's struggles", "source": "Times of India", "published": "2025-04-11T18:00:00Z", "url": "#"},
    ],
    "geopolitics": [
        {"headline": "US deploys additional warships to Persian Gulf amid Iran tensions", "source": "Reuters", "published": "2025-04-12T08:00:00Z", "url": "#"},
        {"headline": "Iran announces enrichment reached 84% purity at Fordow facility", "source": "AP News", "published": "2025-04-11T16:00:00Z", "url": "#"},
        {"headline": "Back-channel talks between US and Iran ongoing through Oman intermediaries", "source": "Financial Times", "published": "2025-04-10T12:00:00Z", "url": "#"},
        {"headline": "Congressional hawks push for new Iran sanctions package this week", "source": "Politico", "published": "2025-04-12T06:00:00Z", "url": "#"},
        {"headline": "European allies urge restraint as US-Iran tensions escalate", "source": "BBC News", "published": "2025-04-11T14:00:00Z", "url": "#"},
    ],
}


async def fetch_news_for_category(category: str) -> List[Dict[str, Any]]:
    """
    Fetch news from Redis cache (populated by scheduler) or NewsAPI.
    Falls back to mock data in dev mode or when API key is not set.
    """
    redis = get_redis()

    # Try Redis cache first (populated by news_fetcher scheduler)
    if redis:
        try:
            cached = await redis.get(f"news:{category}")
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis news cache miss: {e}")

    # Try NewsAPI directly
    # TODO: Set NEWS_API_KEY in .env — get free key at https://newsapi.org
    if settings.news_api_key and settings.news_api_key != "your_newsapi_key_here":
        queries = {
            "ipl": "IPL 2025 cricket match prediction",
            "geopolitics": "US Iran conflict 2025",
        }
        query = queries.get(category, category)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "sortBy": "publishedAt",
                        "pageSize": 15,
                        "language": "en",
                        "apiKey": settings.news_api_key,
                    },
                )
                if resp.status_code == 200:
                    articles = resp.json().get("articles", [])
                    formatted = [
                        {
                            "headline": a.get("title", ""),
                            "source": a.get("source", {}).get("name", "Unknown"),
                            "published": a.get("publishedAt", ""),
                            "url": a.get("url", "#"),
                        }
                        for a in articles[:10]
                        if a.get("title")
                    ]
                    # Cache for 15 minutes
                    if redis:
                        await redis.setex(f"news:{category}", 900, json.dumps(formatted))
                    return formatted
        except Exception as e:
            logger.error(f"NewsAPI fetch failed: {e}")

    # Fallback to mock news
    logger.info(f"Using mock news for category: {category}")
    return MOCK_NEWS.get(category, MOCK_NEWS["ipl"])


def format_news_for_prompt(articles: List[Dict]) -> str:
    """Format news articles for LLM prompt injection."""
    lines = []
    for i, article in enumerate(articles[:8], 1):
        lines.append(f"{i}. [{article.get('source', 'Unknown')}] {article.get('headline', '')}")
        if article.get("published"):
            lines.append(f"   Published: {article['published'][:10]}")
    return "\n".join(lines) if lines else "No recent news available."
