---
name: parallel-big-project-executor
description: Execute large multi-task repo work with minimum user effort by splitting independent tasks into parallel branches/worktrees, implementing changes directly, validating safely, committing each stream, merging cleanly, and preparing PR messages. Use when user asks to do all tasks for them, reduce actions, or run parallel workstreams with commit/merge automation.
---

# Parallel Big Project Executor

Follow this workflow end-to-end.

## 1) Triage and split
- Read the request and split work into independent tracks.
- Keep risky refactors out of early tracks; do safest non-breaking tracks first.
- Prefer 2-5 tracks max unless explicitly asked for more.

## 2) Branch/worktree strategy
- Create one branch per track with clear names:
  - `feat/<short-topic>` for features
  - `fix/<short-topic>` for fixes
  - `chore/<short-topic>` for maintenance
- Use separate worktrees for true parallelism when tracks do not overlap.
- If overlap risk is high, sequence those tracks instead of parallelizing.

## 3) Implement directly
- Make code changes without asking user for intermediate confirmations unless blocked.
- Keep files under ~500 lines when practical; split helpers into focused functions.
- Prefer additive/non-breaking changes first.
- Preserve existing behavior unless the task explicitly requires behavior changes.

## 4) Validate per track
- Run the smallest relevant checks first (lint/type/unit scope).
- Run broader project checks once integration is complete.
- If an environment limitation blocks a check, report it explicitly and continue with available static validation.

## 5) Commit discipline
- Commit each track with focused messages:
  - Subject in imperative mood, ~50-72 chars.
  - Include only relevant files.
- Avoid bundling unrelated changes.

## 6) Integrate and resolve
- Merge tracks back to the target branch in low-conflict order.
- Resolve conflicts while preserving intended behavior from both sides.
- Re-run key validations after final merge.

## 7) PR package
- Prepare a concise PR title and body with:
  - Summary of user-visible outcomes
  - Files/modules changed
  - Validation results
  - Known caveats/limitations
- If tooling supports PR creation, create it after commit.

## 8) Response style for this user preference
- Start with **"Do this now"**.
- Minimize user actions; do work directly whenever possible.
- If user commands are needed, provide strict-order, copy-pasteable PowerShell-safe commands first.
- Keep explanations short unless user asks for detail.

## 9) Safety rules
- Default to safest path first.
- Call out high-risk changes before applying them.
- Do not leave placeholder TODOs for required behavior.
