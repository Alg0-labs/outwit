import json
import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from agentic.state import AgentArenaState
from agentic.tools.news_tool import fetch_news_for_category, format_news_for_prompt
from agentic.prompts.news_analyst_prompt import NEWS_ANALYST_SYSTEM, NEWS_ANALYST_USER
from config import settings

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model=settings.llm_model,
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    temperature=0.2,
)


async def news_analyst_node(state: AgentArenaState) -> AgentArenaState:
    """
    Fetches recent news and extracts prediction-relevant signals using Claude.
    """
    category = state.get("market_category", "ipl")
    question = state.get("market_question", "")
    personality_context = state.get("personality_context", "")

    logger.info(f"News Analyst: fetching news for category={category}")

    try:
        # Fetch news articles
        articles = await fetch_news_for_category(category)
        formatted_news = format_news_for_prompt(articles)

        # Build prompt
        system_prompt = NEWS_ANALYST_SYSTEM.format(personality_context=personality_context)
        user_prompt = NEWS_ANALYST_USER.format(
            market_question=question,
            market_category=category,
            formatted_news=formatted_news,
        )

        # Call Claude
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        # Parse JSON response
        content = response.content
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        result = json.loads(content)

        signals = result.get("signals", [])
        overall_sentiment = result.get("overall_news_sentiment", "neutral")
        confidence = result.get("confidence_from_news", 50)

        logger.info(f"News Analyst: extracted {len(signals)} signals, sentiment={overall_sentiment}")

        return {
            **state,
            "news_signals": signals,
            "news_overall_sentiment": overall_sentiment,
            "news_confidence": int(confidence),
        }

    except json.JSONDecodeError as e:
        logger.error(f"News Analyst JSON parse error: {e}")
        return {
            **state,
            "news_signals": [],
            "news_overall_sentiment": "neutral",
            "news_confidence": 50,
        }
    except Exception as e:
        logger.error(f"News Analyst failed: {e}")
        return {
            **state,
            "news_signals": [],
            "news_overall_sentiment": "neutral",
            "news_confidence": 50,
            "error": f"news_analyst: {str(e)}",
        }
