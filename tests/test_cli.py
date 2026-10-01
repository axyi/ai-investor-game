import json
import os
import time
import types
from pathlib import Path

import pytest

from investor_game.__main__ import main
from investor_game.decision import DecisionRunner, LoadError
from investor_game.fakes import FakeChatModel, FakeDecisionModel
from investor_game.game import check_result
from investor_game.laya_model import PINNED_SHA, REPO, load_decision_model
from investor_game.parse import HINT
from investor_game.rules import OUTCOME_LINES, REJECT_HINT

ROOT = Path(__file__).resolve().parent.parent
ENV = {"CHAT_API_KEY": "sk-test-not-a-real-key"}
SCRIPT = ["1", "1", "Здравствуйте! Предлагаю €500k за 20%", "1"]  # GAME-07's SELFTEST_SCRIPT
# GAME-07's RESULT, spec-v0 line 699.
RESULT_TEXT = (
    '{"outcome":"deal","decision_turns":2,"laya_checks":6,"truncated":0,"chat_ok":3,'
    '"chat_fallbacks":0,"overrides":[],"final_offer":{"investment":500000,"equity":30}}'
)
RESULT_LINE = "RESULT " + RESULT_TEXT
GOOD = json.loads(RESULT_TEXT)
BANNER = ["=== ПЕРЕГОВОРЫ ===", "Загрузка моделей…"]
QUIT = OUTCOME_LINES["player_quit"]
MISSING_KEY = "Ошибка конфигурации: не задана переменная CHAT_API_KEY"
CHECK_NEEDS_SCRIPT = "Ошибка запуска: --check-result работает только вместе с --script"
FALLBACK_OPENING = "Инвестор: Вот моё предложение."
LIVE_SCRIPT = [  # spec-v0 lines 711-715
    "1",
    "1",
    "Здравствуйте! Благодарю за предложение, могу ли я предложить €500k за 20%?",
    "Вы жадный старик, €500k за 20% или проваливайте.",
    "принять",
]


class Exited(Exception):
    """What the monkeypatched `os._exit` raises."""


@pytest.fixture
def exits(monkeypatch):
    def fake_exit(code):
        raise Exited(code)

    monkeypatch.setattr(os, "_exit", fake_exit)


@pytest.fixture
def fast_runner(monkeypatch):
    """DecisionRunner's default `timeout_s` becomes 0.1."""
    assert DecisionRunner.__init__.__defaults__ == (60.0,)
    monkeypatch.setattr(DecisionRunner.__init__, "__defaults__", (0.1,))


class Tweaked(FakeDecisionModel):
    """The fake whose TECH result passes through `tweak` (which may raise)."""

    def __init__(self, tweak):
        self.tweak = tweak

    def predict(self, checkpoint, state, questions):
        result = super().predict(checkpoint, state, questions)
        return self.tweak(result) if "accept" in questions else result


class StubChat:
    def __init__(self, text):
        self.text = text

    def complete(self, system, user):
        return self.text


def reply(options=((500000, 30), (500000, 25))):
    items = [
        {"text": f"Вариант {i}", "investment": investment, "equity": equity}
        for i, (investment, equity) in enumerate(options, 1)
    ]
    return json.dumps({"investor_line": "Ответ.", "options": items}, ensure_ascii=False)


def must_not_load():
    raise AssertionError("load_decision was called")


def call(
    argv, *, env=ENV, load=FakeDecisionModel, chat=None, lines=(), read=None, out=None, err=None
):
    """Run `main` over fakes; returns (exit code, stdout lines, stderr lines)."""
    out = [] if out is None else out
    err = [] if err is None else err
    feed = iter(lines)
    code = main(
        argv,
        env=env,
        load_decision=load,
        make_chat=lambda config: FakeChatModel() if chat is None else chat,
        read_line=read or (lambda: next(feed, None)),
        write=out.append,
        err=err.append,
    )
    return code, out, err


def call_exiting(argv, **kwargs):
    """Like `call`, for runs that end in the patched `os._exit`: (exit code, out, err)."""
    out, err = [], []
    with pytest.raises(Exited) as info:
        call(argv, out=out, err=err, **kwargs)
    return info.value.args[0], out, err


def on_channels(out, err, *, to_err=(), to_out=()):
    """Each line of `to_err` is on err only, each line of `to_out` on write only."""
    for line in to_err:
        assert line in err and line not in out, line
    for line in to_out:
        assert line in out and line not in err, line


def result_of(out):
    assert out[-1].startswith("RESULT ")
    return json.loads(out[-1][len("RESULT ") :])


def test_t_v0_game_12_selftest():
    out, err = [], []
    code = main(["--selftest"], env={}, write=out.append, err=err.append)  # no env, no load
    assert code == 0 and err == []
    assert out[-2:] == ["SELFTEST OK", RESULT_LINE]
    # `--script` is ignored
    out = []
    code = main(["--selftest", "--script", "/nonexistent/x.txt"], env={}, write=out.append)
    assert code == 0 and out[-2:] == ["SELFTEST OK", RESULT_LINE]
    # a failing chat: the verdict comes first, RESULT stays the last stdout line
    code, out, err = call(["--selftest"], env={}, chat=FakeChatModel(fail=True))
    assert code == 4
    assert out[-2].startswith("SELFTEST FAILED: ") and len(out[-2]) > len("SELFTEST FAILED: ")
    result = result_of(out)
    assert result["chat_ok"] == 0 and result["chat_fallbacks"] == 3
    assert err == ["chat_error=http_status:500"] * 3


def test_t_v0_game_13_check_result_outcome():
    assert check_result(dict(GOOD, outcome="won"), 0) == (4, "outcome")
    assert check_result(GOOD, 0) == (0, None)
    for outcome in OUTCOME_LINES:
        assert check_result(dict(GOOD, outcome=outcome), 0) == (0, None)


def test_t_v0_game_17_check_result_laya_checks():
    assert check_result(dict(GOOD, laya_checks=5), 0) == (4, "laya_checks")
    assert check_result(GOOD, 0) == (0, None)


def test_t_v0_game_18_check_result_truncated():
    assert check_result(dict(GOOD, truncated=1), 0) == (4, "truncated")
    assert check_result(GOOD, 0) == (0, None)


def test_t_v0_game_19_check_result_decision_turns():
    result = dict(GOOD, decision_turns=0, laya_checks=0)
    assert check_result(result, 0) == (4, "decision_turns")
    assert check_result(GOOD, 0) == (0, None)


def test_t_v0_game_20_check_result_chat_ok(tmp_path):
    assert check_result(dict(GOOD, chat_ok=0), 0) == (4, "chat_ok")
    assert check_result(GOOD, 0) == (0, None)
    assert check_result(dict(GOOD, chat_ok=1), 0) == (0, None)
    # the first violated invariant wins, in the spec's order
    assert check_result(dict(GOOD, outcome="won", chat_ok=0), 0) == (4, "outcome")
    # the status is passed through when nothing is violated
    assert check_result(GOOD, 3) == (3, None)
    # through main: GAME-07's script in a file over a failing chat
    path = tmp_path / "script.txt"
    path.write_text("\n".join(SCRIPT) + "\n", encoding="utf-8")
    code, out, _ = call(["--script", str(path), "--check-result"], chat=FakeChatModel(fail=True))
    assert code == 4
    assert out[-2] == "RESULT не прошёл проверку: chat_ok"
    assert result_of(out)["chat_ok"] == 0
    # the same script over a working chat passes the check
    code, out, _ = call(["--script", str(path), "--check-result"])
    assert code == 0 and out[-1] == RESULT_LINE
    assert not any(line.startswith("RESULT не прошёл") for line in out)


@pytest.mark.parametrize("env", [{}, {"CHAT_API_KEY": ""}])
def test_t_v0_game_14_missing_key(env):
    code, out, err = call([], env=env, load=must_not_load)
    assert code == 2
    assert err == [MISSING_KEY]
    assert out == []


def test_t_v0_game_15_errors(exits):
    # exit 2: a numeric value out of range, then a failed load
    bad_env = dict(ENV, CHAT_TIMEOUT_S="0")
    code, out, err = call([], env=bad_env, load=must_not_load)
    assert (code, out) == (2, [])
    assert err == ["Ошибка конфигурации: неверное значение переменной CHAT_TIMEOUT_S"]

    def load_fails():
        raise LoadError("OSError")

    code, out, err = call([], load=load_fails)
    assert code == 2
    assert err == ["Ошибка загрузки моделей: OSError", "laya_error=load:OSError"]

    # exit 3: a decision error ends the process through os._exit
    def raising(result):
        raise ValueError("boom")

    code, out, err = call_exiting(
        [], load=lambda: Tweaked(raising), lines=["1", "1", "€500k за 20%"]
    )
    assert code == 3
    assert err == ["Ошибка модели решений: ValueError", "laya_error=exception:ValueError"]
    assert not any(line.startswith("RESULT") for line in out)


def test_t_v0_game_16_script(tmp_path):
    path = tmp_path / "script.txt"
    path.write_text("1\n1\nвыход\n", encoding="utf-8")
    code, out, err = call(["--script", str(path)], read=lambda: pytest.fail("stdin was read"))
    assert code == 0 and err == []
    assert [line for line in out if line.startswith("> ")] == ["> 1", "> 1", "> выход"]
    assert out[-2] == QUIT
    # the file's end is EOF
    path.write_text("1\n1", encoding="utf-8")
    code, out, err = call(["--script", str(path)])
    assert code == 0 and out[-2] == QUIT
    assert result_of(out)["outcome"] == "player_quit"
    # unreadable: missing, a directory, not UTF-8
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\x00")
    for target in (tmp_path / "missing.txt", tmp_path, bad):
        code, out, err = call(["--script", str(target)], load=must_not_load)
        assert code == 2
        assert err == [f"Не удалось прочитать файл сценария: {target}"]
        assert out == []


def test_t_v0_game_21_channels(tmp_path, exits, fast_runner):
    script = tmp_path / "script.txt"
    script.write_text("\n".join(SCRIPT) + "\n", encoding="utf-8")
    offer = ["1", "1", "€500k за 20%"]

    # rows 1-3: before loading, on err only
    code, out, err = call([], env={}, load=must_not_load)
    assert (code, out) == (2, [])
    on_channels(out, err, to_err=[MISSING_KEY])
    code, out, err = call([], env=dict(ENV, CHAT_MAX_TOKENS="1.5"), load=must_not_load)
    assert (code, out) == (2, [])
    on_channels(
        out, err, to_err=["Ошибка конфигурации: неверное значение переменной CHAT_MAX_TOKENS"]
    )
    missing = str(tmp_path / "missing.txt")
    code, out, err = call(["--script", missing], load=must_not_load)
    assert (code, out) == (2, [])
    on_channels(out, err, to_err=[f"Не удалось прочитать файл сценария: {missing}"])
    code, out, err = call(["--check-result"], load=must_not_load)
    assert (code, out) == (2, [])
    on_channels(out, err, to_err=[CHECK_NEEDS_SCRIPT])

    # row 4: the load fails
    def load_fails():
        raise LoadError("OSError")

    code, out, err = call([], load=load_fails)
    assert code == 2 and out == BANNER
    on_channels(out, err, to_err=["Ошибка загрузки моделей: OSError", "laya_error=load:OSError"])

    # rows 5 and 6: predict raised, then truncated
    def raising(result):
        raise KeyError("/home/player/x")

    def truncating(result):
        result["usage"]["truncated"] = True
        return result

    code, out, err = call_exiting([], load=lambda: Tweaked(raising), lines=offer)
    assert code == 3
    on_channels(
        out, err, to_err=["Ошибка модели решений: KeyError", "laya_error=exception:KeyError"]
    )
    code, out, err = call_exiting([], load=lambda: Tweaked(truncating), lines=offer)
    assert code == 3
    on_channels(out, err, to_err=["Ошибка модели решений: truncated", "laya_error=truncated"])

    # rows 7 and 8: the fallback line on write, the chat_error= line on err
    code, out, err = call([], chat=FakeChatModel(fail=True), lines=["1", "1"])
    assert code == 0
    on_channels(out, err, to_out=[FALLBACK_OPENING], to_err=["chat_error=http_status:500"])
    # B8: HTTP 500 on a counter turn: the counter fallback line, options from the new standing offer
    code, out, err = call([], chat=FakeChatModel(fail=True), lines=["1", "1", "€500k за 20%"])
    assert code == 0 and err == ["chat_error=http_status:500"] * 2
    on_channels(out, err, to_out=["Инвестор: Вот моё встречное предложение."])
    assert out.count("1. Предлагаю €500k за 28% (€500k за 28%)") == 1
    assert out.count("2. Предлагаю €500k за 23% (€500k за 23%)") == 1
    code, out, err = call([], chat=StubChat("not json"), lines=["1", "1"])
    assert code == 0
    on_channels(out, err, to_out=[FALLBACK_OPENING], to_err=["chat_error=invalid_json"])

    # row 9: fewer than two valid options, the fallback options in the menu
    code, out, err = call([], chat=StubChat(reply(options=[])), lines=["1", "1"])
    assert code == 0 and err == []
    on_channels(
        out,
        err,
        to_out=["Инвестор: Ответ.", "1. Предлагаю €500k за 30% (€500k за 30%)"],
    )

    # row 10: HINT, the menu hint, REJECT_HINT — no error output
    code, out, err = call([], lines=["9", "1", "1", "дай денег", "отказаться"])
    assert code == 0 and err == []
    on_channels(out, err, to_out=["Введите номер от 1 до 4.", HINT, REJECT_HINT])

    # row 11: EOF
    code, out, err = call([], lines=["1", "1"])
    assert code == 0 and err == []
    assert out[-2] == QUIT and out[-1].startswith("RESULT ")

    # row 12: KeyboardInterrupt
    def interrupted():
        raise KeyboardInterrupt

    code, out, err = call([], read=interrupted)
    assert code == 130 and err == []
    assert out[-1] == "Игра прервана"

    def load_interrupted():
        raise KeyboardInterrupt

    code, out, err = call([], load=load_interrupted)  # Ctrl-C while the models load
    assert code == 130 and err == []
    assert out == [*BANNER, "Игра прервана"]

    # row 13: a --check-result violation
    code, out, err = call(
        ["--script", str(script), "--check-result"], chat=FakeChatModel(fail=True)
    )
    assert code == 4
    on_channels(
        out,
        err,
        to_out=["RESULT не прошёл проверку: chat_ok"],
        to_err=["chat_error=http_status:500"],
    )
    assert out[-1].startswith("RESULT {")

    # row 14: --selftest RESULT differs from GAME-07's
    code, out, err = call(["--selftest"], chat=FakeChatModel(fail=True))
    assert code == 4
    assert out[-2].startswith("SELFTEST FAILED: ") and out[-1].startswith("RESULT {")
    assert not any(line.startswith("SELFTEST") for line in err)


def test_t_v0_game_22_check_result_needs_script():
    code, out, err = call(["--check-result"], load=must_not_load)
    assert code == 2
    assert err == [CHECK_NEEDS_SCRIPT]
    assert "--check-result" in err[0] and "--script" in err[0]
    assert out == []


def fake_laya(load):
    return types.SimpleNamespace(
        PINNED_REVISIONS={REPO: PINNED_SHA},
        load=load,
        common=types.SimpleNamespace(
            serialize_state=lambda state: json.dumps(state, sort_keys=True),
            encode_text=lambda tok, text, add_special_tokens=True: {"input_ids": text.split()},
        ),
    )


def test_t_v0_dec_16_laya_error(exits, fast_runner):
    secret = "/home/player/x"
    offer = ["1", "1", "€500k за 20%"]

    def check(code, out, err, *, expected_code, message, category, hidden):
        assert code == expected_code
        assert err == [message, f"laya_error={category}"]  # one laya_error= line, after the message
        assert not any(line.startswith("laya_error=") for line in out)
        for line in out + err:
            assert "/home/" not in line and hidden not in line

    # a load failure: exit 2
    def boom(*args, **kwargs):
        raise OSError("/home/player/.cache/hf")

    code, out, err = call([], load=lambda: load_decision_model(fake_laya(boom)))
    check(
        code,
        out,
        err,
        expected_code=2,
        message="Ошибка загрузки моделей: OSError",
        category="load:OSError",
        hidden=".cache",
    )

    def sleeping(result):
        time.sleep(0.3)
        return result

    def invalid(result):
        result["answers"] = {}
        return result

    def truncating(result):
        result["usage"]["truncated"] = True
        return result

    def raises(exc):
        def tweak(result):
            raise exc

        return tweak

    cases = [
        (sleeping, "timeout", "timeout", "sleep"),
        (invalid, "shape", "shape", "answers"),
        (truncating, "truncated", "truncated", "truncat" + "ion"),
        (raises(KeyError(secret)), "KeyError", "exception:KeyError", "player"),
        (raises(MemoryError(secret)), "oom", "oom", "player"),
        (
            raises(RuntimeError(f"DefaultCPUAllocator: not enough memory: {secret}")),
            "oom",
            "oom",
            "DefaultCPUAllocator",
        ),
    ]
    for tweak, word, category, hidden in cases:
        code, out, err = call_exiting([], load=lambda tweak=tweak: Tweaked(tweak), lines=offer)
        check(
            code,
            out,
            err,
            expected_code=3,
            message=f"Ошибка модели решений: {word}",
            category=category,
            hidden=hidden,
        )


def test_t_v0_gate_01_live_script(tmp_path):
    path = ROOT / "acceptance" / "live-script.txt"
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "\n".join(LIVE_SCRIPT) + "\n"
    # it is playable: over the fakes it passes --check-result
    code, out, err = call(["--script", str(path), "--check-result"])
    assert code == 0 and err == []
    assert result_of(out)["outcome"] == "deal"
