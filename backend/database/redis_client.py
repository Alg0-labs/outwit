import redis.asyncio as aioredis
from config import settings
import logging
import json
from typing import Any, Optional

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis | None = None


async def connect_to_redis():
    global redis_client
    try:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await redis_client.ping()
        logger.info(f"Connected to Redis: {settings.redis_url}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise


async def close_redis_connection():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis:
    return redis_client


async def set_json(key: str, value: Any, ttl: int = 300) -> None:
    await redis_client.setex(key, ttl, json.dumps(value, default=str))


async def get_json(key: str) -> Optional[Any]:
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def delete_key(key: str) -> None:
    await redis_client.delete(key)


async def increment_counter(key: str, ttl: int = 3600) -> int:
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl)
    results = await pipe.execute()
    return results[0]


async def get_counter(key: str) -> int:
    val = await redis_client.get(key)
    return int(val) if val else 0


async def check_health() -> dict:
    try:
        await redis_client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
