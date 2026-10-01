# ai-investor-game

Console negotiation game: you sell your startup to an AI investor. At the
start you pick the investor's character (greedy, generous, rude…); every
investor decision — accept, counter, walk away — is made by a decision
model ([Laya](https://github.com/NandhaKishorM/laya)), and a regular chat
LLM only voices that decision and suggests your reply options. Built for
assignment 9 of the coders.su AI development course ("Decision LLM").

Laya decides; code computes the investor's numbers and validates the reply
options the chat LLM proposes; the chat LLM voices.

## Usage

```bash
uv run --locked --env-file .env python -m investor_game
# flags:
#   --show-decisions  print each turn's decisions
#   --script PATH     read the player's lines from PATH instead of stdin
#   --check-result    check the RESULT invariants (needs --script)
#   --selftest        play a scripted game over fakes, offline
```

## Setup

```bash
uv sync --locked
cp .env.example .env
# set CHAT_API_KEY and CHAT_MODEL in .env (git-ignored); the first run downloads
# ≈ 1.5 GB of Laya weights into the Hugging Face cache
```

## Testing

```bash
uv run --locked pytest
```

## Build report

Built with AI agents under the lab workflow (spec-driven, one prompt = one
commit). Headline: <spec N tokens · M prompts · first-run: yes/no · $cost>.
Full report: [docs/reports/](docs/reports/), token accounting:
[docs/llm-usage.md](docs/llm-usage.md).
