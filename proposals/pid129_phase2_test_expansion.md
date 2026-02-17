# PID-129 Phase 2: Test Expansion and Replay Tooling Proposal

## Objective
Expand test coverage for BTC Alerts MVP Phase 2 with deterministic replay tooling to reproduce scenarios.

## Targets
- Unit tests for alert generation, persistence, and deduplication.
- Integration tests for webhook delivery, retry/backoff, and idempotency keys.
- Replay tooling to capture live runs and replay deterministically in CI.

## Approach
- Introduce a TestHarness utility to seed data and assert end-to-end results.
- Add a ReplayEngine that stores event traces (inputs, timestamps, responses) in `/tmp/replay-logs` or artifacts.
- Build a deterministic clock mock to allow replay reproducibility.

## Risks & Mitigations
- Sensitive data in logs: redact PII in replay logs.
- CI flakiness: implement retries with exponential backoff.

## Deliverables
- Patch-ready diffs for tests + replay.
- CI configuration to run replay tests.
- Documentation for creating/running replays.

## Note
This file is the Phase 2 planning deliverable and baseline for concrete test/replay implementation in the next execution packet.