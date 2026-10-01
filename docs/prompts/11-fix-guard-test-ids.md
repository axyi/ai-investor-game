---
date: 2026-10-01
model: claude-sonnet-5-5 (orchestrator and the implementing subagent, `sonnet` alias of the Agent tool)
model_reason: "a small, fully specified fix for a clean-context review finding; the spec header fixes the executor to the Sonnet class (`claude-sonnet-5`), the actual id differs from the header's name (noted in report-v0.md NOTES)"
harness: Claude Code, `go docs/spec/spec-v0.md`; fix F2 delegated to a general-purpose subagent briefed by docs/spec/task-briefs/v0-T8.md
stage: fix
tokens_in: unknown   # combined subagent total 51,657 tokens (harness exposes no split); see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: fix F2 of the T8 review (EC-09) — the three guard tests did not carry spec ids (finding 2, 🔴) (`docs/reports/review-v0.md`). Delegated: yes — brief `docs/spec/task-briefs/v0-T8.md`, section "F2" (one brief for all T8 fixes, passed by path).

Subagent prompt (verbatim):

> You are the executor of fix F2 of the ai-investor-game spec-v0 review (repo root: /home/akh/aihome/coders-su/projects/ai-investor-game).
> Your complete assignment is the fix-brief file /home/akh/aihome/coders-su/projects/ai-investor-game/docs/spec/task-briefs/v0-T8.md — read it first, whole, then do ONLY the section "F2" (plus the hard rules), reading the spec only through the line ranges it lists. The review it rests on is docs/reports/review-v0.md.
> Write only the paths F2 owns; do not commit or stage anything; never read or touch .env; never run gate 5.
> Return the summary the brief's rule 9 defines (≤ 40 lines, no file contents) — nothing else.

## Goal

Rename the three guard tests of `tests/test_guards.py` to the spec's id form: `test_t_v0_tst_01_offline`, `test_t_v0_tst_02_import_isolation`, `test_t_v0_sec_01_env_example` (bodies unchanged), so traceability by id (TST-01, TST-02, SEC-01) finds them.

## Constraints

Only the paths the brief's section "F2" owns; no new `T-V0-*` ids; `--locked` uv commands only; no `.env`, no `--env-file`, no live run (gate 5 runs once after all fixes, EC-09); no skip/xfail/weakened tests; no commit, stage or push.

## Acceptance

The brief's section "F2" acceptance, shown by mutation or a red run; gates 1–4 exit 0 (GATE-01), verified again by the orchestrator in the main context before the commit.

## Stop

A spec-internal contradiction, or the same gate failing twice with the same error → the subagent returns BLOCKED; the orchestrator stops under EC-08.

No red run: a rename of structural tests that stay green (EC-02 carve-out, recorded). `pytest -k t_v0_tst_02` selects exactly one test; the suite stays at 75. The historical mention of the old names in `docs/prompts/02-t1-skeleton.md` is a log of what happened in T1 and was left as written.
