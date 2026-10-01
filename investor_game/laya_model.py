import importlib
import os
import re
import warnings
from collections.abc import Callable, Mapping
from typing import Any

from investor_game.decision import LoadError

REPO = "convaiinnovations/laya"
PINNED_SHA = "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"
TEMPERATURE_WARNING = r"laya: this checkpoint ships invalid temperatures"


class LayaDecisionModel:
    """The DecisionModel over loaded Laya agents, keyed by checkpoint (`en`, `ml`).

    `serialize` / `encode` are laya.common.serialize_state / encode_text, injected so this
    module never imports laya (PKG-03); `encode` holds laya's tokenizer lock.
    """

    def __init__(
        self,
        agents: Mapping[str, Any],
        serialize: Callable[[dict], str],
        encode: Callable[..., dict],
    ) -> None:
        self.agents = agents
        self.serialize = serialize
        self.encode = encode

    def count_state_tokens(self, checkpoint: str, state: dict) -> int:
        """DEC-01: the token count laya 0.3.22 itself reports in usage.state_tokens."""
        tok = self.agents[checkpoint].tok
        text = self.serialize(state).replace(tok.mask_token, " ")
        return len(self.encode(tok, text, add_special_tokens=False)["input_ids"])

    def predict(self, checkpoint: str, state: dict, questions: dict) -> dict:
        return self.agents[checkpoint].predict(state, questions)


def _require(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)


def load_decision_model(laya_module: Any = None) -> LayaDecisionModel:
    """Load the English and multilingual checkpoints (DEC-01, PKG-04); LoadError on any failure.

    Every failure, including a failed pin or max_len assert, becomes LoadError carrying the
    exception class name only.
    """
    try:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        if laya_module is None:
            laya_module = importlib.import_module("laya")
            importlib.import_module("laya.common")  # binds laya.common for the lookups below
        _require(laya_module.PINNED_REVISIONS[REPO] == PINNED_SHA, "pinned revision mismatch")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            en = laya_module.load(REPO, device="cpu", revision=PINNED_SHA)
        _require(
            any(re.match(TEMPERATURE_WARNING, str(w.message)) for w in caught),
            "the English checkpoint did not warn about its temperatures",
        )
        warnings.filterwarnings("ignore", message=TEMPERATURE_WARNING, category=RuntimeWarning)
        ml = laya_module.load(REPO, subfolder="multilingual", device="cpu", revision=PINNED_SHA)
        _require(
            en.cfg.get("max_len") == 512 and ml.cfg.get("max_len") == 1024,
            "unexpected max_len",
        )
        common = laya_module.common
        return LayaDecisionModel({"en": en, "ml": ml}, common.serialize_state, common.encode_text)
    except Exception as exc:  # noqa: BLE001 - DEC-01: any failure is a LoadError
        raise LoadError(type(exc).__name__) from None
