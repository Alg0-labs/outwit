import json
import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from agentic.state import AgentArenaState
from agentic.prompts.data_analyst_prompt import DATA_ANALYST_SYSTEM, DATA_ANALYST_USER
from config import settings

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model=settings.llm_model,
    api_key=settings.anthropic_api_key,
    max_tokens=768,
    temperature=0.1,
)


async def data_analyst_node(state: AgentArenaState) -> AgentArenaState:
    """
    Analyzes Polymarket odds and market structure to extract quantitative signals.
    """
    question = state.get("market_question", "")
    yes_price = state.get("yes_price", 0.5)
    no_price = state.get("no_price", 0.5)
    volume = state.get("volume_24h", 0.0)
    personality_context = state.get("personality_context", "")

    logger.info(f"Data Analyst: analyzing market YES={yes_price} NO={no_price} Vol=${volume:.0f}")

    try:
        system_prompt = DATA_ANALYST_SYSTEM.format(personality_context=personality_context)
        user_prompt = DATA_ANALYST_USER.format(
            market_question=question,
            yes_price=yes_price,
            yes_pct=yes_price * 100,
            no_price=no_price,
            volume=volume,
        )

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        content = response.content
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        result = json.loads(content)

        market_signals = {
            "implied_probability_yes": result.get("implied_probability_yes", yes_price),
            "market_momentum": result.get("market_momentum", "stable"),
            "liquidity_assessment": result.get("liquidity_assessment", "medium"),
            "contrarian_signal": result.get("contrarian_signal", ""),
            "recommended_outcome": result.get("recommended_outcome", "yes"),
            "value_assessment": result.get("value_assessment", "fair_value"),
        }
        market_confidence = int(result.get("confidence_from_market", 50))

        logger.info(f"Data Analyst: momentum={market_signals['market_momentum']}, confidence={market_confidence}")

        return {
            **state,
            "market_signals": market_signals,
            "market_momentum": market_signals["market_momentum"],
            "market_confidence": market_confidence,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Data Analyst JSON parse error: {e}")
        return {
            **state,
            "market_signals": {"implied_probability_yes": yes_price, "market_momentum": "stable"},
            "market_momentum": "stable",
            "market_confidence": 50,
        }
    except Exception as e:
        logger.error(f"Data Analyst failed: {e}")
        return {
            **state,
            "market_signals": {"implied_probability_yes": yes_price, "market_momentum": "stable"},
            "market_momentum": "stable",
            "market_confidence": 50,
            "error": f"data_analyst: {str(e)}",
        }
