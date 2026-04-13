import json
import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from agentic.state import AgentArenaState
from agentic.tools.cricket_tool import fetch_cricket_data, format_cricket_data
from agentic.prompts.domain_expert_prompt import (
    DOMAIN_EXPERT_IPL_SYSTEM, DOMAIN_EXPERT_IPL_USER,
    DOMAIN_EXPERT_GEO_SYSTEM, DOMAIN_EXPERT_GEO_USER,
)
from config import settings

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model=settings.llm_model,
    api_key=settings.anthropic_api_key,
    max_tokens=768,
    temperature=0.2,
)


async def domain_expert_node(state: AgentArenaState) -> AgentArenaState:
    """
    Routes to IPL or geopolitics expert based on market_category.
    Provides domain-specific context that general analysts would miss.
    """
    category = state.get("market_category", "ipl")
    question = state.get("market_question", "")
    personality_context = state.get("personality_context", "")

    logger.info(f"Domain Expert: providing {category} context")

    try:
        if category == "ipl":
            return await _ipl_expert(state, question, personality_context)
        else:
            return await _geo_expert(state, question, personality_context)
    except Exception as e:
        logger.error(f"Domain Expert failed: {e}")
        return {
            **state,
            "domain_context": f"Domain analysis unavailable: {str(e)}",
            "domain_key_factor": "Unable to assess",
            "domain_confidence": 50,
        }


async def _ipl_expert(
    state: AgentArenaState, question: str, personality_context: str
) -> AgentArenaState:
    market_id = state.get("market_id", "")
    cricket_data = await fetch_cricket_data(question, market_id)
    cricket_formatted = format_cricket_data(cricket_data)

    system_prompt = DOMAIN_EXPERT_IPL_SYSTEM.format(personality_context=personality_context)
    user_prompt = DOMAIN_EXPERT_IPL_USER.format(
        market_question=question,
        cricket_data=cricket_formatted,
    )

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    result = _parse_json(response.content)
    return {
        **state,
        "domain_context": result.get("domain_context", "IPL context not available"),
        "domain_key_factor": result.get("key_domain_factor", ""),
        "domain_confidence": int(result.get("domain_confidence", 50)),
    }


async def _geo_expert(
    state: AgentArenaState, question: str, personality_context: str
) -> AgentArenaState:
    system_prompt = DOMAIN_EXPERT_GEO_SYSTEM.format(personality_context=personality_context)
    user_prompt = DOMAIN_EXPERT_GEO_USER.format(market_question=question)

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    result = _parse_json(response.content)
    return {
        **state,
        "domain_context": result.get("domain_context", "Geopolitical context not available"),
        "domain_key_factor": result.get("key_domain_factor", ""),
        "domain_confidence": int(result.get("domain_confidence", 50)),
    }


def _parse_json(content: str) -> dict:
    """Safely parse JSON from LLM response, handling markdown code blocks."""
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            if part.strip().startswith("{") or part.strip().startswith("json\n{"):
                content = part.strip()
                if content.startswith("json"):
                    content = content[4:].strip()
                break
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}
