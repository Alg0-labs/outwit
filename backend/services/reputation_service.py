import logging
from datetime import datetime
from bson import ObjectId
from database.mongodb import get_db

logger = logging.getLogger(__name__)


def calculate_reputation_delta(
    status: str,
    confidence_score: int,
    market_category: str,
    agent_expertise: list[str],
    current_streak: int,
) -> float:
    """
    Calculates reputation change for a resolved prediction.
    """
    if status == "won":
        base = 15.0
        confidence_bonus = 10.0 if confidence_score > 70 else 0.0
        domain_bonus = 5.0 if market_category in agent_expertise else 0.0
        streak_multiplier = 1.2 if current_streak >= 3 else 1.0
        return round((base + confidence_bonus + domain_bonus) * streak_multiplier, 2)

    elif status == "lost":
        base = -8.0
        overconfidence_penalty = -5.0 if confidence_score > 80 else 0.0
        return round(base + overconfidence_penalty, 2)

    return 0.0


async def update_agent_reputation(
    agent_id: str,
    prediction_status: str,
    confidence_score: int,
    market_category: str,
) -> float:
    """
    Updates agent reputation score and win/loss stats after a prediction resolves.
    Returns the new reputation score.
    """
    db = get_db()
    agent = await db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    expertise = agent.get("domain_expertise", [])
    current_streak = agent.get("current_streak", 0)
    current_rep = agent.get("reputation_score", 0.0)

    delta = calculate_reputation_delta(
        status=prediction_status,
        confidence_score=confidence_score,
        market_category=market_category,
        agent_expertise=expertise,
        current_streak=current_streak,
    )

    # Update streak
    if prediction_status == "won":
        new_streak = current_streak + 1
        new_win = agent.get("win_count", 0) + 1
        new_loss = agent.get("loss_count", 0)
    elif prediction_status == "lost":
        new_streak = 0
        new_win = agent.get("win_count", 0)
        new_loss = agent.get("loss_count", 0) + 1
    else:
        new_streak = current_streak
        new_win = agent.get("win_count", 0)
        new_loss = agent.get("loss_count", 0)

    new_rep = max(0.0, min(1000.0, current_rep + delta))

    await db.agents.update_one(
        {"_id": ObjectId(agent_id)},
        {
            "$set": {
                "reputation_score": round(new_rep, 2),
                "current_streak": new_streak,
                "win_count": new_win,
                "loss_count": new_loss,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    logger.info(
        f"Reputation updated: agent={agent_id} "
        f"delta={delta:+.1f} ({current_rep:.1f} → {new_rep:.1f}) "
        f"streak={new_streak}"
    )
    return new_rep


async def update_agent_memory(agent_id: str) -> None:
    """
    After every 10 predictions, call Claude to update agent's learned biases
    and confidence calibration based on their prediction history.
    TODO: This is a background job — trigger via scheduler or post-resolution hook.
    """
    db = get_db()
    agent = await db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        return

    total = agent.get("win_count", 0) + agent.get("loss_count", 0)
    if total % 10 != 0 or total == 0:
        return

    # Fetch last 20 predictions for analysis
    predictions = await db.predictions.find(
        {"agent_id": agent_id, "status": {"$in": ["won", "lost"]}},
        sort=[("created_at", -1)],
        limit=20,
    ).to_list(20)

    if not predictions:
        return

    # Calculate domain accuracy
    domain_stats: dict[str, dict] = {}
    confidence_errors = []

    for pred in predictions:
        category = pred.get("market_category", "unknown")
        won = pred.get("status") == "won"
        confidence = pred.get("confidence_score", 60)

        if category not in domain_stats:
            domain_stats[category] = {"wins": 0, "total": 0}
        domain_stats[category]["total"] += 1
        if won:
            domain_stats[category]["wins"] += 1

        # Calibration: did confidence match accuracy?
        expected_p = confidence / 100
        actual = 1.0 if won else 0.0
        confidence_errors.append(abs(expected_p - actual))

    domain_accuracy = {
        cat: round(stats["wins"] / stats["total"], 2)
        for cat, stats in domain_stats.items()
        if stats["total"] > 0
    }

    recent_wins = sum(1 for p in predictions if p.get("status") == "won")
    recent_accuracy = round(recent_wins / len(predictions), 2)

    avg_error = sum(confidence_errors) / len(confidence_errors) if confidence_errors else 0.3
    calibration = max(0.5, min(1.5, 1.0 - (avg_error - 0.2)))

    # TODO: Add Claude call here to generate natural language history_summary
    # and update learned_biases based on systematic patterns in predictions

    await db.agents.update_one(
        {"_id": ObjectId(agent_id)},
        {
            "$set": {
                "memory.domain_accuracy": domain_accuracy,
                "memory.recent_accuracy": recent_accuracy,
                "memory.confidence_calibration": round(calibration, 2),
                "memory.last_updated": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
    )

    logger.info(
        f"Memory updated: agent={agent_id} "
        f"recent_accuracy={recent_accuracy:.0%} "
        f"calibration={calibration:.2f}"
    )
