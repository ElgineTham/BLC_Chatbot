"""STORE: ingest_file with per-bullet chunking for food.md (spec 026 section 6.2). Integration, real Ollama."""

from __future__ import annotations

import pytest

from food_helpers import FOOD_PATH, FOOD_SOURCE, ROOT
from ingest import chunk_markdown, ingest_file

COFFEE_PATH = ROOT / "data" / "supplies" / "coffee.md"


@pytest.mark.integration
def test_ingest_food_returns_per_bullet_count(tmp_store, food_text):
    """Covers: AC-7 (right), STORE-1, STORE-5. ingest_file returns len(chunk_markdown(text, per_bullet=True)); skips without Ollama."""
    written = ingest_file(tmp_store, FOOD_PATH, FOOD_PATH.stat().st_mtime)
    expected = len(chunk_markdown(food_text, per_bullet=True))
    assert written == expected
    assert written > len(chunk_markdown(food_text, per_bullet=False))


@pytest.mark.integration
def test_stored_documents_one_per_chunk(tmp_store, food_text):
    """Covers: AC-7 (right), STORE-1. The store holds exactly one document per per-bullet chunk."""
    ingest_file(tmp_store, FOOD_PATH, FOOD_PATH.stat().st_mtime)
    docs = tmp_store.get()["documents"]
    assert len(docs) == len(chunk_markdown(food_text, per_bullet=True))


@pytest.mark.integration
def test_stored_metadata(tmp_store):
    """Covers: AC-7 (right), STORE-2. source, category pull_sheet and chunk_index 0..n-1 are stored."""
    n = ingest_file(tmp_store, FOOD_PATH, FOOD_PATH.stat().st_mtime)
    metas = tmp_store.get(include=["metadatas"])["metadatas"]
    assert len(metas) == n
    assert {m["source"] for m in metas} == {FOOD_SOURCE}
    assert {m["category"] for m in metas} == {"pull_sheet"}
    assert sorted(m["chunk_index"] for m in metas) == list(range(n))


@pytest.mark.integration
def test_ingest_twice_keeps_count(tmp_store):
    """Covers: AC-7 (boundary), STORE-3. A second ingest of food.md leaves the stored count unchanged."""
    mtime = FOOD_PATH.stat().st_mtime
    ingest_file(tmp_store, FOOD_PATH, mtime)
    first = len(tmp_store.get()["ids"])
    ingest_file(tmp_store, FOOD_PATH, mtime)
    assert len(tmp_store.get()["ids"]) == first


@pytest.mark.integration
def test_other_file_uses_default_chunking(tmp_store):
    """Covers: AC-7 (right), STORE-4. coffee.md is stored with per_bullet=False chunking."""
    if not COFFEE_PATH.exists():
        pytest.skip(f"{COFFEE_PATH} is missing")
    text = COFFEE_PATH.read_text(encoding="utf-8")
    written = ingest_file(tmp_store, COFFEE_PATH, COFFEE_PATH.stat().st_mtime)
    assert written == len(chunk_markdown(text))
    assert len(tmp_store.get()["ids"]) == len(chunk_markdown(text))
