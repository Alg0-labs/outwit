import logging
from agentic.state import AgentArenaState

logger = logging.getLogger(__name__)


def build_personality_context(state: AgentArenaState) -> str:
    """
    Build a personality context string injected into every specialist prompt.
    This is pure Python — no LLM call needed.
    """
    style = state.get("agent_reasoning_style", "statistical")
    risk = state.get("agent_risk_profile", 50)
    expertise = state.get("agent_domain_expertise", [])
    memory = state.get("agent_memory", {})

    if style == "statistical":
        style_description = (
            "You prioritize statistical data, historical patterns, and mathematical probability. "
            "You distrust narratives without data support. "
            "You look for base rates, sample sizes, and quantifiable evidence."
        )
    else:
        style_description = (
            "You prioritize momentum, current narratives, team morale, and sentiment signals. "
            "Statistics tell you the past; narratives tell you the future. "
            "You weight recent events heavily over historical averages."
        )

    if risk <= 35:
        risk_desc = "conservative — you prefer certainty over upside, avoid high-risk wagers"
    elif risk <= 65:
        risk_desc = "balanced — you weigh risk and reward proportionally"
    else:
        risk_desc = "aggressive — you pursue high-confidence high-upside calls, willing to lose big"

    biases = memory.get("learned_biases", {})
    accuracy = memory.get("recent_accuracy", 0.5)
    calibration = memory.get("confidence_calibration", 1.0)

    context = f"""You are analyzing on behalf of agent: {state.get('agent_name', 'Agent')}
Reasoning philosophy: {style_description}
Risk tolerance: {risk}/100 ({risk_desc})
Domain expertise: {', '.join(expertise) if expertise else 'general'}
Recent accuracy: {accuracy:.0%}
Confidence calibration: {calibration:.2f}x (if < 1.0, agent has been overconfident historically)
Known biases: {biases if biases else 'None identified yet'}"""

    return context


def supervisor_node(state: AgentArenaState) -> AgentArenaState:
    """
    Pure Python routing function — no LLM call.
    Prepares personality context for all downstream specialist nodes.
    """
    logger.info(
        f"Supervisor: orchestrating prediction for agent={state.get('agent_name')} "
        f"market={state.get('market_question', '')[:50]}..."
    )

    personality_context = build_personality_context(state)

    return {
        **state,
        "personality_context": personality_context,
        "error": None,
    }
