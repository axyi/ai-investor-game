from dataclasses import replace

import pytest

from investor_game.domain import PERSONAS, STARTUPS, Offer
from investor_game.rules import (
    MAX_TURNS,
    OUTCOME_LINES,
    REJECT_HINT,
    aggregate,
    counter_offer,
    deal_summary,
    facts,
    offer_entry,
    opening_entry,
    recent,
    repeat_entry,
)

GREEDY, GENEROUS, BLUNT, CAUTIOUS = PERSONAS
STANDING = Offer(500000, 35)
PLAYER = Offer(500000, 30)


def run(persona=GREEDY, offer=PLAYER, standing=STANDING, **changes):
    args = {
        "turn": 1,
        "patience": persona.patience,
        "choice": "reject",
        "level": 3,
        "walk_away": False,
        "ethical_concern": False,
        "tone": "neutral",
    }
    args.update(changes)
    return aggregate(persona, offer, standing, **args)


def test_t_v0_rul_01_facts():
    got = facts(Offer(500000, 20), Offer(500000, 33), GREEDY, STARTUPS[0], 1)
    assert got == [
        "The requested investment is within the investor's budget.",
        "The offered equity 20% is far below the investor's current ask of 33%.",
        "The offered equity is below the investor's minimum of 25%.",
        "The implied post-money valuation €2.5M is above the startup's valuation of €2.0M.",
        "Rounds of patience left: 1.",
    ]
    startup = STARTUPS[0]
    s = Offer(500000, 33)
    # fact 1: budget
    assert facts(Offer(700000, 30), s, GREEDY, startup, 4)[0] == (
        "The requested investment is within the investor's budget."
    )
    assert facts(Offer(710000, 30), s, GREEDY, startup, 4)[0] == (
        "The requested investment exceeds the investor's budget."
    )
    # fact 2: equity against the standing ask (step 2: close to is >= 31)
    ask = "the investor's current ask of 33%."
    assert facts(Offer(500000, 35), s, GREEDY, startup, 4)[1] == (
        f"The offered equity 35% is at or above {ask}"
    )
    assert facts(Offer(500000, 33), s, GREEDY, startup, 4)[1] == (
        f"The offered equity 33% is at or above {ask}"
    )
    assert facts(Offer(500000, 31), s, GREEDY, startup, 4)[1] == (
        f"The offered equity 31% is close to {ask}"
    )
    assert facts(Offer(500000, 30), s, GREEDY, startup, 4)[1] == (
        f"The offered equity 30% is far below {ask}"
    )
    # fact 3: minimum equity (is below iff o.equity < p.min_equity)
    assert facts(Offer(500000, 25), s, GREEDY, startup, 4)[2] == (
        "The offered equity meets the investor's minimum of 25%."
    )
    assert facts(Offer(500000, 24), s, GREEDY, startup, 4)[2] == (
        "The offered equity is below the investor's minimum of 25%."
    )
    # fact 4: post-money against the valuation (near iff 10 * |V - S| <= S)
    valuation = "the startup's valuation of €2.0M."
    assert facts(Offer(500000, 25), s, GREEDY, startup, 4)[3] == (
        f"The implied post-money valuation €2.0M is near {valuation}"
    )
    assert facts(Offer(440000, 20), s, GREEDY, startup, 4)[3] == (
        f"The implied post-money valuation €2.2M is near {valuation}"
    )
    assert facts(Offer(450000, 20), s, GREEDY, startup, 4)[3] == (
        f"The implied post-money valuation €2.25M is above {valuation}"
    )
    assert facts(Offer(450000, 25), s, GREEDY, startup, 4)[3] == (
        f"The implied post-money valuation €1.8M is near {valuation}"
    )
    assert facts(Offer(500000, 30), s, GREEDY, startup, 4)[3] == (
        f"The implied post-money valuation €1.67M is below {valuation}"
    )
    # fact 5: patience before this turn's cost
    assert facts(Offer(500000, 30), s, GREEDY, startup, 4)[4] == "Rounds of patience left: 4."


def test_t_v0_rul_02_history():
    history = [opening_entry(GREEDY)]
    assert history == ["Round 0: investor offered €500k for 35%"]
    player = Offer(500000, 20)
    history.append(offer_entry(1, player, Offer(500000, 33), countered=True))
    history.append(offer_entry(2, player, Offer(500000, 33), countered=False))
    history.append(repeat_entry(3, player))
    assert history == [
        "Round 0: investor offered €500k for 35%",
        "Round 1: player offered €500k for 20%; investor countered €500k for 33%",
        "Round 2: player offered €500k for 20%; investor kept €500k for 33%",
        "Round 3: player repeated the offer of €500k for 20%",
    ]
    # a reject turn's repeat entry is that round's only entry
    assert [e for e in history if e.startswith("Round 3:")] == [history[3]]
    assert not any("Player rejected" in e for e in history)
    history.append(offer_entry(4, Offer(600000, 25), Offer(600000, 30), countered=True))
    history.append(offer_entry(5, Offer(600000, 28), Offer(600000, 30), countered=False))
    # states and chat get the last 4
    assert recent(history) == history[-4:]
    assert recent(history)[0].startswith("Round 2:")
    assert recent(history[:2]) == history[:2]


def test_t_v0_rul_03_r1():
    standing = STANDING
    got = run(GENEROUS, choice="accept", ethical_concern=True)
    assert got.outcome == "walk_away_moral"
    assert got.reasons == ("moral",)
    assert got.ended
    assert got.patience == GENEROUS.patience
    assert got.offer == standing
    # a persona without a veto does not walk away on its own ethical concern
    got = run(GREEDY, choice="accept", ethical_concern=True)
    assert got.outcome == "deal"
    assert got.reasons == ()
    got = run(GREEDY, choice="reject", ethical_concern=True)
    assert got.outcome == "reject"
    assert got.reasons == ()
    # a veto persona with no concern is not touched
    assert run(GENEROUS, choice="reject").outcome == "reject"
    assert run(GENEROUS, choice="reject").reasons == ()


def test_t_v0_rul_04_r2():
    got = run(GREEDY, choice="accept", walk_away=True)
    assert got.outcome == "walk_away_investor"
    assert got.reasons == ()
    assert got.ended
    assert got.patience == GREEDY.patience
    assert got.offer == STANDING
    # R1 runs first
    assert run(GENEROUS, walk_away=True, ethical_concern=True).outcome == "walk_away_moral"
    assert run(GREEDY, choice="reject", walk_away=False).outcome == "reject"


def test_t_v0_rul_05_r3():
    # each reason alone: the guard turns an accept into a counter-offer
    got = run(GREEDY, Offer(800000, 30), choice="accept", level=3)
    assert (got.outcome, got.reasons) == ("counter", ("budget",))
    assert got.offer == Offer(700000, 33)
    assert got.patience == GREEDY.patience - 1
    assert not got.ended
    got = run(GREEDY, Offer(500000, 20), choice="accept", level=3)
    assert (got.outcome, got.reasons) == ("counter", ("equity_floor",))
    assert got.offer == Offer(500000, 33)
    for level in (0, 1):
        got = run(GREEDY, Offer(500000, 30), choice="accept", level=level)
        assert (got.outcome, got.reasons) == ("counter", ("inconsistent",)), level
        assert got.offer == Offer(500000, 33)
    # no guard applies: a deal on the player's terms
    got = run(GREEDY, Offer(500000, 30), choice="accept", level=2)
    assert (got.outcome, got.reasons) == ("deal", ())
    assert got.offer == Offer(500000, 30)
    assert got.ended
    assert got.patience == GREEDY.patience
    # every applicable reason, in order
    got = run(GREEDY, Offer(800000, 20), choice="accept", level=1)
    assert got.reasons == ("budget", "equity_floor", "inconsistent")
    assert got.offer == Offer(700000, 33)
    # the guards read the accept-score only on a Laya accept
    got = run(GREEDY, Offer(800000, 20), choice="reject", level=0)
    assert (got.outcome, got.reasons) == ("reject", ())


def test_t_v0_rul_06_r4():
    offer = Offer(600000, 30)
    got = run(GREEDY, offer, choice="counter")
    assert (got.outcome, got.reasons) == ("counter", ())
    assert got.offer == counter_offer(GREEDY, offer, STANDING) == Offer(600000, 33)
    assert got.patience == GREEDY.patience - 1
    assert not got.ended
    got = run(GREEDY, offer, choice="reject")
    assert (got.outcome, got.reasons) == ("reject", ())
    assert got.offer == STANDING
    assert got.patience == GREEDY.patience - 1
    assert not got.ended
    with pytest.raises(ValueError):
        run(GREEDY, offer, choice="maybe")


def test_t_v0_rul_07_r5():
    got = run(CAUTIOUS, choice="reject", tone="rude")
    assert (got.outcome, got.reasons) == ("reject", ("rude",))
    assert got.patience == CAUTIOUS.patience - 2
    got = run(CAUTIOUS, choice="reject", tone="polite")
    assert got.reasons == ()
    assert got.patience == CAUTIOUS.patience - 1
    # a counter-offer's reasons come before `rude`
    got = run(GREEDY, Offer(800000, 30), choice="accept", tone="rude")
    assert (got.outcome, got.reasons) == ("counter", ("budget", "rude"))
    assert got.patience == GREEDY.patience - 2
    # rude on a turn R1, R2 or R3 ends: reason `rude`, patience unchanged
    got = run(GENEROUS, choice="accept", ethical_concern=True, tone="rude")
    assert (got.outcome, got.reasons) == ("walk_away_moral", ("moral", "rude"))
    assert got.patience == GENEROUS.patience
    got = run(GREEDY, choice="accept", walk_away=True, tone="rude")
    assert (got.outcome, got.reasons) == ("walk_away_investor", ("rude",))
    assert got.patience == GREEDY.patience
    got = run(GREEDY, Offer(500000, 30), choice="accept", level=3, tone="rude")
    assert (got.outcome, got.reasons) == ("deal", ("rude",))
    assert got.patience == GREEDY.patience


def test_t_v0_rul_08_r6():
    # patience reaching 0 ends the game
    got = run(GREEDY, choice="reject", patience=2)
    assert (got.outcome, got.patience) == ("reject", 1)
    got = run(GREEDY, choice="reject", patience=1)
    assert (got.outcome, got.reasons, got.patience) == ("walk_away_patience", ("patience",), 0)
    assert got.ended
    # rude costs two: 3 -> 1 goes on, 2 -> 0 ends with both reasons
    assert run(GREEDY, tone="rude", patience=3).outcome == "reject"
    got = run(GREEDY, tone="rude", patience=2)
    assert (got.outcome, got.reasons, got.patience) == (
        "walk_away_patience",
        ("rude", "patience"),
        0,
    )
    # persona 1 (patience 4) runs out on its 4th non-deal turn
    patience = GREEDY.patience
    for turn in range(1, 5):
        got = run(GREEDY, turn=turn, patience=patience)
        patience = got.patience
        assert got.ended == (turn == 4), turn
    assert got.outcome == "walk_away_patience"
    # a test-only persona with patience 20: turn 9 goes on, turn 10 is max_turns
    assert MAX_TURNS == 10
    patient = replace(GREEDY, patience=20)
    patience = patient.patience
    for turn in range(1, MAX_TURNS):
        got = run(patient, turn=turn, patience=patience)
        assert not got.ended, turn
        patience = got.patience
    assert patience == 11
    got = run(patient, turn=MAX_TURNS, patience=patience)
    assert (got.outcome, got.reasons, got.patience) == ("max_turns", (), 10)
    assert got.offer == STANDING
    assert got.ended
    # running out of patience wins over the turn cap
    assert run(patient, turn=MAX_TURNS, patience=1).outcome == "walk_away_patience"


def test_t_v0_rul_09_counter_offer():
    assert counter_offer(GREEDY, Offer(500000, 20), STANDING) == Offer(500000, 33)
    assert counter_offer(GREEDY, Offer(900000, 40), STANDING) == Offer(700000, 40)
    # equity is the largest of the minimum, the player's ask and the standing ask minus a step
    assert counter_offer(GREEDY, Offer(500000, 10), Offer(500000, 27)) == Offer(500000, 25)
    assert counter_offer(GREEDY, Offer(500000, 30), Offer(500000, 27)) == Offer(500000, 30)
    assert counter_offer(GENEROUS, Offer(600000, 5), Offer(600000, 25)) == Offer(600000, 21)


def test_t_v0_rul_10_outcome_lines():
    assert OUTCOME_LINES == {
        "deal": "Итог: сделка заключена.",
        "walk_away_moral": "Итог: инвестор отказался по этическим соображениям.",
        "walk_away_investor": "Итог: инвестор прекратил переговоры.",
        "walk_away_patience": "Итог: у инвестора закончилось терпение.",
        "max_turns": "Итог: лимит ходов, сделки нет.",
        "player_quit": "Итог: вы вышли из переговоров.",
    }
    assert deal_summary(Offer(500000, 30)) == (
        "Условия сделки: €500k за 30%. Оценка компании после сделки: €1.67M."
    )
    assert REJECT_HINT == "Сначала сделайте своё предложение или примите предложение инвестора."


def test_t_v0_rul_11_counter_floor():
    persona = replace(GREEDY, budget=655000)
    assert counter_offer(persona, Offer(900000, 40), STANDING) == Offer(650000, 40)
    with pytest.raises(ValueError):
        replace(GREEDY, budget=9999)
    assert replace(GREEDY, budget=10000).budget == 10000
