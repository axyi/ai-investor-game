import copy
import json
import threading
import time
from collections import Counter
from dataclasses import replace

import pytest

from investor_game.decision import (
    MORAL_QUESTIONS,
    STAKEHOLDER_QUESTIONS,
    STATE_BUDGET,
    TECH_QUESTIONS,
    DecisionError,
    DecisionRunner,
    Decisions,
    fit_state,
    moral_state,
    read_noul,
    read_score,
    stakeholder_state,
    tech_state,
)
from investor_game.domain import PERSONAS, STARTUPS, Offer
from investor_game.laya_model import LayaDecisionModel
from investor_game.rules import facts, offer_entry, opening_entry

GREEDY = PERSONAS[0]

# --- the literals of spec-v0 section 3.2 (lines 325-362), extracted verbatim ---
SPEC_TECH_QUESTIONS = {
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
SPEC_MORAL_QUESTIONS = {
    "ethical_concern": {
        "type": "noul",
        "instructions": "This startup produces weapons or other products that harm people",
        "criteria": {"false": "no ethical conflict", "true": "ethical conflict"},
    }
}
SPEC_STAKEHOLDER_QUESTIONS = {
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
SPEC_TECH_STATE = {
    "player_offer": {"investment": 500000, "equity": 20},
    "investor": {
        "budget": 700000,
        "max_equity": 35,
        "interest": 0.65,
        "patience": 1,
        "persona": "greedy investor who bargains hard",
    },
    "facts": [
        "The requested investment is within the investor's budget.",
        "The offered equity 20% is far below the investor's current ask of 33%.",
        "The offered equity is below the investor's minimum of 25%.",
        "The implied post-money valuation €2.5M is above the startup's valuation of €2.0M.",
        "Rounds of patience left: 1.",
    ],
    "history": [
        "Round 0: investor offered €500k for 35%",
        "Round 1: player offered €500k for 20%; investor countered €500k for 33%",
        "Round 2: player offered €500k for 22%; investor kept €500k for 33%",
        "Round 3: player offered €500k for 24%; investor kept €500k for 33%",
    ],
}
SPEC_MORAL_STATE = {"startup": "A factory producing munitions and attack drones"}
SPEC_STAKE_STATE = {"player_message": "Вы жадный старик, €500k за 20% или проваливайте."}

# --- fakes ---

DEFAULT_CHOICE = {"reaction": "counter", "tone": "polite"}
HISTORY5 = [f"Round {n}: history entry" for n in range(5)]
TECH = dict(SPEC_TECH_STATE, history=HISTORY5)
MORAL = dict(SPEC_MORAL_STATE)
STAKE = dict(SPEC_STAKE_STATE)
NAMES = ("tech", "moral", "stake")


def check_name(questions):
    if "accept" in questions:
        return "tech"
    return "moral" if "ethical_concern" in questions else "stake"


def answers_for(questions):
    out = {}
    for key, question in questions.items():
        if question["type"] == "score":
            probabilities = {"0": 0.1, "1": 0.1, "2": 0.1, "3": 0.5, "4": 0.2}
            out[key] = {"probabilities": probabilities, "score": 2.9}
        elif question["type"] == "choice":
            out[key] = {"choice": DEFAULT_CHOICE[key]}
        else:
            out[key] = {"noul": 0.2}
    return out


class FakeModel:
    """A DecisionModel: counts predict calls per check when each starts, under a lock."""

    def __init__(self, behave=None, tokens=None):
        self.behave = behave
        self.tokens = tokens or (lambda checkpoint, state: 50 + 50 * len(state.get("history", [])))
        self.calls = Counter()
        self.states = {name: [] for name in NAMES}
        self.lock = threading.Lock()

    def count_state_tokens(self, checkpoint, state):
        return self.tokens(checkpoint, state)

    def good(self, checkpoint, state, questions, *, truncated=False):
        usage = {"truncated": truncated, "state_tokens": self.count_state_tokens(checkpoint, state)}
        return {"answers": answers_for(questions), "usage": usage}

    def predict(self, checkpoint, state, questions):
        name = check_name(questions)
        with self.lock:
            self.calls[name] += 1
            attempt = self.calls[name]
            self.states[name].append(copy.deepcopy(state))
        if self.behave is None:
            return self.good(checkpoint, state, questions)
        return self.behave(self, name, attempt, checkpoint, state, questions)


@pytest.fixture
def runner_for():
    runners = []

    def make(model, timeout_s=5.0):
        runners.append(DecisionRunner(model, timeout_s=timeout_s))
        return runners[-1]

    yield make
    for runner in runners:
        runner.close()


def only(name, behave):
    """A behaviour that applies to one check; the others answer well."""

    def wrapped(model, check, attempt, checkpoint, state, questions):
        if check == name:
            return behave(model, attempt, checkpoint, state, questions)
        return model.good(checkpoint, state, questions)

    return wrapped


def fails(runner, state=TECH):
    with pytest.raises(DecisionError) as info:
        runner.run(state, MORAL, STAKE)
    return info.value


# --- tests ---


def test_t_v0_dec_01_questions():
    assert TECH_QUESTIONS == SPEC_TECH_QUESTIONS
    assert MORAL_QUESTIONS == SPEC_MORAL_QUESTIONS
    assert STAKEHOLDER_QUESTIONS == SPEC_STAKEHOLDER_QUESTIONS
    for got, want in (
        (TECH_QUESTIONS, SPEC_TECH_QUESTIONS),
        (MORAL_QUESTIONS, SPEC_MORAL_QUESTIONS),
        (STAKEHOLDER_QUESTIONS, SPEC_STAKEHOLDER_QUESTIONS),
    ):
        assert json.dumps(got) == json.dumps(want)
    assert STATE_BUDGET == {"en": 400, "ml": 900}
    # MORAL and STAKEHOLDER states: exactly one key, no persona word (DOM-01 descriptor)
    descriptor_words = {w for p in PERSONAS for w in p.descriptor.lower().split()}
    for startup in STARTUPS:
        state = moral_state(startup)
        assert list(state) == ["startup"] and state == {"startup": startup.en}
        assert not descriptor_words & set(state["startup"].lower().replace(",", " ").split())
    assert moral_state(STARTUPS[2]) == SPEC_MORAL_STATE
    state = stakeholder_state("Вы жадный старик, €500k за 20% или проваливайте.")
    assert state == SPEC_STAKE_STATE and list(state) == ["player_message"]
    assert stakeholder_state("x" * 300)["player_message"] == "x" * 300
    assert stakeholder_state("x" * 301)["player_message"] == "x" * 300
    assert stakeholder_state("я" * 500) == {"player_message": "я" * 300}


def test_t_v0_dec_02_tech_state():
    player, standing = Offer(500000, 20), Offer(500000, 33)
    history = [
        opening_entry(GREEDY),
        offer_entry(1, player, standing, countered=True),
        offer_entry(2, Offer(500000, 22), standing, countered=False),
        offer_entry(3, Offer(500000, 24), standing, countered=False),
    ]
    given_facts = facts(player, standing, GREEDY, STARTUPS[0], 1)
    state = tech_state(player, GREEDY, 1, given_facts, history)
    assert state == SPEC_TECH_STATE
    assert json.dumps(state) == json.dumps(SPEC_TECH_STATE)  # key order too
    assert list(state) == ["player_offer", "investor", "facts", "history"]
    assert list(state["player_offer"]) == ["investment", "equity"]
    assert list(state["investor"]) == ["budget", "max_equity", "interest", "patience", "persona"]
    # max_equity is the opening equity, persona the descriptor, patience the current one
    assert state["investor"]["max_equity"] == GREEDY.opening.equity == 35
    assert state["investor"]["persona"] == GREEDY.descriptor
    assert state["investor"]["patience"] == 1
    # the state holds copies and only the recent history window (RUL-02)
    longer = [opening_entry(GREEDY), *history]
    assert tech_state(player, GREEDY, 1, given_facts, longer)["history"] == history[-4:]
    assert state["facts"] is not given_facts and state["history"] is not history
    for persona in PERSONAS:
        built = tech_state(player, persona, persona.patience, given_facts, history)
        assert built["investor"] == {
            "budget": persona.budget,
            "max_equity": persona.opening.equity,
            "interest": persona.interest,
            "patience": persona.patience,
            "persona": persona.descriptor,
        }


def test_t_v0_dec_03_reading():
    probabilities = {"0": 0.42, "1": 0.06, "2": 0.32, "3": 0.1, "4": 0.1}
    level = read_score({"probabilities": probabilities, "score": 1.71})
    assert level == 0 and isinstance(level, int)  # argmax, never the score float
    ties = {"0": 0.1, "1": 0.35, "2": 0.35, "3": 0.1, "4": 0.1}
    assert read_score({"probabilities": ties, "score": 3.0}) == 1  # tie -> lower
    assert read_score({"probabilities": dict.fromkeys("01234", 0.2), "score": 2.0}) == 0
    late = {"4": 0.4, "3": 0.4, "2": 0.1, "1": 0.05, "0": 0.05}  # unordered keys, tie 3/4
    assert read_score({"probabilities": late, "score": 0.0}) == 3
    assert read_score({"probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0, "4": 1.0}}) == 4
    assert read_noul({"noul": 0.5}) is True
    assert read_noul({"noul": 0.499}) is False
    assert read_noul({"noul": 0.9}) is True and read_noul({"noul": 0.0}) is False


def test_t_v0_dec_04_fit_state():
    model = FakeModel()  # 50 tokens + 50 per history entry; the en budget is 400
    state = dict(TECH, history=[f"Round {n}" for n in range(10)])
    fitted = fit_state(model, "en", state)
    assert fitted["history"] == [f"Round {n}" for n in range(3, 10)]  # oldest dropped first
    assert model.count_state_tokens("en", fitted) == 400
    assert len(state["history"]) == 10  # the input is not mutated
    assert {k: v for k, v in fitted.items() if k != "history"} == {
        k: v for k, v in state.items() if k != "history"
    }
    assert fit_state(model, "en", TECH) == TECH  # already fits: unchanged
    # the budget is per checkpoint: ml allows 900
    assert fit_state(FakeModel(tokens=lambda cp, st: 700), "ml", STAKE) == STAKE
    with pytest.raises(DecisionError) as info:
        fit_state(FakeModel(tokens=lambda cp, st: 700), "en", STAKE)
    assert info.value.args == ("truncated",) and info.value.category == "truncated"
    # history exhausted and still over: error
    always_over = FakeModel(tokens=lambda checkpoint, st: 401)
    with pytest.raises(DecisionError) as info:
        fit_state(always_over, "en", TECH)
    assert info.value.category == "truncated"
    # the runner fits before it submits: no predict call on an over-budget state
    model = FakeModel(tokens=lambda checkpoint, st: 901)
    runner = DecisionRunner(model)
    try:
        assert fails(runner).category == "truncated"
    finally:
        runner.close()
    assert sum(model.calls.values()) == 0


def test_t_v0_dec_05_truncated(runner_for):
    # a shape-valid truncated result is counted and re-run once without the oldest
    # ceil(n/2) entries (n = 5 -> 3 dropped); the second result is the one used
    def recover(model, attempt, checkpoint, state, questions):
        return model.good(checkpoint, state, questions, truncated=attempt == 1)

    model = FakeModel(only("tech", recover))
    decisions = runner_for(model).run(TECH, MORAL, STAKE)
    assert isinstance(decisions, Decisions)
    assert decisions.truncated == 1
    assert decisions.checks == 3  # the re-run result is the one used: the check counts once
    assert model.calls == {"tech": 2, "moral": 1, "stake": 1}
    first, second = model.states["tech"]
    assert first == TECH and second == dict(TECH, history=HISTORY5[3:])
    # an even history: n = 4 -> 2 dropped
    even = dict(TECH, history=HISTORY5[:4])
    model = FakeModel(only("tech", recover))
    runner_for(model).run(even, MORAL, STAKE)
    assert model.states["tech"][1]["history"] == HISTORY5[2:4]
    # truncated again: the same error, no third call
    model = FakeModel(
        only("tech", lambda m, a, cp, st, q: m.good(cp, st, q, truncated=True)),
    )
    error = fails(runner_for(model))
    assert error.args == ("truncated",) and error.category == "truncated"
    assert model.calls["tech"] == 2

    # a truncated retry after a failed first attempt is final too
    def raise_then_truncate(model, attempt, checkpoint, state, questions):
        if attempt == 1:
            raise ValueError("first attempt fails")
        return model.good(checkpoint, state, questions, truncated=True)

    model = FakeModel(only("tech", raise_then_truncate))
    assert fails(runner_for(model)).category == "truncated"
    assert model.calls["tech"] == 2


def test_t_v0_dec_06_predict_error(runner_for):
    def raise_first(exc):
        def behave(model, attempt, checkpoint, state, questions):
            if attempt == 1:
                raise exc
            return model.good(checkpoint, state, questions)

        return behave

    def raise_always(exc):
        def behave(model, attempt, checkpoint, state, questions):
            raise exc

        return behave

    # one failure is retried once and the turn passes
    model = FakeModel(only("moral", raise_first(ValueError("/home/player/secret"))))
    decisions = runner_for(model).run(TECH, MORAL, STAKE)
    assert decisions.truncated == 0 and model.calls == {"tech": 1, "moral": 2, "stake": 1}
    assert decisions.checks == 3  # the retried check counts once (GAME-05)
    # a second failure ends it: the class name only, never the message text
    model = FakeModel(only("tech", raise_always(ValueError("/home/player/secret"))))
    error = fails(runner_for(model))
    assert error.args == ("ValueError",) and error.category == "exception:ValueError"
    assert "/home" not in str(error) and "secret" not in repr(error)
    assert model.calls["tech"] == 2
    # oom: a MemoryError, or a RuntimeError naming it; the message is inspected, never kept
    oom = [
        MemoryError(),
        RuntimeError("CUDA out of memory. Tried to allocate 2 GiB /home/x"),
        RuntimeError("[enforce fail at DefaultCPUAllocator: can't allocate memory"),
    ]
    for exc in oom:
        error = fails(runner_for(FakeModel(only("tech", raise_always(exc)))))
        assert error.args == ("oom",) and error.category == "oom"
        assert "/home" not in str(error)
    error = fails(runner_for(FakeModel(only("tech", raise_always(RuntimeError("boom"))))))
    assert error.category == "exception:RuntimeError"
    # the category is the second failure's
    seq = [MemoryError(), TypeError("x")]

    def two_kinds(model, attempt, checkpoint, state, questions):
        raise seq[attempt - 1]

    error = fails(runner_for(FakeModel(only("moral", two_kinds))))
    assert error.category == "exception:TypeError"

    # several failed checks: TECH is reported first, then MORAL, then STAKEHOLDER
    def raise_by_check(model, name, attempt, checkpoint, state, questions):
        raise {"tech": ZeroDivisionError, "moral": KeyError, "stake": OSError}[name]()

    assert fails(runner_for(FakeModel(raise_by_check))).category == "exception:ZeroDivisionError"
    # the category property
    assert [DecisionError(word).category for word in ("timeout", "shape", "truncated", "oom")] == [
        "timeout",
        "shape",
        "truncated",
        "oom",
    ]
    assert DecisionError("OSError").category == "exception:OSError"


def test_t_v0_dec_07_timeout(runner_for):
    def slow(model, attempt, checkpoint, state, questions):
        time.sleep(0.3)
        return model.good(checkpoint, state, questions)

    model = FakeModel(only("tech", slow))
    error = fails(runner_for(model, timeout_s=0.1))
    assert error.args == ("timeout",) and error.category == "timeout"
    assert model.calls == {"tech": 2, "moral": 1, "stake": 1}

    # a late first attempt is resubmitted once; its own late result is discarded
    def late_then_fast(model, attempt, checkpoint, state, questions):
        if attempt == 1:
            time.sleep(0.3)
        return model.good(checkpoint, state, questions, truncated=False)

    model = FakeModel(only("moral", late_then_fast))
    decisions = runner_for(model, timeout_s=0.1).run(TECH, MORAL, STAKE)
    assert decisions.ethical_concern is False
    assert model.calls == {"tech": 1, "moral": 2, "stake": 1}
    assert decisions.checks == 3  # two attempts, one used result: still 3 for the turn


def test_t_v0_dec_08_concurrent(runner_for):
    barrier = threading.Barrier(3, timeout=2)

    def meet(model, name, attempt, checkpoint, state, questions):
        barrier.wait()  # passes only if all three predict calls are live at once
        return model.good(checkpoint, state, questions)

    model = FakeModel(meet)
    decisions = runner_for(model).run(TECH, MORAL, STAKE)
    assert model.calls == {"tech": 1, "moral": 1, "stake": 1}
    # the readings (DEC-05) over the fake's default answers
    assert decisions == Decisions(
        choice="counter",
        level=3,
        good_deal=False,
        ethical_concern=False,
        tone="polite",
        truncated=0,
        checks=3,
    )
    assert decisions.walk_away is False
    assert replace(decisions, choice="walk_away").walk_away is True


def test_t_v0_dec_13_shape_invalid(runner_for):
    def broken(mutate):
        def behave(model, attempt, checkpoint, state, questions):
            result = model.good(checkpoint, state, questions)
            replaced = mutate(result, model.count_state_tokens(checkpoint, state))
            return result if replaced is None else replaced

        return behave

    def first_only(mutate):
        def behave(model, attempt, checkpoint, state, questions):
            if attempt == 1:
                return broken(mutate)(model, attempt, checkpoint, state, questions)
            return model.good(checkpoint, state, questions)

        return behave

    def drop(*path):
        def mutate(result, tokens):
            node = result
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]

        return mutate

    def put(*path, value):
        def mutate(result, tokens):
            node = result
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value

        return mutate

    mutations = {
        "answer key missing": drop("answers", "good_deal"),
        "no answers": drop("answers"),
        "no usage": drop("usage"),
        "choice outside the criteria": put("answers", "reaction", value={"choice": "maybe"}),
        "choice missing": put("answers", "reaction", value={}),
        "truncated false, state_tokens mismatched": put("usage", "state_tokens", value=999),
        "state_tokens missing": drop("usage", "state_tokens"),
        "truncated missing": drop("usage", "truncated"),
        "truncated not a bool": put("usage", "truncated", value=0),
        "state_tokens a float": put("usage", "state_tokens", value=250.0),
        "probabilities missing a level": put(
            "answers", "accept", value={"probabilities": {"0": 0.2, "1": 0.8}, "score": 1.0}
        ),
        "probabilities keys not strings": put(
            "answers", "accept", value={"probabilities": {i: 0.2 for i in range(5)}, "score": 1.0}
        ),
        "probabilities not floats": put(
            "answers",
            "accept",
            value={"probabilities": {"0": 1, "1": 0, "2": 0, "3": 0, "4": 0}, "score": 1.0},
        ),
        "noul not a float": put("answers", "good_deal", value={"noul": "high"}),
        "result not a dict": lambda result, tokens: ["answers", "usage"],
    }
    for label, mutate in mutations.items():
        model = FakeModel(only("tech", broken(mutate)))
        error = fails(runner_for(model))
        assert error.args == ("shape",) and error.category == "shape", label
        assert model.calls == {"tech": 2, "moral": 1, "stake": 1}, label  # resubmitted once
        # the same defect on the first attempt only: the retry rescues the turn
        model = FakeModel(only("tech", first_only(mutate)))
        assert runner_for(model).run(TECH, MORAL, STAKE).truncated == 0, label
        assert model.calls["tech"] == 2, label

    # state_tokens a bool is not an int, even where True == the real count
    def bool_tokens(model, attempt, checkpoint, state, questions):
        result = model.good(checkpoint, state, questions)
        result["usage"]["state_tokens"] = True
        return result

    one = FakeModel(only("moral", bool_tokens), tokens=lambda checkpoint, state: 1)
    assert fails(runner_for(one)).category == "shape"
    # a STAKEHOLDER state that holds the tokenizer's mask_token literal still counts equal
    mask = "<mask>"

    class Tok:
        mask_token = mask

        def __call__(self, *args, **kwargs):
            raise AssertionError("the counter reached the tokenizer directly")

    encoded = []

    def serialize(state):
        return json.dumps(state, ensure_ascii=False)

    def encode(tok, text, add_special_tokens=True):
        encoded.append((tok, text, add_special_tokens))
        return {"input_ids": text.split()}

    class Agent:
        def __init__(self):
            self.cfg = {"max_len": 512}
            self.tok = Tok()

        def predict(self, state, questions):
            text = serialize(state).replace(mask, " ")  # as laya's own serialization does
            usage = {"truncated": False, "state_tokens": len(text.split())}
            return {"answers": answers_for(questions), "usage": usage}

    model = LayaDecisionModel({"en": Agent(), "ml": Agent()}, serialize, encode)
    message = f"buy{mask}now{mask}please"
    stake = stakeholder_state(message)
    runner = runner_for(model)
    decisions = runner.run(TECH, MORAL, stake)  # no DecisionError("shape")
    assert decisions.tone == "polite"
    assert encoded and all(add is False and mask not in text for _, text, add in encoded)
    assert any("buy now please" in text for _, text, _ in encoded)


def test_t_v0_dec_14_attempt_counts(runner_for):
    def truncated(model, attempt, checkpoint, state, questions):
        return model.good(checkpoint, state, questions, truncated=True)

    def recovered(model, attempt, checkpoint, state, questions):
        return model.good(checkpoint, state, questions, truncated=attempt == 1)

    def slow(model, attempt, checkpoint, state, questions):
        time.sleep(0.3)
        return model.good(checkpoint, state, questions)

    def invalid(model, attempt, checkpoint, state, questions):
        result = model.good(checkpoint, state, questions)
        result["usage"]["state_tokens"] += 1
        return result

    # persistent truncation: exactly two TECH calls, then the error
    model = FakeModel(only("tech", truncated))
    assert fails(runner_for(model)).category == "truncated"
    assert model.calls["tech"] == 2
    # recovered by the DEC-06 re-run: exactly two, the second result used
    model = FakeModel(only("tech", recovered))
    decisions = runner_for(model).run(TECH, MORAL, STAKE)
    assert model.calls["tech"] == 2 and decisions.truncated == 1
    assert model.states["tech"][1]["history"] == HISTORY5[3:]
    # timeout: exactly two, then the error
    model = FakeModel(only("tech", slow))
    assert fails(runner_for(model, timeout_s=0.1)).category == "timeout"
    assert model.calls["tech"] == 2
    time.sleep(0.4)  # the slept attempts end; nothing starts a third call
    assert model.calls["tech"] == 2
    # invalid shape: exactly two, then the error
    model = FakeModel(only("tech", invalid))
    assert fails(runner_for(model)).category == "shape"
    assert model.calls["tech"] == 2
    # never a third call, whichever way the two attempts fail
    for first, second in ((invalid, truncated), (truncated, invalid)):

        def mixed(model, attempt, checkpoint, state, questions, pair=(first, second)):
            return pair[attempt - 1](model, attempt, checkpoint, state, questions)

        model = FakeModel(only("tech", mixed))
        error = fails(runner_for(model))
        assert error.category == ("truncated" if second is truncated else "shape")
        assert model.calls == {"tech": 2, "moral": 1, "stake": 1}


def test_t_v0_dec_15_retry_capacity(runner_for):
    def slow(model, name, attempt, checkpoint, state, questions):
        time.sleep(0.3)
        return model.good(checkpoint, state, questions)

    model = FakeModel(slow)
    runner = runner_for(model, timeout_s=0.1)
    started = time.monotonic()
    with pytest.raises(DecisionError) as info:
        runner.run(TECH, MORAL, STAKE)
    assert info.value.category == "timeout"
    assert time.monotonic() - started < 0.4  # two shared 0.1 s deadlines, not 3 x 2 in turn
    # each check started exactly two calls; the retries began while the first attempts slept
    assert model.calls == {"tech": 2, "moral": 2, "stake": 2}
    runner.close()
    time.sleep(0.6)
    assert model.calls == {"tech": 2, "moral": 2, "stake": 2}
