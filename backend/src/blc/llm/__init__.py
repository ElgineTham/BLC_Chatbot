"""Gemini model builders (spec 037)."""

from __future__ import annotations

from blc.llm.gemini import (
    API_KEY_ENV,
    CHAT_MODEL,
    EMBED_DIM,
    EMBED_MODEL,
    MissingApiKeyError,
    build_chat_model,
    build_embeddings,
)

__all__ = [
    "API_KEY_ENV",
    "CHAT_MODEL",
    "EMBED_DIM",
    "EMBED_MODEL",
    "MissingApiKeyError",
    "build_chat_model",
    "build_embeddings",
]
