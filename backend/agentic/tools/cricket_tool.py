"""
Cricket Tool — fetches match-specific IPL data for the LangGraph pipeline.

Priority order:
1. If market_id is a CricAPI market → look up match_id from MongoDB, fetch match_info
2. Fetch IPL 2026 season results for team form and H2H
3. Fallback: extract teams from question, build context with whatever we have
"""

import httpx
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

CRICAPI_BASE = "https://api.cricapi.com/v1"
IPL_2026_SERIES_ID = "87c62aac-bc3c-4738-ab93-19da0690488f"

# Full-name lookup for abbreviations used in market questions
_TEAM_ALIASES: Dict[str, str] = {
    "srh": "Sunrisers Hyderabad",
    "sunrisers": "Sunrisers Hyderabad",
    "rr": "Rajasthan Royals",
    "rajasthan": "Rajasthan Royals",
    "csk": "Chennai Super Kings",
    "chennai": "Chennai Super Kings",
    "kkr": "Kolkata Knight Riders",
    "kolkata": "Kolkata Knight Riders",
    "mi": "Mumbai Indians",
    "mumbai": "Mumbai Indians",
    "rcb": "Royal Challengers Bengaluru",
    "royal challengers": "Royal Challengers Bengaluru",
    "dc": "Delhi Capitals",
    "delhi": "Delhi Capitals",
    "gt": "Gujarat Titans",
    "gujarat": "Gujarat Titans",
    "lsg": "Lucknow Super Giants",
    "lucknow": "Lucknow Super Giants",
    "pbks": "Punjab Kings",
    "punjab": "Punjab Kings",
}


# ── CricAPI helpers ───────────────────────────────────────────────────────────

async def _cricapi_get(endpoint: str, extra: Dict = {}) -> Optional[Dict]:
    if not settings.cricapi_key or settings.cricapi_key in ("", "your_cricapi_key_here"):
        return None
    try:
        params = {"apikey": settings.cricapi_key, **extra}
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(f"{CRICAPI_BASE}/{endpoint}", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data
            logger.debug(f"CricAPI {endpoint}: status {resp.status_code}")
    except Exception as e:
        logger.warning(f"CricAPI {endpoint} failed: {e}")
    return None


async def _fetch_match_info(match_id: str) -> Optional[Dict]:
    """Fetch match_info, using Redis to cache for 90s (saves API calls)."""
    from database.redis_client import get_redis
    import json as _json
    cache_key = f"cricket:match:{match_id}"
    redis = get_redis()
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _json.loads(cached)
        except Exception:
            pass

    data = await _cricapi_get("match_info", {"id": match_id})
    result = data.get("data") if data else None

    if result and redis:
        try:
            await redis.setex(cache_key, 30, _json.dumps(result))
        except Exception:
            pass
    return result


async def _fetch_season_completed() -> List[Dict]:
    """Return all completed IPL 2026 matches, cached in Redis for 15 minutes."""
    from database.redis_client import get_redis
    import json as _json
    cache_key = "cricket:season:completed"
    redis = get_redis()
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _json.loads(cached)
        except Exception:
            pass

    data = await _cricapi_get("series_info", {"id": IPL_2026_SERIES_ID})
    if not data:
        return []
    all_matches = data.get("data", {}).get("matchList", [])
    done = []
    for m in all_matches:
        s = m.get("status", "").lower()
        if any(kw in s for kw in ("won", "tied", "no result", "abandoned")):
            done.append(m)

    if redis and done:
        try:
            await redis.setex(cache_key, 300, _json.dumps(done))  # 5 min
        except Exception:
            pass
    return done


# ── Form / H2H builders ───────────────────────────────────────────────────────

def _team_form(completed: List[Dict], team: str) -> str:
    """Last 5 results for a team — W / L / T / NR, most recent last."""
    team_lower = team.lower()
    results = []
    for m in reversed(completed):
        if team_lower not in " ".join(m.get("teams", [])).lower():
            continue
        s = m.get("status", "").lower()
        if "abandoned" in s or "no result" in s:
            results.append("NR")
        elif "tied" in s:
            results.append("T")
        elif team_lower in s:
            results.append("W")
        else:
            results.append("L")
        if len(results) >= 5:
            break
    return " ".join(reversed(results)) if results else "No results yet this season"


def _h2h(completed: List[Dict], team_a: str, team_b: str) -> Dict[str, Any]:
    a_lo, b_lo = team_a.lower(), team_b.lower()
    a_wins = b_wins = 0
    for m in completed:
        teams_lo = " ".join(m.get("teams", [])).lower()
        if a_lo not in teams_lo or b_lo not in teams_lo:
            continue
        s = m.get("status", "").lower()
        if a_lo in s:
            a_wins += 1
        elif b_lo in s:
            b_wins += 1
    return {"team_a_wins": a_wins, "team_b_wins": b_wins, "meetings": a_wins + b_wins}


def _extract_teams_from_question(question: str) -> Tuple[str, str]:
    """Best-effort extraction of two IPL team names from a market question."""
    q = question.lower()
    found: List[str] = []
    # Long names first (avoid short keys matching inside long ones)
    for alias in sorted(_TEAM_ALIASES, key=len, reverse=True):
        full = _TEAM_ALIASES[alias]
        if alias in q and full not in found:
            found.append(full)
        if len(found) == 2:
            break
    if len(found) >= 2:
        return found[0], found[1]
    # Fallback: split on "vs"
    parts = question.split(" vs ")
    if len(parts) >= 2:
        return parts[0].strip().split()[-1], parts[1].strip().split(",")[0].strip()
    return "", ""


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_cricket_data(question: str = "", market_id: str = "") -> Dict[str, Any]:
    """
    Returns a rich context dict for the IPL domain-expert node.

    Steps:
    1. If market_id is a cricapi market, look up match_id + teams from MongoDB.
    2. Fetch live match_info from CricAPI for that specific match.
    3. Fetch completed IPL 2026 results for form / H2H.
    4. Return combined context.
    """
    team_a = team_b = match_name = cricapi_match_id = ""
    match_info: Optional[Dict] = None

    # ── Step 1: DB lookup ─────────────────────────────────────────────────────
    if market_id and market_id.startswith("cricapi-"):
        try:
            from database.mongodb import get_db
            db = get_db()
            doc = await db.markets.find_one({"external_id": market_id})
            if doc:
                team_a = doc.get("team_a", "")
                team_b = doc.get("team_b", "")
                match_name = doc.get("match_name", "")
                cricapi_match_id = doc.get("match_id", "")
        except Exception as e:
            logger.warning(f"Cricket tool: DB lookup failed: {e}")

    # ── Step 2: Specific match info ───────────────────────────────────────────
    if cricapi_match_id:
        match_info = await _fetch_match_info(cricapi_match_id)

    # ── Step 3: Fall back team extraction from question ───────────────────────
    if not team_a:
        team_a, team_b = _extract_teams_from_question(question)

    # ── Step 4: Season results for form / H2H ────────────────────────────────
    season_done: List[Dict] = []
    try:
        season_done = await _fetch_season_completed()
    except Exception as e:
        logger.warning(f"Cricket tool: season fetch failed: {e}")

    # ── Assemble context ──────────────────────────────────────────────────────
    ctx: Dict[str, Any] = {
        "match": match_name or (f"{team_a} vs {team_b}" if team_a else "Unknown IPL match"),
        "team_a": team_a,
        "team_b": team_b,
        "question": question,
    }

    if match_info:
        ctx["venue"] = match_info.get("venue", "TBD")
        ctx["status"] = match_info.get("status", "Upcoming")
        ctx["match_started"] = match_info.get("matchStarted", False)
        ctx["match_ended"] = match_info.get("matchEnded", False)
        dt = match_info.get("dateTimeGMT", "")
        if dt:
            ctx["match_time_utc"] = dt
        toss = match_info.get("toss", {})
        if toss and isinstance(toss, dict) and toss.get("winner"):
            ctx["toss"] = f"{toss['winner']} won toss, chose to {toss.get('decision', '?')}"
        score = match_info.get("score", [])
        if score:
            ctx["live_score"] = score
    else:
        ctx["status"] = "Upcoming (pre-match)"

    if team_a and season_done:
        form_a = _team_form(season_done, team_a)
        form_b = _team_form(season_done, team_b) if team_b else "N/A"
        h2h = _h2h(season_done, team_a, team_b) if team_b else {}
        ctx["season"] = {
            "completed_matches": len(season_done),
            f"{team_a}_form_last5": form_a,
            f"{team_b}_form_last5": form_b,
            "head_to_head_2026": h2h,
        }
        ctx["recent_results"] = [
            m.get("status", m.get("name", ""))
            for m in season_done[-5:]
        ]
    elif team_a:
        # Have teams but no season data (API limit / network issue)
        ctx["season_note"] = (
            f"IPL 2026 season stats temporarily unavailable. "
            f"Teams: {team_a} vs {team_b}. Use your knowledge of IPL 2026 to assess form."
        )

    return ctx


def format_cricket_data(data: Dict[str, Any]) -> str:
    """Render the cricket context dict as a compact prompt-ready string."""
    lines: List[str] = []

    match = data.get("match", "")
    if match:
        lines.append(f"MATCH: {match}")

    q = data.get("question", "")
    if q:
        lines.append(f"PREDICTION QUESTION: {q}")

    status = data.get("status", "")
    if status:
        lines.append(f"STATUS: {status}")

    venue = data.get("venue", "")
    if venue:
        lines.append(f"VENUE: {venue}")

    mt = data.get("match_time_utc", "")
    if mt:
        lines.append(f"MATCH TIME (UTC): {mt}")

    toss = data.get("toss", "")
    if toss:
        lines.append(f"TOSS: {toss}")

    live_score = data.get("live_score", [])
    if live_score:
        lines.append("LIVE SCORE:")
        for inn in live_score:
            lines.append(
                f"  {inn.get('inning', '?')}: "
                f"{inn.get('r', 0)}/{inn.get('w', 0)} ({inn.get('o', '?')} ov)"
            )

    season = data.get("season", {})
    if season:
        n = season.get("completed_matches", 0)
        lines.append(f"\nIPL 2026 SEASON ({n} matches played):")
        team_a = data.get("team_a", "")
        team_b = data.get("team_b", "")
        if team_a:
            lines.append(f"  {team_a} last 5:  {season.get(f'{team_a}_form_last5', 'N/A')}")
        if team_b:
            lines.append(f"  {team_b} last 5:  {season.get(f'{team_b}_form_last5', 'N/A')}")
        h2h = season.get("head_to_head_2026", {})
        if h2h.get("meetings", 0) > 0:
            lines.append(
                f"  H2H 2026: {team_a} {h2h['team_a_wins']}–{h2h['team_b_wins']} {team_b}"
            )
        else:
            lines.append("  H2H 2026: First meeting this season")

    recent = data.get("recent_results", [])
    if recent:
        lines.append("\nRECENT IPL 2026 RESULTS:")
        for r in recent:
            lines.append(f"  • {r}")

    note = data.get("season_note", "")
    if note:
        lines.append(f"\nNOTE: {note}")

    return "\n".join(lines) if lines else "No cricket data available for this match."
