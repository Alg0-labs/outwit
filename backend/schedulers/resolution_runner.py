import logging
from datetime import datetime
from database.mongodb import get_db
from utils.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


async def resolve_expired_markets() -> None:
    """
    Checks for markets that have passed their closes_at date and resolves them.
    Resolves all pending predictions on those markets.
    Runs every 10 minutes via APScheduler.

    Note: In production, market outcome should come from Polymarket's resolved
    outcome field. Here we use the current market yes_price to determine outcome
    (>0.95 → YES resolved, <0.05 → NO resolved).
    """
    db = get_db()
    now = datetime.utcnow()

    # Find markets that should be resolved
    expired = await db.markets.find({
        "is_resolved": False,
        "closes_at": {"$lt": now},
    }).to_list(50)

    if not expired:
        return

    logger.info(f"Resolution runner: found {len(expired)} expired markets")

    for market_doc in expired:
        market_id = market_doc.get("external_id", str(market_doc["_id"]))
        yes_price = market_doc.get("yes_price", 0.5)

        # Determine resolved outcome based on final market price
        if yes_price >= 0.95:
            resolved_outcome = "yes"
        elif yes_price <= 0.05:
            resolved_outcome = "no"
        else:
            # Market not decisively resolved — skip for now
            logger.info(f"Market {market_id} not decisively resolved (yes_price={yes_price:.2f}) — skipping")
            continue

        logger.info(f"Resolving market {market_id}: outcome={resolved_outcome}")

        # Mark market as resolved
        await db.markets.update_one(
            {"_id": market_doc["_id"]},
            {"$set": {"is_resolved": True, "resolved_outcome": resolved_outcome, "updated_at": now}},
        )

        # Resolve all pending predictions on this market
        pending_preds = await db.predictions.find({
            "market_id": market_id,
            "status": "pending",
        }).to_list(500)

        for pred in pending_preds:
            pred_id = str(pred["_id"])
            try:
                from services.prediction_service import resolve_prediction
                await resolve_prediction(pred_id, resolved_outcome)

                # Notify user via WebSocket
                user_id = pred.get("user_id")
                if user_id:
                    won = pred.get("predicted_outcome") == resolved_outcome
                    await ws_manager.send_to_user(
                        user_id,
                        "prediction_resolved",
                        {
                            "prediction_id": pred_id,
                            "market_question": pred.get("market_question", ""),
                            "outcome": resolved_outcome,
                            "won": won,
                        },
                    )
            except Exception as e:
                logger.error(f"Failed to resolve prediction {pred_id}: {e}")

        # Resolve active battles on this market
        active_battles = await db.battles.find({
            "market_id": market_id,
            "status": "active",
        }).to_list(100)

        for battle in active_battles:
            battle_id = str(battle["_id"])
            try:
                from services.battle_service import resolve_battle
                await resolve_battle(battle_id, resolved_outcome)

                # Broadcast battle resolution
                await ws_manager.broadcast(
                    "battle_update",
                    {
                        "battle_id": battle_id,
                        "status": "resolved",
                        "market_outcome": resolved_outcome,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to resolve battle {battle_id}: {e}")

        logger.info(f"Market {market_id} fully resolved: {len(pending_preds)} predictions, {len(active_battles)} battles settled")
