"""Apply all Phase 26 hardening patches to dashboard_server.py and dashboard.html."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
SERVER = BASE / "scripts" / "pid-129" / "dashboard_server.py"
HTML   = BASE / "dashboard.html"

# ──────────────────────────────────────────────
#  PATCH 1: dashboard_server.py
# ──────────────────────────────────────────────
s = SERVER.read_text(encoding="utf-8")

# 1a. Add imports for fetch_btc_price, fetch_flow_context, fetch_derivatives_context
if "fetch_derivatives_context" not in s:
    old_import_block = "# Module-level shared state"
    new_imports = """_LAST_CONTEXT = {}  # Last-known intelligence context (anti-flicker)
_LAST_REBUILD = 0.0

try:
    from collectors.price import fetch_btc_price
    from collectors.flows import fetch_flow_context
    from collectors.derivatives import fetch_derivatives_context
    _HAS_COLLECTORS = True
except ImportError:
    _HAS_COLLECTORS = False
    print("Warning: Could not import collectors. Derivatives/Price alpha may be missing.")

# Module-level shared state"""
    s = s.replace(old_import_block, new_imports)

# 1b. Add /api/dashboard route to do_GET
if "/api/dashboard" not in s:
    s = s.replace(
        """    def do_GET(self):
        if self.path == "/ws":
            self._handle_websocket()
        elif self.path.startswith("/api/alert/"):
            self._serve_alert_detail()
        elif self.path == "/api/alerts":
            self._serve_alerts_full()
        elif self.path == "/api/command":""",
        """    def do_GET(self):
        if self.path == "/ws":
            self._handle_websocket()
        elif self.path.startswith("/api/alert/"):
            self._serve_alert_detail()
        elif self.path == "/api/dashboard":
            with _STATE_LOCK:
                self._json_response(_CACHED_DATA)
            return
        elif self.path == "/api/alerts":
            self._serve_alerts_full()
        elif self.path == "/api/command":""")

# 1c. Add flows, derivatives, cached_context, data_age_seconds to return dict
#     Also add stale-alert fallback + derivatives fetching
old_return_block = """        portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})
        mid = _latest_price(all_recent_alerts)
        spread = _estimate_spread(all_recent_alerts) if mid else 0.0

        # ── Phase 25: Order Flow BS-Filter ──
        # Extract taker_ratio from latest alert's flow data or decision_trace
        taker_ratio = 1.0
        for a in reversed(all_recent_alerts):
            dt_ctx = (a.get("decision_trace") or {}).get("context", {})
            # Check for flow codes that indicate taker direction
            codes = (a.get("decision_trace") or {}).get("codes", [])
            if "FLOW_TAKER_BULLISH" in codes:
                taker_ratio = 1.4
                break
            elif "FLOW_TAKER_BEARISH" in codes:
                taker_ratio = 0.6
                break"""

new_return_block = """        global _LAST_CONTEXT
        portfolio = _safe_json(PORTFOLIO_PATH, {"balance": 10000, "positions": [], "closed_trades": [], "max_drawdown": 0})

        # ── Phase 26: Stale Alert Hardening ──
        last_alert_time = 0.0
        if all_recent_alerts:
            try:
                ts_str = all_recent_alerts[-1].get("timestamp", "")
                if ts_str:
                    ts_clean = ts_str.split(".")[0].replace("Z", "").replace("T", " ")
                    dt_last = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
                    last_alert_time = dt_last.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                pass

        now_ts = datetime.now(timezone.utc).timestamp()
        alerts_stale = (now_ts - last_alert_time > 120) or not all_recent_alerts
        data_age_seconds = now_ts - last_alert_time if last_alert_time > 0 else 9999

        mid = _latest_price(all_recent_alerts)
        taker_ratio = 1.0

        if not alerts_stale:
            for a in reversed(all_recent_alerts):
                codes = (a.get("decision_trace") or {}).get("codes", [])
                if "FLOW_TAKER_BULLISH" in codes:
                    taker_ratio = 1.4
                    break
                elif "FLOW_TAKER_BEARISH" in codes:
                    taker_ratio = 0.6
                    break

        budget = {"remaining": 8}
        if alerts_stale and _HAS_COLLECTORS:
            try:
                price_snap = fetch_btc_price(budget)
                if price_snap.healthy and price_snap.price > 0:
                    mid = price_snap.price
                flow_snap = fetch_flow_context(budget)
                if flow_snap.healthy:
                    taker_ratio = flow_snap.taker_buy_vol_ratio
            except Exception:
                pass

        spread = _estimate_spread(all_recent_alerts) if mid else 0.0

        # ── Phase 26: Derivatives context ──
        derivatives = {"healthy": False, "source": "none"}
        if _HAS_COLLECTORS:
            try:
                deriv_ctx = fetch_derivatives_context(budget)
                derivatives = {
                    "funding_rate": deriv_ctx.funding_rate,
                    "oi_change_24h": deriv_ctx.oi_change_24h,
                    "basis_annualized": deriv_ctx.basis_annualized,
                    "source": deriv_ctx.source,
                    "healthy": deriv_ctx.healthy
                }
            except Exception:
                derivatives = {"healthy": False, "source": "error"}

        # Update cached context for anti-flicker
        if all_recent_alerts:
            latest_ctx = (all_recent_alerts[-1].get("decision_trace") or {}).get("context", {})
            if latest_ctx:
                _LAST_CONTEXT.update(latest_ctx)"""

s = s.replace(old_return_block, new_return_block)

# 1d. Add flows/derivatives/cached_context/data_age_seconds to return dict
old_dict_end = """            "bs_filter": bs_filter,
            "bs_severity": bs_severity,
            "circuit_breaker": circuit_breaker,
            "logs": f"Heartbeat {datetime.now().strftime('%H:%M:%S')}",
        }"""
new_dict_end = """            "bs_filter": bs_filter,
            "bs_severity": bs_severity,
            "flows": {"taker_ratio": round(taker_ratio, 2)},
            "derivatives": derivatives,
            "cached_context": _LAST_CONTEXT,
            "data_age_seconds": round(data_age_seconds, 0),
            "circuit_breaker": circuit_breaker,
            "logs": f"Heartbeat {datetime.now().strftime('%H:%M:%S')}",
        }"""
s = s.replace(old_dict_end, new_dict_end)

# 1e. Watcher loop: also rebuild periodically (every 10s) for stale data fallback
s = s.replace(
    "            if changed or not _CACHED_DATA:",
    """            now = time.time()
            if changed or not _CACHED_DATA or (now - _LAST_REBUILD > 10):"""
)
s = s.replace(
    """                new_data = get_dashboard_data()
                with _STATE_LOCK:
                    _CACHED_DATA = new_data""",
    """                global _LAST_REBUILD
                new_data = get_dashboard_data()
                with _STATE_LOCK:
                    _CACHED_DATA = new_data
                _LAST_REBUILD = now"""
)

SERVER.write_text(s, encoding="utf-8")
print(f"✅ dashboard_server.py patched ({SERVER})")

# ──────────────────────────────────────────────
#  PATCH 2: dashboard.html  
# ──────────────────────────────────────────────
h = HTML.read_text(encoding="utf-8")

# 2a. Task 7: Add Funding / Basis and OI Delta cards after Open PnL
open_pnl_card = """            <div class="stat-card">
                <div class="stat-label">Open PnL</div>
                <div id="live-open-pnl" class="live-value">--</div>
            </div>
        </div>
    </section>"""
sm_cards = """            <div class="stat-card">
                <div class="stat-label">Open PnL</div>
                <div id="live-open-pnl" class="live-value">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Funding / Basis</div>
                <div id="tape-funding" class="live-value" style="color:#00ff88;">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">OI Delta (5m)</div>
                <div id="tape-oi-delta" class="live-value">--</div>
            </div>
        </div>
    </section>"""
if "tape-funding" not in h:
    h = h.replace(open_pnl_card, sm_cards)

# 2b. Task 2: Anti-Flicker Context (merge cached_context with alert context)
if "cachedCtx" not in h and "cached_context" not in h:
    h = h.replace(
        "const wsCtx = ((wsLatest.decision_trace || {}).context) || {};",
        "const alertCtx = ((wsLatest.decision_trace || {}).context) || {};\n                        const cachedCtx = data.cached_context || {};\n                        const wsCtx = Object.assign({}, cachedCtx, alertCtx);"
    )

# 2c. Task 1: Move taker ratio update outside of btcAlerts.length block
# Find the taker line and ensure it runs outside the if block
# Actually the taker line at `_el('tape-taker', taker ? ...)` is inside the if(btcAlerts.length > 0) block.
# We need to add an independent update outside. Search for "els.sync.textContent"
sync_line = "els.sync.textContent = 'Synced: ' + new Date().toLocaleString();"
if "data.data_age_seconds" not in h:
    h = h.replace(sync_line, sync_line + """

                    // ── Phase 26: Taker Ratio (independent of alerts) ──
                    const takerGlobal = (data.flows || {}).taker_ratio;
                    const takerEl = document.getElementById('tape-taker');
                    if (takerEl && takerGlobal) takerEl.textContent = takerGlobal.toFixed(2);

                    // ── Phase 26: Data Freshness Warning ──
                    const age = data.data_age_seconds || 0;
                    if (age > 300) {
                        els.sync.style.color = '#ff4d4d';
                        els.sync.style.fontWeight = 'bold';
                        els.sync.textContent = '⚠️ STALE DATA (' + Math.round(age / 60) + 'm old)';
                    } else {
                        els.sync.style.color = 'var(--text-muted)';
                        els.sync.style.fontWeight = 'normal';
                    }

                    // ── Phase 26: Smart Money Derivatives UI ──
                    const deri = data.derivatives || {};
                    const fndEl = document.getElementById('tape-funding');
                    if (fndEl && deri.funding_rate !== undefined) {
                        const fr = deri.funding_rate * 100;
                        fndEl.textContent = (fr >= 0 ? '+' : '') + fr.toFixed(4) + '%';
                        fndEl.style.color = fr < 0 ? '#00ff88' : (fr > 0.01 ? '#ff4d4d' : '#ffffff');
                    }
                    const oiEl = document.getElementById('tape-oi-delta');
                    if (oiEl && deri.oi_change_24h !== undefined) {
                        const oic = deri.oi_change_24h;
                        oiEl.textContent = (oic >= 0 ? '+' : '') + oic.toFixed(2) + '%';
                        oiEl.style.color = oic >= 0 ? '#00ff88' : '#ff4d4d';
                    }""")

# 2d. Task 3: Copilot PnL NaN guards
h = h.replace("const sz = pos.size_usdt || 0;", "const sz = Number(pos.size_usdt) || 0;")
h = h.replace(
    """                            if (entry > 0) {""",
    """                            if (entry > 0 && sz > 0 && isFinite(entry)) {""")

# 2e. Task 5: BS-Filter CLEAR styling
h = h.replace(
    """                        } else {
                            bsEl.style.background = 'transparent';
                            bsEl.style.color = 'var(--text-muted)';
                            bsEl.style.border = '1px solid transparent';
                        }""",
    """                        } else {
                            bsEl.textContent = '✅ ORDER FLOW CLEAR';
                            bsEl.style.background = 'rgba(0,255,204,0.06)';
                            bsEl.style.color = 'var(--accent)';
                            bsEl.style.border = '1px solid rgba(0,255,204,0.2)';
                        }""")

# 2f. Task 4: Execute Button restoration after circuit breaker clears
h = h.replace(
    """                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                        }""",
    """                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                            const latest = (data.alerts || [])[0] || {};
                            const tier = latest.tier || 'NO-TRADE';
                            if (tier === 'A+') {
                                execBtn.textContent = '🟢 EXECUTE';
                                execBtn.style.background = '#00cc88';
                            } else if (tier === 'B') {
                                execBtn.textContent = '🟡 EXECUTE (WATCH)';
                                execBtn.style.background = '#cc8800';
                            } else {
                                execBtn.textContent = '⚠️ EXECUTE (HIGH RISK)';
                                execBtn.style.background = '#ff4d4d';
                            }
                        }""")

HTML.write_text(h, encoding="utf-8")
print(f"✅ dashboard.html patched ({HTML})")
print("Phase 26 hardening complete.")
