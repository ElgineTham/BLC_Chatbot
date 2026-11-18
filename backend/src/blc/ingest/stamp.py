"""Record and check which embedding model built the chunks (spec 037)."""

from __future__ import annotations

from langchain_chroma import Chroma

from blc.llm import EMBED_MODEL

EMBED_MODEL_KEY = "embed_model"


class StoreModelMismatchError(RuntimeError):
    """Message names the expected model and says to run backend/scripts/ingest.py."""


def check_store_model(store: Chroma, expected: str = EMBED_MODEL) -> None:
    """Raise StoreModelMismatchError if any chunk lacks EMBED_MODEL_KEY or differs."""
    result = store.get(include=["metadatas"])
    for meta in result.get("metadatas") or []:
        if (meta or {}).get(EMBED_MODEL_KEY) != expected:
            raise StoreModelMismatchError(
                f"The vector store was not built with {expected}. "
                "Run backend/scripts/ingest.py to rebuild it."
            )
