# Phase 27 — Signal Accuracy & Global API Fallbacks

**Status:** 📅 PLANNED
**Goal:** Implement ML-driven signal confirmation via order flow confluence and build a robust, circular multi-API fallback system to guarantee data availability despite provider rate limits. 

---

## 1. Context & Architecture Requirements

**Goal 1: Maximize Signal Accuracy (ML + Order Flow Confluence)**
- **Concept:** Traditional signals (RSI/MACD) suffer from noise. We need to filter signals using **Order Flow Confluence** (CVD/Delta) combined with a fast **Machine Learning classifier** (like a lightweight Random Forest or Logistic Regression model).
- **Execution:** Signals should only trigger when Price Action + Macro Data + Orderbook Imbalance (Delta) align. Stale or weak conflunce should downgrade the signal tier or cancel it entirely.

**Goal 2: Indestructible Data Feeds (Multi-API Fallback Chain)**
- **Concept:** When polling high-frequency data (like futures OI, funding, orderbook), free APIs frequently hit HTTP 429 (Too Many Requests).
- **Execution:** Implement a fallback rotation queue for data collectors.

---

## 2. Tasks for the Implementing Agent

### Task 1: Building the API Fallback Rotation Pipeline
Modify the data collection modules (wherever market data is fetched) to use a robust fallback chain:
1. **Primary Feed:** Exchange Direct APIs (Binance / Bybit Public APIs - Highest limits and lowest latency).
2. **Secondary Fallback:** CoinGecko Free API (Generous limits: 30 calls/minute, up to 10k/month).
3. **Tertiary Fallback:** CryptoCompare or CoinMarketCap basic tier (Good for aggregate pricing if original exchanges ban the IP).

**Implementation Details:**
- Wrap HTTP requests in an asynchronous retry loop with a `try/except` block catching `429 Too Many Requests` or `Timeout`.
- When a 429 happens, seamlessly execute the same request signature on the next API provider in the chain.
- Implement exponential backoff for the primary provider while running on the secondary.

### Task 2: Signal Confluence Upgrade
Modify the intelligence decision engine to calculate a "Confluence Score":
1. **Fetch Live Delta & CVD (Cumulative Volume Delta):** Grab short-term buy/sell order imbalances. 
2. **Machine Learning Noise Filter:** Pass the technical indicators, current volatility regime, and the Order Flow Delta into a scoring function. 
3. **Strict Gating:** If a Long signal triggers but order flow shows aggressive market selling (Negative Delta), either downgrade the signal to `B` Tier or cancel it.

### Task 3: Low-Footprint Execution
- Cache API responses heavily. If multiple modules need the same price or OI data within a 5-second window, rely on a central dictionary cache (`_LAST_KNOWN_PRICES`) instead of pinging the API twice.
- Keep token contexts low: do not rewrite large files. Provide modular, targeted patch functions to inject the fallback try/except blocks and the confluence scoring logic.

---

## 3. Verification Checklist
- Run the collector script and force-mock a `429` error on the primary API. Verify that CoinGecko or the secondary provider supplies the data without the dashboard crashing or creating silent `None` values.
- Verify that terminal logs distinctly print: `[WARN] Binance Rate Limited. Falling back to CoinGecko for <Symbol>`.
- Verify the Signal Engine produces a `confluence_score` inside the `decision_trace` JSON.
