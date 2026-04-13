from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class PredictionStatus(str, Enum):
    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"


class PredictionOutcome(str, Enum):
    yes = "yes"
    no = "no"


# ── DB document ───────────────────────────────────────────────────────────────
class PredictionDB(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    agent_id: str
    user_id: str
    market_id: str
    market_question: str
    market_category: str
    predicted_outcome: str  # "yes" | "no"
    confidence_score: int = Field(ge=40, le=95)
    intel_wagered: int
    reasoning_text: str
    key_signal: str
    specialist_outputs: Dict[str, Any] = Field(default_factory=dict)
    status: PredictionStatus = PredictionStatus.pending
    intel_delta: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ── Request schemas ───────────────────────────────────────────────────────────
class CreatePredictionRequest(BaseModel):
    market_id: str = Field(..., description="Market external_id from /api/markets")


# ── Response schemas ──────────────────────────────────────────────────────────
class PredictionResponse(BaseModel):
    id: str
    agent_id: str
    market_id: str
    market_question: str
    market_category: str
    predicted_outcome: str
    confidence_score: int
    intel_wagered: int
    reasoning_text: str
    key_signal: str
    status: str
    intel_delta: int
    created_at: datetime
    resolved_at: Optional[datetime] = None

    @classmethod
    def from_db(cls, p: PredictionDB, doc_id: str) -> "PredictionResponse":
        return cls(
            id=doc_id,
            agent_id=p.agent_id,
            market_id=p.market_id,
            market_question=p.market_question,
            market_category=p.market_category,
            predicted_outcome=p.predicted_outcome,
            confidence_score=p.confidence_score,
            intel_wagered=p.intel_wagered,
            reasoning_text=p.reasoning_text,
            key_signal=p.key_signal,
            status=p.status,
            intel_delta=p.intel_delta,
            created_at=p.created_at,
            resolved_at=p.resolved_at,
        )


class PredictionStreamChunk(BaseModel):
    """Sent via WebSocket during streaming prediction generation."""
    type: str  # "reasoning_chunk" | "complete" | "error"
    content: str = ""
    prediction: Optional[PredictionResponse] = None
