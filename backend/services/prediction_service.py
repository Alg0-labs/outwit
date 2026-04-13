import logging
from datetime import datetime
from bson import ObjectId
from database.mongodb import get_db
from database.redis_client import get_redis, increment_counter, get_counter
from agentic.graph import graph
from agentic.state import AgentArenaState
from models.prediction import PredictionDB, PredictionResponse
from models.agent import AgentDB
from models.market import MarketDB
from services.intel_service import deduct_wager, award_intel
from services.reputation_service import update_agent_memory
from models.intel import IntelTransactionType
from config import settings

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds


async def _check_rate_limit(agent_id: str) -> None:
    """Raises ValueError if agent has exceeded prediction rate limit."""
    key = f"rate_limit:predictions:{agent_id}"
    count = await get_counter(key)
    if count >= settings.prediction_rate_limit:
        raise ValueError(
            f"Rate limit exceeded: max {settings.prediction_rate_limit} predictions per hour"
        )


async def _increment_rate_limit(agent_id: str) -> None:
    key = f"rate_limit:predictions:{agent_id}"
    await increment_counter(key, ttl=RATE_LIMIT_WINDOW)


async def run_prediction(
    agent_id: str,
    user_id: str,
    market_id: str,
) -> PredictionResponse:
    """
    Full prediction pipeline:
    1. Rate limit check
    2. Load agent + market from DB
    3. Deduct wager
    4. Run LangGraph pipeline
    5. Save prediction to DB
    6. Check for battle creation opportunity
    7. Trigger memory update every 10 predictions
    """
    db = get_db()

    # 1. Rate limit
    await _check_rate_limit(agent_id)

    # 2. Load agent
    agent_doc = await db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent_doc:
        raise ValueError(f"Agent {agent_id} not found")
    agent_doc["_id"] = str(agent_doc["_id"])
    agent = AgentDB(**agent_doc)

    # 3. Load market (by external_id string first, then ObjectId)
    market_doc = await db.markets.find_one({"external_id": market_id})
    if not market_doc:
        try:
            market_doc = await db.markets.find_one({"_id": ObjectId(market_id)})
        except Exception:
            pass
    if not market_doc:
        raise ValueError(f"Market {market_id} not found")
    market_doc["_id"] = str(market_doc["_id"])
    market = MarketDB(**market_doc)

    if market.is_resolved:
        raise ValueError("Market is already resolved")

    # Prevent duplicate prediction on same market
    existing_pred = await db.predictions.find_one({
        "agent_id": agent_id,
        "market_id": market_id,
        "status": {"$in": ["pending", "won", "lost"]},
    })
    if existing_pred:
        raise ValueError("Your agent already made a prediction on this market")

    # Determine wager — will be decided by graph, use a placeholder for deduction
    # We'll deduct the final amount after the graph runs
    # First run the graph to know how much to wager
    initial_state: AgentArenaState = {
        "market_id": market_id,
        "market_question": market.question,
        "market_category": market.category,
        "yes_price": market.yes_price,
        "no_price": market.no_price,
        "volume_24h": market.volume_24h,
        "agent_name": agent.name,
        "agent_reasoning_style": agent.reasoning_style,
        "agent_risk_profile": agent.risk_profile,
        "agent_domain_expertise": agent.domain_expertise,
        "agent_memory": agent.memory.model_dump(),
    }

    logger.info(f"Starting prediction pipeline: agent={agent.name} market={market.question[:60]}")

    # 4. Run graph
    final_state = await graph.ainvoke(initial_state)

    intel_to_wager = final_state.get("intel_to_wager", 25)

    # Check balance before deducting
    if agent.intel_balance < intel_to_wager:
        intel_to_wager = agent.intel_balance  # wager everything they have
    if intel_to_wager <= 0:
        raise ValueError("Insufficient INTEL balance to make a prediction")

    # 5. Deduct wager
    await deduct_wager(agent_id, intel_to_wager)

    # Also create a bet_loss transaction placeholder (refunded on win)
    await db.intel_transactions.insert_one({
        "agent_id": agent_id,
        "user_id": user_id,
        "amount": -intel_to_wager,
        "type": "wager",
        "description": f"Wager on: {market.question[:60]}",
        "running_balance": agent.intel_balance - intel_to_wager,
        "created_at": datetime.utcnow(),
    })

    # 6. Save prediction
    prediction = PredictionDB(
        agent_id=agent_id,
        user_id=user_id,
        market_id=market_id,
        market_question=market.question,
        market_category=market.category,
        predicted_outcome=final_state.get("prediction_outcome", "yes"),
        confidence_score=final_state.get("confidence_score", 55),
        intel_wagered=intel_to_wager,
        reasoning_text=final_state.get("reasoning_text", ""),
        key_signal=final_state.get("key_signal", ""),
        specialist_outputs=final_state.get("specialist_outputs", {}),
    )

    pred_doc = prediction.model_dump(exclude={"id"})
    result = await db.predictions.insert_one(pred_doc)
    prediction_id = str(result.inserted_id)

    logger.info(f"Prediction saved: id={prediction_id} outcome={prediction.predicted_outcome} confidence={prediction.confidence_score}")

    # 7. Rate limit increment
    await _increment_rate_limit(agent_id)

    # 8. Add to / create battle for this market
    try:
        await _maybe_create_battle(agent_id, market_id, prediction, agent, user_id, db)
    except Exception as e:
        logger.warning(f"Battle upsert failed (non-fatal): {e}")

    # 9. Memory update every 10 predictions
    try:
        total = agent.win_count + agent.loss_count + 1  # +1 for this pending
        if total % 10 == 0:
            await update_agent_memory(agent_id)
    except Exception as e:
        logger.warning(f"Memory update failed (non-fatal): {e}")

    return PredictionResponse.from_db(prediction, prediction_id)


async def _maybe_create_battle(
    agent_id: str,
    market_id: str,
    prediction: "PredictionDB",
    agent: "AgentDB",
    user_id: str,
    db,
) -> None:
    """
    One battle per market.  Adds this agent as a participant (creating the battle
    if it's the first prediction on this market).
    """
    from services.battle_service import add_agent_to_battle

    # Look up username for display in battle card
    user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
    username = user_doc["username"] if user_doc else user_id

    await add_agent_to_battle(
        market_id=market_id,
        market_question=prediction.market_question,
        market_category=prediction.market_category,
        agent_id=agent_id,
        agent_name=agent.name,
        agent_avatar=agent.avatar_id,
        agent_color=agent.color_theme,
        agent_owner=user_id,
        agent_owner_username=username,
        prediction=prediction.predicted_outcome.upper(),
        confidence=prediction.confidence_score,
        reasoning=prediction.reasoning_text,
    )


async def resolve_prediction(
    prediction_id: str,
    market_resolved_outcome: str,  # "yes" or "no"
) -> None:
    """
    Called by resolution_runner when a market settles.
    Updates prediction status, awards/deducts INTEL, updates reputation.
    """
    from services.intel_service import calculate_win_payout, award_intel
    from services.reputation_service import update_agent_reputation

    db = get_db()
    pred_doc = await db.predictions.find_one({"_id": ObjectId(prediction_id)})
    if not pred_doc:
        logger.warning(f"Prediction {prediction_id} not found for resolution")
        return

    if pred_doc.get("status") != "pending":
        return  # already resolved

    pred_doc["_id"] = str(pred_doc["_id"])
    prediction = PredictionDB(**pred_doc)

    won = prediction.predicted_outcome == market_resolved_outcome

    if won:
        payout = calculate_win_payout(prediction.intel_wagered, prediction.confidence_score)
        intel_delta = payout  # net gain (wager already deducted)
        new_status = "won"
        description = f"Won prediction: {prediction.market_question[:50]} (+{payout} INTEL)"
    else:
        intel_delta = -prediction.intel_wagered  # already deducted, just record the loss
        new_status = "lost"
        description = f"Lost prediction: {prediction.market_question[:50]}"

    now = datetime.utcnow()

    await db.predictions.update_one(
        {"_id": ObjectId(prediction_id)},
        {
            "$set": {
                "status": new_status,
                "intel_delta": intel_delta,
                "resolved_at": now,
            }
        },
    )

    # Award payout if won
    if won:
        await award_intel(
            agent_id=prediction.agent_id,
            user_id=prediction.user_id,
            amount=payout,
            tx_type=IntelTransactionType.bet_win,
            description=description,
            reference_id=prediction_id,
        )

    # Update reputation
    await update_agent_reputation(
        agent_id=prediction.agent_id,
        prediction_status=new_status,
        confidence_score=prediction.confidence_score,
        market_category=prediction.market_category,
    )

    logger.info(
        f"Prediction resolved: id={prediction_id} status={new_status} "
        f"intel_delta={intel_delta:+d}"
    )
