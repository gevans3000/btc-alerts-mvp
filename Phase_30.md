# Phase 30 — Absolute Autonomy (v1.0 Production)

**Status:** 📅 PLANNED
**Goal:** Finalize the "EMBER Swarm" into a distributed, containerized (Docker), multi-agent system capable of running headless 24/7 on AWS/GCP with zero local workstation dependencies.

---

## 1. Context & Architecture Requirements

**Goal 1: The Swarm Architecture (Multi-Agent Subsystem)**
- **Concept:** Currently, `engine.py` does all the thinking. In v1.0, reasoning should be split into discrete microservices to prevent bottlenecking. 
- **Execution:** Break the monolith into: 
	- `Intel_Agent`: Reads orderbook/prices and calculates technicals.
	- `Risk_Agent`: Looks at Kelly, volatility, and sets SL/TP and Size.
	- `Execution_Agent`: Takes the output, runs adaptive slippage, and executes.

**Goal 2: Dockerization and Cloud Readiness**
- **Concept:** The system currently runs on Windows PowerShell (`pipeline.ps1`). It must become OS-agnostic for robust cloud uptime.
- **Execution:** Write a comprehensive `Dockerfile` and `docker-compose.yml`. Containerize the Web UI (Dashboard), the API/WebSocket Server, and the Python Trading Swarm. 

**Goal 3: The 30-Day Audit (Final Boss)**
- **Concept:** Before flipping the switch to live capital, the agentic swarm must survive 30 consecutive days of real-time paper trading without crashing, demonstrating statistically significant Edge.
- **Execution:** Implement an immutable audit log (`audit_ledger.json`) that strictly records uptime, system restarts, and unmodified 30-day PnL curves to mathematically prove profitability.

---

## 2. Tasks for the Implementing Agent

### Task 1: Microservice Refactoring
1. Abstract `engine.py` into distinct modules (`intel.py`, `risk.py`, `exec_agent.py`) using lightweight local sockets, Redis, or simple high-speed async queues to pass state.
2. Ensure if `Intel_Agent` crashes, the `Execution_Agent` fails safe and closes all open positions to prevent unmanaged exposure.

### Task 2: Containerization
1. Write `Dockerfile` with the optimal slim Python base image.
2. Add `requirements.txt` with strictly pinned library versions to prevent future dependency breakage.
3. Map internal dashboard ports (8000) so the user can easily access the web UI via an EC2 public IP or local docker host.

### Task 3: The Sentinel Watchdog
1. Implement a final `watchdog.py` process running outside the containers (or in a master container) that pings the Swarm every 10 seconds.
2. If any sub-agent hangs, the watchdog sends an immediate Telegram or Discord alert to the human operator and pauses all new trading activity.

---

## 3. Verification Checklist
- Run `docker-compose up --build`. Verify the entire system, including WebSocket dashboard, spins up perfectly on a fresh environment.
- Manually kill the `intel.py` process. Verify the system enters `SAFE_MODE` and alerts the console/watchdog exactly as designed.
- Produce a clean, verifiable `audit_ledger.json` proving zero catastrophic faults over a 72-hour simulated high-volatility run.
