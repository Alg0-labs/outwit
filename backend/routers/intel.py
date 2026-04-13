from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database.mongodb import get_db
from models.intel import DailyLoginResponse, IntelTransactionDB
from services.intel_service import claim_daily_login
from utils.jwt_handler import get_user_id_from_token
from bson import ObjectId

router = APIRouter(prefix="/intel", tags=["intel"])
bearer = HTTPBearer()


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@router.get("/balance")
async def get_balance(user_id: str = Depends(get_current_user_id)):
    db = get_db()
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found")
    return {"intel_balance": agent.get("intel_balance", 0), "agent_id": str(agent["_id"])}


@router.get("/transactions")
async def get_transactions(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
):
    db = get_db()
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found")

    agent_id = str(agent["_id"])
    cursor = db.intel_transactions.find({"agent_id": agent_id}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(limit)

    results = []
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


@router.post("/claim-daily", response_model=DailyLoginResponse)
async def claim_daily(user_id: str = Depends(get_current_user_id)):
    db = get_db()
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found. Create an agent first.")

    agent_id = str(agent["_id"])
    try:
        result = await claim_daily_login(user_id=user_id, agent_id=agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DailyLoginResponse(**result)
