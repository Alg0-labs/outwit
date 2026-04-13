from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from database.mongodb import get_db
from models.market import MarketDB, MarketResponse

router = APIRouter(prefix="/markets", tags=["markets"])


def _doc_to_response(doc: dict) -> MarketResponse:
    doc_id = str(doc["_id"])
    doc["_id"] = doc_id
    m = MarketDB(**doc)
    return MarketResponse.from_db(m, doc_id)


@router.get("", response_model=List[MarketResponse])
async def list_markets(
    category: Optional[str] = Query(default=None, description="ipl | geopolitics"),
    resolved: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
):
    db = get_db()

    if category:
        # IPL: soonest closing first (today's match before tomorrow's)
        # Geopolitics: highest volume first
        if category == "ipl":
            docs = await db.markets.find(
                {"is_resolved": resolved, "category": "ipl"}
            ).sort("closes_at", 1).limit(limit).to_list(limit)
        else:
            docs = await db.markets.find(
                {"is_resolved": resolved, "category": category}
            ).sort("volume_24h", -1).limit(limit).to_list(limit)
        return [_doc_to_response(d) for d in docs]

    # No category filter: balanced mix — IPL (soonest first) + geo (highest volume first)
    per_cat = max(limit // 2, 5)

    ipl_docs = await db.markets.find(
        {"is_resolved": resolved, "category": "ipl"}
    ).sort("closes_at", 1).limit(per_cat).to_list(per_cat)

    geo_docs = await db.markets.find(
        {"is_resolved": resolved, "category": "geopolitics"}
    ).sort("volume_24h", -1).limit(per_cat).to_list(per_cat)

    # IPL first (most time-sensitive), then geo
    results = [_doc_to_response(d) for d in ipl_docs]
    results += [_doc_to_response(d) for d in geo_docs]
    return results[:limit]


@router.get("/{market_id}", response_model=MarketResponse)
async def get_market(market_id: str):
    db = get_db()

    # Try external_id first
    doc = await db.markets.find_one({"external_id": market_id})
    if not doc:
        try:
            from bson import ObjectId
            doc = await db.markets.find_one({"_id": ObjectId(market_id)})
        except Exception:
            pass

    if not doc:
        raise HTTPException(status_code=404, detail="Market not found")

    doc_id = str(doc["_id"])
    doc["_id"] = doc_id
    m = MarketDB(**doc)
    return MarketResponse.from_db(m, doc_id)
