"""Shared fixtures for the food menu ingest and retrieval tests (spec 025)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import food_helpers as fh  # noqa: E402


@pytest.fixture(scope="session")
def food_text() -> str:
    assert fh.FOOD_PATH.exists(), f"{fh.FOOD_PATH} is missing"
    return fh.FOOD_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def golden_cases() -> list[dict]:
    assert fh.GOLDEN_PATH.exists(), f"{fh.GOLDEN_PATH} is missing"
    return fh.load_golden()


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    """Name kept for the dependent fixtures. Spec 037: embeddings run on Gemini, so this skips when
    GOOGLE_API_KEY is unset (Ollama is no longer needed here)."""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set; set it to run the food retrieval tests.")
    return True


@pytest.fixture
def tmp_store(tmp_path, ollama_available):
    """Empty Chroma store in a pytest temp dir with the real embedding model."""
    from langchain_chroma import Chroma

    from blc.llm import build_embeddings
    from ingest import COLLECTION_NAME

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=build_embeddings(),
        persist_directory=str(tmp_path / "chroma"),
    )


@pytest.fixture(scope="session")
def real_store(ollama_available):
    """The real store (read only); skips if food.md has not been ingested."""
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run scripts/ingest.py first.")
    store = build_store()
    data = store.get(include=["metadatas"])
    sources = {(m or {}).get("source", "") for m in (data.get("metadatas") or [])}
    if fh.FOOD_SOURCE not in sources:
        pytest.skip(
            f"No documents with source {fh.FOOD_SOURCE} in the store: run scripts/ingest.py first."
        )
    return store
