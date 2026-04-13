import logging
from datetime import datetime
from bson import ObjectId
from database.mongodb import get_db
from models.battle import BattleDB, BattleParticipant, BattleResponse

logger = logging.getLogger(__name__)


async def add_agent_to_battle(
    market_id: str,
    market_question: str,
    market_category: str,
    agent_id: str,
    agent_name: str,
    agent_avatar: str,
    agent_color: str,
    agent_owner: str,          # user_id
    agent_owner_username: str,
    prediction: str,           # "YES" | "NO"
    confidence: int,
    reasoning: str,
) -> str:
    """
    One battle per market.  If an active battle already exists for this market,
    append this agent as a participant (unless they're already in it).
    If no battle exists, create one.
    Returns the battle_id.
    """
    db = get_db()

    participant = BattleParticipant(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_avatar=agent_avatar,
        agent_color=agent_color,
        agent_owner=agent_owner,
        agent_owner_username=agent_owner_username,
        prediction=prediction,
        confidence=confidence,
        reasoning=reasoning,
    )

    existing = await db.battles.find_one({"market_id": market_id, "status": "active"})

    if existing:
        battle_id = str(existing["_id"])

        # Check this agent isn't already a participant
        already_in = any(p["agent_id"] == agent_id for p in existing.get("participants", []))
        if already_in:
            logger.info(f"Agent {agent_id} already in battle {battle_id} — skipping")
            return battle_id

        await db.battles.update_one(
            {"_id": ObjectId(battle_id)},
            {"$push": {"participants": participant.model_dump()}},
        )
        n = len(existing.get("participants", [])) + 1
        logger.info(
            f"Agent {agent_name} joined battle {battle_id} "
            f"({n} participants, {prediction} @ {confidence}%)"
        )
    else:
        battle = BattleDB(
            market_id=market_id,
            market_question=market_question,
            market_category=market_category,
            participants=[participant],
        )
        result = await db.battles.insert_one(battle.model_dump(exclude={"id"}))
        battle_id = str(result.inserted_id)
        logger.info(
            f"Battle created: {battle_id} — {agent_name} is first participant "
            f"on '{market_question[:50]}'"
        )

    return battle_id


async def vote_on_battle(battle_id: str, user_id: str, voted_agent_id: str) -> BattleResponse:
    """
    Records a crowd vote for a specific participant.
    One vote per user per battle.
    """
    db = get_db()

    existing_vote = await db.battle_votes.find_one({
        "battle_id": battle_id,
        "user_id": user_id,
    })
    if existing_vote:
        raise ValueError("You already voted on this battle")

    # Verify the agent is a participant
    battle_doc = await db.battles.find_one({"_id": ObjectId(battle_id)})
    if not battle_doc:
        raise ValueError(f"Battle {battle_id} not found")

    participant_ids = [p["agent_id"] for p in battle_doc.get("participants", [])]
    if voted_agent_id not in participant_ids:
        raise ValueError("That agent is not a participant in this battle")

    # Record vote
    await db.battle_votes.insert_one({
        "battle_id": battle_id,
        "user_id": user_id,
        "voted_agent_id": voted_agent_id,
        "created_at": datetime.utcnow(),
    })

    # Increment that participant's crowd_votes using positional operator
    await db.battles.update_one(
        {"_id": ObjectId(battle_id), "participants.agent_id": voted_agent_id},
        {"$inc": {"participants.$.crowd_votes": 1}},
    )

    updated = await db.battles.find_one({"_id": ObjectId(battle_id)})
    updated["_id"] = str(updated["_id"])
    battle = BattleDB(**updated)

    market_doc = await db.markets.find_one({"external_id": battle.market_id})
    closes_at = market_doc.get("closes_at") if market_doc else None

    return BattleResponse.from_db(battle, battle_id, closes_at=closes_at)


async def resolve_battle(battle_id: str, market_outcome: str) -> None:
    """
    Resolves a battle.  All participants whose prediction matches the outcome win.
    Awards each winner a 50 INTEL battle bonus.
    """
    from services.intel_service import award_intel
    from models.intel import IntelTransactionType

    db = get_db()
    battle_doc = await db.battles.find_one({"_id": ObjectId(battle_id)})
    if not battle_doc:
        logger.warning(f"Battle {battle_id} not found for resolution")
        return

    battle_doc["_id"] = str(battle_doc["_id"])
    battle = BattleDB(**battle_doc)

    if battle.status == "resolved":
        return

    outcome_upper = market_outcome.upper()
    winner_ids = [
        p.agent_id for p in battle.participants
        if p.prediction.upper() == outcome_upper
    ]
    winner_names = [
        p.agent_name for p in battle.participants
        if p.agent_id in winner_ids
    ]

    resolution_reason = (
        f"Market resolved {outcome_upper}. "
        f"Winners: {', '.join(winner_names) if winner_names else 'None'}."
    )

    await db.battles.update_one(
        {"_id": ObjectId(battle_id)},
        {
            "$set": {
                "status": "resolved",
                "winner_agent_ids": winner_ids,
                "resolution_reason": resolution_reason,
                "resolved_at": datetime.utcnow(),
            }
        },
    )

    for participant in battle.participants:
        if participant.agent_id in winner_ids:
            await award_intel(
                agent_id=participant.agent_id,
                user_id=participant.agent_owner,
                amount=50,
                tx_type=IntelTransactionType.battle_win,
                description=f"Battle victory: {battle.market_question[:50]}",
                reference_id=battle_id,
            )

    logger.info(
        f"Battle resolved: id={battle_id} outcome={outcome_upper} "
        f"winners={winner_ids}"
    )
