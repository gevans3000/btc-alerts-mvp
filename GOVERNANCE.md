# PID-129 — EMBER Progressive Capability Loop (BTC Alerts MVP)

## Objective
Continuously improve EMBER in **2-hour cycles** on the **BTC Alerts MVP** subject so each interval is measurably better than the previous one.

## Scope
### In
- 2-hour recurring improvement cycles on BTC Alerts MVP
- **OpenClaw governance:** Multi-platform automation (systemd/Mac, PowerShell/Windows), health checks, watchdogs, scorecards
- **Remote operations:** Control from Mac mini (Strategic Command) to any target (Windows PC/Nitro 5)
- Failure & outcome matrix handling
- Pre-gate checks before each cycle

### Out
- External/public messaging without explicit approval
- Destructive or irreversible actions
- Off-subject optimization loops

## Core Operating Model (2-Hour Progressive Loop)

Each cycle EMBER must do all 8 steps:

1) **Load subject context**
   - Determine current state from latest alert logs, scorecards, and implementation plan.
   - Check OpenClaw health status and systemd service state.

2) **Assess current readiness**
   - Report `READY` or `NOT_READY` only.
   - If uncertain, default `NOT_READY`.

3) **Execute one meaningful improvement**
   - Exactly one high-leverage, low-risk improvement per cycle.
   - Prefer fixes that reduce George effort and future back-and-forth.

4) **Compare vs prior cycle (mandatory delta)**
   - What improved since last cycle?
   - What remains blocked?
   - What got simpler/faster/reliable?

5) **Self-grade this cycle**
   - Grade: `A / B / C / D / F`
   - Include one-line justification.

6) **Write durable evidence artifact**
   - Path: `reports/pid-129-cycle-YYYYMMDD-HHMM.md`
   - Include proof paths, commands, and resulting state.

7) **Emit strict output contract**
   - `STATUS: READY|NOT_READY`
   - `SUBJECT: BTC Alerts MVP`
   - `IMPROVEMENT: <one concrete improvement completed>`
   - `DELTA: <what is better than last cycle>`
   - `GRADE: <A-F> | REASON: <one line>`
   - `NEXT_STEP: <single least-action next action>`
   - `EVIDENCE: <file path(s)>`

8) **Set next-cycle target**
   - One specific target for the next 2-hour run.

## Quality Gate (must pass each cycle)

A cycle is valid only if all are true:
1. Includes explicit `SUBJECT`
2. Includes one completed improvement (not just analysis)
3. Includes previous-cycle delta
4. Includes grade + reason
5. Includes evidence path

If any gate fails, cycle result = `NOT_READY`.

## OpenClaw Infrastructure

### Systemd Services
- **Main Service:** `pid-129-btc-alerts.service` (runs alert loop continuously)
- **Watchdog:** `pid-129-watchdog.service` (monitors health and restarts if needed)

### Health Check Script
- **Path:** `scripts/pid-129/healthcheck.sh`
- **Checks:** Service status, log files, data freshness, recent alerts, venv availability
- **Exit Codes:** 0 = HEALTHY, 1 = UNHEALTHY, 2 = CHECK FAILED

### Logging
- **Alerts:** `logs/pid-129-alerts.jsonl` (JSONL format)
- **Health:** `logs/pid-129-health.log`
- **Watchdog:** `logs/pid-129-watchdog.log`
- **Service:** `logs/service.log`

### Reporting
- **Daily Scorecard:** `reports/pid-129-daily-scorecard.md`
- **Generator:** `scripts/pid-129/generate_scorecard.py`
- **Schedule:** Daily at midnight UTC

### Remote Operations (from Mac mini)
```bash
# Status check (Mac/Linux)
ssh <target> "systemctl --user status pid-129-btc-alerts.service"

# Status check (Windows)
ssh <target> "powershell -File <path>/scripts/pid-129/healthcheck.ps1"

# Restart service (Mac/Linux)
ssh <target> "systemctl --user restart pid-129-btc-alerts.service"

# Manual alert cycle
ssh <target> "cd <path> && python app.py --once"

# Generate scorecard
ssh <target> "cd <path> && python scripts/pid-129/generate_scorecard.py"
```

## Failure & Outcome Matrix

### Failure Modes

| Failure Mode | Detection | Action | Escalation |
|--------------|-----------|--------|------------|
| Service not running | Health check | Restart service | Log + notify EMBER |
| Service crashloop | Health check + logs | Restart + inspect logs | Notify EMBER |
| Missing credentials | Health check + logs | Pause only this step | Trigger onboarding prompt |
| API error | Alert generation | Retry 3x + NO-TRADE fallback | Log + notify EMBER |
| Market data stale | Health check | Suppress signal + NO-TRADE | Log + notify EMBER |
| Telegram send failure | Alert generation | Retry with backoff | Queue local alert + notify EMBER |
| Disk/log pressure | Health check | Rotate/compress logs | Log + notify EMBER |

### Alert Schema

```json
{
  "pid": "129",
  "symbol": "BTCUSD",
  "bias": "LONG|SHORT|NO-TRADE",
  "confidence": 0-100,
  "strategy": "strategy_name",
  "entry": 0.0,
  "tp1": 0.0,
  "tp2": 0.0,
  "invalidation": 0.0,
  "risk": "low|moderate|high",
  "reason": ["code1", "code2"],
  "telegram_failed": false,
  "timestamp": "2026-02-16T10:00:00Z"
}
```

## Test Gates (Mandatory Before Complete)

Completion is blocked unless all pass:

- **T1:** Health check passes (exit code 0)
- **T2:** Service active for burn-in period (5 minutes)
- **T3:** LONG fixture emits valid schema alert
- **T4:** SHORT fixture emits valid schema alert
- **T5:** NO-TRADE fixture emits valid schema alert
- **T6:** Telegram smoke send succeeds
- **T7:** Service restart succeeds without data loss
- **T8:** Watchdog restart succeeds
- **T9:** One induced failure handled safely
- **T10:** Daily scorecard generates correctly

## Definition of Done

PID-129 is complete when:
1. All pre-gate checks pass,
2. All test gates T1–T10 pass,
3. Failure matrix handling is validated for critical cases,
4. Evidence is written to durable report files,
5. System is remotely controllable from Mac mini with no further George input except unavoidable onboarding prompts.

## Immediate Activation Contract

When this PID is active, the next cycle starts with:
- subject detection (BTC Alerts MVP)
- one concrete improvement
- delta + grade + evidence
- explicit next-step target for the following 2-hour interval
