"""Spec 037 section 6.2 (STAMP-1 to STAMP-4): check_store_model."""

from __future__ import annotations

import pytest
from gm_helpers import seed
from ingest import EMBED_MODEL, EMBED_MODEL_KEY, StoreModelMismatchError, check_store_model


def _meta(i, **extra):
    m = {"source": f"data/f{i}.md", "category": "c", "domain": "d", "chunk_index": 0}
    m.update(extra)
    return m


def test_key_and_model_values():
    """Covers: AC-4 (right), AC-12. The metadata key and default model are the spec values."""
    assert EMBED_MODEL_KEY == "embed_model"
    assert EMBED_MODEL == "gemini-embedding-2"


def test_empty_store_passes(store):
    """Covers: AC-4 (boundary), STAMP-1. An empty store passes."""
    assert check_store_model(store) is None


def test_all_stamped_passes(store):
    """Covers: AC-4 (right), STAMP-2. Every chunk stamped with the expected model passes."""
    seed(store, [(f"id{i}", f"text {i}", _meta(i, embed_model=EMBED_MODEL)) for i in range(3)])
    check_store_model(store)


def test_explicit_expected_passes(store):
    """Covers: AC-4 (right). The expected argument overrides the default."""
    seed(store, [("a", "t", _meta(1, embed_model="m1"))])
    check_store_model(store, "m1")


def test_other_model_raises_with_names(store):
    """Covers: AC-4 (wrong), STAMP-3. A chunk from nomic-embed-text raises; message names the model and ingest.py."""
    seed(store, [("a", "t", _meta(1, embed_model="nomic-embed-text"))])
    with pytest.raises(StoreModelMismatchError) as exc:
        check_store_model(store)
    assert "gemini-embedding-2" in str(exc.value)
    assert "ingest.py" in str(exc.value)


def test_message_names_custom_expected(store):
    """Covers: AC-4 (wrong). With expected='m9' the message names m9."""
    seed(store, [("a", "t", _meta(1, embed_model="m1"))])
    with pytest.raises(StoreModelMismatchError) as exc:
        check_store_model(store, "m9")
    assert "m9" in str(exc.value)


def test_unstamped_chunk_raises(store):
    """Covers: AC-4 (wrong). A chunk with no embed_model key raises."""
    seed(store, [("a", "t", _meta(1))])
    with pytest.raises(StoreModelMismatchError):
        check_store_model(store)


def test_mix_of_stamped_and_unstamped_raises(store):
    """Covers: AC-4 (boundary), STAMP-4. Many stamped chunks plus one unstamped chunk raises."""
    entries = [(f"id{i}", f"t{i}", _meta(i, embed_model=EMBED_MODEL)) for i in range(5)]
    entries.append(("odd", "odd", _meta(9)))
    seed(store, entries)
    with pytest.raises(StoreModelMismatchError):
        check_store_model(store)


def test_one_foreign_among_many_stamped_raises(store):
    """Covers: AC-4 (boundary). A single other-model chunk among stamped ones raises."""
    entries = [(f"id{i}", f"t{i}", _meta(i, embed_model=EMBED_MODEL)) for i in range(5)]
    entries.append(("odd", "odd", _meta(9, embed_model="nomic-embed-text")))
    seed(store, entries)
    with pytest.raises(StoreModelMismatchError):
        check_store_model(store)


def test_mismatch_error_is_runtime_error():
    """Covers: AC-4 (right). The error is a RuntimeError subclass (contract)."""
    assert issubclass(StoreModelMismatchError, RuntimeError)
