"""The command line: `python -m investor_game` (GAME-03)."""

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from investor_game.chat import HttpChatModel
from investor_game.config import ConfigError, load_config
from investor_game.decision import DecisionError, DecisionRunner, LoadError
from investor_game.domain import strip_control
from investor_game.fakes import SELFTEST_RESULT, SELFTEST_SCRIPT, FakeChatModel, FakeDecisionModel
from investor_game.game import check_result, play
from investor_game.laya_model import load_decision_model


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise _UsageError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m investor_game")
    parser.add_argument("--show-decisions", action="store_true", help="print each turn's decisions")
    parser.add_argument("--script", metavar="PATH", help="read the player's lines from PATH")
    parser.add_argument(
        "--check-result", action="store_true", help="check RESULT's invariants (needs --script)"
    )
    parser.add_argument("--selftest", action="store_true", help="play the self-test over fakes")
    return parser


def _print(line: str) -> None:
    print(line, flush=True)


def _print_err(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _stdin_line() -> str | None:
    try:
        return input("> ")
    except EOFError:
        return None


def _script_reader(lines: list[str], write: Callable[[str], None]) -> Callable[[], str | None]:
    """GAME-08: the script's lines, each echoed as `> {line}`; the end of the list is EOF."""
    feed = iter(lines)

    def read_line() -> str | None:
        line = next(feed, None)
        if line is not None:
            write(f"> {strip_control(line)}")
        return line

    return read_line


def _now() -> datetime:
    return datetime.now().astimezone()


def _selftest_reason(result: dict) -> str | None:
    """GAME-07: why RESULT differs from the expected one, None when it matches."""
    for key, expected in SELFTEST_RESULT.items():
        if result.get(key) != expected:
            got = json.dumps(result.get(key), ensure_ascii=False)
            return f"{key}: ожидалось {json.dumps(expected, ensure_ascii=False)}, получено {got}"
    return None


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    load_decision: Callable | None = None,
    make_chat: Callable | None = None,
    read_line: Callable[[], str | None] | None = None,
    write: Callable[[str], None] | None = None,
    err: Callable[[str], None] | None = None,
) -> int:
    write = _print if write is None else write
    err = _print_err if err is None else err
    try:
        args = _parser().parse_args(argv)
    except _UsageError as exc:
        err(f"Ошибка запуска: {exc}")
        return 2
    if args.check_result and args.script is None:
        err("Ошибка запуска: --check-result работает только вместе с --script")
        return 2
    if args.selftest:
        env = {}  # the self-test needs no environment
    try:
        config = load_config(os.environ if env is None else env, require_key=not args.selftest)
    except ConfigError as exc:
        err(str(exc))
        return 2
    lines = None
    if args.selftest:
        lines = SELFTEST_SCRIPT
    elif args.script is not None:
        try:
            lines = Path(args.script).read_text(encoding="utf-8").splitlines()
        except OSError, UnicodeError:
            err(f"Не удалось прочитать файл сценария: {args.script}")
            return 2

    write("=== ПЕРЕГОВОРЫ ===")
    write("Загрузка моделей…")
    if load_decision is None:
        load_decision = FakeDecisionModel if args.selftest else load_decision_model
    try:
        try:
            model = load_decision()
        except LoadError as exc:
            err(f"Ошибка загрузки моделей: {exc.args[0]}")
            err(f"laya_error={exc.category}")
            return 2
        if make_chat is None:
            make_chat = (lambda config: FakeChatModel()) if args.selftest else HttpChatModel
        runner = DecisionRunner(model)
        if lines is not None:
            read_line = _script_reader(lines, write)
        try:
            result = play(
                runner,
                make_chat(config),
                _stdin_line if read_line is None else read_line,
                write,
                err,
                show_decisions=args.show_decisions,
                now=_now,
            )
        finally:
            runner.close()
    except KeyboardInterrupt:
        write("Игра прервана")
        return 130
    except DecisionError as exc:
        err(f"Ошибка модели решений: {exc.args[0]}")
        err(f"laya_error={exc.category}")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(3)  # worker threads may still sit in predict: a normal exit would join them

    verdict, status = None, 0
    if args.selftest:
        reason = _selftest_reason(result)
        verdict, status = (
            ("SELFTEST OK", 0) if reason is None else (f"SELFTEST FAILED: {reason}", 4)
        )
    elif args.check_result:
        status, name = check_result(result, 0)
        verdict = None if name is None else f"RESULT не прошёл проверку: {name}"
    if verdict is not None:
        write(verdict)
    write("RESULT " + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
