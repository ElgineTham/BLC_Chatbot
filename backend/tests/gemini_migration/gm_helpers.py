"""Plain helpers for spec 037 tests (imported by test files; fixtures live in conftest.py)."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

X_TEXT = "Coffee service notes. Alpha original text about the coffee station setup."
Y_TEXT = "Pasta recipe. Boil water, salt it, cook the noodles until tender."
X2_TEXT = "Coffee service notes. Beta revised wording about the urn and the cream."
Y2_TEXT = "Pasta recipe. Gamma revised: simmer the sauce slowly and stir often."
FAIL_MARKER = "Pasta"
DIM = 768


def fake_embeddings():
    from langchain_core.embeddings import DeterministicFakeEmbedding

    return DeterministicFakeEmbedding(size=DIM)


def make_store(persist_dir: Path, embeddings=None, collection: str = "spec037_test"):
    from langchain_chroma import Chroma

    return Chroma(
        collection_name=collection,
        embedding_function=embeddings or fake_embeddings(),
        persist_directory=str(persist_dir),
    )


def dump(store) -> dict:
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


def joined(store, source: str) -> str:
    return "\n".join(c["doc"] for c in chunks_for(store, source))


def seed(store, entries):
    """entries: list of (id, text, metadata dict)."""
    store.add_texts(
        [t for _, t, _ in entries],
        metadatas=[m for _, _, m in entries],
        ids=[i for i, _, _ in entries],
    )


def seed_persisted(persist_dir: Path, embed_model: str | None):
    """Seed a store the entry points can open: ingest.COLLECTION_NAME, 768-dim fake vectors."""
    import ingest

    store = make_store(persist_dir, collection=ingest.COLLECTION_NAME)
    meta = {"source": "data/x.md", "category": "x", "domain": "x", "chunk_index": 0}
    if embed_model is not None:
        meta["embed_model"] = embed_model
    seed(store, [("seed-1", X_TEXT, meta)])
    return store
