from dataclasses import dataclass
from collectors.base import BudgetManager

@dataclass
class DerivativesSnapshot:
    funding_rate: float
    oi_change_pct: float
    basis_pct: float
    healthy: bool = True

def fetch_derivatives_context(budget: BudgetManager, timeout: float = 10.0) -> DerivativesSnapshot:
    return DerivativesSnapshot(0.0, 0.0, 0.0, healthy=False)

