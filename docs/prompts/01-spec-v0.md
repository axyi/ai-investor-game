---
date: 2026-09-30
model: claude-opus-5-5 (lab session, 1M context; drafting, audit and apply subagents on the same model)
model_reason: "spec authoring is where an error multiplies downstream, so standards/workflow.md §3 sends it to the strongest model; the executor that runs this spec is claude-sonnet-5 (named in the spec header)"
harness: Claude Code (lab session), spec-authoring skill
stage: spec
tokens_in: unknown   # measured afterwards from session transcripts, see docs/llm-usage.md row 1
tokens_out: unknown
---

Owner of: `docs/spec/spec-v0.md`, `docs/prompts/01-spec-v0.md`, `docs/llm-usage.md` row 1.
REQ ids: none implemented; this prompt produces the file that defines `REQ-V0-*` and
`T-V0-*`. The run it describes starts at prompt `02`.

Operator request (verbatim): `/spec-authoring projects/ai-investor-game spec-v0`

## Goal

Write `docs/spec/spec-v0.md`, the first specification of this greenfield project, so an
autonomous executor can build the game end-to-end via `go docs/spec/spec-v0.md` in a
session with no access to the authoring conversation. The game is assignment 9 of the
coders.su course ("Decision LLM"): a console negotiation in which the player sells a
startup to an AI investor; a decision model (Laya) makes every investor decision, a chat
LLM only voices it and proposes the player's reply options.

Decisions taken by the operator in the authoring session (2026-09-30):

1. The game UI is Russian.
2. The lecturer's Tech / Moral / Kind-Stakeholder checks run in v0, as three concurrent
   Laya requests per investor turn.
3. The player moves by picking one of the chat LLM's generated options or by typing an
   own offer; code, not an LLM, parses the numbers.
4. The live acceptance run uses OpenRouter.

Decisions taken by the lab from authoring-time measurements (disposable venvs outside
this repo, "authoring proof" in the spec): `laya==0.3.22` + CPU-only `torch==2.14.1` on
Python 3.14 through the PyTorch CPU index (the pinned pyproject and `uv.lock` form were
proven); `httpx==0.28.1` instead of the `openai` SDK; two Laya checkpoints at the pinned
Hub commit — English for TECH and MORAL, multilingual for STAKEHOLDER as an insult
detector; `score` answers read as argmax; code-owned numbers, guards and neutral
history; persona words kept out of the MORAL and STAKEHOLDER states; the live gate
checks structural invariants only.

## Constraints

- Pipeline: `.claude/skills/spec-authoring/SKILL.md` of the lab repo — decisions frozen
  into a brief, draft by one subagent, a fresh-context citation + fence audit, written
  lab rulings before any change is applied, cross-review against OpenAI Codex
  (`gpt-5.6-sol`) for at most three rounds with written verdicts per finding.
- Lab standards: `standards/workflow.md` (§1 SDD and proven skeletons, §5.1 delegation,
  §11 checklist, §12 spec budget, §13 cross-review), `standards/reporting.md`,
  `standards/project-structure.md`.
- No code changes, no live chat-LLM calls; no `.env` opened; no secret values in the
  spec.

## Acceptance

- Every MUST id appears in exactly one Appendix A row and every defined test id is cited
  there (checked by script).
- Every laya / httpx / pyproject fence re-runs against the pins (offline).
- The cross-review log (Appendix C) records every round, finding and verdict; the
  header's Status reads `ready for go` only after the last round.

## Stop

- Stop after the third cross-review round, or earlier when a round returns no Critical
  or High finding; record which in Appendix C.
- A decision the operator did not take and the measurements cannot settle → ask the
  operator; never pick silently.
