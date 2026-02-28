# 📟 Operator Manual: BTC Trading Terminal

This document provides the standard operating procedure (SOP) for interpreting the Phase 24 "Trading Terminal" dashboard. It is designed for both human traders and AI agents.

---

## 🏗️ 1. Data Hierarchy & Sources

| Layer | Source | Update Freq | Purpose |
| :--- | :--- | :--- | :--- |
| **Live Tape** | Collectors (Bybit/OKX/Bitunix) | 2s (WS) | Immediate market state (Mid, Spread, RVol) |
| **Edge Analytics** | `paper_portfolio.json` | On Change | Statistical advantage (LONG vs SHORT edge) |
| **Signal Core** | `engine.py` / `intelligence/` | Multi-TF | Raw signal conviction (Radar Dots, Tier) |
| **Overrides** | `dashboard_overrides.json` | Immediate | Dynamic filters (Min Score, Muted Recipes) |

---

## � 2. Decision Workflow: The "Triple Green" Process

Before clicking **EXECUTE**, you must satisfy three distinct layers of confirmation:

### Layer A: The Statistical Edge (Long/Short Stats)
*   **Rule**: Never trade against your 7-day trailing edge.
*   **Action**: Check the `Verdict Center` for LONG Edge vs SHORT Edge WR%.
*   **Threshold**: If your LONG Edge is < 40%, SKIP all long alerts regardless of "A" tier.

### Layer B: The Signal Quality (Confluence Radar)
*   **Rule**: Signal must be mechanically sound.
*   **Threshold**: 
    *   **7/15+ Dots**: High Conviction (Execute with Full Kelly).
    *   **4-6 Dots**: Moderate Conviction (Execute with 0.25x Size or WATCH).
    *   **< 4 Dots**: Noise / Weak Conviction (SKIP).
*   **Critical Probes**: Ensure `AVWAP`, `Structure (BOS)`, and `OI Regime` are aligned.

### Layer C: Risk Management (Kelly Sizing)
*   **Rule**: Position sizing is mathematical, not emotional.
*   **Action**: Read the `Kelly Sizing %` on the Live Tape. 
*   **Execution**: Risk exactly that % of your current balance per trade.

---

## 🛠️ 3. Dashboard Controls (POST /api/command)

The operator can interact with the backend live without restarting:
1.  **Mute Recipe**: If `HTF_REVERSAL` is getting chopped up in a trending market, mute it for 60 mins.
2.  **Score Floor**: Raise the filter to `70+` during high-noise/news events to see only the cleanest setups.
3.  **Direction Filter**: If the macro trend is BEARISH, set the dashboard to "SHORT ONLY" to eliminate counter-trend distraction.

---

## 🤖 4. AI-Operator Quick Specs

*   **REST Endpoint**: `GET http://localhost:8000/api/alerts`
    *   Returns the full `decision_trace` with all 17 intelligence probes for deep analysis.
*   **WebSocket Feed**: `ws://localhost:8000/ws`
    *   Provides a lightweight 15-alert buffer + global performance stats.
*   **State Persistence**: All user overrides are saved to `data/dashboard_overrides.json`.

---

## 📉 5. Exit Priorities

Monitor the **Unrealized PnL** and **Drawdown** fields:
- **Automatic Halt**: If `Drawdown %` hits 12%, the system is in a state of "Unforced Error." Halt all trading until the edge recalibrates.
- **Profit Scaling**: Look at `TP1` distance. If the distance to TP1 is < 1x Spread, the R:R is no longer valid; skip the entry.

---
_OPERATOR | v1.0 | Dashboard Phase 24_
