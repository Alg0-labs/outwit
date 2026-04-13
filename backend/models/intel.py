from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class IntelTransactionType(str, Enum):
    bet_win = "bet_win"
    bet_loss = "bet_loss"
    daily_login = "daily_login"
    referral = "referral"
    battle_win = "battle_win"
    streak_bonus = "streak_bonus"
    initial_grant = "initial_grant"


class IntelTransactionDB(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    agent_id: str
    user_id: str
    amount: int
    type: IntelTransactionType
    reference_id: Optional[str] = None
    description: str
    running_balance: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "use_enum_values": True}


class IntelTransactionResponse(BaseModel):
    id: str
    amount: int
    type: str
    description: str
    running_balance: int
    created_at: datetime


class IntelBalanceResponse(BaseModel):
    agent_id: str
    balance: int
    total_earned: int
    total_wagered: int


class DailyLoginResponse(BaseModel):
    intel_awarded: int
    new_balance: int
    streak: int
    streak_complete: bool
    message: str
