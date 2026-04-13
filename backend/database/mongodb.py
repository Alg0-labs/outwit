from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from config import settings
import logging

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient | None = None
db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo():
    global client, db
    try:
        client = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
        )
        # Verify connection
        await client.admin.command("ping")
        db = client.get_default_database()
        logger.info(f"Connected to MongoDB: {settings.mongodb_url}")
        await create_indexes()
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise


async def close_mongo_connection():
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


async def create_indexes():
    """Create all required indexes for performance."""
    try:
        # Users
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)

        # Agents
        await db.agents.create_index("user_id")
        await db.agents.create_index([("reputation_score", DESCENDING)])
        await db.agents.create_index([("intel_balance", DESCENDING)])

        # Predictions
        await db.predictions.create_index([("agent_id", ASCENDING), ("status", ASCENDING)])
        await db.predictions.create_index("user_id")
        await db.predictions.create_index("market_id")
        await db.predictions.create_index([("created_at", DESCENDING)])

        # Markets
        await db.markets.create_index("external_id", unique=True)
        await db.markets.create_index([("category", ASCENDING), ("is_resolved", ASCENDING)])
        await db.markets.create_index("closes_at")

        # Battles
        await db.battles.create_index("status")
        await db.battles.create_index("market_id")
        await db.battles.create_index([("agent_a_id", ASCENDING), ("agent_b_id", ASCENDING)])

        # Intel transactions
        await db.intel_transactions.create_index([("agent_id", ASCENDING), ("created_at", DESCENDING)])
        await db.intel_transactions.create_index("user_id")

        # Battle thoughts (live agent updates)
        await db.battle_thoughts.create_index([("battle_id", ASCENDING), ("created_at", DESCENDING)])
        await db.battle_thoughts.create_index([("battle_id", ASCENDING), ("agent_id", ASCENDING), ("created_at", DESCENDING)])

        logger.info("MongoDB indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


def get_db() -> AsyncIOMotorDatabase:
    return db


async def check_health() -> dict:
    try:
        await client.admin.command("ping")
        return {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
