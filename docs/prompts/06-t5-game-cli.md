---
date: 2026-10-01
model: claude-sonnet-5-5 (orchestrator and the implementing subagent, `sonnet` alias of the Agent tool)
model_reason: "the spec header fixes the executor to the Sonnet class (`claude-sonnet-5`); T5 is a fully specified task — the spec carries the decisions; the actual id differs from the header's name (noted in report-v0.md NOTES)"
harness: Claude Code, `go docs/spec/spec-v0.md`; T5 delegated to a general-purpose subagent briefed by docs/spec/task-briefs/v0-T5.md
stage: generation
tokens_in: unknown   # combined subagent total 205,126 tokens (harness exposes no split); see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: T5 of `docs/spec/spec-v0.md` §10. Delegated: yes — brief `docs/spec/task-briefs/v0-T5.md` (written by the orchestrator, passed by path, committed with this task).

Subagent prompt (verbatim):

> You are the executor of task T5 of the ai-investor-game spec-v0 (repo root: <repo>).
> Your complete assignment is the task-brief file <repo>/docs/spec/task-briefs/v0-T5.md — read it first, whole, and follow it exactly (read the spec only through the line ranges it lists).
> Write only the paths it says you own; do not commit or stage anything; never read or touch .env.
> Return the summary the brief's rule 9 defines (≤ 40 lines, no file contents) — nothing else.

## Goal

Implement `investor_game/game.py` (`play`, `check_result`), `fakes.py`, `__main__.py` (`main`: argparse, exit codes, `--selftest`, `--script`, `--check-result`), `acceptance/live-script.txt` and `tests/test_game.py`, `tests/test_cli.py` (spec §4.5, §6, §7, App. B; offline on the fakes; the live script is not run before T7).

## Constraints

Test-first (EC-02); only the paths the brief lists; `--locked` uv commands only; no `.env`, no `--env-file`, no live LLM/Laya run; no skip/xfail/weakened tests; no commit, stage or push; fix loop ≤ 3 cycles (EC-05).

## Acceptance

The brief's "Acceptance" section; gates 1–4 exit 0 (GATE-01), verified again by the orchestrator in the main context before the commit.

## Stop

A spec-internal contradiction, the same gate failing twice with the same error, or three exhausted repair cycles → the subagent returns BLOCKED with the last 40 output lines; the orchestrator stops under EC-08.
