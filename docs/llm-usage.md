# LLM usage

| # | Stage | Model | Tokens in | Tokens out | Cost |
|---|-------|-------|-----------|------------|------|
| 1 | spec — `spec-v0.md` authoring (prompt `01`): lab session with the `spec-authoring` skill; 11 subagents (two proof runs of laya / the pinned pyproject in disposable venvs, one house-style mapping, one drafting, one citation + fence audit, one applier for the audit's 11 rulings, three round appliers, two appliers for the post-round-3 rulings); 3 rounds of cross-review against OpenAI Codex (24 findings, 23 accepted of which 7 adapted, 1 rejected; `round_limit`) | claude-opus-5-5 (lab session and 9 subagents), claude-sonnet-5 (house-style mapping, tokenizer-lock fix); challenger OpenAI `gpt-5.6-sol` | Claude: main 291,271 (228 uncached + 291,043 cache write) + 22,226,725 cache read over 103 requests; subagents 1,900,721 (904 + 1,899,817 cache write) + 65,241,334 cache read over 447 requests — measured from the local session transcripts (`tools/session-usage.py`, deduplicated by request id). Codex: 69,124 prompt over 3 requests | Claude: main 123,521; subagents 241,100. Codex: 20,950 (16,096 of them reasoning) | Claude: — (flat-rate subscription). Codex: ≈ $0.35 (estimate at the $2 / $10 per MTok price listed for `openai/gpt-5.6-sol` on OpenRouter's model list, 2026-09-30) |
| **Σ** | | | see row 1 | see row 1 | ≈ $0.35 metered (Codex) + flat-rate Claude |

Evidence: per-request `usage` fields of the lab session's local Claude Code transcripts
(main session and its `subagents/` files), aggregated by `tools/session-usage.py` of the lab
repo; Codex usage lines (`finish=stop`, prompt / completion / reasoning tokens) returned by
each cross-review round.
