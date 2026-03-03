# Phase 28 — Canonical Product Spec (Single-Click Verified Trading)

**Prime Directive:** "A singular, perfectly calibrated Bitcoin futures dashboard where a single click yields a mathematically verified, high-confidence LONG or SHORT play."

**Status:** Active canonical spec
**Updated:** 2026-03-03

---

## Scope

This phase defines the final decision contract for the dashboard. It is **single-click**, not zero-click.

- Human confirms execution with one click.
- System must present a deterministic `EXECUTE` or `WAIT` decision.
- Decision must be backed by explicit math/risk gates shown to the operator.

---

## Decision Contract (Authoritative)

A trade is executable only when all required gates pass.

`READY = true` iff all are true:
1. Circuit breaker is inactive.
2. Data freshness is within threshold.
3. Spread/slippage gate passes.
4. Candidate exists (LONG or SHORT).
5. Confidence >= configured floor.
6. R:R >= configured floor for timeframe.
7. Signal age <= max signal age.

If any gate fails:
- `READY = false`
- `operator_decision = WAIT`
- Blockers must be shown as explicit reasons.

---

## Required Above-the-Fold Output

The command screen must show, without scrolling:
1. Direction verdict (`LONG` / `SHORT` / `WAIT`).
2. Gate status (`GREEN` / `AMBER` / `RED`).
3. Confidence, R:R, entry, invalidation, TP.
4. Trade safety checklist with pass/fail states.
5. Exact blocker text when not executable.
6. One-click execute control (disabled unless executable).

---

## Mathematical Verification Requirements

The dashboard must display the exact inputs used in gating:
- Confidence score
- R:R value and threshold
- Signal age
- Data age
- Spread estimate
- Circuit breaker status

The operator should not infer hidden logic; all decisive inputs must be visible.

---

## Execution Mode Policy

- Default execution mode: `PAPER`.
- `LIVE` requires explicit environment enablement.
- One-click path must execute only the current vetted candidate.

---

## Out of Scope for Phase 28

- Zero-click autonomous execution as primary mode.
- New external data programs (macro calendar, CVD collector) unless separately approved.
- Broad UI redesign not tied to decision quality.

---

## Supersession Notes

- This document supersedes older "zero-click" framing in previous Phase 28 notes.
- Historical docs remain for audit but are non-authoritative.
