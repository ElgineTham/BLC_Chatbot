"""Shared fixtures for spec 039 tests (chat on Claude Haiku). Unit tests use env vars, fakes and tmp_path only."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "backend" / "scripts"), str(ROOT / "backend" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_env():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover
        pass


@pytest.fixture
def block_network(monkeypatch):
    """Any attempt to open a socket or resolve a name fails the test."""

    def _no(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", _no)
    monkeypatch.setattr(socket, "create_connection", _no)
    monkeypatch.setattr(socket, "getaddrinfo", _no)


@pytest.fixture
def no_anthropic_key(monkeypatch):
    """ANTHROPIC_API_KEY unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def no_google_key(monkeypatch):
    """GOOGLE_API_KEY (and the library's alternative name) unset."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def live_anthropic_key():
    """Presence check for integration tests (AC-4: never returns a key value); loads .env; skips when absent."""
    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is not set")
    return True


@pytest.fixture
def live_both_keys(live_anthropic_key):
    """Presence check for both keys (never returns a key value); skips when either is missing."""
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set")
    return True
