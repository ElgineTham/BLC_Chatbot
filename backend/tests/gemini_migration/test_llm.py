"""Spec 037 section 6.1: the Gemini builders (LLM-1 to LLM-6). Unit tests: env vars only, no network."""

from __future__ import annotations

import socket

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

import blc.llm as llm_mod
from blc.llm import (
    API_KEY_ENV,
    CHAT_MODEL,
    EMBED_DIM,
    EMBED_MODEL,
    MissingApiKeyError,
    build_chat_model,
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
    """Covers: AC-12 (right), LLM-6. Constants have the spec values."""
    assert API_KEY_ENV == "GOOGLE_API_KEY"
    assert CHAT_MODEL == "gemini-3.5-flash-lite"
    assert EMBED_MODEL == "gemini-embedding-2"
    assert EMBED_DIM == 768


def test_package_reexports_builders():
    """Covers: AC-1 (right). The names are exported from blc.llm and the error is a RuntimeError."""
    for name in ("build_chat_model", "build_embeddings", "MissingApiKeyError", "API_KEY_ENV"):
        assert hasattr(llm_mod, name)
    assert issubclass(MissingApiKeyError, RuntimeError)


def test_builders_return_models_with_key(monkeypatch, block_network):
    """Covers: AC-1 (right), LLM-1. With a key set, correct base types and no network call."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert isinstance(build_chat_model(), BaseChatModel)
    assert isinstance(build_embeddings(), Embeddings)


def test_chat_model_accepts_temperature(monkeypatch, block_network):
    """Covers: AC-1 (boundary). Explicit temperatures 0.0 and 0.1 build a model."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert isinstance(build_chat_model(temperature=0.0), BaseChatModel)
    assert isinstance(build_chat_model(temperature=0.1), BaseChatModel)


def test_one_character_key_is_enough(monkeypatch, block_network):
    """Covers: AC-1 (boundary). Any non-blank string is a valid key; the shortest is one character."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert isinstance(build_chat_model(), BaseChatModel)
    assert isinstance(build_embeddings(), Embeddings)


@pytest.mark.parametrize("builder", [build_chat_model, build_embeddings])
def test_unset_key_raises(no_key, builder):
    """Covers: AC-2 (wrong), LLM-2. Unset key: MissingApiKeyError naming GOOGLE_API_KEY."""
    with pytest.raises(MissingApiKeyError) as exc:
        builder()
    assert "GOOGLE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("builder", [build_chat_model, build_embeddings])
@pytest.mark.parametrize("blank", BLANKS)
def test_blank_key_raises(monkeypatch, no_key, builder, blank):
    """Covers: AC-2 (boundary), LLM-3. Empty and whitespace-only keys are rejected."""
    monkeypatch.setenv("GOOGLE_API_KEY", blank)
    with pytest.raises(MissingApiKeyError) as exc:
        builder()
    assert "GOOGLE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("builder", [build_chat_model, build_embeddings])
def test_dotenv_file_is_not_loaded(monkeypatch, no_key, tmp_path, builder):
    """Covers: AC-2 (wrong), LLM-4. A .env with a key in the cwd does not rescue an unset env var."""
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=from-dotenv-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MissingApiKeyError):
        builder()


@pytest.mark.parametrize("builder", [build_chat_model, build_embeddings])
def test_key_never_in_str_or_repr(monkeypatch, builder):
    """Covers: AC-3 (right), LLM-5. The key value is absent from str() and repr() of the built object."""
    secret = "sk-secret-123"
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    obj = builder()
    assert secret not in str(obj)
    assert secret not in repr(obj)


@pytest.mark.parametrize("builder", [build_chat_model, build_embeddings])
def test_missing_key_message_has_no_key_value(monkeypatch, builder):
    """Covers: AC-3 (wrong). An error for a whitespace key does not echo the key text."""
    monkeypatch.setenv("GOOGLE_API_KEY", "  \t  ")
    with pytest.raises(MissingApiKeyError) as exc:
        builder()
    assert "\t" not in str(exc.value)
