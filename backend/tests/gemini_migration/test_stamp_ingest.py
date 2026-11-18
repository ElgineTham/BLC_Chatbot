"""Spec 037 section 6.2 (STAMP-5 to STAMP-10): ingest stamps and re-embeds by embedding model."""

from __future__ import annotations

import pytest
from gm_helpers import (
    FAIL_MARKER,
    X2_TEXT,
    X_TEXT,
    Y2_TEXT,
    Y_TEXT,
    chunks_for,
    count,
    dump,
    fake_embeddings,
    joined,
    make_store,
    seed,
)
from langchain_core.embeddings import Embeddings

from ingest import (
    EMBED_MODEL,
    HASH_KEY,
    check_store_model,
    content_hash,
    ingest,
    ingest_file,
)

X = "data/x.md"
Y = "data/sub/y.md"


class FlakyEmbeddings(Embeddings):
    """Raises on any document text containing FAIL_MARKER while `fail` is True."""

    def __init__(self):
        self.inner = fake_embeddings()
        self.fail = False

    def embed_documents(self, texts):
        if self.fail and any(FAIL_MARKER in t for t in texts):
            raise RuntimeError("embedding service down")
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def test_ingest_stamps_default_model(store, data_dir):
    """Covers: AC-5 (right), STAMP-5. Every chunk carries embed_model == EMBED_MODEL by default."""
    ingest(store, data_dir)
    metas = dump(store)["metadatas"]
    assert metas
    assert all(m.get("embed_model") == EMBED_MODEL for m in metas)
    check_store_model(store)


def test_ingest_stamps_explicit_model_and_keeps_036_metadata(store, data_dir):
    """Covers: AC-5 (right). An explicit embed_model is stamped, next to source, hash and chunk_index."""
    ingest(store, data_dir, embed_model="m1")
    for m in dump(store)["metadatas"]:
        assert m["embed_model"] == "m1"
        for key in ("source", "category", "domain", "chunk_index", HASH_KEY):
            assert key in m


def test_ingest_file_stamps_given_model(store, data_dir):
    """Covers: AC-5 (right), STAMP-6. ingest_file(store, path, 1.0, embed_model='x') stamps 'x'."""
    n = ingest_file(store, data_dir / "x.md", 1.0, embed_model="x")
    assert n > 0
    assert count(store) == n
    assert all(m.get("embed_model") == "x" for m in dump(store)["metadatas"])


def test_ingest_file_default_model(store, data_dir):
    """Covers: AC-5 (boundary). ingest_file without embed_model stamps EMBED_MODEL."""
    ingest_file(store, data_dir / "x.md")
    assert all(m.get("embed_model") == EMBED_MODEL for m in dump(store)["metadatas"])


def test_model_change_reembeds_everything(tmp_path, store, data_dir):
    """Covers: AC-6 (right), STAMP-7. Switching m1 -> m2 on unchanged files: all updated, no m1 left, counts as fresh."""
    ingest(store, data_dir, embed_model="m1")
    plan = ingest(store, data_dir, embed_model="m2")
    assert plan.updated == (Y, X)
    assert plan.new == () and plan.unchanged == () and plan.deleted == ()
    assert all(m["embed_model"] == "m2" for m in dump(store)["metadatas"])

    fresh = make_store(tmp_path / "fresh")
    ingest(fresh, data_dir, embed_model="m2")
    for src in (X, Y):
        assert len(chunks_for(store, src)) == len(chunks_for(fresh, src)) > 0


def test_same_model_second_run_unchanged(store, data_dir):
    """Covers: AC-6 (right), STAMP-8. After the switch, another run with m2 reports all unchanged and rewrites nothing."""
    ingest(store, data_dir, embed_model="m1")
    ingest(store, data_dir, embed_model="m2")
    before = sorted(dump(store)["ids"])
    plan = ingest(store, data_dir, embed_model="m2")
    assert plan.unchanged == (Y, X)
    assert plan.new == () and plan.updated == () and plan.deleted == ()
    assert sorted(dump(store)["ids"]) == before


def test_same_model_twice_is_unchanged_from_the_start(store, data_dir):
    """Covers: AC-6 (boundary). Same model both runs: the second run is all unchanged (no needless re-embed)."""
    ingest(store, data_dir, embed_model="m1")
    plan = ingest(store, data_dir, embed_model="m1")
    assert plan.unchanged == (Y, X) and plan.updated == ()


def test_legacy_chunk_with_matching_hash_is_updated_and_stamped(store, data_dir):
    """Covers: AC-7 (right), STAMP-9. A chunk with the right content_hash but no embed_model is updated, then stamped."""
    h = content_hash((data_dir / "x.md").read_bytes())
    seed(store, [("old-1", X_TEXT, {"source": X, "category": "c", "domain": "d", "chunk_index": 0, HASH_KEY: h})])
    plan = ingest(store, data_dir)
    assert X in plan.updated
    assert Y in plan.new
    assert chunks_for(store, X)
    assert all(c["meta"].get("embed_model") == EMBED_MODEL for c in chunks_for(store, X))
    check_store_model(store)


def test_legacy_chunk_without_hash_is_updated_and_stamped(store, data_dir):
    """Covers: AC-7 (wrong). A pre-036 chunk (mtime only, no hash, no model) is updated and then stamped."""
    seed(store, [("old-1", "stale text", {"source": X, "mtime": 1.0})])
    plan = ingest(store, data_dir)
    assert X in plan.updated
    assert "stale text" not in joined(store, X)
    assert all(c["meta"].get("embed_model") == EMBED_MODEL for c in chunks_for(store, X))


class SecondCallFails(Embeddings):
    """Succeeds on its 1st embed_documents call, raises on the 2nd (STAMP-10), then works again once `armed`
    is cleared. Counts calls."""

    def __init__(self):
        self.inner = fake_embeddings()
        self.calls = 0
        self.armed = True

    def embed_documents(self, texts):
        self.calls += 1
        if self.armed and self.calls == 2:
            raise RuntimeError("embedding service down")
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def test_failure_after_first_file_embedded_then_rerun_heals(tmp_path, data_dir):
    """Covers: AC-8 (wrong then right), STAMP-10. The 1st embed_documents call works and the 2nd raises: ingest
    raises; a rerun with a working embedder passes check_store_model and every file's chunks match its content."""
    emb = SecondCallFails()
    store = make_store(tmp_path / "second_fails", embeddings=emb)
    with pytest.raises(RuntimeError):
        ingest(store, data_dir)
    assert emb.calls >= 2  # the first file was embedded before the failure
    emb.armed = False
    ingest(store, data_dir)
    check_store_model(store)
    assert X_TEXT in joined(store, X)
    assert Y_TEXT in joined(store, Y)
    assert all(m["embed_model"] == EMBED_MODEL for m in dump(store)["metadatas"])
    assert ingest(store, data_dir).unchanged == (Y, X)


def test_failure_after_first_file_with_edited_files_leaves_no_stale_chunks(tmp_path, data_dir):
    """Covers: AC-8 (boundary), STAMP-10. Both files edited after a model change, 2nd embed call fails: after
    the rerun no chunk of old text and no old model stamp remains."""
    emb = SecondCallFails()
    emb.armed = False
    store = make_store(tmp_path / "second_fails_edit", embeddings=emb)
    ingest(store, data_dir, embed_model="m1")
    (data_dir / "x.md").write_text(X2_TEXT, encoding="utf-8")
    (data_dir / "sub" / "y.md").write_text(Y2_TEXT, encoding="utf-8")
    emb.calls = 0
    emb.armed = True
    with pytest.raises(RuntimeError):
        ingest(store, data_dir, embed_model="m2")
    emb.armed = False
    ingest(store, data_dir, embed_model="m2")
    check_store_model(store, "m2")
    assert X2_TEXT in joined(store, X) and "Alpha original" not in joined(store, X)
    assert Y2_TEXT in joined(store, Y) and "Boil water" not in joined(store, Y)


def test_embedding_failure_propagates_and_rerun_heals(tmp_path, data_dir):
    """Covers: AC-8 (wrong then right), STAMP-10. A failing embedder makes ingest raise; a rerun brings
    the store fully in line (stamped, every file's chunks match its content)."""
    emb = FlakyEmbeddings()
    store = make_store(tmp_path / "flaky", embeddings=emb)
    emb.fail = True
    with pytest.raises(RuntimeError):
        ingest(store, data_dir)
    emb.fail = False
    ingest(store, data_dir)
    check_store_model(store)
    assert X_TEXT in joined(store, X)
    assert Y_TEXT in joined(store, Y)
    for c in chunks_for(store, X) + chunks_for(store, Y):
        assert HASH_KEY in c["meta"]
    again = ingest(store, data_dir)
    assert again.unchanged == (Y, X)


def test_embedding_failure_on_edited_files_leaves_no_stale_chunks(tmp_path, data_dir):
    """Covers: AC-8 (boundary). Files edited, then the embedder fails mid-run: after a rerun no chunk of old text remains."""
    emb = FlakyEmbeddings()
    store = make_store(tmp_path / "flaky2", embeddings=emb)
    ingest(store, data_dir, embed_model="m1")
    (data_dir / "x.md").write_text(X2_TEXT, encoding="utf-8")
    (data_dir / "sub" / "y.md").write_text(Y2_TEXT, encoding="utf-8")
    emb.fail = True
    with pytest.raises(RuntimeError):
        ingest(store, data_dir, embed_model="m2")
    emb.fail = False
    ingest(store, data_dir, embed_model="m2")
    check_store_model(store, "m2")
    assert X2_TEXT in joined(store, X) and "Alpha original" not in joined(store, X)
    assert Y2_TEXT in joined(store, Y) and "Boil water" not in joined(store, Y)
    assert all(m["embed_model"] == "m2" for m in dump(store)["metadatas"])
