import socket

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(self, address):
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
