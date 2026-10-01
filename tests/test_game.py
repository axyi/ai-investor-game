import copy
import json
import threading
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from investor_game.__main__ import main
from investor_game.decision import DecisionRunner
from investor_game.fakes import FakeChatModel, FakeDecisionModel
from investor_game.game import play
from investor_game.parse import HINT
from investor_game.rules import OUTCOME_LINES, REJECT_HINT

NOW = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
ENV = {"CHAT_API_KEY": "sk-test-not-a-real-key"}
SCRIPT = ["1", "1", "Здравствуйте! Предлагаю €500k за 20%", "1"]  # GAME-07's SELFTEST_SCRIPT
# GAME-07's RESULT, spec-v0 line 699.
RESULT_LINE = (
    'RESULT {"outcome":"deal","decision_turns":2,"laya_checks":6,"truncated":0,"chat_ok":3,'
    '"chat_fallbacks":0,"overrides":[],"final_offer":{"investment":500000,"equity":30}}'
)
QUIT = OUTCOME_LINES["player_quit"]
DEAL = OUTCOME_LINES["deal"]
OFFER_35 = "Предложение инвестора: €500k за 35%"
OFFER_33 = "Предложение инвестора: €500k за 33%"
MENU_30_25 = [
    "Ваш ход:",
    "1. Предлагаю €500k за 30% (€500k за 30%)",
    "2. Предлагаю €500k за 25% (€500k за 25%)",
    "3. Принять предложение инвестора",
    "4. Выйти из переговоров",
]
TRANSCRIPT = [
    "=== ПЕРЕГОВОРЫ ===",
    "Загрузка моделей…",
    "Выберите инвестора:",
    "1. Жадный — торгуется за каждый процент",
    "2. Щедрый — дружелюбный, ободряющий",
    "3. Грубый — грубоватый и нетерпеливый, без оскорблений",
    "4. Осторожный — вежливый, задаёт уточняющие вопросы",
    "> 1",
    "Выберите стартап:",
    "1. Репетитор-ИИ — ИИ-репетитор для школьников, оценка €2.0M",
    "2. СолнцеГрид — домашние аккумуляторы для солнечных панелей, оценка €2.5M",
    "3. Оборонзавод — завод боеприпасов и ударных дронов, оценка €3.0M",
    "> 1",
    "Вы продаёте стартап «Репетитор-ИИ». Текущая оценка: €2.0M",
    "Инвестор: Фейковый инвестор: ход принят.",
    OFFER_35,
    *MENU_30_25,
    "> Здравствуйте! Предлагаю €500k за 20%",
    "Инвестор: Фейковый инвестор: ход принят.",
    OFFER_33,
    *MENU_30_25,
    "> 1",
    "Инвестор: Фейковый инвестор: ход принят.",
    DEAL,
    "Условия сделки: €500k за 30%. Оценка компании после сделки: €1.67M.",
    RESULT_LINE,
]


def check_name(questions):
    if "accept" in questions:
        return "tech"
    return "moral" if "ethical_concern" in questions else "stake"


class Recorder(FakeDecisionModel):
    """The fake decision model plus a record of every state it was asked about."""

    def __init__(self):
        self.calls = []

    def predict(self, checkpoint, state, questions):
        self.calls.append((check_name(questions), copy.deepcopy(state)))
        return super().predict(checkpoint, state, questions)

    def states(self, name):
        return [state for call, state in self.calls if call == name]


class Scripted(Recorder):
    """`behave(name, attempt, result)` may replace or raise over the fake's answer."""

    def __init__(self, behave):
        super().__init__()
        self.behave = behave
        self.attempts = Counter()
        self.lock = threading.Lock()

    def predict(self, checkpoint, state, questions):
        name = check_name(questions)
        with self.lock:
            self.attempts[name] += 1
            attempt = self.attempts[name]
        return self.behave(name, attempt, super().predict(checkpoint, state, questions))


class Reporting(DecisionRunner):
    """A real runner whose turns report the next number of used results (`Decisions.checks`)."""

    def __init__(self, model, reports):
        super().__init__(model, timeout_s=5.0)
        self.reports = iter(reports)

    def run(self, tech, moral, stake):
        return replace(super().run(tech, moral, stake), checks=next(self.reports))


class CountingChat(FakeChatModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return super().complete(system, user)


class StubChat:
    """A chat model that always returns `text`."""

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.text


def reply(line="Ответ.", options=((500000, 30), (500000, 25))):
    items = [
        {"text": f"Вариант {i}", "investment": investment, "equity": equity}
        for i, (investment, equity) in enumerate(options, 1)
    ]
    return json.dumps({"investor_line": line, "options": items}, ensure_ascii=False)


def play_lines(lines, *, model=None, chat=None, show=False, runner=None):
    """Run `play` over a real DecisionRunner; returns (result, written, errors, model, chat)."""
    model = Recorder() if model is None else model
    chat = CountingChat() if chat is None else chat
    runner = DecisionRunner(model, timeout_s=5.0) if runner is None else runner
    feed = iter(lines)
    written, errors = [], []
    try:
        result = play(
            runner,
            chat,
            lambda: next(feed, None),
            written.append,
            errors.append,
            show_decisions=show,
            now=lambda: NOW,
        )
    finally:
        runner.close()
    return result, written, errors, model, chat


def ends_once(written, outcome_line):
    """The outcome line appears exactly once and no prompt or options follow it."""
    assert written.count(outcome_line) == 1
    assert "Ваш ход:" not in written[written.index(outcome_line) :]


def test_t_v0_game_01_transcript(tmp_path):
    path = tmp_path / "script.txt"
    path.write_text("\n".join(SCRIPT) + "\n", encoding="utf-8")
    out, err = [], []
    code = main(
        ["--script", str(path)],
        env=ENV,
        load_decision=FakeDecisionModel,
        make_chat=lambda config: FakeChatModel(),
        write=out.append,
        err=err.append,
    )
    assert code == 0
    assert err == []
    assert out == TRANSCRIPT
    # TST-04's pins, one by one
    assert out[0] == "=== ПЕРЕГОВОРЫ ==="
    assert out.index(OFFER_35) < out.index(OFFER_33) < out.index(DEAL)
    assert out.count(DEAL) == 1
    assert "Ваш ход:" not in out[out.index(DEAL) :]
    assert out[-2] == "Условия сделки: €500k за 30%. Оценка компании после сделки: €1.67M."
    assert out[-1] == RESULT_LINE


def test_t_v0_game_02_options_display():
    result, out, err, model, chat = play_lines(["1", "1"])
    # `play` prints the menus, the opening and the options; the `> ` echo belongs to the reader
    assert out == [line for line in TRANSCRIPT[2:21] if not line.startswith("> ")] + [QUIT]
    assert err == []
    assert result["outcome"] == "player_quit"
    assert result["final_offer"] == {"investment": 500000, "equity": 35}
    assert chat.calls == 1 and model.calls == []


def test_t_v0_game_03_player_accept():
    for accept in ("принять", "ACCEPT", "3"):
        result, out, _, model, chat = play_lines(["1", "1", accept])
        assert model.calls == []  # no Laya
        assert chat.calls == 1  # the opening only, no chat for the shortcut
        ends_once(out, DEAL)
        assert out[-2:] == [
            DEAL,
            "Условия сделки: €500k за 35%. Оценка компании после сделки: €1.43M.",
        ]
        assert result == {
            "outcome": "deal",
            "decision_turns": 0,
            "laya_checks": 0,
            "truncated": 0,
            "chat_ok": 1,
            "chat_fallbacks": 0,
            "overrides": [],
            "final_offer": {"investment": 500000, "equity": 35},
        }


def test_t_v0_game_04_player_reject():
    # before any own offer: REJECT_HINT, no model call, no turn consumed
    result, out, _, model, chat = play_lines(["1", "1", "отказаться", "REJECT"])
    assert out.count(REJECT_HINT) == 2
    assert model.calls == [] and chat.calls == 1
    assert result["decision_turns"] == 0 and result["outcome"] == "player_quit"
    # after one: a decision turn on the player's last offer, with the repeat entry
    result, out, _, model, chat = play_lines(["1", "1", "€500k за 20%", "отказаться"])
    assert REJECT_HINT not in out
    assert result["decision_turns"] == 2
    tech = model.states("tech")
    assert len(tech) == 2
    assert tech[1]["player_offer"] == {"investment": 500000, "equity": 20}
    assert tech[1]["history"][-1] == "Round 2: player repeated the offer of €500k for 20%"
    assert tech[1]["history"][-2] == (
        "Round 1: player offered €500k for 20%; investor countered €500k for 33%"
    )
    assert not any("Player rejected" in json.dumps(state) for _, state in model.calls)


def test_t_v0_game_05_invalid_move():
    lines = ["9", "x", "1", "0", "1", "дай денег", "600k", "20%", "5 6"]
    result, out, err, model, chat = play_lines(lines)
    assert out.count("Введите номер от 1 до 4.") == 2  # "9", "x" at the investor menu
    assert out.count("Введите номер от 1 до 3.") == 1  # "0" at the startup menu
    assert out.count(HINT) == 4
    assert model.calls == [] and chat.calls == 1
    assert result["decision_turns"] == 0 and result["outcome"] == "player_quit"
    assert err == []


def test_t_v0_game_06_quit_eof():
    for ending in (["выход"], ["QUIT"], ["4"], []):  # a command, a menu number, EOF
        result, out, _, model, chat = play_lines(["1", "1", *ending])
        ends_once(out, QUIT)
        assert out[-1] == QUIT
        assert result["outcome"] == "player_quit"
        assert result["final_offer"] == {"investment": 500000, "equity": 35}
        assert model.calls == []
    # EOF at a menu: before any standing offer
    result, out, _, model, chat = play_lines(["1"])
    assert out[-1] == QUIT and chat.calls == 0
    assert result["final_offer"] is None


def test_t_v0_game_07_interrupt():
    def interrupted():
        raise KeyboardInterrupt

    out, err = [], []
    code = main(
        [],
        env=ENV,
        load_decision=FakeDecisionModel,
        make_chat=lambda config: FakeChatModel(),
        read_line=interrupted,
        write=out.append,
        err=err.append,
    )
    assert code == 130
    assert out[-1] == "Игра прервана"
    assert not any(line.startswith("RESULT") for line in out)
    assert err == []
    # `play` itself lets the interrupt through
    runner = DecisionRunner(Recorder(), timeout_s=5.0)
    with pytest.raises(KeyboardInterrupt):
        play(
            runner,
            FakeChatModel(),
            interrupted,
            lambda line: None,
            show_decisions=False,
            now=lambda: NOW,
        )
    runner.close()


def test_t_v0_game_08_code_owns_numbers():
    ansi_line = "\x1b[31mRED\x1b[0m Беру €5M за 1%!"
    chat = StubChat(reply(line=ansi_line, options=((600000, 22), (600000, 26))))
    typed = "\x1b[31m€500k за 20%\x1b[0m"
    _, out, _, model, chat = play_lines(["1", "1", typed], chat=chat)
    # ANSI stripped from the chat line and from the typed input
    assert "Инвестор: RED Беру €5M за 1%!" in out
    assert not any("\x1b" in line for line in out)
    assert not any("\x1b" in json.dumps(state) for _, state in model.calls)
    assert model.states("tech")[0]["player_offer"] == {"investment": 500000, "equity": 20}
    assert model.states("stake")[0] == {"player_message": "€500k за 20%"}
    # prose never reaches the offer line: only code's numbers do
    offer_lines = [line for line in out if line.startswith("Предложение инвестора:")]
    assert offer_lines == [OFFER_35, OFFER_33]
    # B11: a typed "дай €5M за 1%" with a chat line quoting €5M: the offer line is code's counter
    chat = StubChat(reply(line="Беру €5M за 1%!"))
    _, out, _, model, _ = play_lines(["1", "1", "дай €5M за 1%"], chat=chat)
    assert model.states("tech")[0]["player_offer"] == {"investment": 5000000, "equity": 1}
    offer_lines = [line for line in out if line.startswith("Предложение инвестора:")]
    assert offer_lines == [OFFER_35, "Предложение инвестора: €700k за 33%"]
    # an offer option's numbers reach TECH only once the player picks it
    chat = StubChat(reply(options=((600000, 22), (600000, 26))))
    _, out, _, model, chat = play_lines(["1", "1"], chat=chat)
    assert "1. Вариант 1 (€600k за 22%)" in out
    assert model.calls == []  # displaying the options called no model
    _, out, _, model, chat = play_lines(["1", "1", "2"], chat=chat)
    assert model.states("tech")[0]["player_offer"] == {"investment": 600000, "equity": 26}
    assert model.states("stake")[0] == {"player_message": "Вариант 2"}


def test_t_v0_game_09_result_counters():
    # a check failing once, then valid, counts once; the retry is not a second check
    def flaky(name, attempt, result):
        if name == "moral" and attempt == 1:
            raise RuntimeError("transient")
        return result

    model = Scripted(flaky)
    result, _, _, model, _ = play_lines(["1", "1", "€500k за 20%"], model=model)
    assert model.attempts["moral"] == 2
    assert result["decision_turns"] == 1 and result["laya_checks"] == 3

    # a truncated result its DEC-06 re-run recovered is counted once in `truncated`
    def truncating(name, attempt, result):
        if name == "tech" and attempt == 1:
            result["usage"]["truncated"] = True
        return result

    model = Scripted(truncating)
    result, _, _, model, _ = play_lines(["1", "1", "€500k за 20%"], model=model)
    assert model.attempts["tech"] == 2
    assert result["truncated"] == 1
    assert result["decision_turns"] == 1 and result["laya_checks"] == 3

    # the opening, a player accept and a reject before an own offer are not decision turns
    result, _, _, model, _ = play_lines(["1", "1", "отказаться", "€500k за 20%", "принять"])
    assert result["decision_turns"] == 1 and result["laya_checks"] == 3
    assert result["outcome"] == "deal"
    assert result["chat_ok"] == 2  # the opening and turn 1; the accept shortcut has no chat

    # `laya_checks` adds what the runner reports per turn (+1 per used result, never a constant 3)
    model = Recorder()
    runner = Reporting(model, [3, 2])
    result, _, _, _, _ = play_lines(
        ["1", "1", "€500k за 20%", "€500k за 25%"], model=model, runner=runner
    )
    assert result["decision_turns"] == 2 and result["laya_checks"] == 5


def test_t_v0_game_10_show_decisions():
    _, out, _, _, _ = play_lines(SCRIPT, show=True)
    assert (
        "[решения] ход 1: accept=1 reaction=counter good_deal=нет ethical_concern=нет "
        "tone=neutral → counter; правила: —"
    ) in out
    assert (
        "[решения] ход 2: accept=4 reaction=accept good_deal=да ethical_concern=нет "
        "tone=neutral → deal; правила: —"
    ) in out
    quiet = play_lines(SCRIPT)[1]
    assert not any(line.startswith("[решения]") for line in quiet)

    # GAME-03/04: the flag reaches `play` through `main`; the same run without it has no line
    def through_main(argv):
        feed, written, errors = iter(SCRIPT), [], []
        code = main(
            argv,
            env=ENV,
            load_decision=FakeDecisionModel,
            make_chat=lambda config: FakeChatModel(),
            read_line=lambda: next(feed, None),
            write=written.append,
            err=errors.append,
        )
        assert code == 0 and errors == []
        return [line for line in written if line.startswith("[решения]")]

    assert through_main(["--show-decisions"]) == [
        (
            "[решения] ход 1: accept=1 reaction=counter good_deal=нет ethical_concern=нет "
            "tone=neutral → counter; правила: —"
        ),
        (
            "[решения] ход 2: accept=4 reaction=accept good_deal=да ethical_concern=нет "
            "tone=neutral → deal; правила: —"
        ),
    ]
    assert through_main([]) == []

    # a Laya walk_away reaction ends the game: R2, wired through `walk_away=`
    def walks_away(name, attempt, result):
        if name == "tech":
            result["answers"]["reaction"] = {"choice": "walk_away"}
        return result

    _, out, _, _, _ = play_lines(["1", "1", "€500k за 20%"], model=Scripted(walks_away), show=True)
    outcome = OUTCOME_LINES["walk_away_investor"]
    ends_once(out, outcome)
    assert out[-1] == outcome
    assert any("reaction=walk_away" in line and "→ walk_away_investor" in line for line in out)
    rude = ["1", "1", "€500k за 20%", "Вы жадный старик, €500k за 20% или проваливайте."]
    _, out, _, _, _ = play_lines(rude, show=True)
    assert (
        "[решения] ход 2: accept=1 reaction=counter good_deal=нет ethical_concern=нет "
        "tone=rude → counter; правила: rude"
    ) in out


def test_t_v0_game_11_moral():
    result, out, _, _, _ = play_lines(["2", "3", "€600k за 20%"], show=True)
    outcome = "Итог: инвестор отказался по этическим соображениям."
    ends_once(out, outcome)
    assert out[-1] == outcome
    assert result["outcome"] == "walk_away_moral"
    assert result["overrides"] == ["moral"]
    assert result["decision_turns"] == 1 and result["laya_checks"] == 3
    assert result["final_offer"] == {"investment": 600000, "equity": 25}
    assert any(
        "ethical_concern=да tone=neutral → walk_away_moral; правила: moral" in x for x in out
    )
    # persona 1 and the same startup: no veto (B2)
    result, out, _, _, _ = play_lines(["1", "3", "€500k за 20%"])
    assert result["overrides"] == [] and result["outcome"] == "player_quit"
    # B5 (RUL-03 R5 / R6) through the game: persona 3 has patience 3 and a rude message costs 2,
    # so only patience carried from turn 1 (3 -> 1) lets turn 2 end `walk_away_patience`
    rude = "Вы жадный старик, €500k за 20% или проваливайте."
    result, out, _, model, _ = play_lines(["3", "1", rude, rude], show=True)
    outcome = OUTCOME_LINES["walk_away_patience"]
    ends_once(out, outcome)
    assert out[-1] == outcome
    assert result["outcome"] == "walk_away_patience" and result["decision_turns"] == 2
    assert result["overrides"] == ["rude", "rude", "patience"]
    tech = model.states("tech")
    assert "Rounds of patience left: 3." in tech[0]["facts"]
    assert "Rounds of patience left: 1." in tech[1]["facts"]
    assert any(
        "ход 2:" in x and "tone=rude → walk_away_patience; правила: rude, patience" in x
        for x in out
    )


@pytest.mark.parametrize(
    ("chat", "k", "offers"),
    [
        (FakeChatModel(fail=True), 2, [(500000, 30), (500000, 25)]),  # the fallback options
        (StubChat(reply(options=((500000, 30), (500000, 28), (600000, 26)))), 3, None),
    ],
    ids=["fallback-k2", "valid-k3"],
)
def test_t_v0_game_23_option_mapping(chat, k, offers):
    offers = offers or [(500000, 30), (500000, 28), (600000, 26)]
    for pick in (1, k):
        investment, equity = offers[pick - 1]
        result, out, _, model, _ = play_lines(["1", "1", str(pick)], chat=chat)
        assert model.states("tech")[0]["player_offer"] == {
            "investment": investment,
            "equity": equity,
        }
    result, out, _, model, _ = play_lines(["1", "1", str(k + 1)], chat=chat)  # player accept
    assert model.calls == [] and result["outcome"] == "deal"
    assert result["final_offer"] == {"investment": 500000, "equity": 35}
    result, out, _, model, _ = play_lines(["1", "1", str(k + 2)], chat=chat)  # player quit
    assert model.calls == [] and result["outcome"] == "player_quit"
    result, out, _, model, _ = play_lines(["1", "1", "0", str(k + 3)], chat=chat)
    assert out.count(HINT) == 2
    assert model.calls == [] and result["decision_turns"] == 0


def test_t_v0_game_24_reject_keeps_offer():
    def reject_first(name, attempt, result):
        if name == "tech" and attempt == 1:
            result["answers"]["reaction"] = {"choice": "reject"}
        return result

    lines = ["1", "1", "€500k за 20%", "€500k за 22%"]
    _, out, _, model, _ = play_lines(lines, model=Scripted(reject_first))
    offer_lines = [line for line in out if line.startswith("Предложение инвестора:")]
    # the opening, the menu after the reject (the standing offer is kept), then turn 2's counter
    assert offer_lines == [OFFER_35, OFFER_35, OFFER_33]
    tech = model.states("tech")
    assert tech[1]["history"][-1] == (
        "Round 1: player offered €500k for 20%; investor kept €500k for 35%"
    )
    assert (
        "The offered equity 22% is far below the investor's current ask of 35%." in tech[1]["facts"]
    )
    assert tech[1]["player_offer"] == {"investment": 500000, "equity": 22}
