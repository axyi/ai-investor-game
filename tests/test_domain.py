import pytest

from investor_game.domain import (
    PERSONAS,
    STARTUPS,
    Offer,
    Persona,
    Startup,
    format_eur,
    post_money,
    strip_control,
)


def test_t_v0_dom_01_tables():
    assert PERSONAS == (
        Persona(
            name="Жадный",
            descriptor="greedy investor who bargains hard",
            tone="торгуется за каждый процент",
            budget=700000,
            opening=Offer(500000, 35),
            min_equity=25,
            step=2,
            patience=4,
            veto=False,
            interest=0.65,
        ),
        Persona(
            name="Щедрый",
            descriptor="generous friendly investor",
            tone="дружелюбный, ободряющий",
            budget=900000,
            opening=Offer(600000, 25),
            min_equity=12,
            step=4,
            patience=5,
            veto=True,
            interest=0.85,
        ),
        Persona(
            name="Грубый",
            descriptor="blunt impatient investor",
            tone="грубоватый и нетерпеливый, без оскорблений",
            budget=600000,
            opening=Offer(400000, 40),
            min_equity=28,
            step=3,
            patience=3,
            veto=True,
            interest=0.55,
        ),
        Persona(
            name="Осторожный",
            descriptor="cautious investor who checks every detail",
            tone="вежливый, задаёт уточняющие вопросы",
            budget=500000,
            opening=Offer(300000, 30),
            min_equity=20,
            step=2,
            patience=5,
            veto=True,
            interest=0.70,
        ),
    )
    assert STARTUPS == (
        Startup(
            name="Репетитор-ИИ",
            description="ИИ-репетитор для школьников",
            en="An AI tutoring app for school students",
            valuation=2000000,
        ),
        Startup(
            name="СолнцеГрид",
            description="домашние аккумуляторы для солнечных панелей",
            en="Home battery storage for rooftop solar panels",
            valuation=2500000,
        ),
        Startup(
            name="Оборонзавод",
            description="завод боеприпасов и ударных дронов",
            en="A factory producing munitions and attack drones",
            valuation=3000000,
        ),
    )


def test_t_v0_dom_02_offer():
    bad = [
        (5000, 20),
        (5010000, 20),
        (605000, 20),
        (500000, 0),
        (500000, 100),
        (500000, True),
        (True, 20),
        (500000.0, 20),
        (500000, 20.0),
    ]
    for investment, equity in bad:
        with pytest.raises(ValueError):
            Offer(investment, equity)
    assert Offer(10000, 1).investment == 10000
    assert Offer(5000000, 99).equity == 99
    assert post_money(Offer(500000, 25)) == 2000000
    assert post_money(Offer(500000, 30)) == 1666666


def test_t_v0_dom_03_format_eur():
    pinned = {
        500000: "€500k",
        999999: "€999k",
        2000000: "€2.0M",
        2500000: "€2.5M",
        1250000: "€1.25M",
        1666666: "€1.67M",
    }
    for amount, text in pinned.items():
        assert format_eur(amount) == text


def test_t_v0_sec_02_strip_control():
    assert strip_control("\x1b[31mRED\x1b[0m") == "RED"
    assert strip_control("a\x07b") == "ab"
    assert strip_control("a\nb") == "a b"
    assert strip_control("a\r\tb") == "a  b"
    assert strip_control("\x1bXa") == "a"
    assert strip_control("ok \x1b[1;32m€600k\x1b[0m за 20%") == "ok €600k за 20%"
