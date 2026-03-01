import sys
from pathlib import Path

p = Path("dashboard.html")
c = p.read_text(encoding="utf-8")

# Task 7.1: SM Cards
sm_cards = """            <div class="stat-card">
                <div class="stat-label">Funding / Basis</div>
                <div id="tape-funding" class="live-value" style="color:#00ff88;">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">OI Delta (5m)</div>
                <div id="tape-oi-delta" class="live-value">--</div>
            </div>
        </div>
    </section>"""
c = c.replace("""            <div class="stat-card">
                <div class="stat-label">Open PnL</div>
                <div id="live-open-pnl" class="live-value">--</div>
            </div>
        </div>
    </section>""", """            <div class="stat-card">
                <div class="stat-label">Open PnL</div>
                <div id="live-open-pnl" class="live-value">--</div>
            </div>""" + sm_cards)

# Task 2: Anti-Flicker Context
c = c.replace('const wsCtx = ((wsLatest.decision_trace || {}).context) || {};', 
              'const alertCtx = ((wsLatest.decision_trace || {}).context) || {};\n                        const cachedCtx = data.cached_context || {};\n                        const wsCtx = Object.assign({}, cachedCtx, alertCtx);')

# Task 3: Copilot Harden
c = c.replace('const sz = pos.size_usdt || 0;', 'const sz = Number(pos.size_usdt) || 0;')
c = c.replace('if (entry > 0) {', 'if (entry > 0 && sz > 0 && isFinite(entry)) {')

# Task 5: BS-Filter style
c = c.replace('''                        } else {
                            bsEl.style.background = 'transparent';
                            bsEl.style.color = 'var(--text-muted)';
                            bsEl.style.border = '1px solid transparent';
                        }''', 
'''                        } else {
                            bsEl.textContent = '✅ ORDER FLOW CLEAR';
                            bsEl.style.background = 'rgba(0,255,204,0.06)';
                            bsEl.style.color = 'var(--accent)';
                            bsEl.style.border = '1px solid rgba(0,255,204,0.2)';
                        }''')

# Task 6 & 7.2: Sync + Data Age + SM JS Injection
c = c.replace("els.sync.textContent = 'Synced: ' + new Date().toLocaleString();", 
'''els.sync.textContent = 'Synced: ' + new Date().toLocaleString();

                    // ── Phase 26: Data Freshness Warning ──
                    const age = data.data_age_seconds || 0;
                    if (age > 300) { // 5 minutes
                        els.sync.style.color = '#ff4d4d';
                        els.sync.style.fontWeight = 'bold';
                        els.sync.textContent = '⚠️ STALE DATA (' + Math.round(age / 60) + 'm old)';
                    } else {
                        els.sync.style.color = 'var(--text-muted)';
                        els.sync.style.fontWeight = 'normal';
                    }

                    // ── Phase 26: Smart Money UI Injection ──
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
                    }''')

# Task 4: Restore Exec Button
c = c.replace('''                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                        }''', 
'''                        } else {
                            execBtn.disabled = false;
                            execBtn.style.opacity = '1';
                            execBtn.style.cursor = 'pointer';
                            // Restore correct tier-colored label
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
                        }''')

p.write_text(c, encoding="utf-8")
print("Dashboard hardened.")
