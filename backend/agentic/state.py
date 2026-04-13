from typing import TypedDict, List, Optional, Dict, Any


class AgentArenaState(TypedDict, total=False):
    # ── Market input ──────────────────────────────────────────────────────────
    market_question: str
    market_id: str
    market_category: str          # "ipl" | "geopolitics"
    yes_price: float
    no_price: float
    volume_24h: float

    # ── Agent personality (injected at runtime) ───────────────────────────────
    agent_name: str
    agent_reasoning_style: str    # "statistical" | "narrative"
    agent_risk_profile: int       # 0-100
    agent_domain_expertise: List[str]
    agent_memory: Dict[str, Any]  # learned biases, calibration, etc.

    # ── Supervisor output ─────────────────────────────────────────────────────
    personality_context: str

    # ── Specialist outputs (populated as graph runs) ──────────────────────────
    news_signals: Optional[List[Dict[str, Any]]]
    news_overall_sentiment: Optional[str]
    news_confidence: Optional[int]

    market_signals: Optional[Dict[str, Any]]
    market_momentum: Optional[str]
    market_confidence: Optional[int]

    domain_context: Optional[str]
    domain_key_factor: Optional[str]
    domain_confidence: Optional[int]

    # ── Final output ──────────────────────────────────────────────────────────
    prediction_outcome: Optional[str]       # "yes" | "no"
    confidence_score: Optional[int]         # 40-95
    intel_to_wager: Optional[int]
    reasoning_text: Optional[str]
    key_signal: Optional[str]
    specialist_outputs: Optional[Dict[str, Any]]  # raw debug data

    # ── Control ───────────────────────────────────────────────────────────────
    error: Optional[str]
