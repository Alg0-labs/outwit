from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class BattleStatus(str, Enum):
    active = "active"
    resolved = "resolved"


class BattleType(str, Enum):
    mixed = "mixed"        # agents disagree (YES vs NO)
    conviction = "conviction"  # all agents agree


# ── Participant (embedded in BattleDB) ───────────────────────────────────────

class BattleParticipant(BaseModel):
    agent_id: str
    agent_name: str
    agent_avatar: str
    agent_color: str
    agent_owner: str           # user_id
    agent_owner_username: str  # for display
    prediction: str            # "YES" or "NO"
    confidence: int            # 0-100
    reasoning: str
    crowd_votes: int = 0


# ── DB document ───────────────────────────────────────────────────────────────

class BattleDB(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    market_id: str
    market_question: str
    market_category: str
    participants: List[BattleParticipant] = []
    status: BattleStatus = BattleStatus.active
    winner_agent_ids: List[str] = []
    resolution_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    model_config = {"populate_by_name": True, "use_enum_values": True}


# ── Request schemas ───────────────────────────────────────────────────────────

class VoteRequest(BaseModel):
    agent_id: str  # vote for this participant


# ── Response schemas ──────────────────────────────────────────────────────────

class ParticipantResponse(BaseModel):
    agent_id: str
    agent_name: str
    agent_avatar: str
    agent_color: str
    agent_owner: str
    agent_owner_username: str
    prediction: str
    confidence: int
    reasoning: str
    crowd_votes: int
    crowd_vote_pct: float


class BattleResponse(BaseModel):
    id: str
    market_id: str
    market_question: str
    market_category: str
    participants: List[ParticipantResponse]
    total_votes: int
    status: str
    winner_agent_ids: List[str]
    resolution_reason: Optional[str] = None
    time_remaining: str
    created_at: datetime

    @classmethod
    def from_db(cls, b: BattleDB, doc_id: str, closes_at: Optional[datetime] = None) -> "BattleResponse":
        total_votes = sum(p.crowd_votes for p in b.participants)

        participant_responses = []
        for p in b.participants:
            pct = round(p.crowd_votes / total_votes * 100, 1) if total_votes > 0 else 0.0
            participant_responses.append(
                ParticipantResponse(
                    agent_id=p.agent_id,
                    agent_name=p.agent_name,
                    agent_avatar=p.agent_avatar,
                    agent_color=p.agent_color,
                    agent_owner=p.agent_owner,
                    agent_owner_username=p.agent_owner_username,
                    prediction=p.prediction,
                    confidence=p.confidence,
                    reasoning=p.reasoning,
                    crowd_votes=p.crowd_votes,
                    crowd_vote_pct=pct,
                )
            )

        # Time remaining
        if closes_at:
            now = datetime.utcnow()
            delta = closes_at - now
            if delta.total_seconds() > 0:
                days = delta.days
                hours = delta.seconds // 3600
                time_remaining = f"{days}d {hours}h" if days > 0 else f"{hours}h"
            else:
                time_remaining = "Closed"
        else:
            time_remaining = "Unknown"

        return cls(
            id=doc_id,
            market_id=b.market_id,
            market_question=b.market_question,
            market_category=b.market_category,
            participants=participant_responses,
            total_votes=total_votes,
            status=b.status,
            winner_agent_ids=b.winner_agent_ids,
            resolution_reason=b.resolution_reason,
            time_remaining=time_remaining,
            created_at=b.created_at,
        )
