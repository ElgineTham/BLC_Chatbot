"""Spec 037 section 6.1: the Gemini embeddings builder (LLM-1 to LLM-6). Unit tests: env vars only, no network.

Spec 039 (AC-14) moved the chat model to Claude; the chat-model builder tests live in tests/claude_chat/test_llm.py.
Only the embedding assertions stay here.
"""

from __future__ import annotations

import socket

import pytest
from langchain_core.embeddings import Embeddings

import blc.llm as llm_mod
from blc.llm import (
    API_KEY_ENV,
    EMBED_DIM,
    EMBED_MODEL,
    MissingApiKeyError,
    build_embeddings,
)

BLANKS = ["", " ", "   ", "\t", "\n  \t"]


@pytest.fixture
def block_network(monkeypatch):
    def _no(*a, **k):
        raise AssertionError("network access attempted while building a model")

    monkeypatch.setattr(socket.socket, "connect", _no)
    monkeypatch.setattr(socket, "create_connection", _no)
    monkeypatch.setattr(socket, "getaddrinfo", _no)


def test_constants_match_spec():
    """Covers: AC-12 (right), LLM-6. Embedding constants have the spec values."""
    assert API_KEY_ENV == "GOOGLE_API_KEY"
    assert EMBED_MODEL == "gemini-embedding-2"
    assert EMBED_DIM == 768


def test_package_reexports_builders():
    """Covers: AC-1 (right). The names are exported from blc.llm and the error is a RuntimeError."""
    for name in ("build_chat_model", "build_embeddings", "MissingApiKeyError", "API_KEY_ENV"):
        assert hasattr(llm_mod, name)
    assert issubclass(MissingApiKeyError, RuntimeError)


def test_embeddings_built_with_key(monkeypatch, block_network):
    """Covers: AC-1 (right), LLM-1. With a key set, an Embeddings object is built and no network call is made."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert isinstance(build_embeddings(), Embeddings)


def test_one_character_key_is_enough(monkeypatch, block_network):
    """Covers: AC-1 (boundary). Any non-blank string is a valid key; the shortest is one character."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert isinstance(build_embeddings(), Embeddings)


def test_unset_key_raises(no_key):
    """Covers: AC-2 (wrong), LLM-2. Unset key: MissingApiKeyError naming GOOGLE_API_KEY."""
    with pytest.raises(MissingApiKeyError) as exc:
        build_embeddings()
    assert "GOOGLE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("blank", BLANKS)
def test_blank_key_raises(monkeypatch, no_key, blank):
    """Covers: AC-2 (boundary), LLM-3. Empty and whitespace-only keys are rejected."""
    monkeypatch.setenv("GOOGLE_API_KEY", blank)
    with pytest.raises(MissingApiKeyError) as exc:
        build_embeddings()
    assert "GOOGLE_API_KEY" in str(exc.value)


def test_dotenv_file_is_not_loaded(monkeypatch, no_key, tmp_path):
    """Covers: AC-2 (wrong), LLM-4. A .env with a key in the cwd does not rescue an unset env var."""
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=from-dotenv-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MissingApiKeyError):
        build_embeddings()


def test_key_never_in_str_or_repr(monkeypatch):
    """Covers: AC-3 (right), LLM-5. The key value is absent from str() and repr() of the embeddings object."""
    secret = "sk-secret-123"
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    obj = build_embeddings()
    assert secret not in str(obj)
    assert secret not in repr(obj)


def test_missing_key_message_has_no_key_value(monkeypatch):
    """Covers: AC-3 (wrong). An error for a whitespace key does not echo the key text."""
    monkeypatch.setenv("GOOGLE_API_KEY", "  \t  ")
    with pytest.raises(MissingApiKeyError) as exc:
        build_embeddings()
    assert "\t" not in str(exc.value)
