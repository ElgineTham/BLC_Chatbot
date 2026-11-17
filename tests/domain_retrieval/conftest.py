"""Shared fixtures for domain-filtered retrieval tests (spec 028)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import domain_helpers as dh  # noqa: E402


@pytest.fixture
def lexicon():
    return dict(dh.LEXICON)


@pytest.fixture(scope="session")
def real_lexicon():
    from blc.retrieval import load_lexicon

    return load_lexicon()


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    if not dh.ollama_running():
        pytest.skip("Ollama is not running; start it to run the domain retrieval integration/eval tests.")
    return True


@pytest.fixture
def tmp_store(tmp_path, ollama_available):
    """Empty Chroma store in a pytest temp dir with the real embedding model."""
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings

    from ingest import COLLECTION_NAME, EMBED_MODEL

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
        persist_directory=str(tmp_path / "chroma"),
    )


@pytest.fixture(scope="session")
def domain_store(ollama_available):
    """DomainStore over the real store (read only); skips if missing, empty or lacking domain labels."""
    from blc.retrieval import DomainStore
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run scripts/ingest.py first.")
    store = build_store()
    metas = store.get(include=["metadatas"]).get("metadatas") or []
    if not metas:
        pytest.skip(f"Chroma store at {CHROMA_DIR} is empty: run scripts/ingest.py first.")
    if any(not (m or {}).get("domain") for m in metas):
        pytest.skip(dh.SKIP_NO_DOMAIN)
    return DomainStore(store)
