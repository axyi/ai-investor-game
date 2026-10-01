---
date: 2026-10-01
model: claude-sonnet-5-5 (orchestrator and the implementing subagent, `sonnet` alias of the Agent tool)
model_reason: "a small, fully specified fix for a clean-context review finding; the spec header fixes the executor to the Sonnet class (`claude-sonnet-5`), the actual id differs from the header's name (noted in report-v0.md NOTES)"
harness: Claude Code, `go docs/spec/spec-v0.md`; fix F4 delegated to a general-purpose subagent briefed by docs/spec/task-briefs/v0-T8.md
stage: fix
tokens_in: unknown   # combined subagent total 66,916 tokens (harness exposes no split); see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: fix F4 of the T8 review (EC-09) — the `--show-decisions` wiring was not tested through `main` (finding 4, 🟡 ruled up to must-fix) (`docs/reports/review-v0.md`). Delegated: yes — brief `docs/spec/task-briefs/v0-T8.md`, section "F4" (one brief for all T8 fixes, passed by path).

Subagent prompt (verbatim):

> You are the executor of fix F4 of the ai-investor-game spec-v0 review (repo root: <repo>).
> Your complete assignment is the fix-brief file <repo>/docs/spec/task-briefs/v0-T8.md — read it first, whole, then do ONLY the section "F4" (plus the hard rules), reading the spec only through the line ranges it lists. The review it rests on is docs/reports/review-v0.md.
> Write only the paths F4 owns; do not commit or stage anything; never read or touch .env; never run gate 5.
> Return the summary the brief's rule 9 defines (≤ 40 lines, no file contents) — nothing else.

## Goal

Prove through `main` over the fakes that `--show-decisions` reaches `play`: the run with the flag prints exactly GAME-04's two `[решения]` lines, the same run without it prints none. The proof extends the existing `T-V0-GAME-10` test; no new id.

## Constraints

Only the paths the brief's section "F4" owns; no new `T-V0-*` ids; `--locked` uv commands only; no `.env`, no `--env-file`, no live run (gate 5 runs once after all fixes, EC-09); no skip/xfail/weakened tests; no commit, stage or push.

## Acceptance

The brief's section "F4" acceptance, shown by mutation or a red run; gates 1–4 exit 0 (GATE-01), verified again by the orchestrator in the main context before the commit.

## Stop

A spec-internal contradiction, or the same gate failing twice with the same error → the subagent returns BLOCKED; the orchestrator stops under EC-08.

Red evidence is by mutation (EC-02 deviation, recorded: a coverage gap, green against correct code): `show_decisions=args.show_decisions` → `show_decisions=False` in `__main__.py` fails the extended `T-V0-GAME-10` (`[] == [...]`); the orchestrator repeated it and compared the restored file identical to HEAD. The subagent hit ruff ISC004 in its own test literals before the first gate run and wrapped the strings in parentheses (not a gate repair cycle).
