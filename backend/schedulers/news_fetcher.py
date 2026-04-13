import json
import logging
import httpx
from database.redis_client import get_redis
from config import settings

logger = logging.getLogger(__name__)

CATEGORY_QUERIES = {
    "ipl": "IPL 2025 cricket match prediction",
    "geopolitics": "US Iran conflict geopolitics 2025",
}


async def refresh_news_cache() -> None:
    """
    Fetches fresh news from NewsAPI and writes to Redis for all categories.
    Runs every 15 minutes via APScheduler.
    """
    if not settings.news_api_key or settings.news_api_key in ("", "your_newsapi_key_here"):
        logger.info("Scheduler: NEWS_API_KEY not set — skipping news refresh (mock data will be used)")
        return

    redis = get_redis()
    logger.info("Scheduler: refreshing news cache from NewsAPI...")

    for category, query in CATEGORY_QUERIES.items():
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
                    if redis:
                        await redis.setex(f"news:{category}", 900, json.dumps(formatted))
                    logger.info(f"Scheduler: cached {len(formatted)} articles for {category}")
                else:
                    logger.warning(f"NewsAPI returned {resp.status_code} for {category}")
        except Exception as e:
            logger.error(f"News cache refresh failed for {category}: {e}")
