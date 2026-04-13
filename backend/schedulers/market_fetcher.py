import ast
import logging
from datetime import datetime
from database.mongodb import get_db
from agentic.tools.polymarket_tool import fetch_markets_by_category, classify_market

logger = logging.getLogger(__name__)


async def fetch_and_sync_markets() -> None:
    """
    Fetches IPL and geopolitics markets from Polymarket using the /events?tag_slug=X
    endpoint (much cleaner than the generic /markets endpoint).
    Runs every 5 minutes via APScheduler.
    """
    logger.info("Scheduler: fetching tagged markets from Polymarket...")
    db = get_db()

    # Bust Redis cache so every run gets a fresh batch
    from database.redis_client import get_redis
    redis = get_redis()
    if redis:
        try:
            await redis.delete("polymarket:tagged_markets")
            await redis.delete("polymarket:all_markets")
        except Exception:
            pass

    try:
        tagged_markets = await fetch_markets_by_category()
    except Exception as e:
        logger.error(f"Market fetch failed: {e}")
        return

    synced = 0
    for market, category in tagged_markets:
        external_id = market.get("id") or market.get("conditionId", "")
        question = market.get("question", "").strip()
        if not external_id or not question:
            continue

        yes_price, no_price = _parse_prices(market.get("outcomePrices"))

        doc = {
            "external_id": external_id,
            "question": question,
            "category": category,
            "yes_price": yes_price,
            "no_price": no_price,
            "volume_24h": _safe_float(market.get("volume24hr") or market.get("volume24Hour", 0)),
            "total_volume": _safe_float(market.get("volume", 0)),
            "liquidity": _safe_float(market.get("liquidity", 0)),
            "is_resolved": bool(market.get("closed", False)),
            "closes_at": _parse_date(market.get("endDate")),
            "updated_at": datetime.utcnow(),
        }

        if not doc["closes_at"]:
            continue  # skip markets with no close date

        await db.markets.update_one(
            {"external_id": external_id},
            {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )
        synced += 1

    logger.info(f"Scheduler: synced {synced} Polymarket markets")

    # Purge any stale markets that are no longer valid
    await _purge_stale_markets(db)


async def _purge_stale_markets(db) -> None:
    """
    Remove markets from DB that:
    - Are now resolved/closed on Polymarket side
    - Don't match our two categories
    Excludes demo markets and CricAPI-sourced markets (they are managed by ipl_market_seeder).
    """
    all_stored = await db.markets.find(
        {
            "external_id": {"$not": {"$regex": "^demo-"}},
            "source": {"$ne": "cricapi"},
        }
    ).to_list(1000)

    to_delete = []
    for doc in all_stored:
        q = doc.get("question", "")
        cat = doc.get("category", "")
        # geopolitics markets come from the geopolitics tag — always valid category
        # ipl markets must pass the keyword check
        if cat == "ipl" and not classify_market(q):
            to_delete.append(doc["_id"])
        elif cat not in ("ipl", "geopolitics"):
            to_delete.append(doc["_id"])

    if to_delete:
        result = await db.markets.delete_many({"_id": {"$in": to_delete}})
        logger.info(f"Purged {result.deleted_count} stale/misclassified markets")


def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except Exception:
        return 0.0


def _parse_prices(raw) -> tuple[float, float]:
    try:
        if raw is None:
            return 0.5, 0.5
        if isinstance(raw, str):
            parsed = ast.literal_eval(raw)
        else:
            parsed = raw
        yes = float(parsed[0]) if len(parsed) > 0 else 0.5
        no = float(parsed[1]) if len(parsed) > 1 else round(1.0 - yes, 4)
        return yes, no
    except Exception:
        return 0.5, 0.5


def _parse_date(date_str) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
