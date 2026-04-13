import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from database.mongodb import get_db
from models.prediction import CreatePredictionRequest, PredictionResponse, PredictionDB
from services.prediction_service import run_prediction
from utils.jwt_handler import get_user_id_from_token

router = APIRouter(prefix="/predictions", tags=["predictions"])
bearer = HTTPBearer()
logger = logging.getLogger(__name__)


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@router.post("", response_model=PredictionResponse, status_code=201)
async def create_prediction(body: CreatePredictionRequest, user_id: str = Depends(get_current_user_id)):
    db = get_db()

    # Get user's agent
    agent = await db.agents.find_one({"user_id": user_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Create an agent first before making predictions")

    agent_id = str(agent["_id"])

    try:
        prediction = await run_prediction(
            agent_id=agent_id,
            user_id=user_id,
            market_id=body.market_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Prediction pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Prediction pipeline failed. Please try again.")

    return prediction


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: str, user_id: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        doc = await db.predictions.find_one({"_id": ObjectId(prediction_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid prediction ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Prediction not found")

    doc_id = str(doc["_id"])
    doc["_id"] = doc_id
    p = PredictionDB(**doc)

    # Only allow viewing own predictions
    if p.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your prediction")

    return PredictionResponse.from_db(p, doc_id)
