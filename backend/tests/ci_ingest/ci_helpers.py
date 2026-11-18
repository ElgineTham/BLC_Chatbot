"""Plain helpers for spec 036 tests (imported by test files; fixtures live in conftest.py)."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

X_TEXT = "Coffee service notes. Alpha original text about the coffee station setup."
Y_TEXT = "Pasta recipe. Boil water, salt it, cook the noodles until tender."


def make_store(persist_dir: Path):
    from langchain_chroma import Chroma
    from langchain_core.embeddings import DeterministicFakeEmbedding

    return Chroma(
        collection_name="spec036_test",
        embedding_function=DeterministicFakeEmbedding(size=32),
        persist_directory=str(persist_dir),
    )


def dump(store) -> dict:
    """All chunks as {'ids': [...], 'metadatas': [...], 'documents': [...]}."""
    got = store.get(include=["metadatas", "documents"])
    return {
        "ids": list(got.get("ids") or []),
        "metadatas": [dict(m or {}) for m in (got.get("metadatas") or [])],
        "documents": list(got.get("documents") or []),
    }


def chunks_for(store, source: str) -> list[dict]:
    d = dump(store)
    return [
        {"id": i, "meta": m, "doc": t}
        for i, m, t in zip(d["ids"], d["metadatas"], d["documents"])
        if m.get("source") == source
    ]


def count(store) -> int:
    return len(dump(store)["ids"])
