# 🤖 EMBER OPERATOR GUIDE

> **System Purpose:** Autonomous BTC intelligence, alerting, and self-tuning.
> **Current Engine:** v18.0 (Precision Dashboard + Confluence + Auto-Tuning)

---

## 🕹️ Quick Commands (On-Liners)

| Task | Command |
|:---|:---|
| **Toggle ON** | `python scripts/toggle.py on` |
| **Toggle OFF** | `python scripts/toggle.py off` |
| **Check Status** | `python scripts/toggle.py status` |
| **Run Once** | `python app.py --once` |
| **Get Briefing** | `python scripts/morning_briefing.py` |
| **Self-Tune** | `python tools/auto_tune.py` |
| **Full Pipeline** | `powershell -File scripts/pipeline.ps1` |
| **Generate Dashboard** | `python scripts/pid-129/generate_dashboard.py` |
| **Serve Dashboard (localhost:8000)** | `python scripts/pid-129/dashboard_server.py` |

---

## 📂 Key Files & State

- **`config.py`**: Central tunables. `TIMEFRAME_RULES` are auto-adjusted by the tuner.
- **`reports/morning_briefing.md`**: Human-readable 6 AM briefing.
- **`reports/morning_briefing.json`**: **Machine-readable** state for other agents.
- **`logs/pid-129-alerts.jsonl`**: The source of truth for all signals and outcomes.
- **`dashboard.html`**: Visual representation of current market intelligence.

---

## 🤖 Instructions for AI Agents

If you are an AI agent helping with this project, follow these rules:

1. **State Discovery**: Always check `reports/morning_briefing.json` first to understand the current market regime and system bias.
2. **Context Limits**: Do not read `app.py` or `engine.py` unless you are fixing a bug. All business logic is summarized in `config.py`.
3. **Execution**: Use `python app.py --once` for testing. Never change `config.py` manually unless asked; let `tools/auto_tune.py` handle it.
4. **Verification**: If you change intelligence logic, run `PYTHONPATH=. python -m pytest tests/` immediately.
5. **Briefing Integration**: After making changes, run the full pipeline to see how your changes impact the morning briefing numbers.

---

## 🛠️ Troubleshooting

- **System won't run?** Check if `DISABLED` file exists in root. Use `python scripts/toggle.py on`.
- **Too many alerts?** The auto-tuner will tighten thresholds nightly. Or manually increase `trade_long` in `config.py`.
- **Missing dashboard data?** Ensure `app.py` is running or has run recently to populate `decision_trace` in the logs.

---
_Build v18.0 | Last Updated: 2026-02-26_
