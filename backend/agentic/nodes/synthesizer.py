import json
import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from agentic.state import AgentArenaState
from agentic.prompts.synthesizer_prompt import SYNTHESIZER_SYSTEM, SYNTHESIZER_USER
from config import settings

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model=settings.llm_model,
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    temperature=0.4,  # slightly more creative for agent personality
)


async def synthesizer_node(state: AgentArenaState) -> AgentArenaState:
    """
    Final synthesis node — combines all specialist outputs into a single
    confident prediction reflecting the agent's full personality.
    """
    agent_name = state.get("agent_name", "Agent")
    question = state.get("market_question", "")
    yes_price = state.get("yes_price", 0.5)
    no_price = state.get("no_price", 0.5)
    personality_context = state.get("personality_context", "")
    memory = state.get("agent_memory", {})
    risk_profile = state.get("agent_risk_profile", 50)

    logger.info(f"Synthesizer: building final prediction for {agent_name}")

    # Gather specialist outputs
    news_signals = state.get("news_signals", [])
    news_signals_formatted = "\n".join([
        f"  - [{s.get('strength', '?').upper()}] {s.get('headline', '')} → {s.get('signal_direction', '')} ({s.get('reasoning', '')})"
        for s in (news_signals or [])[:5]
    ]) or "  No news signals available"

    market_signals = state.get("market_signals", {})
    domain_context = state.get("domain_context", "No domain context")
    domain_key_factor = state.get("domain_key_factor", "Unknown")

    try:
        system_prompt = SYNTHESIZER_SYSTEM.format(
            agent_name=agent_name,
            personality_context=personality_context,
        )
        user_prompt = SYNTHESIZER_USER.format(
            agent_name=agent_name,
            market_question=question,
            yes_price=yes_price,
            no_price=no_price,
            news_sentiment=state.get("news_overall_sentiment", "neutral"),
            news_confidence=state.get("news_confidence", 50),
            news_signals_formatted=news_signals_formatted,
            implied_prob_yes=market_signals.get("implied_probability_yes", yes_price),
            market_momentum=market_signals.get("market_momentum", "stable"),
            market_confidence=state.get("market_confidence", 50),
            contrarian_signal=market_signals.get("contrarian_signal", "None identified"),
            value_assessment=market_signals.get("value_assessment", "fair_value"),
            domain_confidence=state.get("domain_confidence", 50),
            domain_key_factor=domain_key_factor,
            domain_context=domain_context,
            recent_accuracy=memory.get("recent_accuracy", 0.5),
            confidence_calibration=memory.get("confidence_calibration", 1.0),
            learned_biases=memory.get("learned_biases", {}),
        )

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        result = _parse_json(response.content)

        # Validate and clamp values
        outcome = result.get("outcome", "yes").lower()
        if outcome not in ("yes", "no"):
            outcome = "yes"

        raw_confidence = int(result.get("confidence", 60))
        calibration = memory.get("confidence_calibration", 1.0)
        confidence = max(40, min(95, int(raw_confidence * calibration)))

        # Intel wagering based on risk profile
        max_wager = 50 if risk_profile <= 35 else (150 if risk_profile <= 65 else 300)
        intel_to_wager = min(
            max_wager,
            max(10, int(result.get("intel_to_wager", max_wager // 2)))
        )

        reasoning = result.get("reasoning", f"{agent_name} makes this call based on available signals.")
        key_signal = result.get("key_signal", "Signal analysis complete.")

        logger.info(
            f"Synthesizer: {agent_name} → {outcome.upper()} at {confidence}% confidence, "
            f"wagering {intel_to_wager} INTEL"
        )

        # Package all specialist outputs for transparency
        specialist_outputs = {
            "news": {
                "signals": news_signals,
                "sentiment": state.get("news_overall_sentiment"),
                "confidence": state.get("news_confidence"),
            },
            "market": {
                **market_signals,
                "confidence": state.get("market_confidence"),
            },
            "domain": {
                "context": domain_context,
                "key_factor": domain_key_factor,
                "confidence": state.get("domain_confidence"),
            },
        }

        return {
            **state,
            "prediction_outcome": outcome,
            "confidence_score": confidence,
            "intel_to_wager": intel_to_wager,
            "reasoning_text": reasoning,
            "key_signal": key_signal,
            "specialist_outputs": specialist_outputs,
        }

    except Exception as e:
        logger.error(f"Synthesizer failed: {e}")
        # Graceful fallback prediction
        return {
            **state,
            "prediction_outcome": "yes",
            "confidence_score": 55,
            "intel_to_wager": 25,
            "reasoning_text": f"{agent_name} is processing this market. Preliminary analysis suggests a YES position with conservative confidence.",
            "key_signal": "Agent processing — full analysis unavailable.",
            "specialist_outputs": {},
            "error": f"synthesizer: {str(e)}",
        }


def _parse_json(content: str) -> dict:
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{"):
                content = stripped
                break
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON object from mixed text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except Exception:
                pass
        return {}
