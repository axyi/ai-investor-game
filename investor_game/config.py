from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.8-flash"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_TOKENS = 2000
DEFAULT_REASONING_EFFORT = "low"


class ConfigError(Exception):
    """A configuration the game cannot start with.

    str(exc) is the finished ERR-01 row 1 / row 2 line (Russian, no secret, no value):
    `main` writes it to `err` as it is and exits 2.
    """


@dataclass(frozen=True)
class Config:
    """The chat settings; reasoning_effort "" means no `reasoning` field in the request."""

    api_key: str = field(repr=False)
    base_url: str
    model: str
    timeout_s: float
    max_tokens: int
    reasoning_effort: str


def _bad(name: str) -> ConfigError:
    return ConfigError(f"Ошибка конфигурации: неверное значение переменной {name}")


def _timeout(env: Mapping[str, str]) -> float:
    raw = env.get("CHAT_TIMEOUT_S")
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        raise _bad("CHAT_TIMEOUT_S") from None
    if not value > 0:
        raise _bad("CHAT_TIMEOUT_S")
    return value


def _max_tokens(env: Mapping[str, str]) -> int:
    raw = env.get("CHAT_MAX_TOKENS")
    if not raw:
        return DEFAULT_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        raise _bad("CHAT_MAX_TOKENS") from None
    if not value >= 1:
        raise _bad("CHAT_MAX_TOKENS")
    return value


def load_config(env: Mapping[str, str], *, require_key: bool = True) -> Config:
    """Read the CHAT_* variables from `env` (CHAT-01); raises ConfigError."""
    api_key = env.get("CHAT_API_KEY") or ""
    if require_key and not api_key:
        raise ConfigError("Ошибка конфигурации: не задана переменная CHAT_API_KEY")
    return Config(
        api_key=api_key,
        base_url=env.get("CHAT_BASE_URL") or DEFAULT_BASE_URL,
        model=env.get("CHAT_MODEL") or DEFAULT_MODEL,
        timeout_s=_timeout(env),
        max_tokens=_max_tokens(env),
        reasoning_effort=env.get("CHAT_REASONING_EFFORT", DEFAULT_REASONING_EFFORT),
    )
