# ai-investor-game

Console negotiation game: you sell your startup to an AI investor. At the
start you pick the investor's character (greedy, generous, rude…); every
investor decision — accept, counter, walk away — is made by a decision
model ([Laya](https://github.com/NandhaKishorM/laya)), and a regular chat
LLM only voices that decision and suggests your reply options. Built for
assignment 9 of the coders.su AI development course ("Decision LLM").

## Usage

```bash
# Run command: defined by docs/spec/spec-v0.md
```

## Setup

```bash
uv sync
# Chat-LLM endpoint configuration (.env, git-ignored): defined by spec-v0
```

## Testing

```bash
uv run pytest
```

## Build report

Built with AI agents under the lab workflow (spec-driven, one prompt = one
commit). Headline: <spec N tokens · M prompts · first-run: yes/no · $cost>.
Full report: [docs/reports/](docs/reports/), token accounting:
[docs/llm-usage.md](docs/llm-usage.md).
