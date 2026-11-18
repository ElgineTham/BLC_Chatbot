"""Spec 037 section 6.4 (ENTRY-1 to ENTRY-4): entry points, missing key and mismatched store."""

from __future__ import annotations

import builtins
import sys

import pytest
from gm_helpers import dump, fake_embeddings, make_store, seed_persisted

import chat
import ingest


class _Boom:
    """Injected voice component that fails the test if it is ever used."""

    def __getattr__(self, name):
        raise AssertionError(f"component used unexpectedly: {name}")


def _run(name):
    if name == "chat":
        return chat.main()
    if name == "ingest":
        return ingest.main()
    if name == "web":
        import web

        return web.main([])
    if name == "trace_flow":
        import trace_flow

        return trace_flow.main(["Where is the coffee?"])
    if name == "voice_chat":
        try:
            import voice_chat
        except ImportError as e:  # voice dependencies are an optional group
            pytest.skip(f"voice_chat not importable: {e}")
        return voice_chat.main(recorder=_Boom(), transcriber=_Boom(), speaker=_Boom())
    raise ValueError(name)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Keep every entry point off the real data/, argv, stdin and server."""
    monkeypatch.setattr(sys, "argv", ["entry.py"])

    def no_input(*a, **k):
        raise AssertionError("input() must not be read")

    monkeypatch.setattr(builtins, "input", no_input)

    def no_server(*a, **k):
        raise AssertionError("the server must not be started")

    monkeypatch.setattr("uvicorn.run", no_server)
    monkeypatch.setattr(chat, "load_catalog", lambda *a, **k: object(), raising=False)


@pytest.fixture
def key_missing(monkeypatch):
    """Spec 039: only the embeddings need GOOGLE_API_KEY; the chat model builds (it needs ANTHROPIC_API_KEY)."""

    def boom(*a, **k):
        raise chat.MissingApiKeyError("GOOGLE_API_KEY is not set")

    monkeypatch.setattr(chat, "build_chat_model", lambda *a, **k: object())
    monkeypatch.setattr(chat, "build_embeddings", boom)
    monkeypatch.setattr(ingest, "build_embeddings", boom)


@pytest.fixture
def mismatched(monkeypatch, tmp_path, offline):
    """A persisted store with nomic chunks; models faked so only the store check can stop main()."""
    persist = tmp_path / "chroma_nomic"
    seed_persisted(persist, "nomic-embed-text")
    monkeypatch.setattr(chat, "CHROMA_DIR", persist)
    monkeypatch.setattr(chat, "build_chat_model", lambda *a, **k: object())
    monkeypatch.setattr(chat, "build_embeddings", lambda *a, **k: fake_embeddings())
    return persist


# ---- ENTRY-1 / AC-10

@pytest.mark.parametrize("name", ["chat", "web", "trace_flow", "voice_chat", "ingest"])
def test_missing_key_returns_1_without_traceback(name, offline, key_missing, tmp_path, monkeypatch, capsys):
    """Covers: AC-10 (wrong), ENTRY-1. MissingApiKeyError -> return 1, stderr names GOOGLE_API_KEY, no traceback."""
    monkeypatch.setattr(chat, "CHROMA_DIR", tmp_path)
    monkeypatch.setattr(ingest, "CHROMA_DIR", tmp_path / "ingest_chroma", raising=False)
    monkeypatch.setattr(ingest, "DATA_DIR", tmp_path / "data", raising=False)
    (tmp_path / "data").mkdir(exist_ok=True)
    rc = _run(name)
    err = capsys.readouterr().err
    assert rc == 1
    assert "GOOGLE_API_KEY" in err
    assert "Traceback" not in err


def test_ingest_missing_key_leaves_store_untouched(offline, key_missing, tmp_path, monkeypatch):
    """Covers: AC-10 (right), ENTRY-2. ingest.main() with no key does not change a pre-seeded store."""
    persist = tmp_path / "chroma_seeded"
    store = seed_persisted(persist, "nomic-embed-text")
    before = dump(store)
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.md").write_text("Some new markdown that would be ingested.", encoding="utf-8")
    monkeypatch.setattr(ingest, "CHROMA_DIR", persist, raising=False)
    monkeypatch.setattr(ingest, "DATA_DIR", data, raising=False)
    monkeypatch.setattr(chat, "CHROMA_DIR", persist)
    assert ingest.main() == 1
    after = dump(make_store(persist, collection=ingest.COLLECTION_NAME))
    assert sorted(after["ids"]) == sorted(before["ids"])
    assert after["metadatas"] == before["metadatas"]


# ---- ENTRY-3 / AC-11

@pytest.mark.parametrize("name", ["chat", "web", "trace_flow", "voice_chat"])
def test_mismatched_store_returns_1(name, mismatched, capsys):
    """Covers: AC-11 (wrong), ENTRY-3. A store built by another model -> return 1, stderr says ingest.py,
    before input is read or the server started (both are patched to fail the test)."""
    rc = _run(name)
    err = capsys.readouterr().err
    assert rc == 1
    assert "ingest.py" in err
    assert "Traceback" not in err


def test_mismatched_store_message_names_expected_model(mismatched, capsys):
    """Covers: AC-11 (wrong). The message names the expected embedding model."""
    assert chat.main() == 1
    assert "gemini-embedding-2" in capsys.readouterr().err


def test_matching_store_is_not_refused(monkeypatch, tmp_path, offline, capsys):
    """Covers: AC-11 (right). A store stamped with EMBED_MODEL passes the check: chat.main() starts and
    exits normally when stdin hits EOF (return 0)."""
    persist = tmp_path / "chroma_ok"
    seed_persisted(persist, chat.EMBED_MODEL)
    monkeypatch.setattr(chat, "CHROMA_DIR", persist)
    monkeypatch.setattr(chat, "build_chat_model", lambda *a, **k: object())
    monkeypatch.setattr(chat, "build_embeddings", lambda *a, **k: fake_embeddings())

    def eof(*a, **k):
        raise EOFError

    monkeypatch.setattr(builtins, "input", eof)
    assert chat.main() == 0
    assert "ingest.py" not in capsys.readouterr().err


# ---- ENTRY-4 / AC-12

def test_chat_exposes_new_names():
    """Covers: AC-12 (right), ENTRY-4. The spec 3 names are importable from chat."""
    for name in (
        "CHAT_MODEL",
        "EMBED_MODEL",
        "CHAT_TEMPERATURE",
        "build_chat_model",
        "build_embeddings",
        "MissingApiKeyError",
        "check_store_model",
        "StoreModelMismatchError",
    ):
        assert hasattr(chat, name), name


@pytest.mark.parametrize("name", ["CHAT_KEEP_ALIVE", "ChatOllama", "OllamaEmbeddings"])
def test_chat_has_no_ollama_names(name):
    """Covers: AC-12 (wrong), ENTRY-4. The removed Ollama names are not attributes of chat."""
    assert not hasattr(chat, name)


def test_model_constants():
    """Covers: AC-12 (boundary). Exact model names, and chat/ingest agree on the embedding model."""
    assert chat.CHAT_MODEL == "claude-haiku-4-5"  # spec 039
    assert chat.EMBED_MODEL == ingest.EMBED_MODEL == "gemini-embedding-2"


def test_stamp_names_reexported_from_ingest():
    """Covers: AC-4 (right). Stamp names are re-exported from ingest.py as well as chat.py."""
    from blc.ingest.stamp import StoreModelMismatchError, check_store_model

    assert ingest.StoreModelMismatchError is StoreModelMismatchError is chat.StoreModelMismatchError
    assert ingest.check_store_model is check_store_model is chat.check_store_model
    assert ingest.EMBED_MODEL_KEY == "embed_model"


def test_chat_builders_are_the_llm_builders():
    """Covers: AC-12 (right). chat re-exports the blc.llm builders and error type."""
    import blc.llm as llm

    assert chat.build_chat_model is llm.build_chat_model
    assert chat.build_embeddings is llm.build_embeddings
    assert chat.MissingApiKeyError is llm.MissingApiKeyError
