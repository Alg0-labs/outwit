"""
Agent Arena LangGraph Pipeline

Architecture:
    START
      │
      ▼
  supervisor  (pure Python, injects agent personality)
      │
      ├──► news_analyst   ──┐
      ├──► data_analyst   ──┤  (parallel execution via asyncio.gather)
      └──► domain_expert  ──┘
                              │
                              ▼
                         synthesizer  (final LLM call, produces prediction)
                              │
                              ▼
                            END
"""

import asyncio
import logging
from typing import Any, Dict
from agentic.state import AgentArenaState
from agentic.nodes.supervisor import supervisor_node
from agentic.nodes.news_analyst import news_analyst_node
from agentic.nodes.data_analyst import data_analyst_node
from agentic.nodes.domain_expert import domain_expert_node
from agentic.nodes.synthesizer import synthesizer_node

logger = logging.getLogger(__name__)


class AgentArenaGraph:
    """
    Custom async graph that runs specialist nodes in parallel,
    then synthesizes results. This mirrors the LangGraph Send API pattern
    but implemented directly for full async control.
    """

    async def ainvoke(self, initial_state: AgentArenaState) -> AgentArenaState:
        logger.info(
            f"Graph: starting pipeline for agent={initial_state.get('agent_name')} "
            f"market_category={initial_state.get('market_category')}"
        )

        # Step 1: Supervisor — inject personality context (sync)
        state = supervisor_node(initial_state)

        # Step 2: Run all three specialists in parallel
        logger.info("Graph: running specialists in parallel...")
        try:
            news_task = news_analyst_node(state)
            data_task = data_analyst_node(state)
            domain_task = domain_expert_node(state)

            news_result, data_result, domain_result = await asyncio.gather(
                news_task, data_task, domain_task,
                return_exceptions=False,
            )

            # Merge specialist results into state (deep merge)
            state = self._merge_states(state, news_result, data_result, domain_result)

        except Exception as e:
            logger.error(f"Graph: parallel specialist execution failed: {e}")
            state = {
                **state,
                "news_signals": [],
                "news_overall_sentiment": "neutral",
                "news_confidence": 50,
                "market_signals": {},
                "market_momentum": "stable",
                "market_confidence": 50,
                "domain_context": "Specialist analysis unavailable",
                "domain_key_factor": "Unknown",
                "domain_confidence": 50,
                "error": str(e),
            }

        # Step 3: Synthesizer — final prediction
        logger.info("Graph: running synthesizer...")
        final_state = await synthesizer_node(state)

        logger.info(
            f"Graph: complete → outcome={final_state.get('prediction_outcome')} "
            f"confidence={final_state.get('confidence_score')} "
            f"wager={final_state.get('intel_to_wager')}"
        )

        return final_state

    def _merge_states(
        self,
        base: AgentArenaState,
        news: AgentArenaState,
        data: AgentArenaState,
        domain: AgentArenaState,
    ) -> AgentArenaState:
        """Merge specialist state fragments into the base state."""
        return {
            **base,
            # From news analyst
            "news_signals": news.get("news_signals", []),
            "news_overall_sentiment": news.get("news_overall_sentiment", "neutral"),
            "news_confidence": news.get("news_confidence", 50),
            # From data analyst
            "market_signals": data.get("market_signals", {}),
            "market_momentum": data.get("market_momentum", "stable"),
            "market_confidence": data.get("market_confidence", 50),
            # From domain expert
            "domain_context": domain.get("domain_context", ""),
            "domain_key_factor": domain.get("domain_key_factor", ""),
            "domain_confidence": domain.get("domain_confidence", 50),
        }


# Module-level graph instance (created once, reused per request)
graph = AgentArenaGraph()
