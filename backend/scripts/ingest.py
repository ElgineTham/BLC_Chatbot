"""Ingest Bay Laurel markdown docs into a local Chroma vector store."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_ollama import OllamaEmbeddings  # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

from blc.ingest import (  # noqa: E402
    HASH_KEY,
    PER_BULLET_SOURCES,
    IngestPlan,
    chunk_per_bullet,
    content_hash,
    plan_changes,
)
from blc.retrieval import domain_for  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
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


def chunk_markdown(text: str, per_bullet: bool = False) -> list[str]:
    if per_bullet:
        return chunk_per_bullet(text)

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


def stored_hashes(store: Chroma) -> dict[str, str | None]:
    """Map source path -> stored content hash (None if any chunk lacks one)."""
    result = store.get(include=["metadatas"])
    hashes: dict[str, str | None] = {}
    for meta in result.get("metadatas") or []:
        source = (meta or {}).get("source")
        if not source:
            continue
        digest = meta.get(HASH_KEY)
        if source not in hashes:
            hashes[source] = digest
        elif digest is None:
            hashes[source] = None
    return hashes


def scan_data_dir(data_dir: Path) -> dict[str, tuple[Path, str]]:
    """Map source path -> (file, content hash) for every .md under data_dir."""
    found: dict[str, tuple[Path, str]] = {}
    for path in sorted(data_dir.rglob("*.md")):
        source = "data/" + path.relative_to(data_dir).as_posix()
        found[source] = (path, content_hash(path.read_bytes()))
    return found


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


def write_file(
    store: Chroma, path: Path, source: str, mtime: float | None = None
) -> int:
    """Replace the chunks of `source` with the chunks of the file at `path`."""
    raw = path.read_bytes()
    digest = content_hash(raw)
    chunks = chunk_markdown(
        raw.decode("utf-8"), per_bullet=source in PER_BULLET_SOURCES
    )
    delete_source(store, source)
    if not chunks:
        print(f"skip empty: {source}")
        return 0

    documents = []
    for index, chunk in enumerate(chunks):
        metadata: dict[str, str | int | float] = {
            "source": source,
            "category": category_for(path),
            "domain": domain_for(source),
            HASH_KEY: digest,
            "chunk_index": index,
        }
        if mtime is not None:
            metadata["mtime"] = mtime
        documents.append(Document(page_content=chunk, metadata=metadata))
    store.add_documents(documents)
    return len(documents)


def ingest_file(store: Chroma, path: Path, mtime: float | None = None) -> int:
    try:
        source = relative_source(path)
    except ValueError:
        source = path.as_posix()
    return write_file(store, path, source, mtime)


def ingest(store: Chroma, data_dir: Path = DATA_DIR) -> IngestPlan:
    """Bring `store` in line with data_dir/**/*.md and return the plan applied."""
    if not data_dir.exists():
        raise FileNotFoundError(f"data directory not found: {data_dir}")

    files = scan_data_dir(data_dir)
    if not files:
        return IngestPlan((), (), (), ())

    plan = plan_changes(
        {source: digest for source, (_, digest) in files.items()},
        stored_hashes(store),
    )
    for source in plan.deleted:
        delete_source(store, source)
        print(f"deleted: {source}")
    for reason, sources in (("new", plan.new), ("updated", plan.updated)):
        for source in sources:
            count = write_file(store, files[source][0], source)
            print(f"ingest ({reason}): {source} -> {count} chunk(s)")
    for source in plan.unchanged:
        print(f"skip unchanged: {source}")
    return plan


def main() -> int:
    if not DATA_DIR.exists():
        print(f"data directory not found: {DATA_DIR}", file=sys.stderr)
        return 1

    plan = ingest(build_store(), DATA_DIR)
    print(
        f"done: {len(plan.new)} new, {len(plan.updated)} updated, "
        f"{len(plan.unchanged)} unchanged, {len(plan.deleted)} deleted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
