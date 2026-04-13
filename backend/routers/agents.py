import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from database.mongodb import get_db
from models.agent import AgentDB, AgentResponse, AgentPublicResponse, CreateAgentRequest, UpdateAgentRequest
from models.prediction import PredictionResponse, PredictionDB
from utils.jwt_handler import get_user_id_from_token

router = APIRouter(prefix="/agents", tags=["agents"])
bearer = HTTPBearer()
logger = logging.getLogger(__name__)


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(body: CreateAgentRequest, user_id: str = Depends(get_current_user_id)):
    db = get_db()

    # One agent per user
    existing = await db.agents.find_one({"user_id": user_id})
    if existing:
        raise HTTPException(status_code=409, detail="You already have an agent. Update it instead.")

    # Name uniqueness
    if await db.agents.find_one({"name": body.name}):
        raise HTTPException(status_code=409, detail="Agent name already taken")

    agent = AgentDB(
        user_id=user_id,
        name=body.name,
        avatar_id=body.avatar_id,
        color_theme=body.color_theme,
        domain_expertise=body.domain_expertise,
        reasoning_style=body.reasoning_style,
        risk_profile=body.risk_profile,
    )

    doc = agent.model_dump(exclude={"id"})
    result = await db.agents.insert_one(doc)
    agent_id = str(result.inserted_id)

    # Award initial INTEL grant
    from services.intel_service import award_intel
    from models.intel import IntelTransactionType
    await award_intel(
        agent_id=agent_id,
        user_id=user_id,
        amount=500,
        tx_type=IntelTransactionType.initial_grant,
        description="Welcome to Agent Arena! Starting INTEL balance.",
    )

    logger.info(f"Agent created: {body.name} for user={user_id}")

    agent_doc = await db.agents.find_one({"_id": ObjectId(agent_id)})
    agent_doc["_id"] = str(agent_doc["_id"])
    agent_obj = AgentDB(**agent_doc)
    return AgentResponse.from_db(agent_obj)


@router.get("/me", response_model=AgentResponse)
async def get_my_agent(user_id: str = Depends(get_current_user_id)):
    db = get_db()
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found. Create one first.")
    agent["_id"] = str(agent["_id"])
    return AgentResponse.from_db(AgentDB(**agent))


@router.patch("/me", response_model=AgentResponse)
async def update_my_agent(body: UpdateAgentRequest, user_id: str = Depends(get_current_user_id)):
    db = get_db()
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found")

    updates = body.model_dump(exclude_none=True)
    if "name" in updates:
        conflict = await db.agents.find_one({"name": updates["name"], "user_id": {"$ne": user_id}})
        if conflict:
            raise HTTPException(status_code=409, detail="Agent name already taken")

    updates["updated_at"] = datetime.utcnow()
    await db.agents.update_one({"user_id": user_id}, {"$set": updates})

    updated = await db.agents.find_one({"user_id": user_id})
    updated["_id"] = str(updated["_id"])
    return AgentResponse.from_db(AgentDB(**updated))


@router.get("/{agent_id}", response_model=AgentPublicResponse)
async def get_agent(agent_id: str):
    db = get_db()
    try:
        agent = await db.agents.find_one({"_id": ObjectId(agent_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid agent ID")
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent["_id"] = str(agent["_id"])
    a = AgentDB(**agent)
    return AgentPublicResponse(
        id=str(agent["_id"]),
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
    )


@router.get("/{agent_id}/predictions", response_model=List[PredictionResponse])
async def get_agent_predictions(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
):
    db = get_db()
    query: dict = {"agent_id": agent_id}
    if status:
        query["status"] = status

    cursor = db.predictions.find(query).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(limit)

    results = []
    for doc in docs:
        doc_id = str(doc["_id"])
        doc["_id"] = doc_id
        p = PredictionDB(**doc)
        results.append(PredictionResponse.from_db(p, doc_id))
    return results
