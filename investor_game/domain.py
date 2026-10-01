import re
import unicodedata
from dataclasses import dataclass

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b.", re.DOTALL)
_BLANKS = "\n\r\t"


def strip_control(text: str) -> str:
    """Drop ANSI sequences and control characters; newline, return and tab become a space."""
    text = _ANSI.sub("", text)
    return "".join(
        " " if ch in _BLANKS else "" if unicodedata.category(ch) == "Cc" else ch for ch in text
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Offer:
    investment: int
    equity: int

    def __post_init__(self) -> None:
        if not _is_int(self.investment) or not (
            self.investment % 10000 == 0 and 10000 <= self.investment <= 5000000
        ):
            raise ValueError(
                f"investment must be a multiple of 10000 in [10000, 5000000]: {self.investment!r}"
            )
        if not _is_int(self.equity) or not 1 <= self.equity <= 99:
            raise ValueError(f"equity must be an int in [1, 99]: {self.equity!r}")


@dataclass(frozen=True)
class Persona:
    name: str
    descriptor: str
    tone: str
    budget: int
    opening: Offer
    min_equity: int
    step: int
    patience: int
    veto: bool
    interest: float

    def __post_init__(self) -> None:
        if self.budget < 10000:
            raise ValueError(f"budget must be at least 10000: {self.budget!r}")


@dataclass(frozen=True)
class Startup:
    name: str
    description: str
    en: str
    valuation: int


PERSONAS = (
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

STARTUPS = (
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


def post_money(o: Offer) -> int:
    return o.investment * 100 // o.equity


def format_eur(a: int) -> str:
    if a < 1000000:
        return f"€{a // 1000}k"
    text = f"{a / 1000000:.2f}".removesuffix("0")
    return f"€{text}M"
