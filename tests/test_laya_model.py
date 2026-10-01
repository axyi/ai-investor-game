import json
import os
import sys
import types
import warnings

import pytest

from investor_game.decision import LoadError
from investor_game.laya_model import (
    PINNED_SHA,
    REPO,
    TEMPERATURE_WARNING,
    LayaDecisionModel,
    load_decision_model,
)

PROGRESS = "HF_HUB_DISABLE_PROGRESS_BARS"
MASK = "<mask>"


class FakeTok:
    mask_token = MASK

    def __call__(self, *args, **kwargs):
        raise AssertionError("the tokenizer was called directly")


class FakeAgent:
    """TST-01's fake agent: predict, tok with mask_token, cfg."""

    def __init__(self, label, max_len):
        self.label = label
        self.tok = FakeTok()
        self.cfg = {"max_len": max_len}
        self.predicted = []

    def predict(self, state, questions):
        self.predicted.append((state, questions))
        return {"label": self.label, "state": state}


def temperature_filters():
    return [
        f
        for f in warnings.filters
        if f[0] == "ignore" and f[1] is not None and f[1].pattern == TEMPERATURE_WARNING
    ]


class FakeLaya:
    """TST-01's fake laya_module: pin, load (the English load warns), common."""

    def __init__(
        self, *, sha=PINNED_SHA, en_warns=True, en_max=512, ml_max=1024, fail=None, other=False
    ):
        self.PINNED_REVISIONS = {REPO: sha}
        self.en_warns, self.en_max, self.ml_max = en_warns, en_max, ml_max
        self.fail, self.other = fail, other
        self.calls = []
        self.temperature_filters_at_load = []
        self.agents = []
        self.common = types.SimpleNamespace(
            serialize_state=lambda state: json.dumps(state, sort_keys=True),
            encode_text=lambda tok, text, add_special_tokens=True: {"input_ids": text.split()},
        )

    def load(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.temperature_filters_at_load.append(len(temperature_filters()))
        multilingual = "subfolder" in kwargs
        if self.fail is not None:
            raise self.fail
        message = TEMPERATURE_WARNING + " (fake): clamped"
        if multilingual or self.en_warns:
            warnings.warn(message, RuntimeWarning, stacklevel=2)
        if multilingual and self.other:
            warnings.warn("laya: some other warning", RuntimeWarning, stacklevel=2)
        agent = FakeAgent("ml", self.ml_max) if multilingual else FakeAgent("en", self.en_max)
        self.agents.append(agent)
        return agent


@pytest.fixture
def fresh_progress_env(monkeypatch):
    """Forget HF_HUB_DISABLE_PROGRESS_BARS for the test; teardown restores the old state."""
    monkeypatch.setenv(PROGRESS, "placeholder")
    monkeypatch.delenv(PROGRESS)
    return monkeypatch


def test_t_v0_dec_09_load_calls(fresh_progress_env):
    assert REPO == "convaiinnovations/laya"
    assert PINNED_SHA == "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"
    assert TEMPERATURE_WARNING == r"laya: this checkpoint ships invalid temperatures"
    laya = FakeLaya()
    model = load_decision_model(laya)
    assert os.environ[PROGRESS] == "1"  # the default, applied before any laya import
    assert laya.calls == [
        ((REPO,), {"device": "cpu", "revision": PINNED_SHA}),
        ((REPO,), {"subfolder": "multilingual", "device": "cpu", "revision": PINNED_SHA}),
    ]
    assert isinstance(model, LayaDecisionModel)
    en, ml = laya.agents
    assert model.agents == {"en": en, "ml": ml}
    assert model.serialize is laya.common.serialize_state
    assert model.encode is laya.common.encode_text
    # an existing value is kept: only a default is applied
    fresh_progress_env.setenv(PROGRESS, "0")
    load_decision_model(FakeLaya())
    assert os.environ[PROGRESS] == "0"
    # laya_module=None imports laya (and laya.common) itself
    imported = FakeLaya()
    fresh_progress_env.setitem(sys.modules, "laya", imported)
    fresh_progress_env.setitem(sys.modules, "laya.common", imported.common)
    model = load_decision_model()
    assert len(imported.calls) == 2 and model.serialize is imported.common.serialize_state


def test_t_v0_dec_10_warning_filter():
    laya = FakeLaya(other=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        before = list(warnings.filters)
        load_decision_model(laya)
        after = list(warnings.filters)
    # the English load's temperature warning was recorded (no LoadError); the filter came after
    assert laya.temperature_filters_at_load == [0, 1]
    # the multilingual load's temperature warning is dropped, another RuntimeWarning is kept
    assert [str(w.message) for w in caught] == ["laya: some other warning"]
    assert caught[0].category is RuntimeWarning
    # exactly one filter added, the narrow one: no blanket warning filter
    assert after[1:] == before
    action, message, category, module, lineno = after[0]
    assert (action, message.pattern, category, module, lineno) == (
        "ignore",
        TEMPERATURE_WARNING,
        RuntimeWarning,
        None,
        0,
    )
    # no English temperature warning -> LoadError, and no filter is left behind
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        before = list(warnings.filters)
        silent = FakeLaya(en_warns=False)
        with pytest.raises(LoadError) as info:
            load_decision_model(silent)
        assert list(warnings.filters) == before
    assert info.value.category == "load:AssertionError"
    assert len(silent.calls) == 1  # the multilingual checkpoint was never loaded


def test_t_v0_dec_11_load_failure(fresh_progress_env):
    # a load that raises: LoadError carries the class name only, never the message text
    for fail in ("en", "ml"):
        laya = FakeLaya()
        original = laya.load

        def failing(*args, _fail=fail, _laya=laya, _original=original, **kwargs):
            if ("subfolder" in kwargs) == (_fail == "ml"):
                raise OSError("/home/akh/.cache/secret weights missing")
            return _original(*args, **kwargs)

        laya.load = failing
        with pytest.raises(LoadError) as info:
            load_decision_model(laya)
        assert info.value.args == ("OSError",) and info.value.category == "load:OSError"
        assert "/home" not in str(info.value) and "secret" not in repr(info.value)
    # max_len other than 512 / 1024
    for kwargs in ({"en_max": 256}, {"ml_max": 512}, {"en_max": 1024, "ml_max": 512}):
        with pytest.raises(LoadError) as info:
            load_decision_model(FakeLaya(**kwargs))
        assert info.value.args == ("AssertionError",)
    # another PINNED_REVISIONS[REPO]: LoadError("AssertionError"), load never called
    laya = FakeLaya(sha="0" * 40)
    with pytest.raises(LoadError) as info:
        load_decision_model(laya)
    assert info.value.args == ("AssertionError",) and info.value.category == "load:AssertionError"
    assert laya.calls == []
    # a missing pin entry and a missing laya both fail as LoadError too
    laya = FakeLaya()
    laya.PINNED_REVISIONS = {}
    with pytest.raises(LoadError) as info:
        load_decision_model(laya)
    assert info.value.category == "load:KeyError" and laya.calls == []
    fresh_progress_env.setitem(sys.modules, "laya", None)  # `import laya` fails
    with pytest.raises(LoadError) as info:
        load_decision_model()
    assert info.value.category == "load:ModuleNotFoundError"


def test_t_v0_dec_12_tokens_predict():
    encoded = []

    def serialize(state):
        return json.dumps(state, ensure_ascii=False)

    def encode(tok, text, add_special_tokens=True):
        encoded.append((tok, text, add_special_tokens))
        return {"input_ids": text.split()}

    en, ml = FakeAgent("en", 512), FakeAgent("ml", 1024)
    model = LayaDecisionModel({"en": en, "ml": ml}, serialize, encode)
    # DEC-01: serialize, mask_token -> " ", encode on the checkpoint's own tok, no special tokens
    state = {"player_message": f"buy{MASK}now{MASK}please"}
    assert model.count_state_tokens("ml", state) == 4
    assert encoded == [(ml.tok, '{"player_message": "buy now please"}', False)]
    assert model.count_state_tokens("en", {"startup": "A tutoring app"}) == 4
    assert encoded[1] == (en.tok, '{"startup": "A tutoring app"}', False)
    # predict passes through to the checkpoint's agent
    questions = {"tone": {"type": "choice"}}
    assert model.predict("en", state, questions) == {"label": "en", "state": state}
    assert en.predicted == [(state, questions)] and ml.predicted == []
    assert model.predict("ml", state, questions)["label"] == "ml"
    assert ml.predicted == [(state, questions)]
