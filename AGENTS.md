# ai-investor-game — agent rules

Console negotiation game: the player sells a startup to an AI investor; a
decision model (Laya) makes every investor decision, a chat LLM only voices
it and proposes the player's reply options.

## Spec

SDD: implementation task → spec first (`docs/spec/spec-vN.md`); the spec is
the contract.

**Spec drift:** architecture/tests/interfaces change → update
`docs/spec/spec-vN.md` same commit.

## Stack

- Language: Python 3.14 (latest stable: 3.14.7, released 2026-08-05; pinned
  via `.python-version`), uv-managed.
- Frameworks/libs:
  - `laya` — the decision model (typed choice / score decisions). Pin an
    exact version: 0.3.20–0.3.22 shipped within five days (latest 0.3.22,
    2026-09-29), so the API moves; the lecturer's reference repo requires
    `laya>=0.3.21`. Verified 2026-09-30: `laya==0.3.22` resolves on Python
    3.14 (torch 2.14.1 with cp314 wheels, transformers 5.18.0).
  - Chat LLM — any OpenAI-compatible endpoint (LM Studio or OpenRouter);
    the client library is fixed by `docs/spec/spec-v0.md`.
  - Everything else: stdlib.
- Tooling: uv, pytest, ruff.
- NEVER add dependencies beyond the allowed list without asking.
- Open for spec-v0: the default Linux torch wheel pulls CUDA (gigabytes) —
  the dev box is AMD Renoir, so use the CPU index; the English `laya`
  checkpoint takes 512 input tokens — state and negotiation history must
  fit.

## Project layout

- `docs/` — spec, prompts, reports, assets, `llm-usage.md` (see the lab's
  `standards/project-structure.md`).
- Source and test layout: defined by `docs/spec/spec-v0.md`.
- Context boundaries: NEVER read or print `.env`; NEVER read or edit
  anything above the repository root; model weights stay in the Hugging
  Face cache outside the repo, NEVER committed.

## Context discipline

- **Delegate bulk reading and implementation (RLM-style) — mandatory, not
  a preference.** The main context coordinates and verifies; it does not
  carry the work. Subagent when ANY of: >1 file/folder to explore, a read
  >100 lines/8 KB, **a task that writes source files**, >~10 edits within a
  task across all files, or applying a review to a spec. This holds
  **inside a `go` run, per task**, not only in interactive work. The brief
  is ~5 lines, names the files and line ranges, carries no history; the
  subagent returns a summary (findings, counts, `file:line`), NEVER raw
  file content. In the main context: `Read` with offset/limit,
  `grep`/`find` with line context. "One iteration, one artifact → no
  subagents" is about how many *perspectives* a task needs — it never
  cancels a trigger above.
- **Brief by file, never by retyping.** Anything load-bearing the
  orchestrator already resolved — a mechanism table, a control-flow
  finding, shapes agreed in an earlier task — goes into a **task-brief
  file** and the subagent gets its path. Re-dictating it into a prompt is
  a transcription risk, and avoiding that risk is the reason runs skip
  delegation and then compact.
- **Staying in the main context is a closed list.** Only: commands only
  (no file writes); artefacts only (docs, config, fixtures with no
  code-shape dependency); a single edit under every threshold; or the task
  *is* the clean-context review. The run report names which one, in those
  words. "The main context already holds what this needs" is not on the
  list.
- **Absolute paths in shell.** cwd isn't preserved across tool calls; every
  Bash call uses absolute paths or `cd <absolute> && …`.

## go protocol

<!-- SYNC: canonical text lives in standards/workflow.md §9 (lab repo); this copy is intentionally self-contained -->

`go docs/spec/spec-v0.md` = execute that spec end-to-end per its Execution
contract: work from the repo root, create the files its tree lists, follow
its implementation order, run its acceptance gates verbatim, respect its
bounded fix loop, log every prompt to `docs/prompts/`, append tokens/cost to
`docs/llm-usage.md`, delegate per Context discipline above — implementation
tasks included, briefed by a task-brief file rather than a retyped summary —
record per task what was delegated and, for anything kept in the main
context, which exemption applied, and finish with its report template (or its
blocker template). On a spec-internal contradiction (two requirements that
cannot both hold), surface the options and stop for a decision — or emit
the spec's blocker template when running unattended; NEVER resolve it
silently.

## Commit format

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- **One prompt → one commit.** Reference the prompt file in the body:
  `(prompt: docs/prompts/NN-<slug>.md)`.
- NEVER mix results of different prompts in one commit or MR.
<!-- SYNC: canonical text lives in standards/workflow.md §6 (lab repo); this copy is intentionally self-contained -->

## Branch strategy

- One task → one branch: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`.
- Exception: a solo run of a whole spec may commit directly to `main`;
  branches are for parallel or partial work.
- Parallel agent work: **one git worktree per agent**, merge via MR; NEVER two
  agents in one working tree.
- Parallelism is decided by **edit scope, not agent count**: split into
  ownership zones (a zone = files exactly one agent may write). Disjoint
  zones → parallel, one worktree each. Tasks that would edit the same files
  → run them sequentially; separate worktrees only defer the conflict to
  merge time.

## Gates — run before reporting success

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
<acceptance command — defined by docs/spec/spec-v0.md (a live game run needs the Laya weights and a reachable chat-LLM endpoint)>
```

All five MUST exit 0, run in this order.

A spec may define a mutation-testing gate; when it does, the command is
listed here and run verbatim like the others.

## Review

Code review: `code-reviewer` subagent (`.claude/agents/code-reviewer.md`),
clean context — NEVER self-review in the writing context. The reviewer runs
on `sonnet` with the checklist; `opus` only when the spec marks the change
security-critical.

## Reporting

Every LLM prompt: logged in `docs/prompts/` (one file each). Tokens/cost →
`docs/llm-usage.md`. Run reports → `docs/reports/`.

After each run report, generate `docs/reports/tg-post-vN.md` — Telegram
post, **Russian**, ≤1500 chars: constraints → result → metrics (executor
model always named; spec tokens, prompts, first-run, bugs, tokens in/out,
cost; no harness token/cost exposure → note it + public-API-price estimate)
→ link to this repo's GitHub page.

## Secrets

Secrets live in `.env` (git-ignored). NEVER write secrets into code, docs,
prompts, or reports.
