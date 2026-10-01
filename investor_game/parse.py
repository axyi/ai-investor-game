import re
from dataclasses import dataclass
from decimal import Decimal

from investor_game.domain import Offer, strip_control

HINT = "Не понял ход. Введите номер, «принять», «отказаться», «выход» или «€600k за 20%»."

_COMMANDS = {
    "принять": "accept",
    "accept": "accept",
    "отказаться": "reject",
    "reject": "reject",
    "выход": "quit",
    "quit": "quit",
}
_MULTIPLIERS = {"k": 1000, "K": 1000, "тыс": 1000, "M": 1000000, "m": 1000000, "млн": 1000000}

_NUMBER = r"\d{1,2}"
_UNIT = r"(?:k|K|M|m|млн|тыс)"
_AMOUNT = rf"€?(?:\d+(?:[.,]\d+)? ?{_UNIT}|\d{{1,3}}(?: \d{{3}})+|\d{{4,7}})"
_PERCENT = r"\d{1,2}\s?%"
_JOIN = r"\s+(?:(?:за|for)\s+)?"
# The pair is bounded by line ends, whitespace or punctuation: no word character on either side.
_AMOUNT_PERCENT = re.compile(rf"(?<!\w)(?P<amount>{_AMOUNT}){_JOIN}(?P<percent>{_PERCENT})(?!\w)")
_PERCENT_AMOUNT = re.compile(rf"(?<!\w)(?P<percent>{_PERCENT}){_JOIN}(?P<amount>{_AMOUNT})(?!\w)")
_UNIT_AMOUNT = re.compile(rf"€?(\d+(?:[.,]\d+)?) ?({_UNIT})")


@dataclass(frozen=True)
class Move:
    kind: str  # accept | reject | quit | option | offer | invalid
    index: int | None = None  # one-based option number, kind "option" only
    offer: Offer | None = None  # kind "offer" only
    text: str = ""  # the cleaned input line


def _clean(line: str) -> str:
    return strip_control(line)[:300].strip()


def _number(text: str, count: int) -> int | None:
    if re.fullmatch(_NUMBER, text) and 1 <= int(text) <= count:
        return int(text)
    return None


def _amount(text: str) -> int | None:
    unit = _UNIT_AMOUNT.fullmatch(text)
    if unit:
        value = Decimal(unit.group(1).replace(",", ".")) * _MULTIPLIERS[unit.group(2)]
    else:
        value = Decimal(re.sub(r"[€ ]", "", text))
    return int(value) if value == value.to_integral_value() else None


def _offer(text: str) -> Offer | None:
    spans = {}
    for start in range(len(text)):
        for pattern in (_AMOUNT_PERCENT, _PERCENT_AMOUNT):
            match = pattern.match(text, start)
            if match:
                spans[match.span()] = match
    # a match inside a longer one ("200 000" in "1 200 000") is the same offer
    outer = [
        m
        for (start, end), m in spans.items()
        if not any(s <= start and end <= e and (s, e) != (start, end) for s, e in spans)
    ]
    if len(outer) != 1:
        return None
    amount = _amount(outer[0].group("amount"))
    if amount is None:
        return None
    equity = int(re.sub(r"\D", "", outer[0].group("percent")))
    try:
        return Offer(amount, equity)
    except ValueError:
        return None


def parse_menu(line: str, count: int) -> int | None:
    return _number(_clean(line), count)


def parse_move(line: str, option_count: int) -> Move:
    text = _clean(line)
    command = _COMMANDS.get(text.casefold())
    if command:
        return Move(command, None, None, text)
    if re.fullmatch(_NUMBER, text):
        index = _number(text, option_count)
        return Move("option", index, None, text) if index else Move("invalid", None, None, text)
    offer = _offer(text)
    if offer:
        return Move("offer", None, offer, text)
    return Move("invalid", None, None, text)
