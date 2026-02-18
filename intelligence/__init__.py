from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class IntelligenceBundle:
    """Container for all intelligence layer results.
    Each field is Optional so compute_score() works even if a layer fails."""
    squeeze: Optional[Dict[str, Any]] = None        # Phase 1
    sentiment: Optional[Dict[str, Any]] = None       # Phase 2
    confluence: Optional[Dict[str, Any]] = None      # Extra logic