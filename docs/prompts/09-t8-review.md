---
date: 2026-10-01
model: sonnet (the `code-reviewer` agent's frontmatter alias, `.claude/agents/code-reviewer.md`; Claude Sonnet 5.5)
model_reason: "AGENTS.md § Review: the reviewer runs on `sonnet` with the checklist; `opus` only when the spec marks the change security-critical, which spec-v0 does not"
harness: Claude Code, `code-reviewer` subagent in a clean context (read-only: Read, Glob, Grep, Bash), spawned by the orchestrator under `go docs/spec/spec-v0.md`
stage: review
tokens_in: unknown   # combined subagent total 210,560 tokens (harness exposes no split); see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: T8 of `docs/spec/spec-v0.md` §10 — *the task is itself the clean-context review* (EC-09). Output: `docs/reports/review-v0.md`.

Request text (verbatim, the whole prompt the reviewer received):

> Review `git diff 8385584..HEAD` of the repo /home/akh/aihome/coders-su/projects/ai-investor-game against its spec docs/spec/spec-v0.md (the contract; Appendix A maps requirements to tests). Read AGENTS.md first.
> Gates 1–4 are green (`uv run --locked pytest`: 75 passed) and one live gate-5 run passed (capture: docs/assets/acceptance-v0.txt). Do not re-run gate 5, never read or print `.env`, never use `--env-file`, no network.
> Report per your output format. One entry per finding: severity, `file:line`, one-sentence problem, concrete failure scenario, and whether you consider it must-fix (spec violation, wrong behavior, secret exposure, a test that proves nothing) or optional.
> Return findings only, no file dumps, ≤ 120 lines.

## Goal

A clean-context review of everything the run added since the scaffold, against the spec as the contract.

## Constraints

Read-only; no file written by the reviewer (the orchestrator writes `docs/reports/review-v0.md` from its report and rules on each finding); no `.env`, no live run, no network.

## Acceptance

Every finding carries severity, `file:line`, a one-sentence problem and a failure scenario; the orchestrator rules each as must-fix or waived with a reason.

## Stop

A red live run after the fixes stops the run (EC-09, EC-08); the reviewer itself has no stop condition.
