from typing import List
from fastapi import APIRouter, Query
from database.mongodb import get_db
from models.agent import AgentDB, AgentPublicResponse

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("", response_model=List[AgentPublicResponse])
async def get_leaderboard(
    sort_by: str = Query(default="reputation_score", pattern="^(reputation_score|win_count|intel_balance)$"),
    limit: int = Query(default=20, ge=1, le=100),
):
    db = get_db()
    cursor = db.agents.find({}).sort(sort_by, -1).limit(limit)
    docs = await cursor.to_list(limit)

    results = []
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        a = AgentDB(**doc)
        results.append(AgentPublicResponse(
            id=doc["_id"],
            name=a.name,
            avatar_id=a.avatar_id,
            color_theme=a.color_theme,
            domain_expertise=a.domain_expertise,
            reasoning_style=a.reasoning_style,
            reputation_score=a.reputation_score,
            win_rate=a.win_rate,
            total_predictions=a.total_predictions,
            current_streak=a.current_streak,
            intel_balance=a.intel_balance,
        ))
    return results
