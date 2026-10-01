---
date: 2026-10-01
model: claude-sonnet-5-5 (orchestrator, main context)
model_reason: "T6 is a documentation edit with literal targets in the spec (DOC-01, DOC-02); the spec header fixes the executor to the Sonnet class (`claude-sonnet-5`), the actual id differs from the header's name (noted in report-v0.md NOTES)"
harness: Claude Code, `go docs/spec/spec-v0.md`; not delegated
stage: docs
tokens_in: unknown   # the orchestrator's own counters are not exposed to it; see docs/llm-usage.md at T9
tokens_out: unknown
---

Task: T6 of `docs/spec/spec-v0.md` §10. Delegated: **no** — exemption quoted verbatim from the map: *artefacts only* (docs: README, AGENTS.md; nothing a gate compiles, imports or runs).

## Goal

Apply REQ-V0-DOC-01 to `README.md` (run command with the flags, `uv sync --locked`, `cp .env.example .env` with `CHAT_API_KEY` / `CHAT_MODEL` and the ≈ 1.5 GB of weights, `uv run --locked pytest`, the paragraph "Laya decides; code computes …; the chat LLM voices") and REQ-V0-DOC-02 to `AGENTS.md` (the acceptance command of the gates block = GATE-02's command without `tee`; Stack lines 20–33 = §3.1's pins, both checkpoints, budgets 400 / 900, the "Open for spec-v0" item removed; the `Context boundaries` bullet exactly as the spec's fenced text). The README `Headline:` line stays for T9.

## Constraints

Only `README.md` and `AGENTS.md`. The Context-boundaries bullet is extracted from the spec by line range and compared with `diff`, never retyped. `--check-result` and `grep -q '^NAME=.'` appear on exactly one AGENTS.md line each (DOC-02's acceptance count is 2). No python fences in the docs (gate 3 formats Markdown python blocks).

## Acceptance

`git show` of the commit shows the six README edits and the three AGENTS.md edits; `grep -cF -e '--check-result' -e "grep -q '^NAME=.'" AGENTS.md` = 2; the bullet is `diff`-identical to the spec; gates 1–4 exit 0.

## Stop

A spec-internal contradiction between DOC-01/DOC-02 and the files as they stand → surface it, do not resolve silently.
