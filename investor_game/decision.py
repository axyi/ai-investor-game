import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Protocol

from investor_game.domain import Offer, Persona, Startup
from investor_game.rules import recent

STATE_BUDGET = {"en": 400, "ml": 900}
PLAYER_MESSAGE_MAX = 300
_WORDS = ("timeout", "shape", "truncated", "oom")

# The question sets: spec-v0 section 3.2, verbatim (REQ-V0-DEC-02..04).
TECH_QUESTIONS = {
    "accept": {
        "type": "score",
        "instructions": "How likely is the investor to accept the player's offer?",
        "criteria": [
            "Definitely reject",
            "Probably reject",
            "Uncertain",
            "Probably accept",
            "Definitely accept",
        ],
    },
    "reaction": {
        "type": "choice",
        "instructions": "How should the investor react?",
        "criteria": {
            "accept": "Accept the offer",
            "counter": "Make a counter-offer",
            "reject": "Reject the offer",
            "walk_away": "End the negotiation",
        },
    },
    "good_deal": {
        "type": "noul",
        "instructions": "The player's offer is attractive enough for the investor",
        "criteria": {
            "false": "the offer is not attractive to the investor",
            "true": "the offer is attractive to the investor",
        },
    },
}
MORAL_QUESTIONS = {
    "ethical_concern": {
        "type": "noul",
        "instructions": "This startup produces weapons or other products that harm people",
        "criteria": {"false": "no ethical conflict", "true": "ethical conflict"},
    }
}
STAKEHOLDER_QUESTIONS = {
    "tone": {
        "type": "choice",
        "instructions": "How does the founder address the investor?",
        "criteria": {
            "polite": "The founder is polite",
            "neutral": "The founder is neutral or businesslike",
            "rude": "The founder is rude or insulting",
        },
    }
}


class DecisionError(Exception):
    """A decision that failed; args[0] is a category word or the exception class name."""

    @property
    def category(self) -> str:
        """The DEC-10 `laya_error=` category."""
        word = self.args[0]
        return word if word in _WORDS else f"exception:{word}"


class LoadError(Exception):
    """The models failed to load; args[0] is the exception class name, never its message."""

    @property
    def category(self) -> str:
        """The DEC-10 `laya_error=` category."""
        return f"load:{self.args[0]}"


class DecisionModel(Protocol):
    def count_state_tokens(self, checkpoint: str, state: dict) -> int: ...

    def predict(self, checkpoint: str, state: dict, questions: dict) -> dict: ...


@dataclass(frozen=True)
class Decisions:
    """The readings (DEC-05) of one turn's three checks.

    choice: TECH reaction, one of accept, counter, reject, walk_away.
    level: TECH accept score level, 0-4 (argmax of the probabilities).
    good_deal / ethical_concern: noul answers, true iff P >= 0.5.
    tone: STAKEHOLDER label (polite, neutral, rude).
    truncated: results this turn that came back truncated (RESULT `truncated`).
    checks: the final shape-valid results the turn used, one per check however often it was
        retried or re-run (RESULT `laya_checks`, GAME-05).
    """

    choice: str
    level: int
    good_deal: bool
    ethical_concern: bool
    tone: str
    truncated: int
    checks: int

    @property
    def walk_away(self) -> bool:
        return self.choice == "walk_away"


@dataclass(frozen=True)
class _Check:
    checkpoint: str
    questions: dict


_CHECKS = (
    _Check("en", TECH_QUESTIONS),
    _Check("en", MORAL_QUESTIONS),
    _Check("ml", STAKEHOLDER_QUESTIONS),
)


class _ShapeInvalid(Exception):
    pass


def tech_state(
    offer: Offer, persona: Persona, patience: int, facts: Sequence[str], history: Sequence[str]
) -> dict:
    """DEC-02: the TECH state; patience is the current one, history the recent window."""
    return {
        "player_offer": {"investment": offer.investment, "equity": offer.equity},
        "investor": {
            "budget": persona.budget,
            "max_equity": persona.opening.equity,
            "interest": persona.interest,
            "patience": patience,
            "persona": persona.descriptor,
        },
        "facts": list(facts),
        "history": recent(history),
    }


def moral_state(startup: Startup) -> dict:
    return {"startup": startup.en}


def stakeholder_state(text: str) -> dict:
    return {"player_message": text[:PLAYER_MESSAGE_MAX]}


def read_score(answer: dict) -> int:
    """DEC-05: argmax of the probabilities, ties to the lower level; never the score float."""
    probabilities = answer["probabilities"]
    return int(max(sorted(probabilities, key=int), key=lambda level: probabilities[level]))


def read_noul(answer: dict) -> bool:
    return answer["noul"] >= 0.5


def _without_oldest(state: dict, count: int) -> dict:
    history = state.get("history")
    return state if history is None else {**state, "history": list(history[count:])}


def fit_state(model: DecisionModel, checkpoint: str, state: dict) -> dict:
    """DEC-06: drop the oldest history until the state fits the checkpoint's token budget."""
    while model.count_state_tokens(checkpoint, state) > STATE_BUDGET[checkpoint]:
        if not state.get("history"):
            raise DecisionError("truncated")
        state = _without_oldest(state, 1)
    return state


def _valid_answer(question: dict, answer: object) -> bool:
    if not isinstance(answer, dict):
        return False
    if question["type"] == "score":
        probabilities = answer.get("probabilities")
        return (
            isinstance(probabilities, dict)
            and set(probabilities) == set("01234")
            and all(isinstance(p, float) for p in probabilities.values())
        )
    if question["type"] == "choice":
        choice = answer.get("choice")
        return isinstance(choice, str) and choice in question["criteria"]
    return isinstance(answer.get("noul"), float)


def _valid(model: DecisionModel, check: _Check, state: dict, result: object) -> bool:
    """DEC-07 shape validation of one predict result."""
    if not isinstance(result, dict):
        return False
    answers, usage = result.get("answers"), result.get("usage")
    if not isinstance(answers, dict) or not isinstance(usage, dict):
        return False
    if not all(
        key in answers and _valid_answer(question, answers[key])
        for key, question in check.questions.items()
    ):
        return False
    tokens = usage.get("state_tokens")
    return (
        isinstance(usage.get("truncated"), bool)
        and isinstance(tokens, int)
        and not isinstance(tokens, bool)
        and tokens == model.count_state_tokens(check.checkpoint, state)
    )


def _category(exc: BaseException) -> str:
    """DEC-07 / DEC-10: the class name, or oom; the message is inspected, never kept."""
    if isinstance(exc, _ShapeInvalid):
        return "shape"
    if isinstance(exc, MemoryError) or (
        isinstance(exc, RuntimeError)
        and ("out of memory" in str(exc) or "DefaultCPUAllocator" in str(exc))
    ):
        return "oom"
    return type(exc).__name__


class DecisionRunner:
    """DEC-07: the three checks of a turn on one pool of six workers."""

    def __init__(self, model: DecisionModel, timeout_s: float = 60.0) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._pool = ThreadPoolExecutor(max_workers=6)

    def _attempt(self, check: _Check, state: dict) -> dict:
        result = self._model.predict(check.checkpoint, state, check.questions)
        if not _valid(self._model, check, state, result):
            raise _ShapeInvalid
        return result

    def _batch(self, jobs: list[tuple[_Check, dict]]) -> list[tuple[dict | None, str | None]]:
        """Submit the jobs at once and wait one deadline; (result, None) or (None, category)."""
        futures = [self._pool.submit(self._attempt, check, state) for check, state in jobs]
        wait(futures, timeout=self._timeout_s)
        outcomes: list[tuple[dict | None, str | None]] = []
        for future in futures:
            if not future.done():
                outcomes.append((None, "timeout"))
            elif (exc := future.exception()) is not None:
                outcomes.append((None, _category(exc)))
            else:
                outcomes.append((future.result(), None))
        return outcomes

    def run(self, tech: dict, moral: dict, stake: dict) -> Decisions:
        """Run TECH, MORAL and STAKEHOLDER; every check gets at most two attempts in total.

        A failed or late check (exception, timeout, invalid shape) is retried once with the
        same state; a shape-valid truncated result is re-run once without the oldest
        ceil(n/2) history entries (DEC-06), and DEC-07 never retries it. The retries of all
        checks form one batch with a fresh deadline. A second failure raises DecisionError for
        the first failed check in TECH, MORAL, STAKEHOLDER order.
        """
        states = [
            fit_state(self._model, check.checkpoint, state)
            for check, state in zip(_CHECKS, (tech, moral, stake), strict=True)
        ]
        results: list[dict | None] = [None] * len(_CHECKS)
        retry: list[int] = []
        truncated = 0
        for i, (result, _) in enumerate(self._batch(list(zip(_CHECKS, states, strict=True)))):
            if result is None:
                retry.append(i)
            elif result["usage"]["truncated"]:
                truncated += 1
                half = math.ceil(len(states[i].get("history", ())) / 2)
                states[i] = _without_oldest(states[i], half)
                retry.append(i)
            else:
                results[i] = result
        for i, (result, failure) in zip(
            retry, self._batch([(_CHECKS[i], states[i]) for i in retry]), strict=True
        ):
            if failure is None and result["usage"]["truncated"]:
                failure = "truncated"
            if failure is not None:
                raise DecisionError(failure)
            results[i] = result
        tech_answers, moral_answers, stake_answers = (r["answers"] for r in results)
        return Decisions(
            choice=tech_answers["reaction"]["choice"],
            level=read_score(tech_answers["accept"]),
            good_deal=read_noul(tech_answers["good_deal"]),
            ethical_concern=read_noul(moral_answers["ethical_concern"]),
            tone=stake_answers["tone"]["choice"],
            truncated=truncated,
            checks=sum(result is not None for result in results),
        )

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
