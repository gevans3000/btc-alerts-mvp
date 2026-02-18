from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

@dataclass
class IntelligenceBundle:
    """Container for all intelligence layer results.
    Each field is Optional so compute_score() works even if a layer fails."""
    squeeze: Optional[Dict[str, Any]] = None        # Phase 1
    sentiment: Optional[Dict[str, Any]] = None       # Phase 2
    confluence: Optional[Dict[str, Any]] = None      # Extra logic

@dataclass
class AlertScore:
    symbol: str
    timeframe: str
    regime: str
    confidence: int
    tier: str
    action: str
    reasons: List[str]
    reason_codes: List[str]
    blockers: List[str]
    quality: str
    direction: str
    strategy_type: str
    entry_zone: str
    invalidation: float
    tp1: float
    tp2: float
    rr_ratio: float
    session: str
    score_breakdown: Dict[str, float]
    lifecycle_key: str
    last_candle_ts: int = 0
    intel: Optional[IntelligenceBundle] = None
    decision_trace: Dict[str, object] = field(default_factory=dict)
    context: Dict[str, object] = field(default_factory=dict)