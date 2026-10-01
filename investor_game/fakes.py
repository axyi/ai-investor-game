"""Offline fakes for `--selftest` and the tests (GAME-07)."""

import json

from investor_game.chat import FENCE, ChatError
from investor_game.domain import format_eur

SELFTEST_SCRIPT = ["1", "1", "Здравствуйте! Предлагаю €500k за 20%", "1"]
SELFTEST_RESULT = {
    "outcome": "deal",
    "decision_turns": 2,
    "laya_checks": 6,
    "truncated": 0,
    "chat_ok": 3,
    "chat_fallbacks": 0,
    "overrides": [],
    "final_offer": {"investment": 500000, "equity": 30},
}


def _score(level: int) -> dict:
    return {
        "probabilities": {str(i): 0.9 if i == level else 0.025 for i in range(5)},
        "score": float(level),
    }


class FakeDecisionModel:
    """A DecisionModel that answers from the state alone: no weights, no network."""

    def count_state_tokens(self, checkpoint: str, state: dict) -> int:
        return len(json.dumps(state, ensure_ascii=False)) // 4

    def predict(self, checkpoint: str, state: dict, questions: dict) -> dict:
        if "accept" in questions:  # TECH
            agrees = state["player_offer"]["equity"] >= state["investor"]["max_equity"] - 10
            answers = {
                "accept": _score(4 if agrees else 1),
                "reaction": {"choice": "accept" if agrees else "counter"},
                "good_deal": {"noul": 0.8 if agrees else 0.2},
            }
        elif "ethical_concern" in questions:  # MORAL
            answers = {
                "ethical_concern": {"noul": 0.9 if "munitions" in state["startup"] else 0.05}
            }
        else:  # STAKEHOLDER
            rude = "проваливайте" in state["player_message"].lower()
            answers = {"tone": {"choice": "rude" if rude else "neutral"}}
        usage = {"truncated": False, "state_tokens": self.count_state_tokens(checkpoint, state)}
        return {"answers": answers, "usage": usage}


class FakeChatModel:
    """A ChatModel with a fixed fenced-JSON reply; `fail=True` raises ChatError("http_status:500")."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def complete(self, system: str, user: str) -> str:
        if self.fail:
            raise ChatError("http_status:500")
        options = [
            {
                "text": f"Предлагаю {format_eur(500000)} за {equity}%",
                "investment": 500000,
                "equity": equity,
            }
            for equity in (30, 25)
        ]
        reply = {"investor_line": "Фейковый инвестор: ход принят.", "options": options}
        return f"{FENCE}json\n{json.dumps(reply, ensure_ascii=False)}\n{FENCE}"
