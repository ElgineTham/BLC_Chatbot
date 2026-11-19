"""Spec 040 AC-9 (integration): ingested markdown for the new drinks (DOCS-1, DOCS-2). Skips without Ollama."""

from __future__ import annotations

import pytest

from chat import retrieve


def _sources(docs):
    return [str((d.metadata or {}).get("source", "")).replace("\\", "/") for d in docs]


@pytest.mark.integration
def test_strawberry_lemonade_doc_retrieved(real_store):
    """Covers: AC-9 (right), DOCS-1. The strawberry lemonade file is among the retrieved documents."""
    docs = retrieve(real_store, "How do I make strawberry lemonade?")
    assert any(s.endswith("data/recipes/flavored_lemonades.md") for s in _sources(docs)), _sources(docs)


@pytest.mark.integration
def test_raspberry_iced_tea_doc_retrieved(real_store):
    """Covers: AC-9 (right), DOCS-2. The raspberry iced tea file is among the retrieved documents."""
    docs = retrieve(real_store, "How do I make raspberry iced tea?")
    assert any(s.endswith("data/recipes/flavored_iced_teas.md") for s in _sources(docs)), _sources(docs)
