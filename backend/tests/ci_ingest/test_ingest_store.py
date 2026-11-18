"""Spec 036 section 6.2: ingest() against a fake-embedding Chroma store in tmp_path."""

from __future__ import annotations

import os
import time
import urllib.request

import pytest
from ci_helpers import chunks_for, count, dump, make_store

from ingest import HASH_KEY, content_hash, ingest, ingest_file

X = "data/x.md"
Y = "data/sub/y.md"


def test_first_ingest_embeds_all_md_only(store, data_dir):
    """Covers: AC-3 (right), INGEST-1. New = both md files sorted; json/jpg ignored."""
    plan = ingest(store, data_dir)
    assert plan.new == ("data/sub/y.md", "data/x.md")
    assert plan.updated == () and plan.unchanged == () and plan.deleted == ()
    sources = {m.get("source") for m in dump(store)["metadatas"]}
    assert sources == {X, Y}
    assert chunks_for(store, X) and chunks_for(store, Y)


def test_first_ingest_no_json_or_jpg_chunks(store, data_dir):
    """Covers: AC-3 (wrong), INGEST-1. Non-md files produce no chunks."""
    ingest(store, data_dir)
    for src in ("data/z.json", "data/p.jpg"):
        assert chunks_for(store, src) == []


def test_nested_depth_md_found(store, data_dir):
    """Covers: AC-3 (boundary). Markdown at deep nesting is picked up."""
    deep = data_dir / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.md").write_text("Deeply nested knowledge file.", encoding="utf-8")
    plan = ingest(store, data_dir)
    assert "data/a/b/c/deep.md" in plan.new


def test_second_run_all_unchanged_same_ids(store, data_dir):
    """Covers: AC-4 (right), INGEST-2. Second run: all unchanged, ids and count identical."""
    ingest(store, data_dir)
    before = sorted(dump(store)["ids"])
    plan = ingest(store, data_dir)
    assert plan.unchanged == ("data/sub/y.md", "data/x.md")
    assert plan.new == () and plan.updated == () and plan.deleted == ()
    assert sorted(dump(store)["ids"]) == before


def test_edit_with_old_mtime_is_updated(store, data_dir):
    """Covers: AC-5 (right), INGEST-3. Content change with mtime in 2000 -> updated; old text gone."""
    ingest(store, data_dir)
    x = data_dir / "x.md"
    x.write_text("Completely different replacement wording about linens.", encoding="utf-8")
    os.utime(x, (946684800, 946684800))  # 2000-01-01
    plan = ingest(store, data_dir)
    assert X in plan.updated
    assert Y in plan.unchanged
    docs = " ".join(c["doc"] for c in chunks_for(store, X))
    assert "Alpha original" not in docs
    assert "replacement wording" in docs
    assert not any("Alpha original" in d for d in dump(store)["documents"])


def test_edit_with_same_mtime_is_updated(store, data_dir):
    """Covers: AC-5 (boundary). Content change while restoring the exact same mtime -> updated."""
    ingest(store, data_dir)
    x = data_dir / "x.md"
    st = x.stat()
    x.write_text("Different words here, equal length not required.", encoding="utf-8")
    os.utime(x, ns=(st.st_atime_ns, st.st_mtime_ns))
    plan = ingest(store, data_dir)
    assert X in plan.updated


def test_touch_without_change_is_unchanged(store, data_dir):
    """Covers: AC-5 (wrong), INGEST-4. Only mtime changes -> unchanged, nothing rewritten."""
    ingest(store, data_dir)
    before = sorted(dump(store)["ids"])
    future = time.time() + 10_000
    os.utime(data_dir / "x.md", (future, future))
    plan = ingest(store, data_dir)
    assert plan.unchanged == (Y, X)
    assert plan.updated == () and plan.new == ()
    assert sorted(dump(store)["ids"]) == before


def test_delete_file_removes_only_its_chunks(store, data_dir):
    """Covers: AC-6 (right), INGEST-5. Deleted x: chunks gone, y untouched."""
    ingest(store, data_dir)
    y_before = sorted(c["id"] for c in chunks_for(store, Y))
    (data_dir / "x.md").unlink()
    plan = ingest(store, data_dir)
    assert plan.deleted == (X,)
    assert plan.new == () and plan.updated == ()
    assert plan.unchanged == (Y,)
    assert chunks_for(store, X) == []
    assert sorted(c["id"] for c in chunks_for(store, Y)) == y_before


def test_empty_content_removes_old_chunks(store, data_dir):
    """Covers: AC-7 (right), INGEST-6. Overwriting with empty text leaves no chunks for that source."""
    ingest(store, data_dir)
    assert chunks_for(store, X)
    (data_dir / "x.md").write_text("", encoding="utf-8")
    ingest(store, data_dir)
    assert chunks_for(store, X) == []
    assert chunks_for(store, Y)  # other file untouched


def test_migration_of_hashless_store(store, data_dir):
    """Covers: AC-8 (right), INGEST-7. Legacy chunk with mtime but no hash -> updated; all x chunks hashed after."""
    store.add_texts(
        ["legacy chunk text"],
        metadatas=[{"source": X, "mtime": 1.0}],
        ids=["legacy-x-0"],
    )
    plan = ingest(store, data_dir)
    assert X in plan.updated
    assert X not in plan.new
    x_chunks = chunks_for(store, X)
    assert x_chunks
    assert all(c["meta"].get(HASH_KEY) == content_hash((data_dir / "x.md").read_bytes()) for c in x_chunks)
    assert not any(c["doc"] == "legacy chunk text" for c in x_chunks)


def test_migration_second_run_unchanged(store, data_dir):
    """Covers: AC-8 (right). After migration the source is unchanged on the next run."""
    store.add_texts(["legacy"], metadatas=[{"source": X, "mtime": 1.0}], ids=["legacy-x-0"])
    ingest(store, data_dir)
    plan = ingest(store, data_dir)
    assert X in plan.unchanged
    assert plan.updated == ()


def test_every_chunk_carries_hash_and_existing_metadata(store, data_dir):
    """Covers: AC-9 (right), INGEST-8. HASH_KEY equals content_hash of the file bytes; other keys kept."""
    ingest(store, data_dir)
    expected = {X: content_hash((data_dir / "x.md").read_bytes()), Y: content_hash((data_dir / "sub" / "y.md").read_bytes())}
    for src, h in expected.items():
        chunks = chunks_for(store, src)
        assert chunks
        for c in chunks:
            assert c["meta"][HASH_KEY] == h
            for key in ("source", "category", "domain", "chunk_index"):
                assert key in c["meta"]


def test_hash_changes_after_edit(store, data_dir):
    """Covers: AC-9 (boundary). After an edit the stored hash equals the new bytes' hash."""
    ingest(store, data_dir)
    (data_dir / "x.md").write_text("New body text for hashing.", encoding="utf-8")
    ingest(store, data_dir)
    h = content_hash((data_dir / "x.md").read_bytes())
    assert {c["meta"][HASH_KEY] for c in chunks_for(store, X)} == {h}


def test_ingest_file_three_positional_args(store, data_dir):
    """Covers: AC-9 (right), INGEST-9. ingest_file(store, path, 123.0) returns chunks > 0 and hashes them."""
    path = data_dir / "x.md"
    n = ingest_file(store, path, 123.0)
    assert n > 0
    d = dump(store)
    assert len(d["ids"]) == n
    h = content_hash(path.read_bytes())
    assert all(m.get(HASH_KEY) == h for m in d["metadatas"])


def test_ingest_file_mtime_optional(store, data_dir):
    """Covers: AC-9 (boundary). mtime may be omitted."""
    assert ingest_file(store, data_dir / "x.md") > 0


def test_ingest_file_mtime_plays_no_part(store, data_dir):
    """Covers: AC-9 (boundary), AC-5 (right). Different mtime arguments do not change the stored hash."""
    path = data_dir / "x.md"
    ingest_file(store, path, 1.0)
    h1 = {c["meta"][HASH_KEY] for c in dump_chunks(store)}
    ingest_file(store, path, 999.0)
    h2 = {c["meta"][HASH_KEY] for c in dump_chunks(store)}
    assert h1 == h2 == {content_hash(path.read_bytes())}


def dump_chunks(store):
    d = dump(store)
    return [{"meta": m} for m in d["metadatas"]]


def test_no_md_files_is_noop(store, data_dir, tmp_path):
    """Covers: AC-10 (right), INGEST-10. Only a.json in data_dir: empty plan, store untouched."""
    ingest(store, data_dir)
    before = sorted(dump(store)["ids"])
    only_json = tmp_path / "only_json"
    only_json.mkdir()
    (only_json / "a.json").write_text("{}", encoding="utf-8")
    plan = ingest(store, only_json)
    assert plan.new == () and plan.updated == () and plan.unchanged == () and plan.deleted == ()
    assert sorted(dump(store)["ids"]) == before
    assert count(store) > 0


def test_empty_data_dir_is_noop(store, data_dir, tmp_path):
    """Covers: AC-10 (boundary). A completely empty data_dir deletes nothing."""
    ingest(store, data_dir)
    before = count(store)
    empty = tmp_path / "empty"
    empty.mkdir()
    plan = ingest(store, empty)
    assert plan.deleted == ()
    assert count(store) == before


def test_missing_data_dir_raises_and_store_unchanged(store, data_dir, tmp_path):
    """Covers: AC-10 (wrong), INGEST-11. Missing dir -> FileNotFoundError, chunk count unchanged."""
    ingest(store, data_dir)
    before = sorted(dump(store)["ids"])
    with pytest.raises(FileNotFoundError):
        ingest(store, tmp_path / "does_not_exist")
    assert sorted(dump(store)["ids"]) == before


def test_missing_data_dir_on_empty_store(store, tmp_path):
    """Covers: AC-10 (wrong). Missing dir with an empty store still raises."""
    with pytest.raises(FileNotFoundError):
        ingest(store, tmp_path / "nope")
    assert count(store) == 0


def test_mixed_new_updated_deleted_in_one_run(store, data_dir):
    """Covers: AC-2/AC-5/AC-6 (right). New, edited and deleted files are classified in a single run."""
    ingest(store, data_dir)
    (data_dir / "x.md").write_text("Edited x content for the mixed run.", encoding="utf-8")
    (data_dir / "sub" / "y.md").unlink()
    (data_dir / "w.md").write_text("Brand new w file.", encoding="utf-8")
    plan = ingest(store, data_dir)
    assert plan.new == ("data/w.md",)
    assert plan.updated == (X,)
    assert plan.deleted == (Y,)
    assert plan.unchanged == ()
    assert chunks_for(store, Y) == []


def test_persisted_store_reopened_is_unchanged(tmp_path, data_dir):
    """Covers: AC-4 (boundary). A fresh Chroma object on the same persisted dir sees the hashes (fresh CI-style run)."""
    s1 = make_store(tmp_path / "persist")
    ingest(s1, data_dir)
    s2 = make_store(tmp_path / "persist")
    plan = ingest(s2, data_dir)
    assert plan.unchanged == (Y, X) or set(plan.unchanged) == {X, Y}
    assert plan.new == () and plan.updated == ()


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.mark.integration
def test_real_ollama_two_real_files_new_then_unchanged(tmp_path):
    """Covers: AC-15 (right), INGEST-12. Real embeddings: first run new, second run unchanged."""
    if not _ollama_up():
        pytest.skip("Ollama is not running.")
    import shutil

    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings

    from ingest import DATA_DIR

    real = sorted(DATA_DIR.rglob("*.md")) if DATA_DIR.exists() else []
    if len(real) < 2:
        pytest.skip("Fewer than two real markdown files under data/.")
    src_dir = tmp_path / "data"
    for f in real[:2]:
        dest = src_dir / f.relative_to(DATA_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, dest)
    store = Chroma(
        collection_name="spec036_integration",
        embedding_function=OllamaEmbeddings(model="nomic-embed-text"),
        persist_directory=str(tmp_path / "chroma"),
    )
    first = ingest(store, src_dir)
    assert len(first.new) == 2
    assert first.updated == () and first.unchanged == () and first.deleted == ()
    second = ingest(store, src_dir)
    assert second.unchanged == first.new
    assert second.new == () and second.updated == () and second.deleted == ()
