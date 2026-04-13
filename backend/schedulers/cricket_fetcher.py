import json
import logging
from datetime import datetime, time
import httpx
from database.redis_client import get_redis
from config import settings

logger = logging.getLogger(__name__)

# IPL matches typically run 14:00–23:00 IST (08:30–17:30 UTC)
IST_OFFSET_HOURS = 5.5
ACTIVE_START_UTC = time(8, 30)
ACTIVE_END_UTC = time(17, 30)

MOCK_CRICKET_DATA = {
    "match": "Mumbai Indians vs Chennai Super Kings",
    "venue": "Wankhede Stadium, Mumbai",
    "status": "In Progress",
    "score": {"MI": "156/4 (18.2 ov)", "CSK": "Yet to bat"},
    "head_to_head": {"MI_wins": 21, "CSK_wins": 20, "total": 41},
    "form": {
        "MI": ["W", "W", "L", "W", "W"],
        "CSK": ["L", "W", "W", "W", "L"],
    },
    "key_players": {
        "MI": [{"name": "Rohit Sharma", "role": "Batsman", "form": "Excellent"}],
        "CSK": [{"name": "MS Dhoni", "role": "Wicket-keeper Batsman", "form": "Good"}],
    },
    "weather": {"condition": "Clear", "temperature": "32°C", "humidity": "65%"},
    "toss": {"winner": "MI", "decision": "bat"},
}


def _is_active_hours() -> bool:
    """Check if current time falls within IPL match hours (UTC)."""
    now_utc = datetime.utcnow().time()
    return ACTIVE_START_UTC <= now_utc <= ACTIVE_END_UTC


async def fetch_cricket_scores() -> None:
    """
    Fetches live cricket data from CricAPI and caches in Redis.
    Runs every 2 minutes via APScheduler, but only during active hours.
    """
    if not _is_active_hours():
        logger.debug("Scheduler: outside cricket hours — skipping cricket fetch")
        return

    redis = get_redis()
    logger.info("Scheduler: fetching live cricket scores...")

    if not settings.cricapi_key or settings.cricapi_key in ("", "your_cricapi_key_here"):
        logger.info("Scheduler: CRICAPI_KEY not set — using mock cricket data")
        if redis:
            await redis.setex("cricket:live", 120, json.dumps(MOCK_CRICKET_DATA))
        return

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.cricapi.com/v1/currentMatches",
                params={"apikey": settings.cricapi_key, "offset": 0},
            )
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("data", [])
                # Filter for IPL matches
                ipl_matches = [
                    m for m in matches
                    if "IPL" in m.get("name", "").upper() or "Indian Premier League" in m.get("name", "")
                ]
                if ipl_matches and redis:
                    await redis.setex("cricket:live", 120, json.dumps(ipl_matches[0]))
                    logger.info(f"Scheduler: cached live cricket: {ipl_matches[0].get('name', 'Unknown match')}")
            else:
                logger.warning(f"CricAPI returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Cricket fetch failed: {e}")
        # Cache mock data as fallback
        if redis:
            await redis.setex("cricket:live", 120, json.dumps(MOCK_CRICKET_DATA))
