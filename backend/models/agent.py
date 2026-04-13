from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ReasoningStyle(str, Enum):
    statistical = "statistical"
    narrative = "narrative"


class AgentMemory(BaseModel):
    history_summary: str = ""
    learned_biases: Dict[str, float] = Field(default_factory=dict)
    confidence_calibration: float = 1.0
    domain_accuracy: Dict[str, float] = Field(default_factory=dict)
    recent_accuracy: float = 0.5
    last_updated: Optional[datetime] = None


# ── DB document ───────────────────────────────────────────────────────────────
class AgentDB(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    name: str
    avatar_id: str = "robot"
    color_theme: str = "blue"
    domain_expertise: List[str] = Field(default_factory=list)
    reasoning_style: ReasoningStyle = ReasoningStyle.statistical
    risk_profile: int = Field(default=50, ge=0, le=100)
    intel_balance: int = 500
    reputation_score: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    current_streak: int = 0
    memory: AgentMemory = Field(default_factory=AgentMemory)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "use_enum_values": True}

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return round(self.win_count / total * 100, 1) if total > 0 else 0.0

    @property
    def total_predictions(self) -> int:
        return self.win_count + self.loss_count


# ── Request schemas ───────────────────────────────────────────────────────────
class CreateAgentRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=20)
    avatar_id: str = "robot"
    color_theme: str = "blue"
    domain_expertise: List[str] = Field(default_factory=list)
    reasoning_style: ReasoningStyle = ReasoningStyle.statistical
    risk_profile: int = Field(default=50, ge=0, le=100)


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=20)
    avatar_id: Optional[str] = None
    color_theme: Optional[str] = None
    domain_expertise: Optional[List[str]] = None
    reasoning_style: Optional[ReasoningStyle] = None
    risk_profile: Optional[int] = Field(default=None, ge=0, le=100)


# ── Response schemas ──────────────────────────────────────────────────────────
class AgentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    avatar_id: str
    color_theme: str
    domain_expertise: List[str]
    reasoning_style: str
    risk_profile: int
    intel_balance: int
    reputation_score: float
    win_count: int
    loss_count: int
    current_streak: int
    win_rate: float
    total_predictions: int
    memory: AgentMemory
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db(cls, agent: AgentDB) -> "AgentResponse":
        data = agent.model_dump(by_alias=False)
        data["id"] = str(data.get("_id") or data.get("id") or "")
        data["win_rate"] = agent.win_rate
        data["total_predictions"] = agent.total_predictions
        return cls(**data)


class AgentPublicResponse(BaseModel):
    """Stripped-down public view of an agent (no memory details)."""
    id: str
    name: str
    avatar_id: str
    color_theme: str
    domain_expertise: List[str]
    reasoning_style: str
    reputation_score: float
    win_rate: float
    total_predictions: int
    current_streak: int
    intel_balance: int
