import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MODULES = {
    "__main__",
    "chat",
    "config",
    "decision",
    "domain",
    "fakes",
    "game",
    "laya_model",
    "parse",
    "rules",
}

IMPORT_ALL = """
import importlib
import json
import pkgutil
import sys

import investor_game

names = sorted(m.name for m in pkgutil.iter_modules(investor_game.__path__))
for name in names:
    importlib.import_module("investor_game." + name)
leaked = [name for name in ("laya", "torch") if name in sys.modules]
print(json.dumps({"modules": names, "leaked": leaked}))
"""

ENV_EXAMPLE = [
    "CHAT_API_KEY=",
    "CHAT_MODEL=google/gemini-3.8-flash",
    "# CHAT_BASE_URL=https://openrouter.ai/api/v1",
    "# CHAT_TIMEOUT_S=30",
    "# CHAT_MAX_TOKENS=2000",
    "# CHAT_REASONING_EFFORT=low",
]


def test_t_v0_tst_01_offline():
    with socket.socket() as sock, pytest.raises(RuntimeError):
        sock.connect(("127.0.0.1", 9))
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_t_v0_tst_02_import_isolation():
    proc = subprocess.run(
        [sys.executable, "-c", IMPORT_ALL],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert set(report["modules"]) == MODULES
    assert report["leaked"] == []


def test_t_v0_sec_01_env_example():
    path = ROOT / ".env.example"
    assert path.is_file()
    assert path.read_text().splitlines() == ENV_EXAMPLE
