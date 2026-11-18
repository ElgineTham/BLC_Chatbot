"""Shared fixtures for napkin knowledge tests (spec 031)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import napkin_helpers as nh  # noqa: E402


@pytest.fixture
def napkin_lexicon(tmp_path):
    """Lexicon from a data dir with the napkin file, a food file and a beverage file."""
    from blc.retrieval import load_lexicon

    return load_lexicon(nh.write_data_dir(tmp_path / "with"))


@pytest.fixture
def no_napkin_lexicon(tmp_path):
    """Lexicon from a data dir with food and beverage files but no napkin file."""
    from blc.retrieval import load_lexicon

    return load_lexicon(nh.write_data_dir(tmp_path / "without", with_napkin=False))


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    if not nh.ollama_running():
        pytest.skip("Ollama is not running; start it to run the napkin integration/eval tests.")
    return True


@pytest.fixture(scope="session")
def real_store(ollama_available):
    """Real Chroma store (read only); skips if missing or holding no napkin chunk."""
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run scripts/ingest.py first.")
    store = build_store()
    metas = store.get(include=["metadatas"]).get("metadatas") or []
    if not any((m or {}).get("source") == nh.NAPKIN_SOURCE for m in metas):
        pytest.skip("Store has no napkin chunk: run scripts/ingest.py first.")
    return store


@pytest.fixture(scope="session")
def domain_store(real_store):
    from blc.retrieval import DomainStore

    return DomainStore(real_store)
