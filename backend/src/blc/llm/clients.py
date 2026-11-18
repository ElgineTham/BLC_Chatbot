"""Claude chat model (spec 039) and Gemini embeddings (spec 037) builders. Read only os.environ."""

from __future__ import annotations

import math
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

API_KEY_ENV = "GOOGLE_API_KEY"
CHAT_API_KEY_ENV = "ANTHROPIC_API_KEY"
CHAT_MODEL = "claude-haiku-4-5"
ANTHROPIC_API_VERSION = "2023-06-01"  # newer SDK default version rejects top-level temperature
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768


class MissingApiKeyError(RuntimeError):
    """Message names the missing env var (CHAT_API_KEY_ENV or API_KEY_ENV) and never contains a key value."""


class NormalizedEmbeddings(Embeddings):
    """Wraps an Embeddings object and scales every vector to unit L2 norm."""

    def __init__(self, inner: Embeddings) -> None:
        self._inner = inner

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_unit(vector) for vector in self._inner.embed_documents(texts)]

    def embed_query(self, text: str) -> list[float]:
        return _unit(self._inner.embed_query(text))

    def __repr__(self) -> str:
        return f"NormalizedEmbeddings(model={EMBED_MODEL!r}, dim={EMBED_DIM})"


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else list(vector)


def _api_key(env_name: str, hint: str) -> str:
    key = os.environ.get(env_name, "")
    if not key.strip():
        raise MissingApiKeyError(
            f"{env_name} is not set. Put it in .env or the environment ({hint})."
        )
    return key


def build_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """Claude chat model. Raises MissingApiKeyError if the key is unset or blank. No network call."""
    from langchain_anthropic import ChatAnthropic

    key = _api_key(CHAT_API_KEY_ENV, "get a key in the Claude Console")
    return ChatAnthropic(
        model=CHAT_MODEL,
        temperature=temperature,
        api_key=key,
        default_headers={"anthropic-version": ANTHROPIC_API_VERSION},
    )


def build_embeddings() -> Embeddings:
    """768-d unit-norm vectors. Raises MissingApiKeyError as above. No network call."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return NormalizedEmbeddings(
        GoogleGenerativeAIEmbeddings(
            model=EMBED_MODEL,
            google_api_key=_api_key(API_KEY_ENV, "get a key in Google AI Studio"),
            output_dimensionality=EMBED_DIM,
        )
    )
