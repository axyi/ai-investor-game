"""The game loop (GAME-01..GAME-06): menus, turns, the outcome and RESULT."""

from collections.abc import Callable
from datetime import datetime

from investor_game.chat import ChatModel, Option, Turn, voice
from investor_game.decision import (
    DecisionRunner,
    Decisions,
    moral_state,
    stakeholder_state,
    tech_state,
)
from investor_game.domain import PERSONAS, STARTUPS, Offer, Persona, Startup, format_eur
from investor_game.parse import HINT, Move, parse_menu, parse_move
from investor_game.rules import (
    OUTCOME_LINES,
    REJECT_HINT,
    Ruling,
    aggregate,
    deal_summary,
    facts,
    offer_entry,
    opening_entry,
    repeat_entry,
)

_YES_NO = {True: "да", False: "нет"}


def _terms(offer: Offer) -> str:
    return f"{format_eur(offer.investment)} за {offer.equity}%"


class _Session:
    """One game: the I/O callables and the RESULT counters."""

    def __init__(
        self,
        runner: DecisionRunner,
        chat: ChatModel,
        read_line: Callable[[], str | None],
        write: Callable[[str], None],
        err: Callable[[str], None] | None,
        show_decisions: bool,
        now: Callable[[], datetime],
    ) -> None:
        self.runner = runner
        self.chat = chat
        self.read_line = read_line
        self.write = write
        self.err = err
        self.show_decisions = show_decisions
        self.now = now
        self.result: dict = {
            "outcome": None,
            "decision_turns": 0,
            "laya_checks": 0,
            "truncated": 0,
            "chat_ok": 0,
            "chat_fallbacks": 0,
            "overrides": [],
            "final_offer": None,
        }

    def run(self) -> dict:
        persona = self._choose(
            "Выберите инвестора:", [f"{p.name} — {p.tone}" for p in PERSONAS], PERSONAS
        )
        startup = None
        if persona is not None:
            rows = [
                f"{s.name} — {s.description}, оценка {format_eur(s.valuation)}" for s in STARTUPS
            ]
            startup = self._choose("Выберите стартап:", rows, STARTUPS)
        if persona is None or startup is None:
            self._end("player_quit")
        else:
            self.write(
                f"Вы продаёте стартап «{startup.name}». "
                f"Текущая оценка: {format_eur(startup.valuation)}"
            )
            self._negotiate(persona, startup)
        return self.result

    def _choose(self, title: str, rows: list[str], items: tuple):
        """A numbered menu: the chosen item, or None at EOF."""
        self.write(title)
        for number, row in enumerate(rows, 1):
            self.write(f"{number}. {row}")
        while True:
            line = self.read_line()
            if line is None:
                return None
            number = parse_menu(line, len(items))
            if number is not None:
                return items[number - 1]
            self.write(f"Введите номер от 1 до {len(items)}.")

    def _negotiate(self, persona: Persona, startup: Startup) -> None:
        standing, patience = persona.opening, persona.patience
        history = [opening_entry(persona)]
        last_offer = None  # the player's last offer: what `отказаться` repeats (RUL-06)
        options = self._speak(persona, startup, "opening", standing, None, history, "")
        while True:
            self._show(standing, options)
            count = len(options)
            move = self._ask(count + 2, last_offer is not None)
            if move is None or move.kind == "quit" or move.index == count + 2:
                return self._end("player_quit", standing)
            if move.kind == "accept" or move.index == count + 1:
                return self._end("deal", standing)  # RUL-06: no Laya, no chat
            if move.kind == "option":
                offer, text = options[move.index - 1].offer, options[move.index - 1].text
            elif move.kind == "offer":
                offer, text = move.offer, move.text
            else:  # reject, after an own offer
                offer, text = last_offer, move.text
            turn = self.result["decision_turns"] + 1
            if move.kind == "reject":
                history.append(repeat_entry(turn, offer))  # that round's only entry
            decisions, ruling = self._decide(
                turn, persona, startup, offer, text, standing, patience, history
            )
            last_offer, patience = offer, ruling.patience
            if ruling.ended:
                reaction = "accept" if ruling.outcome == "deal" else "walk_away"
            else:
                reaction = ruling.outcome  # counter | reject
                if move.kind != "reject":
                    entry = offer_entry(
                        turn, offer, ruling.offer, countered=ruling.outcome == "counter"
                    )
                    history.append(entry)
                standing = ruling.offer
            options = self._speak(
                persona, startup, reaction, ruling.offer, decisions.good_deal, history, text
            )
            if ruling.ended:
                return self._end(ruling.outcome, ruling.offer)

    def _ask(self, count: int, has_offer: bool) -> Move | None:
        """The next playable move (PAR-03, RUL-06 re-prompt on the rest); None at EOF."""
        while True:
            line = self.read_line()
            if line is None:
                return None
            move = parse_move(line, count)
            if move.kind == "invalid":
                self.write(HINT)
            elif move.kind == "reject" and not has_offer:
                self.write(REJECT_HINT)
            else:
                return move

    def _decide(
        self,
        turn: int,
        persona: Persona,
        startup: Startup,
        offer: Offer,
        text: str,
        standing: Offer,
        patience: int,
        history: list[str],
    ) -> tuple[Decisions, Ruling]:
        decisions = self.runner.run(
            tech_state(
                offer,
                persona,
                patience,
                facts(offer, standing, persona, startup, patience),
                history,
            ),
            moral_state(startup),
            stakeholder_state(text),
        )
        self.result["decision_turns"] = turn
        self.result["laya_checks"] += decisions.checks
        self.result["truncated"] += decisions.truncated
        ruling = aggregate(
            persona,
            offer,
            standing,
            turn=turn,
            patience=patience,
            choice=decisions.choice,
            level=decisions.level,
            walk_away=decisions.walk_away,
            ethical_concern=decisions.ethical_concern,
            tone=decisions.tone,
        )
        self.result["overrides"].extend(ruling.reasons)
        if self.show_decisions:
            self.write(
                f"[решения] ход {turn}: accept={decisions.level} reaction={decisions.choice} "
                f"good_deal={_YES_NO[decisions.good_deal]} "
                f"ethical_concern={_YES_NO[decisions.ethical_concern]} tone={decisions.tone} "
                f"→ {ruling.outcome}; правила: {', '.join(ruling.reasons) or '—'}"
            )
        return decisions, ruling

    def _speak(
        self,
        persona: Persona,
        startup: Startup,
        reaction: str,
        offer: Offer,
        good_deal: bool | None,
        history: list[str],
        text: str,
    ) -> tuple[Option, ...]:
        """One voice call: print the investor's line, count it, return the player's options."""
        turn = Turn(persona, startup, reaction, offer, good_deal, history, text, self.now())
        voiced = voice(self.chat, turn, self.err)
        self.result["chat_fallbacks" if voiced.fallback else "chat_ok"] += 1
        self.write(f"Инвестор: {voiced.line}")
        return voiced.options

    def _show(self, standing: Offer, options: tuple[Option, ...]) -> None:
        self.write(f"Предложение инвестора: {_terms(standing)}")
        self.write("Ваш ход:")
        for number, option in enumerate(options, 1):
            self.write(f"{number}. {option.text} ({_terms(option.offer)})")
        self.write(f"{len(options) + 1}. Принять предложение инвестора")
        self.write(f"{len(options) + 2}. Выйти из переговоров")

    def _end(self, outcome: str, offer: Offer | None = None) -> None:
        """The outcome line once, `deal_summary` once on a deal (GAME-02)."""
        self.result["outcome"] = outcome
        if offer is not None:
            self.result["final_offer"] = {"investment": offer.investment, "equity": offer.equity}
        self.write(OUTCOME_LINES[outcome])
        if outcome == "deal":
            self.write(deal_summary(offer))


def play(
    runner: DecisionRunner,
    chat: ChatModel,
    read_line: Callable[[], str | None],
    write: Callable[[str], None],
    err: Callable[[str], None] | None = None,
    *,
    show_decisions: bool,
    now: Callable[[], datetime],
) -> dict:
    """Play one game and return RESULT (GAME-05); `main` prints it.

    read_line returns None at EOF; write takes one finished line; err None means stderr (it only
    receives voice's `chat_error=` lines); now is the clock each chat turn reads. A DecisionError
    and a KeyboardInterrupt propagate to `main`.
    """
    return _Session(runner, chat, read_line, write, err, show_decisions, now).run()


def check_result(result: dict, status: int) -> tuple[int, str | None]:
    """GAME-06: (status, None) when every invariant holds, else (4, the first violated name)."""
    invariants = (
        ("outcome", result["outcome"] in OUTCOME_LINES),
        ("laya_checks", result["laya_checks"] == 3 * result["decision_turns"]),
        ("truncated", result["truncated"] == 0),
        ("decision_turns", result["decision_turns"] >= 1),
        ("chat_ok", result["chat_ok"] >= 1),
    )
    for name, holds in invariants:
        if not holds:
            return 4, name
    return status, None
