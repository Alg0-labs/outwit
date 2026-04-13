from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class MarketCategory(str, Enum):
    ipl = "ipl"
    geopolitics = "geopolitics"


class MarketDB(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    external_id: str
    source: str = "polymarket"
    question: str
    yes_price: float = Field(ge=0.0, le=1.0)
    no_price: float = Field(ge=0.0, le=1.0)
    volume_24h: float = 0.0
    category: MarketCategory
    closes_at: datetime
    is_resolved: bool = False
    resolution: Optional[str] = None  # "yes" | "no"
    last_fetched: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "use_enum_values": True, "extra": "ignore"}


class MarketResponse(BaseModel):
    id: str
    external_id: str
    source: str = "polymarket"
    question: str
    yes_price: float
    no_price: float
    volume_24h: float
    category: str
    closes_at: datetime
    is_resolved: bool
    resolution: Optional[str] = None
    time_remaining: str
    last_fetched: datetime

    @classmethod
    def from_db(cls, m: MarketDB, doc_id: str) -> "MarketResponse":
        now = datetime.utcnow()
        delta = m.closes_at - now
        if delta.total_seconds() > 0:
            days = delta.days
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            if days > 0:
                time_remaining = f"{days}d {hours}h"
            elif hours > 0:
                time_remaining = f"{hours}h {mins}m"
            else:
                time_remaining = f"{mins}m"
        else:
            time_remaining = "Closed"

        return cls(
            id=doc_id,
            external_id=m.external_id,
            source=m.source,
            question=m.question,
            yes_price=m.yes_price,
            no_price=m.no_price,
            volume_24h=m.volume_24h,
            category=m.category,
            closes_at=m.closes_at,
            is_resolved=m.is_resolved,
            resolution=m.resolution,
            time_remaining=time_remaining,
            last_fetched=m.last_fetched,
        )


class MarketListResponse(BaseModel):
    markets: list[MarketResponse]
    total: int
    category: Optional[str] = None
