"""Ingest Bay Laurel markdown docs into a local Chroma vector store."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CHROMA_DIR = ROOT / ".chroma"
COLLECTION_NAME = "blc_knowledge"
EMBED_MODEL = "nomic-embed-text"
MAX_TOKENS = 500
# Rough English estimate used for the size threshold and hard splits.
CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def extract_h1(text: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def split_on_h2(text: str) -> list[str]:
    """Split markdown into sections starting at ## headings (preamble kept)."""
    parts = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)
    return [part.strip() for part in parts if part.strip()]


def hard_split(text: str, max_tokens: int = MAX_TOKENS) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_tokens * CHARS_PER_TOKEN,
        chunk_overlap=max(50, max_tokens * CHARS_PER_TOKEN // 10),
        separators=["\n\n", "\n", " ", ""],
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def chunk_markdown(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    if count_tokens(text) <= MAX_TOKENS:
        return [text]

    title = extract_h1(text)
    sections = split_on_h2(text)
    chunks: list[str] = []

    for section in sections:
        if title and not section.lstrip().startswith("#"):
            piece = f"# {title}\n\n{section}".strip()
        elif title and section.lstrip().startswith("##"):
            piece = f"# {title}\n\n{section}".strip()
        else:
            piece = section

        if count_tokens(piece) <= MAX_TOKENS:
            chunks.append(piece)
        else:
            chunks.extend(hard_split(piece))

    return chunks


def relative_source(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def category_for(path: Path) -> str:
    try:
        return path.relative_to(DATA_DIR).parts[0]
    except ValueError:
        return "unknown"


def existing_mtimes(store: Chroma) -> dict[str, float]:
    """Map source path -> stored mtime (one value per file)."""
    result = store.get(include=["metadatas"])
    mtimes: dict[str, float] = {}
    metadatas = result.get("metadatas") or []
    for meta in metadatas:
        if not meta:
            continue
        source = meta.get("source")
        if not source:
            continue
        raw = meta.get("mtime")
        if raw is None:
            continue
        mtimes[source] = float(raw)
    return mtimes


def delete_source(store: Chroma, source: str) -> None:
    existing = store.get(where={"source": source}, include=[])
    ids = existing.get("ids") or []
    if ids:
        store.delete(ids=ids)


def build_store() -> Chroma:
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def ingest_file(store: Chroma, path: Path, mtime: float) -> int:
    text = path.read_text(encoding="utf-8")
    chunks = chunk_markdown(text)
    if not chunks:
        print(f"skip empty: {relative_source(path)}")
        return 0

    source = relative_source(path)
    delete_source(store, source)

    documents = [
        Document(
            page_content=chunk,
            metadata={
                "source": source,
                "category": category_for(path),
                "mtime": mtime,
                "chunk_index": index,
            },
        )
        for index, chunk in enumerate(chunks)
    ]
    store.add_documents(documents)
    return len(documents)


def main() -> int:
    if not DATA_DIR.exists():
        print(f"data directory not found: {DATA_DIR}", file=sys.stderr)
        return 1

    md_files = sorted(DATA_DIR.rglob("*.md"))
    if not md_files:
        print(f"no markdown files under {DATA_DIR}")
        return 0

    store = build_store()
    known = existing_mtimes(store)

    ingested = 0
    skipped = 0
    chunk_count = 0

    for path in md_files:
        source = relative_source(path)
        mtime = path.stat().st_mtime
        stored = known.get(source)

        if stored is not None and mtime <= stored:
            print(f"skip unchanged: {source}")
            skipped += 1
            continue

        reason = "new" if stored is None else "updated"
        n_chunks = ingest_file(store, path, mtime)
        if n_chunks == 0:
            skipped += 1
            continue

        print(f"ingest ({reason}): {source} -> {n_chunks} chunk(s)")
        ingested += 1
        chunk_count += n_chunks

    print(
        f"done: ingested {ingested} file(s), "
        f"skipped {skipped}, wrote {chunk_count} chunk(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
