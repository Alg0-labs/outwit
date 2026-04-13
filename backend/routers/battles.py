import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from database.mongodb import get_db
from models.battle import BattleDB, BattleResponse, VoteRequest
from services.battle_service import vote_on_battle
from utils.jwt_handler import get_user_id_from_token

router = APIRouter(prefix="/battles", tags=["battles"])
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[str]:
    if not credentials:
        return None
    return get_user_id_from_token(credentials.credentials)


async def require_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> str:
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@router.get("", response_model=List[BattleResponse])
async def list_battles(
    status: str = Query(default="active", pattern="^(active|resolved)$"),
    limit: int = Query(default=20, ge=1, le=100),
    min_participants: int = Query(default=1, ge=1, le=50),
):
    """
    Returns active battles from Polymarket markets.
    A battle is created when any agent predicts on a market.
    Multiple agents can join the same battle.
    """
    db = get_db()

    pipeline = [
        {"$match": {"status": status}},
        {"$addFields": {"participant_count": {"$size": "$participants"}}},
        {"$match": {"participant_count": {"$gte": min_participants}}},
        {"$sort": {"participant_count": -1, "created_at": -1}},
        {"$limit": limit},
    ]

    docs = await db.battles.aggregate(pipeline).to_list(limit)

    results = []
    for doc in docs:
        doc_id = str(doc["_id"])
        doc["_id"] = doc_id
        battle = BattleDB(**doc)

        market_doc = await db.markets.find_one({"external_id": battle.market_id})
        closes_at = market_doc.get("closes_at") if market_doc else None

        results.append(BattleResponse.from_db(battle, doc_id, closes_at=closes_at))
    return results


@router.get("/{battle_id}", response_model=BattleResponse)
async def get_battle(battle_id: str):
    db = get_db()
    try:
        doc = await db.battles.find_one({"_id": ObjectId(battle_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid battle ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Battle not found")

    doc_id = str(doc["_id"])
    doc["_id"] = doc_id
    battle = BattleDB(**doc)

    market_doc = await db.markets.find_one({"external_id": battle.market_id})
    closes_at = market_doc.get("closes_at") if market_doc else None

    return BattleResponse.from_db(battle, doc_id, closes_at=closes_at)


@router.get("/{battle_id}/live-feed")
async def get_live_feed(battle_id: str):
    """
    Returns live cricket score + recent news for a battle's market.
    Polled every 30s by the BattlePage.
    """
    import json as _json
    from database.redis_client import get_redis

    db = get_db()
    try:
        battle_doc = await db.battles.find_one({"_id": ObjectId(battle_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid battle ID")
    if not battle_doc:
        raise HTTPException(status_code=404, detail="Battle not found")

    market_id = battle_doc.get("market_id", "")
    market_doc = await db.markets.find_one({"external_id": market_id})
    source = market_doc.get("source", "polymarket") if market_doc else "polymarket"
    category = battle_doc.get("market_category", "")

    feed: dict = {
        "source": source,
        "category": category,
        "market_question": battle_doc.get("market_question", ""),
        "match_score": None,
        "match_status": None,
        "news": [],
    }

    # ── Live cricket score (CricAPI markets only) ─────────────────────────────
    # Uses the Redis-cached helper from cricket_tool — all callers share the same
    # 30s cache entry per match_id, so multiple users viewing the page simultaneously
    # don't each burn a separate API call.
    if source == "cricapi" and market_doc:
        cricapi_match_id = market_doc.get("match_id", "")
        if cricapi_match_id:
            try:
                from agentic.tools.cricket_tool import _fetch_match_info
                mi = await _fetch_match_info(cricapi_match_id)
                if mi:
                    feed["match_status"] = mi.get("status", "")
                    feed["match_started"] = mi.get("matchStarted", False)
                    feed["match_ended"] = mi.get("matchEnded", False)
                    feed["venue"] = mi.get("venue", "")
                    toss = mi.get("toss", {})
                    if toss and isinstance(toss, dict) and toss.get("winner"):
                        feed["toss"] = f"{toss['winner']} won toss, chose to {toss.get('decision', '?')}"
                    score = mi.get("score", [])
                    if score:
                        feed["match_score"] = [
                            {
                                "inning": s.get("inning", ""),
                                "runs": s.get("r", 0),
                                "wickets": s.get("w", 0),
                                "overs": s.get("o", ""),
                            }
                            for s in score
                        ]
            except Exception as e:
                logger.warning(f"Live feed: CricAPI fetch failed: {e}")

    # ── News from Redis cache ─────────────────────────────────────────────────
    redis = get_redis()
    if redis:
        try:
            cache_key = f"news:{category}"
            raw = await redis.get(cache_key)
            if raw:
                articles = _json.loads(raw)
                feed["news"] = articles[:5]  # top 5 headlines
        except Exception as e:
            logger.warning(f"Live feed: news cache read failed: {e}")

    return feed


@router.get("/{battle_id}/thoughts")
async def get_battle_thoughts(battle_id: str, limit: int = Query(default=30, ge=1, le=100)):
    """
    Returns the latest live thoughts from agents during an active CricAPI battle.
    Polled every 20s by BattlePage to show live debate updates.
    """
    db = get_db()
    thoughts = await db.battle_thoughts.find(
        {"battle_id": battle_id}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    result = []
    for t in thoughts:
        result.append({
            "id": str(t["_id"]),
            "battle_id": t.get("battle_id", ""),
            "agent_id": t.get("agent_id", ""),
            "agent_name": t.get("agent_name", ""),
            "agent_color": t.get("agent_color", "#6366f1"),
            "agent_avatar": t.get("agent_avatar", "bot"),
            "prediction": t.get("prediction", ""),
            "confidence": t.get("confidence", 50),
            "confidence_delta": t.get("confidence_delta", 0),
            "thought": t.get("thought", ""),
            "reasoning": t.get("reasoning", ""),
            "match_context": t.get("match_context", ""),
            "created_at": t.get("created_at", "").isoformat() if hasattr(t.get("created_at", ""), "isoformat") else str(t.get("created_at", "")),
        })

    # Return chronological order (oldest first for rendering)
    result.reverse()
    return result


@router.post("/{battle_id}/vote", response_model=BattleResponse)
async def vote(
    battle_id: str,
    body: VoteRequest,
    user_id: str = Depends(require_user_id),
):
    """Vote for a specific participant in a battle."""
    try:
        return await vote_on_battle(battle_id, user_id, body.agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
