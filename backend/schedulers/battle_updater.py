"""
battle_updater.py — runs every 90 seconds

For each active CricAPI battle:
  1. Fetch current live match score (Redis-cached, so minimal CricAPI calls)
  2. For each participant, invoke Claude Haiku to reassess confidence given the live score
     - Agent CAN adjust confidence (0-100) and add a new thought
     - Agent CANNOT change their YES/NO prediction
  3. Save the thought to `battle_thoughts` collection
  4. Update participant confidence + reasoning in the battle doc (so the debate cards refresh)

Thoughts schema:
  {
    battle_id: str,
    agent_id: str,
    agent_name: str,
    agent_color: str,
    agent_avatar: str,
    prediction: str,       # "YES" | "NO"
    confidence: int,       # updated confidence
    confidence_delta: int, # positive = more confident, negative = less
    thought: str,          # short reactive thought (≤ 150 chars)
    match_context: str,    # score/status at time of thought
    created_at: datetime,
  }
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId

logger = logging.getLogger(__name__)

# Minimum gap between thoughts for the same agent (seconds).
# Scheduler fires every 90s — use 85s so the previous thought is always still
# inside the window when the next cycle runs, preventing back-to-back duplication.
_DEDUP_SECONDS = 85

_UPDATER_PROMPT = """You are {agent_name}, a prediction market analyst. Update your live bet.

{bet_condition_block}
Previous confidence: {prev_confidence}%

Live match data:
{match_context}

Previous thought: {reasoning}

MANDATORY REASONING CHAIN (follow this exactly):
1. Read the live match data above.
2. Look at YOUR BET WINS / YOUR BET LOSES conditions above.
3. Ask: "Given the current score, is my WIN condition becoming more likely or less likely?"
4. Set confidence accordingly. Move 5-15 pts if there is a real change; ±2 pts max if static.
5. Write thought + reasoning that correctly reflects step 3.

CRITICAL: Do NOT equate "dominant team winning" with a specific YES/NO direction.
Always trace back to YOUR specific WIN condition stated above.

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "confidence": <integer 0-100>,
  "thought": "<≤ 120 chars — state the live score, then whether your WIN condition is more/less likely>",
  "reasoning": "<2-3 sentences — start by restating your WIN condition, then explain whether current data supports it>"
}}"""


async def _get_match_context(market_doc: dict) -> Optional[str]:
    """Fetch current match info and return a compact context string."""
    from agentic.tools.cricket_tool import _fetch_match_info

    match_id = market_doc.get("match_id", "")
    if not match_id:
        return None

    try:
        match_info = await _fetch_match_info(match_id)
        if not match_info:
            logger.warning(f"battle_updater: no match_info returned for match_id={match_id}")
            return None

        team_a = market_doc.get("team_a", "")
        team_b = market_doc.get("team_b", "")
        status = match_info.get("status", "Unknown")
        venue = match_info.get("venue", "")
        score_data = match_info.get("score", [])

        lines = [f"Match: {team_a} vs {team_b}", f"Status: {status}"]
        if venue:
            lines.append(f"Venue: {venue}")

        toss = match_info.get("toss", {})
        if toss and isinstance(toss, dict) and toss.get("winner"):
            lines.append(f"Toss: {toss['winner']} won, chose to {toss.get('decision', '?')}")

        if score_data:
            lines.append("Live Scores:")
            target = None
            first_innings_runs = None
            for idx, inn in enumerate(score_data):
                runs = int(inn.get("r", 0))
                wickets = int(inn.get("w", 0))
                overs_raw = inn.get("o", "0")
                try:
                    overs_float = float(overs_raw)
                except (ValueError, TypeError):
                    overs_float = 0.0
                lines.append(
                    f"  {inn.get('inning', '?')}: "
                    f"{runs}/{wickets} ({overs_raw} overs)"
                )
                if idx == 0:
                    first_innings_runs = runs
                    target = runs + 1  # runs + 1 needed to win
                elif idx == 1 and first_innings_runs is not None:
                    # 2nd innings — calculate required run rate
                    overs_remaining = 20.0 - overs_float
                    runs_needed = target - runs
                    if overs_remaining > 0 and runs_needed > 0:
                        rrr = runs_needed / overs_remaining
                        wickets_left = 10 - wickets
                        lines.append(
                            f"  → Chase: need {runs_needed} off {overs_remaining:.1f} overs "
                            f"(RRR {rrr:.1f}), {wickets_left} wickets remaining"
                        )
                    elif runs_needed <= 0:
                        lines.append("  → Chase complete — batting team has won")
        else:
            match_started = match_info.get("matchStarted", False)
            lines.append("Match has not started yet." if not match_started else "Match in progress — no score data yet.")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"battle_updater: failed to get match context: {e}")
        return None


async def _run_agent_thought(
    agent_name: str,
    prediction: str,
    prev_confidence: int,
    reasoning: str,
    match_context: str,
    market_question: str = "",
) -> dict:
    """Run Claude Haiku to get updated confidence + thought for one agent."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    from config import settings

    haiku = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=settings.anthropic_api_key,
        max_tokens=200,
        temperature=0.5,
    )

    bet_block = _bet_condition_block(prediction, market_question or "this cricket market")
    prompt = _UPDATER_PROMPT.format(
        agent_name=agent_name,
        bet_condition_block=bet_block,
        prediction=prediction,
        prev_confidence=prev_confidence,
        match_context=match_context,
        reasoning=reasoning[:400],
    )

    try:
        response = await haiku.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        # Strip markdown code blocks if present
        if "```" in content:
            for part in content.split("```"):
                stripped = part.strip().lstrip("json").strip()
                if stripped.startswith("{"):
                    content = stripped
                    break

        # Find JSON object even if there's surrounding text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            content = content[start:end]

        result = json.loads(content)
        confidence = max(0, min(100, int(result.get("confidence", prev_confidence))))
        thought = str(result.get("thought", "Monitoring the match closely..."))[:150]
        reasoning = str(result.get("reasoning", ""))[:400]
        return {"confidence": confidence, "thought": thought, "reasoning": reasoning}
    except Exception as e:
        logger.warning(f"battle_updater: Haiku parse failed for {agent_name}: {e}")
        return {"confidence": prev_confidence, "thought": "Staying focused on the live situation...", "reasoning": ""}


def _bet_condition_block(prediction: str, market_question: str) -> str:
    """
    Returns an explicit IF-THEN block explaining exactly when the bet wins/loses.
    Makes it unambiguous so the LLM can't flip the logic.

    e.g. prediction="NO", question="Will SRH beat RR in today's IPL match?"
    →
    YOUR BET: NO on "Will SRH beat RR in today's IPL match?"
    ┌─ YOUR BET WINS  if: "Will SRH beat RR?" resolves NO  → SRH does NOT win → RR wins
    └─ YOUR BET LOSES if: "Will SRH beat RR?" resolves YES → SRH WINS the match
    """
    q = market_question.strip()
    if prediction.upper() == "YES":
        return (
            f'YOUR BET: YES on "{q}"\n'
            f'  YOUR BET WINS  when: {q} → YES (the stated outcome HAPPENS)\n'
            f'  YOUR BET LOSES when: {q} → NO  (the stated outcome does NOT happen)\n'
        )
    else:
        return (
            f'YOUR BET: NO on "{q}"\n'
            f'  YOUR BET WINS  when: {q} → NO  (the stated outcome does NOT happen)\n'
            f'  YOUR BET LOSES when: {q} → YES (the stated outcome HAPPENS)\n'
        )


def _score_unchanged(prev_ctx: str, curr_ctx: str) -> bool:
    """
    Returns True if the match score lines are identical between two context strings.
    Strips the dynamic RRR/required-runs line (prefixed with '  →') before comparing
    because that line drifts every over even with no scoring event.
    """
    def _score_lines(ctx: str) -> list[str]:
        return [
            line for line in ctx.splitlines()
            if line.strip() and not line.strip().startswith("→")
        ]

    return _score_lines(prev_ctx) == _score_lines(curr_ctx)


async def update_active_battles() -> None:
    """
    Main entry point — called every 90s by the scheduler.
    Processes all active CricAPI battles.
    """
    from database.mongodb import get_db
    from config import settings

    if not settings.anthropic_api_key:
        logger.warning("battle_updater: no anthropic_api_key set, skipping")
        return

    db = get_db()
    now = datetime.utcnow()
    dedup_cutoff = now - timedelta(seconds=_DEDUP_SECONDS)

    # Find active battles
    active_battles = await db.battles.find({"status": "active"}).to_list(50)
    if not active_battles:
        return

    cricapi_battles = [b for b in active_battles if b.get("market_id", "").startswith("cricapi-")]
    if not cricapi_battles:
        return

    logger.info(f"battle_updater: checking {len(cricapi_battles)} active CricAPI battle(s)")

    for battle_doc in cricapi_battles:
        battle_id = str(battle_doc["_id"])
        market_id = battle_doc.get("market_id", "")

        market_doc = await db.markets.find_one({"external_id": market_id})
        if not market_doc:
            logger.warning(f"battle_updater: market {market_id} not found")
            continue

        match_id = market_doc.get("match_id", "")
        if not match_id:
            logger.warning(f"battle_updater: market {market_id} has no match_id")
            continue

        match_context = await _get_match_context(market_doc)
        if not match_context:
            logger.warning(f"battle_updater: no match context for battle {battle_id}")
            continue

        participants = battle_doc.get("participants", [])
        if not participants:
            logger.info(f"battle_updater: battle {battle_id} has no participants yet")
            continue

        updated_participants = [dict(p) for p in participants]
        thoughts_generated = 0

        for i, participant in enumerate(participants):
            agent_id = participant.get("agent_id", "")
            agent_name = participant.get("agent_name", "Agent")
            prediction = participant.get("prediction", "YES")
            prev_confidence = int(participant.get("confidence", 55))
            reasoning = participant.get("reasoning", "")

            # Gate 1 — time dedup: skip if this agent got a thought within _DEDUP_SECONDS
            last_thought = await db.battle_thoughts.find_one(
                {"battle_id": battle_id, "agent_id": agent_id},
                sort=[("created_at", -1)],
            )
            if last_thought and last_thought.get("created_at", datetime.min) >= dedup_cutoff:
                logger.debug(f"battle_updater: {agent_name} already updated recently, skipping")
                continue

            # Gate 2 — score-change check: skip if the match situation hasn't changed
            # since the last thought. Compares the score lines only (strips the RRR
            # line which drifts with overs even if no runs are scored).
            if last_thought:
                prev_ctx = last_thought.get("match_context", "")
                if _score_unchanged(prev_ctx, match_context):
                    logger.debug(f"battle_updater: {agent_name} — score unchanged since last thought, skipping")
                    continue

            logger.info(f"battle_updater: running Haiku for {agent_name} ({prediction}, {prev_confidence}%)")

            result = await _run_agent_thought(
                agent_name=agent_name,
                prediction=prediction,
                prev_confidence=prev_confidence,
                reasoning=reasoning,
                match_context=match_context,
                market_question=battle_doc.get("market_question", ""),
            )

            new_confidence = result["confidence"]
            thought = result["thought"]
            reasoning_text = result["reasoning"]
            delta = new_confidence - prev_confidence

            logger.info(
                f"battle_updater: {agent_name} → confidence {prev_confidence}→{new_confidence} "
                f"(Δ{delta:+d}) | \"{thought[:60]}\""
            )

            # Save to battle_thoughts collection
            await db.battle_thoughts.insert_one({
                "battle_id": battle_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_color": participant.get("agent_color", "#6366f1"),
                "agent_avatar": participant.get("agent_avatar", "bot"),
                "prediction": prediction,
                "confidence": new_confidence,
                "confidence_delta": delta,
                "thought": thought,
                "reasoning": reasoning_text,
                "match_context": match_context,
                "created_at": now,
            })

            # Update confidence + reasoning in the battle participant so the
            # main debate card refreshes when the battle is polled every 20s.
            # Store both the short thought (headline) and full reasoning.
            updated_participants[i]["confidence"] = new_confidence
            updated_participants[i]["reasoning"] = (
                f"{thought}\n\n{reasoning_text}" if reasoning_text else thought
            )
            thoughts_generated += 1

        if thoughts_generated > 0:
            # Persist updated participants (confidence + reasoning) back to battle doc
            await db.battles.update_one(
                {"_id": ObjectId(battle_id)},
                {"$set": {"participants": updated_participants}},
            )
            logger.info(f"battle_updater: generated {thoughts_generated} thought(s) for battle {battle_id}")
