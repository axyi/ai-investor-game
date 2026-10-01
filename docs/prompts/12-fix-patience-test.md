---
date: 2026-10-01
model: claude-sonnet-5-5 (orchestrator and the implementing subagent, `sonnet` alias of the Agent tool)
model_reason: "a small, fully specified fix for a clean-context review finding; the spec header fixes the executor to the Sonnet class (`claude-sonnet-5`), the actual id differs from the header's name (noted in report-v0.md NOTES)"
harness: Claude Code, `go docs/spec/spec-v0.md`; fix F3 delegated to a general-purpose subagent briefed by docs/spec/task-briefs/v0-T8.md
stage: fix
tokens_in: unknown   # combined subagent total 77,918 tokens (harness exposes no split); see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: fix F3 of the T8 review (EC-09) — patience carry across turns was not tested at game level (finding 3, 🟡 ruled up to must-fix) (`docs/reports/review-v0.md`). Delegated: yes — brief `docs/spec/task-briefs/v0-T8.md`, section "F3" (one brief for all T8 fixes, passed by path).

Subagent prompt (verbatim):

> You are the executor of fix F3 of the ai-investor-game spec-v0 review (repo root: <repo>).
> Your complete assignment is the fix-brief file <repo>/docs/spec/task-briefs/v0-T8.md — read it first, whole, then do ONLY the section "F3" (plus the hard rules), reading the spec only through the line ranges it lists. The review it rests on is docs/reports/review-v0.md.
> Write only the paths F3 owns; do not commit or stage anything; never read or touch .env; never run gate 5.
> Return the summary the brief's rule 9 defines (≤ 40 lines, no file contents) — nothing else.

## Goal

Prove through `play` over the fakes that patience carries across turns (Appendix B scenario B5): persona 3, a rude message on both turns, Laya counter → turn 2 ends `walk_away_patience`, and the TECH facts of turn 2 show `Rounds of patience left: 1.` after turn 1's 3. The proof extends the existing `T-V0-GAME-11` test; no new id.

## Constraints

Only the paths the brief's section "F3" owns; no new `T-V0-*` ids; `--locked` uv commands only; no `.env`, no `--env-file`, no live run (gate 5 runs once after all fixes, EC-09); no skip/xfail/weakened tests; no commit, stage or push.

## Acceptance

The brief's section "F3" acceptance, shown by mutation or a red run; gates 1–4 exit 0 (GATE-01), verified again by the orchestrator in the main context before the commit.

## Stop

A spec-internal contradiction, or the same gate failing twice with the same error → the subagent returns BLOCKED; the orchestrator stops under EC-08.

Red evidence is by mutation, not a red run (EC-02 deviation, recorded): the new assertions are green against correct code because this is a coverage gap, not missing code. The subagent dropped `patience = ruling.patience` in `game.py` and the extended `T-V0-GAME-11` failed (`walk_away_patience` line count 0 instead of 1); the orchestrator repeated that mutation and added a second one — passing `persona.patience` into `facts(...)` — which fails the `Rounds of patience left` assertion. `game.py` was restored from a backup and compared identical to HEAD both times.
