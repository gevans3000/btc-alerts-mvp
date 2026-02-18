from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class IntelligenceBundle:
    """Container for all intelligence layer results.
    Each field is Optional so compute_score() works even if a layer fails."""
    squeeze: Optional[Dict[str, Any]] = None        # Phase 1
    volume_profile: Optional[Dict[str, Any]] = None  # Phase 2
    liquidity: Optional[Dict[str, Any]] = None       # Phase 3
    macro: Optional[Dict[str, Any]] = None           # Phase 4
    sentiment: Optional[Dict[str, Any]] = None       # Phase 5
    confluence: Optional[Dict[str, Any]] = None      # Phase 6