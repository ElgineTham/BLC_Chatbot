"""Spec 039 section 6.2 (ENTRY-1 to ENTRY-3): entry points with a missing Anthropic or Google key."""

from __future__ import annotations

import builtins
import sys

import pytest
from cc_helpers import fake_embeddings, seed_persisted

import chat
import ingest


def _run(name):
    if name == "chat":
        return chat.main()
    if name == "web":
        import web

        return web.main([])
    raise ValueError(name)


CHAT_ENTRY_POINTS = ["chat", "web"]


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """A stamped store, no stdin, no server: only a missing key can stop main() with a message."""
    monkeypatch.setattr(sys, "argv", ["entry.py"])

    def no_input(*a, **k):
        raise AssertionError("input() must not be read")

    def no_server(*a, **k):
        raise AssertionError("the server must not be started")

    monkeypatch.setattr(builtins, "input", no_input)
    monkeypatch.setattr("uvicorn.run", no_server)
    monkeypatch.setattr(chat, "load_catalog", lambda *a, **k: object(), raising=False)
    persist = tmp_path / "chroma_ok"
    seed_persisted(persist, chat.EMBED_MODEL)
    monkeypatch.setattr(chat, "CHROMA_DIR", persist)
    monkeypatch.setattr(chat, "build_embeddings", lambda *a, **k: fake_embeddings())


@pytest.fixture
def anthropic_missing(monkeypatch, offline):
    def boom(*a, **k):
        raise chat.MissingApiKeyError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(chat, "build_chat_model", boom)


@pytest.fixture
def google_missing(monkeypatch, offline):
    def boom(*a, **k):
        raise chat.MissingApiKeyError("GOOGLE_API_KEY is not set")

    monkeypatch.setattr(chat, "build_chat_model", lambda *a, **k: object())
    monkeypatch.setattr(chat, "build_embeddings", boom)


# ---- ENTRY-1 / AC-6

@pytest.mark.parametrize("name", CHAT_ENTRY_POINTS)
def test_missing_anthropic_key_returns_1_without_traceback(name, anthropic_missing, capsys):
    """Covers: AC-6 (wrong), ENTRY-1. MissingApiKeyError for the chat key: return 1, stderr names
    ANTHROPIC_API_KEY, no traceback; input() and the server are patched to fail the test."""
    rc = _run(name)
    err = capsys.readouterr().err
    assert rc == 1
    assert "ANTHROPIC_API_KEY" in err
    assert "Traceback" not in err


# ---- ENTRY-2 / AC-6

@pytest.mark.parametrize("name", CHAT_ENTRY_POINTS)
def test_missing_google_key_returns_1_without_traceback(name, google_missing, capsys):
    """Covers: AC-6 (wrong), ENTRY-2. Spec 037 behaviour kept: embeddings raise for the Google key ->
    return 1, stderr names GOOGLE_API_KEY, no traceback."""
    rc = _run(name)
    err = capsys.readouterr().err
    assert rc == 1
    assert "GOOGLE_API_KEY" in err
    assert "Traceback" not in err


def test_matching_store_and_keys_start_normally(monkeypatch, offline, capsys):
    """Covers: AC-6 (right). With both models building and a stamped store, chat.main() starts and returns 0
    when stdin hits EOF; stderr names neither key."""
    monkeypatch.setattr(chat, "build_chat_model", lambda *a, **k: object())

    def eof(*a, **k):
        raise EOFError

    monkeypatch.setattr(builtins, "input", eof)
    assert chat.main() == 0
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" not in err
    assert "GOOGLE_API_KEY" not in err


# ---- ENTRY-3 / AC-7

def test_ingest_needs_only_google_key(monkeypatch, tmp_path, capsys):
    """Covers: AC-7 (right), ENTRY-3. GOOGLE_API_KEY set, ANTHROPIC_API_KEY unset, fake embeddings: ingest.main()
    returns 0, the store is filled, and nothing printed mentions ANTHROPIC_API_KEY."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["ingest.py"])
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.md").write_text(
        "Coffee service notes. The urn is kept in the back kitchen next to the cream.", encoding="utf-8"
    )
    persist = tmp_path / "ingest_chroma"
    monkeypatch.setattr(ingest, "DATA_DIR", data, raising=False)
    monkeypatch.setattr(ingest, "CHROMA_DIR", persist, raising=False)
    monkeypatch.setattr(ingest, "build_embeddings", lambda *a, **k: fake_embeddings())
    rc = ingest.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "ANTHROPIC_API_KEY" not in captured.err
    assert "ANTHROPIC_API_KEY" not in captured.out
    assert persist.exists() and any(persist.iterdir())
