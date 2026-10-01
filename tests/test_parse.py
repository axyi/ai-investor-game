from investor_game.domain import Offer
from investor_game.parse import HINT, Move, parse_menu, parse_move


def test_t_v0_par_01_commands():
    accept = ["принять", "accept", "Принять", "ACCEPT", "  Accept  ", "\x1b[1maccept\x1b[0m"]
    reject = ["отказаться", "reject", "Отказаться", "REJECT"]
    quit_ = ["выход", "quit", "ВЫХОД", "Quit"]
    for line in accept:
        assert parse_move(line, 4).kind == "accept"
    for line in reject:
        assert parse_move(line, 4).kind == "reject"
    for line in quit_:
        assert parse_move(line, 4).kind == "quit"
    assert parse_move("accept", 4) == Move("accept", None, None, "accept")
    assert parse_move("  Принять \n", 4) == Move("accept", None, None, "Принять")
    # a command is a whole line only
    assert parse_move("accept please", 4).kind == "invalid"
    assert parse_move("принять!", 4).kind == "invalid"
    # numbers: one or two digits in 1..option_count
    assert parse_move("3", 4) == Move("option", 3, None, "3")
    assert parse_move("12", 12) == Move("option", 12, None, "12")
    assert parse_move(" 1 ", 4) == Move("option", 1, None, "1")
    # input is cut to 300 characters before it is stripped
    assert parse_move("accept" + " " * 400, 4).kind == "accept"
    assert parse_move(" " * 301 + "accept", 4).kind == "invalid"
    assert len(parse_move("a" * 400, 4).text) == 300
    # parse_menu: \d{1,2} in 1..count, else None
    assert parse_menu("2", 4) == 2
    assert parse_menu(" 4 ", 4) == 4
    assert parse_menu("0", 4) is None
    assert parse_menu("5", 4) is None
    assert parse_menu("123", 200) is None
    assert parse_menu("accept", 4) is None
    assert parse_menu("", 4) is None
    assert parse_menu("\x1b[1m3\x1b[0m", 4) == 3


def test_t_v0_par_02_offers():
    for amount in ["€600k", "600k", "600 000", "600000", "0.6M", "600 тыс"]:
        move = parse_move(f"{amount} за 20%", 3)
        assert move == Move("offer", None, Offer(600000, 20), f"{amount} за 20%"), amount
    assert parse_move("1,2 млн за 25%", 3).offer == Offer(1200000, 25)
    assert parse_move("1 200 000 за 25%", 3).offer == Offer(1200000, 25)
    assert parse_move("€1.5M за 10 %", 3).offer == Offer(1500000, 10)
    assert parse_move("600K за 20%", 3).offer == Offer(600000, 20)
    assert parse_move("0,6m за 20%", 3).offer == Offer(600000, 20)
    assert parse_move("600 k за 20%", 3).offer == Offer(600000, 20)
    # both orders
    assert parse_move("20% за €600k", 3).offer == Offer(600000, 20)
    assert parse_move("20% 600 000", 3).offer == Offer(600000, 20)
    assert parse_move("20 % for 0.6M", 3).offer == Offer(600000, 20)
    # each join: whitespace, `за`, `for`
    for join in [" ", " за ", " for "]:
        assert parse_move(f"€600k{join}20%", 3).offer == Offer(600000, 20), join
        assert parse_move(f"20%{join}€600k", 3).offer == Offer(600000, 20), join
    # text around the offer stays in the message; punctuation bounds the offer
    line = "Давайте €600k за 20%, это честно"
    assert parse_move(line, 3) == Move("offer", None, Offer(600000, 20), line)
    assert parse_move("(600k за 20%).", 3).offer == Offer(600000, 20)
    assert parse_move("Ок. 20% за 600k!", 3).offer == Offer(600000, 20)
    # input is cleaned before it is parsed
    assert parse_move("\x1b[1m600k за 20%\x1b[0m", 3).offer == Offer(600000, 20)


def test_t_v0_par_03_invalid():
    lines = [
        "",
        "   ",
        "дай денег",
        "600k",
        "20%",
        "600k за 20% или 500k за 25%",
        "20% за 600k за 25%",
        "605k за 20%",
        "600k за 0%",
        "600k за 100%",
        "600k за 120%",
        "6000k за 20%",
        "600.0005k за 20%",
        "5000 за 20%",
        "60000000 за 20%",
        "600kb за 20%",
        "600k за 20%a",
        "600m за 20%",
        "0 600k",
        "4",
        "0",
        "99",
    ]
    for line in lines:
        move = parse_move(line, 3)
        assert move.kind == "invalid", line
        assert move.index is None and move.offer is None, line
    assert parse_move("", 3) == Move("invalid", None, None, "")
    assert parse_move("дай денег", 3).text == "дай денег"
    assert HINT == (
        "Не понял ход. Введите номер, «принять», «отказаться», «выход» или «€600k за 20%»."
    )


def test_t_v0_par_04_option_bounds():
    for k in (2, 3):
        count = k + 2
        for bad in ("0", str(k + 3)):
            move = parse_move(bad, count)
            assert move.kind == "invalid", (k, bad)
            assert move.index is None
        for number in (1, k, k + 1, k + 2):
            move = parse_move(str(number), count)
            assert move == Move("option", number, None, str(number)), (k, number)
