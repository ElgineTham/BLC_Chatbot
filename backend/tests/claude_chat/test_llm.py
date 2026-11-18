"""Spec 039 section 6.1 (LLM-1 to LLM-7): the Claude chat builder and the unchanged embeddings builder.
Unit tests: env vars only, no network."""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

import blc.llm as llm_mod
from blc.llm import (
    API_KEY_ENV,
    CHAT_API_KEY_ENV,
    CHAT_MODEL,
    EMBED_DIM,
    EMBED_MODEL,
    MissingApiKeyError,
    build_chat_model,
    build_embeddings,
)

BLANKS = ["", " ", "   ", "\t", "\n  \t"]


# ---- LLM-1 / AC-1

def test_chat_model_is_chat_anthropic_without_google_key(monkeypatch, no_google_key, block_network):
    """Covers: AC-1 (right), LLM-1. Anthropic key set, Google key unset: a ChatAnthropic, no network call."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-a")
    model = build_chat_model()
    assert isinstance(model, ChatAnthropic)
    assert isinstance(model, BaseChatModel)


def test_one_character_key_is_enough(monkeypatch, no_google_key, block_network):
    """Covers: AC-1 (boundary), LLM-1. Any non-blank string is a valid key; the shortest is one character."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(build_chat_model(), ChatAnthropic)


# ---- LLM-2 / AC-1

def test_temperature_is_applied(monkeypatch, block_network):
    """Covers: AC-1 (right), LLM-2. build_chat_model(temperature=0.1) has temperature 0.1."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-a")
    assert build_chat_model(temperature=0.1).temperature == pytest.approx(0.1)


def test_temperature_zero_is_applied(monkeypatch, block_network):
    """Covers: AC-1 (boundary), LLM-2. Temperature 0.0 (also the default) is kept as 0.0, not dropped."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-a")
    assert build_chat_model(temperature=0.0).temperature == 0.0
    assert build_chat_model().temperature == 0.0


# ---- LLM-3 / AC-2

def test_unset_anthropic_key_raises(monkeypatch, no_anthropic_key):
    """Covers: AC-2 (wrong), LLM-3. Unset Anthropic key, Google key set: MissingApiKeyError naming it."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    with pytest.raises(MissingApiKeyError) as exc:
        build_chat_model()
    assert "ANTHROPIC_API_KEY" in str(exc.value)


@pytest.mark.parametrize("blank", BLANKS)
def test_blank_anthropic_key_raises(monkeypatch, blank):
    """Covers: AC-2 (boundary), LLM-3. Empty and whitespace-only keys are rejected, Google key set."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", blank)
    with pytest.raises(MissingApiKeyError) as exc:
        build_chat_model()
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_google_key_does_not_rescue_missing_anthropic_key(monkeypatch, no_anthropic_key):
    """Covers: AC-2 (wrong). A set Google key (and the alternative GEMINI_API_KEY) is no substitute."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    monkeypatch.setenv("GEMINI_API_KEY", "test-g")
    with pytest.raises(MissingApiKeyError):
        build_chat_model()


# ---- LLM-4 / AC-2

def test_dotenv_file_is_not_loaded(monkeypatch, no_anthropic_key, tmp_path):
    """Covers: AC-2 (wrong), LLM-4. A .env in the cwd holding the key does not rescue an unset env var."""
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-dotenv-file\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MissingApiKeyError):
        build_chat_model()


# ---- LLM-5 / AC-3

def test_embeddings_work_without_anthropic_key(monkeypatch, no_anthropic_key, block_network):
    """Covers: AC-3 (right), LLM-5. Google key set, Anthropic key unset: build_embeddings succeeds, no network."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-g")
    assert isinstance(build_embeddings(), Embeddings)


@pytest.mark.parametrize("blank", BLANKS)
def test_embeddings_still_reject_blank_google_key(monkeypatch, no_anthropic_key, blank):
    """Covers: AC-3 (boundary), LLM-5. Spec 037 still holds: blank Google key raises, naming GOOGLE_API_KEY."""
    monkeypatch.setenv("GOOGLE_API_KEY", blank)
    with pytest.raises(MissingApiKeyError) as exc:
        build_embeddings()
    assert "GOOGLE_API_KEY" in str(exc.value)


def test_embeddings_missing_google_key_with_anthropic_set(monkeypatch, no_google_key):
    """Covers: AC-3 (wrong). An Anthropic key does not stand in for the Google key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-a")
    with pytest.raises(MissingApiKeyError) as exc:
        build_embeddings()
    assert "GOOGLE_API_KEY" in str(exc.value)


# ---- LLM-6 / AC-4

def test_anthropic_key_not_in_str_or_repr(monkeypatch):
    """Covers: AC-4 (right), LLM-6. The key value is absent from str() and repr() of the chat model."""
    secret = "sk-ant-secret-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    model = build_chat_model()
    assert secret not in str(model)
    assert secret not in repr(model)


def test_error_messages_never_contain_a_key_value(monkeypatch):
    """Covers: AC-4 (wrong), LLM-6. No MissingApiKeyError message contains a key value, whether the
    chat key is whitespace or the other key is a secret."""
    secret = "sk-ant-secret-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("GOOGLE_API_KEY", "   ")
    with pytest.raises(MissingApiKeyError) as exc_embed:
        build_embeddings()
    assert secret not in str(exc_embed.value)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "  \t  ")
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google-secret-456")
    with pytest.raises(MissingApiKeyError) as exc_chat:
        build_chat_model()
    assert "sk-google-secret-456" not in str(exc_chat.value)
    assert "\t" not in str(exc_chat.value)


# ---- LLM-7 / AC-5

def test_blc_llm_constants():
    """Covers: AC-5 (right), LLM-7. Constants in blc.llm equal the spec values."""
    assert CHAT_API_KEY_ENV == "ANTHROPIC_API_KEY"
    assert CHAT_MODEL == "claude-haiku-4-5"
    assert API_KEY_ENV == "GOOGLE_API_KEY"
    assert EMBED_MODEL == "gemini-embedding-2"
    assert EMBED_DIM == 768


def test_chat_entry_point_constants():
    """Covers: AC-5 (right), LLM-7. The names are importable from chat with the same values."""
    import chat

    assert chat.CHAT_API_KEY_ENV == "ANTHROPIC_API_KEY"
    assert chat.CHAT_MODEL == "claude-haiku-4-5"
    assert chat.EMBED_MODEL == "gemini-embedding-2"


def test_chat_model_is_not_the_old_gemini_model():
    """Covers: AC-5 (wrong). The old chat model name is gone from both modules."""
    import chat

    assert CHAT_MODEL != "gemini-3.5-flash-lite"
    assert chat.CHAT_MODEL != "gemini-3.5-flash-lite"


def test_missing_key_error_is_exported_runtime_error():
    """Covers: AC-2 (right). MissingApiKeyError stays a RuntimeError exported from blc.llm and chat."""
    import chat

    assert issubclass(MissingApiKeyError, RuntimeError)
    assert hasattr(llm_mod, "MissingApiKeyError")
    assert chat.MissingApiKeyError is MissingApiKeyError
    assert chat.build_chat_model is build_chat_model
