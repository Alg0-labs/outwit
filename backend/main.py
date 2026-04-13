"""
Agent Arena — FastAPI Backend
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database.mongodb import connect_to_mongo, close_mongo_connection, create_indexes, check_health as mongo_health
from database.redis_client import connect_to_redis, close_redis_connection, check_health as redis_health

from routers import auth, agents, markets, predictions, battles, leaderboard, intel, websocket

# APScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from schedulers.market_fetcher import fetch_and_sync_markets
from schedulers.news_fetcher import refresh_news_cache
from schedulers.cricket_fetcher import fetch_cricket_scores
from schedulers.resolution_runner import resolve_expired_markets
from schedulers.ipl_market_seeder import seed_ipl_markets
from schedulers.ipl_resolver import resolve_ipl_markets
from schedulers.battle_updater import update_active_battles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Agent Arena starting up...")

    await connect_to_mongo()
    logger.info("MongoDB connected and indexes ensured")

    await connect_to_redis()
    logger.info("Redis connected")

    # Schedule background jobs
    scheduler.add_job(fetch_and_sync_markets, "interval", minutes=5, id="market_fetcher")
    scheduler.add_job(refresh_news_cache, "interval", minutes=15, id="news_fetcher")
    scheduler.add_job(fetch_cricket_scores, "interval", minutes=2, id="cricket_fetcher")
    scheduler.add_job(resolve_expired_markets, "interval", minutes=10, id="resolution_runner")
    scheduler.add_job(seed_ipl_markets, "interval", minutes=30, id="ipl_market_seeder")
    scheduler.add_job(resolve_ipl_markets, "interval", minutes=5, id="ipl_resolver")
    scheduler.add_job(update_active_battles, "interval", seconds=90, id="battle_updater")
    scheduler.start()
    logger.info("Schedulers started")

    # Initial market fetch on startup
    try:
        await fetch_and_sync_markets()
    except Exception as e:
        logger.warning(f"Initial Polymarket fetch failed (non-fatal): {e}")

    # Seed IPL markets from CricAPI on startup (if key is set)
    try:
        await seed_ipl_markets()
    except Exception as e:
        logger.warning(f"Initial IPL market seed failed (non-fatal): {e}")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Agent Arena shutting down...")
    scheduler.shutdown(wait=False)
    await close_mongo_connection()
    await close_redis_connection()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Agent Arena API",
    description="AI agent prediction market platform with LangGraph multi-agent architecture",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In development we accept any localhost port.  In production, replace the regex
# with the exact deployed origin (e.g. "https://agentarena.app").
_cors_origins = settings.allowed_origins  # explicit list for production
_cors_regex = r"http://localhost:\d+" if settings.environment == "development" else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
API_PREFIX = "/api"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(markets.router, prefix=API_PREFIX)
app.include_router(predictions.router, prefix=API_PREFIX)
app.include_router(battles.router, prefix=API_PREFIX)
app.include_router(leaderboard.router, prefix=API_PREFIX)
app.include_router(intel.router, prefix=API_PREFIX)
app.include_router(websocket.router)  # No /api prefix — WS at /ws/{user_id}


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    mongo_status = await mongo_health()
    redis_status = await redis_health()
    mongo_ok = mongo_status.get("status") == "healthy"
    redis_ok = redis_status.get("status") == "healthy"
    return {
        "status": "ok" if (mongo_ok and redis_ok) else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "mongodb": "healthy" if mongo_ok else "unhealthy",
            "redis": "healthy" if redis_ok else "unhealthy",
        },
    }


# ── Demo seed endpoint ────────────────────────────────────────────────────────
@app.post("/api/demo/seed")
async def seed_demo_data():
    """
    Seeds the database with sample markets for demo/development.
    Safe to call multiple times — uses upsert.
    """
    from database.mongodb import get_db

    db = get_db()
    now = datetime.utcnow()

    sample_markets = [
        {
            "external_id": "demo-ipl-mi-csk-001",
            "question": "Will Mumbai Indians beat Chennai Super Kings in today's IPL match?",
            "category": "ipl",
            "yes_price": 0.54,
            "no_price": 0.46,
            "volume_24h": 125000.0,
            "total_volume": 480000.0,
            "liquidity": 95000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 5, 15, 14, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
        {
            "external_id": "demo-ipl-rcb-kkr-002",
            "question": "Will RCB score 200+ against KKR at Eden Gardens?",
            "category": "ipl",
            "yes_price": 0.38,
            "no_price": 0.62,
            "volume_24h": 87000.0,
            "total_volume": 320000.0,
            "liquidity": 72000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 5, 20, 14, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
        {
            "external_id": "demo-geo-us-iran-003",
            "question": "Will the US impose new sanctions on Iran before June 2026?",
            "category": "geopolitics",
            "yes_price": 0.67,
            "no_price": 0.33,
            "volume_24h": 340000.0,
            "total_volume": 1200000.0,
            "liquidity": 280000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 6, 1, 0, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
        {
            "external_id": "demo-geo-nuclear-004",
            "question": "Will Iran resume nuclear talks with EU before end of 2026?",
            "category": "geopolitics",
            "yes_price": 0.43,
            "no_price": 0.57,
            "volume_24h": 198000.0,
            "total_volume": 750000.0,
            "liquidity": 165000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 12, 31, 0, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
        {
            "external_id": "demo-ipl-srh-dc-005",
            "question": "Will SunRisers Hyderabad qualify for IPL 2026 playoffs?",
            "category": "ipl",
            "yes_price": 0.71,
            "no_price": 0.29,
            "volume_24h": 62000.0,
            "total_volume": 220000.0,
            "liquidity": 55000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 5, 25, 0, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
        {
            "external_id": "demo-geo-russia-ukraine-006",
            "question": "Will there be a formal ceasefire between Russia and Ukraine in 2026?",
            "category": "geopolitics",
            "yes_price": 0.29,
            "no_price": 0.71,
            "volume_24h": 520000.0,
            "total_volume": 3200000.0,
            "liquidity": 480000.0,
            "is_resolved": False,
            "closes_at": datetime(2026, 12, 31, 0, 0, 0),
            "updated_at": now,
            "created_at": now,
        },
    ]

    seeded = 0
    for market in sample_markets:
        await db.markets.update_one(
            {"external_id": market["external_id"]},
            {"$set": market, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        seeded += 1

    return {"message": f"Seeded {seeded} demo markets", "count": seeded}
