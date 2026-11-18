"""Plain helpers for spec 039 tests (imported by test files; fixtures live in conftest.py)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

DIM = 768
X_TEXT = "Coffee service notes. Alpha original text about the coffee station setup."


def fake_embeddings():
    from langchain_core.embeddings import DeterministicFakeEmbedding

    return DeterministicFakeEmbedding(size=DIM)


def make_store(persist_dir: Path, collection: str = "spec039_test"):
    from langchain_chroma import Chroma

    return Chroma(
        collection_name=collection,
        embedding_function=fake_embeddings(),
        persist_directory=str(persist_dir),
    )


def seed_persisted(persist_dir: Path, embed_model: str):
    """A store the entry points can open: ingest.COLLECTION_NAME, 768-dim fake vectors, stamped with embed_model."""
    import ingest

    store = make_store(persist_dir, collection=ingest.COLLECTION_NAME)
    meta = {
        "source": "data/x.md",
        "category": "x",
        "domain": "x",
        "chunk_index": 0,
        "embed_model": embed_model,
    }
    store.add_texts([X_TEXT], metadatas=[meta], ids=["seed-1"])
    return store


def parse_lines(response) -> list[dict]:
    """The JSON lines of a streamed /api/chat response."""
    return [json.loads(x) for x in response.text.split("\n") if x.strip()]
