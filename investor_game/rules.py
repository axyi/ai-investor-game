from collections.abc import Sequence
from dataclasses import dataclass

from investor_game.domain import Offer, Persona, Startup, format_eur, post_money

MAX_TURNS = 10
HISTORY_WINDOW = 4
REJECT_HINT = "Сначала сделайте своё предложение или примите предложение инвестора."
OUTCOME_LINES = {
    "deal": "Итог: сделка заключена.",
    "walk_away_moral": "Итог: инвестор отказался по этическим соображениям.",
    "walk_away_investor": "Итог: инвестор прекратил переговоры.",
    "walk_away_patience": "Итог: у инвестора закончилось терпение.",
    "max_turns": "Итог: лимит ходов, сделки нет.",
    "player_quit": "Итог: вы вышли из переговоров.",
}


@dataclass(frozen=True)
class Ruling:
    """The aggregated result of one decision turn.

    outcome: "counter" or "reject" when the game goes on, else an OUTCOME_LINES key.
    offer: the offer on the table after the turn (deal terms, counter-offer or standing offer).
    patience: patience after this turn's cost.
    reasons: RESULT `overrides` entries, in rule order.
    """

    outcome: str
    offer: Offer
    patience: int
    reasons: tuple[str, ...]

    @property
    def ended(self) -> bool:
        return self.outcome in OUTCOME_LINES


def _terms(offer: Offer) -> str:
    return f"{format_eur(offer.investment)} for {offer.equity}%"


def facts(
    offer: Offer, standing: Offer, persona: Persona, startup: Startup, patience: int
) -> list[str]:
    """TECH facts for the decision model (RUL-01), in order; patience is before this turn's cost."""
    if offer.equity >= standing.equity:
        ask = "at or above"
    elif offer.equity >= standing.equity - persona.step:
        ask = "close to"
    else:
        ask = "far below"
    value = post_money(offer)
    if 10 * abs(value - startup.valuation) <= startup.valuation:
        relation = "near"
    elif value < startup.valuation:
        relation = "below"
    else:
        relation = "above"
    budget = "is within" if offer.investment <= persona.budget else "exceeds"
    minimum = "is below" if offer.equity < persona.min_equity else "meets"
    return [
        f"The requested investment {budget} the investor's budget.",
        (
            f"The offered equity {offer.equity}% is {ask} "
            f"the investor's current ask of {standing.equity}%."
        ),
        f"The offered equity {minimum} the investor's minimum of {persona.min_equity}%.",
        (
            f"The implied post-money valuation {format_eur(value)} is {relation} "
            f"the startup's valuation of {format_eur(startup.valuation)}."
        ),
        f"Rounds of patience left: {patience}.",
    ]


def opening_entry(persona: Persona) -> str:
    return f"Round 0: investor offered {_terms(persona.opening)}"


def offer_entry(n: int, player: Offer, investor: Offer, *, countered: bool) -> str:
    verb = "countered" if countered else "kept"
    return f"Round {n}: player offered {_terms(player)}; investor {verb} {_terms(investor)}"


def repeat_entry(n: int, player: Offer) -> str:
    return f"Round {n}: player repeated the offer of {_terms(player)}"


def recent(history: Sequence[str]) -> list[str]:
    """The history that states and chat get: the last HISTORY_WINDOW entries."""
    return list(history[-HISTORY_WINDOW:])


def counter_offer(persona: Persona, offer: Offer, standing: Offer) -> Offer:
    equity = max(persona.min_equity, offer.equity, standing.equity - persona.step)
    investment = min(persona.budget, offer.investment) // 10000 * 10000
    return Offer(investment, equity)


def aggregate(
    persona: Persona,
    offer: Offer,
    standing: Offer,
    *,
    turn: int,
    patience: int,
    choice: str,
    level: int,
    walk_away: bool,
    ethical_concern: bool,
    tone: str,
) -> Ruling:
    """RUL-03 R1-R6 over one decision turn.

    offer: the player's offer; standing: the investor's standing offer; turn: this decision
    turn, one-based; patience: before this turn's cost; choice: TECH reaction.choice (accept,
    counter or reject); level: TECH accept-score level; walk_away / ethical_concern: the
    Laya answers; tone: the Laya tone label.
    """
    reasons: list[str] = []
    result = standing
    if persona.veto and ethical_concern:  # R1
        outcome = "walk_away_moral"
        reasons.append("moral")
    elif walk_away:  # R2
        outcome = "walk_away_investor"
    elif choice == "accept":  # R3
        guards = [
            reason
            for reason, applies in (
                ("budget", offer.investment > persona.budget),
                ("equity_floor", offer.equity < persona.min_equity),
                ("inconsistent", level <= 1),
            )
            if applies
        ]
        if guards:
            outcome = "counter"
            result = counter_offer(persona, offer, standing)
            reasons.extend(guards)
        else:
            outcome = "deal"
            result = offer
    elif choice == "counter":  # R4
        outcome = "counter"
        result = counter_offer(persona, offer, standing)
    elif choice == "reject":  # R4
        outcome = "reject"
    else:
        raise ValueError(f"unknown reaction choice: {choice!r}")
    if tone == "rude":  # R5
        reasons.append("rude")
    if outcome in ("counter", "reject"):  # R5 and R6 cost, only if R1-R4 did not end the game
        patience -= 2 if tone == "rude" else 1
        if patience <= 0:
            outcome = "walk_away_patience"
            result = standing
            reasons.append("patience")
        elif turn >= MAX_TURNS:
            outcome = "max_turns"
            result = standing
    return Ruling(outcome, result, patience, tuple(reasons))


def deal_summary(offer: Offer) -> str:
    return (
        f"Условия сделки: {format_eur(offer.investment)} за {offer.equity}%. "
        f"Оценка компании после сделки: {format_eur(post_money(offer))}."
    )
