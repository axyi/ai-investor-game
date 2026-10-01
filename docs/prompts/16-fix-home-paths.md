---
date: 2026-10-01
model: claude-sonnet-5-5 (lab session subagent, `sonnet` alias)
model_reason: "a mechanical redaction plus three fixture literals; the cheapest model that keeps gates 1–4 green"
harness: Claude Code (lab session, post-verify fix)
stage: fix
tokens_in: see docs/llm-usage.md row 16
tokens_out: see docs/llm-usage.md row 16
---

Raised by `/verify-run` of the v0 run, item 7 (operator decision 2026-10-01: fix by a new
prompt): the operator's home path appears in three test fixtures, where the spec's
convention is `/home/player/…` (spec §8 TST-01 / `T-V0-DEC-16`), and as the absolute
repository root in the run's prompt files and task briefs.

In this record the operator's user name is redacted as `<operator>`; the prompt as sent
carried the literal home directory.

## Goal

Remove every `/home/<operator>` occurrence from the tracked files of this repository without
changing what any test asserts or what any record says beyond the path itself.

## Constraints

- Repository root: the directory holding this file's `docs/`. Work only there; never
  open `.env`; no commits, no `git add`.
- Test fixtures, exactly three lines: `tests/test_decision.py:356` and `:361`
  (`ValueError("/home/<operator>/secret")` → `ValueError("/home/player/secret")`) and
  `tests/test_laya_model.py:162` (`"/home/<operator>/.cache/secret weights missing"` →
  `"/home/player/.cache/secret weights missing"`). The assertions next to them
  (`"/home" not in …`, `"secret" not in …`) stay unchanged.
- Run records: in `docs/prompts/{02,03,04,05,06,09,10,11,12,13}-*.md` and
  `docs/spec/task-briefs/v0-T{1,2,3,4,5,8}.md`, replace the exact string
  `/home/<operator>/aihome/coders-su/projects/ai-investor-game` with `<repo>` (the repository
  root, redacted after the run). Replace that exact long string only — no other edit to
  these files, no other pattern, no reflow.
- Do not touch `docs/prompts/01-spec-v0.md`, `docs/spec/spec-v0.md`, any other file.

## Acceptance

- `git grep -n '/home/<operator>'` → no output (exit 1).
- `git diff --stat` lists exactly the 18 files above; `git diff` shows only the replaced
  path strings and the three fixture literals.
- Gates 1–4 exit 0, in order: `uv sync --locked`, `uv run --locked ruff check .`,
  `uv run --locked ruff format --check .`, `uv run --locked pytest`.

## Stop

Any other `/home/<operator>` pattern, a gate going red, or a test whose assertion would have to
change → stop and report; do not improvise.
