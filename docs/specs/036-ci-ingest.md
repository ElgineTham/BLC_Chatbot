# Spec 036: Chroma store in git, ingested by GitHub Actions

- **Status:** complete (all 58 unit tests and the AC-15 integration test pass after one fix round on `.gitignore`; manual ACs 13, 14, 16 checked by the planner; full-suite regression not run; marked complete by the user 2026-11-17)
- **Date:** 2026-11-17

## 1. Goal
Anyone who pulls the repo gets an up-to-date vector store without running ingest. The knowledge files (`data/**/*.md`) and the Chroma store (`.chroma/`) are committed, and a GitHub Actions workflow re-ingests whenever a markdown file under `data/` is added, changed or deleted on `main`, then commits the updated `.chroma/` back. To make that work on a fresh CI checkout, ingest stops using file modification times: it re-embeds a file only when its **content** changes, and removes the chunks of files that no longer exist.

Decided with the user: the repo stays **public**, so everything committed under `data/` and `.chroma/` (which stores chunk text verbatim) is publicly readable.

## 2. Out of scope
- Making the repo private, secrets handling, encrypting `data/` or `.chroma/`.
- Committing anything else under `data/`: JSON tool data (recipes, pull-sheet menu/rules) and photos stay gitignored, so a fresh clone has the vector store but not the tools' data files.
- Building or pushing Docker images in CI; running the pytest suite in CI.
- Changing chunking, embedding model, collection name, retrieval or chat.
- Resolving merge conflicts in `.chroma/` (only the workflow commits it; see AC-12).
- Pinning the `nomic-embed-text` digest between CI and local machines.
- Non-UTF-8 markdown (behaviour unchanged).

## 3. Interface contract
```python
# backend/src/blc/ingest/changes.py  (re-exported from backend/scripts/ingest.py)
HASH_KEY = "content_hash"          # chunk metadata key holding the file's content hash

@dataclass(frozen=True)
class IngestPlan:
    new: tuple[str, ...]           # each tuple holds source paths, sorted ascending
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    deleted: tuple[str, ...]

def content_hash(data: bytes) -> str:
    """Lowercase hex SHA-256 of the raw bytes (64 chars)."""

def plan_changes(current: Mapping[str, str], stored: Mapping[str, str | None]) -> IngestPlan:
    """current: source -> hash of each file on disk.
    stored: source -> hash stored in Chroma, or None if that source's chunks carry no hash."""
```

```python
# backend/scripts/ingest.py  (existing entry point; names below are importable from it)
DATA_DIR: Path                     # unchanged: <repo>/data

def ingest(store: Chroma, data_dir: Path = DATA_DIR) -> IngestPlan:
    """Brings `store` in line with data_dir/**/*.md and returns the plan it applied.
    Raises FileNotFoundError if data_dir does not exist (store untouched)."""

def ingest_file(store: Chroma, path: Path, mtime: float | None = None) -> int:
    """Unchanged return value (chunks written). `mtime` is optional and plays no part in change detection."""
```
- **Source path** of a file = `"data/"` + its POSIX path relative to `data_dir` (e.g. `data/recipes/pasta.md`); same values as today for the real `data/`.
- Every chunk written by `ingest` / `ingest_file` has metadata `HASH_KEY` = `content_hash(<file bytes>)`, plus the existing `source`, `category`, `domain`, `chunk_index`.
- `store` may be any `langchain_chroma.Chroma` (tests use a temp dir and fake embeddings).
- `main()` exit codes unchanged: 1 if `data/` is missing, else 0.

**Files:**
- `.gitignore`: `.chroma/` no longer ignored; under `data/` only `*.md` files (any depth) are not ignored.
- `.github/workflows/ingest.yml` (YAML; note PyYAML loads the `on:` key as boolean `True`):
```text
triggers        : push to branch main, filtered by paths containing "data/**/*.md"
                  workflow_dispatch
permissions     : contents: write
concurrency     : group "ingest", cancel-in-progress false
commit message  : contains "[skip ci]"
```

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `ingest(store, data_dir)` | Chroma, dir | dir exists | store matches the `.md` files; returns `IngestPlan` |
| file new / edited / unchanged / deleted | `.md` under `data_dir` | — | embedded / re-embedded / untouched / chunks removed |
| `data_dir` has no `.md` files | — | — | store untouched, all-empty plan (no mass delete) |
| `data_dir` missing | — | — | `FileNotFoundError`, store untouched |
| push to `main` touching `data/**/*.md` | git push | — | workflow ingests, commits `.chroma/` if it changed |
| push touching only code or `.chroma/` | git push | — | workflow does not run |

## 5. Acceptance criteria
- **AC-1:** `content_hash` returns the lowercase hex SHA-256 of its input; equal bytes give equal hashes, any byte difference (including line endings) gives a different hash.
- **AC-2:** `plan_changes` puts a source in `new` if it is only in `current`, `unchanged` if both hashes are equal, `updated` if they differ or the stored hash is `None`, `deleted` if it is only in `stored`. Every source appears in exactly one tuple; each tuple is sorted.
- **AC-3:** `ingest` on an empty store embeds every `.md` file under `data_dir` (any depth) and returns them all in `new`; non-`.md` files are ignored.
- **AC-4:** Running `ingest` a second time with no file changes returns every source in `unchanged` and writes nothing: chunk ids and count in the store stay the same.
- **AC-5:** Changing a file's content (even if its mtime is older, or the same) puts it in `updated` and replaces its chunks: no chunk of the old text remains. Touching a file without changing content (new mtime) leaves it `unchanged`.
- **AC-6:** Deleting a file puts it in `deleted` and removes all its chunks; chunks of other files are untouched.
- **AC-7:** A file whose content becomes empty (no chunks) loses all its old chunks.
- **AC-8:** A store written before this spec (chunks with `mtime` but no `HASH_KEY`) is migrated: those sources are `updated` on the first run, and afterwards carry `HASH_KEY`.
- **AC-9:** Every chunk written by `ingest` / `ingest_file` carries `HASH_KEY` equal to `content_hash` of the file's bytes. `ingest_file(store, path, mtime)` with three positional arguments still works.
- **AC-10:** If `data_dir` contains no `.md` files, `ingest` returns an all-empty plan and deletes nothing, even when the store has chunks. If `data_dir` does not exist it raises `FileNotFoundError` and the store is unchanged.
- **AC-11:** `.gitignore`: `.chroma/chroma.sqlite3` and any `data/**/*.md` are not ignored; `data/recipes/recipes.json`, `data/pull_sheet/rules/food.json`, `data/pull_sheet/examples/IMG_1512.jpg`, other non-md files under `data/`, `.env`, `.venv/` and `logs/` still are (checked with `git check-ignore --no-index`).
- **AC-12:** The workflow file matches §3: triggers on push to `main` with a paths filter that includes `data/**/*.md` and does not include `.chroma` patterns, plus `workflow_dispatch`; `permissions.contents == "write"`; concurrency group `ingest` with `cancel-in-progress` false; a step's command contains `[skip ci]`.
- **AC-13** *(manual)*: The workflow installs Python deps without the `voice` group, installs Ollama and pulls `nomic-embed-text`, runs `backend/scripts/ingest.py`, stages **only** `.chroma/`, and commits and pushes only when `.chroma/` changed (no empty commits).
- **AC-14** *(manual)*: README documents: data and `.chroma/` are committed and the repo is public; the workflow owns `.chroma/` (don't commit local `.chroma/` changes; `git restore .chroma` before pulling); only `data/**/*.md` is committed, so JSON tool data must still be copied to a new machine by hand.
- **AC-15** *(integration)*: With real Ollama, `ingest` on a temp copy of two real `data/` markdown files into a temp store returns both as `new`; a second call returns both as `unchanged`.
- **AC-16** *(manual)*: Only these change: `backend/scripts/ingest.py`, new `backend/src/blc/ingest/changes.py` (and `blc/ingest/__init__.py` exports), `.gitignore`, `.github/workflows/ingest.yml`, `README.md`. `plan_changes` and `content_hash` do no I/O. Chunking output is unchanged.

## 6. Test cases
Unit tests use a Chroma store in `tmp_path` with fake embeddings (e.g. `DeterministicFakeEmbedding`) and a temp `data_dir`. Existing tests calling `ingest_file(store, path, mtime)` must keep passing unchanged.

### 6.1 PLAN (pure functions)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PLAN-1 | `content_hash(b"abc")` | `"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"` | AC-1 |
| PLAN-2 | `b"a\n"` vs `b"a\r\n"` | different hashes | AC-1 |
| PLAN-3 | current `{a:h1}`, stored `{}` | `new=(a,)`, others empty | AC-2 |
| PLAN-4 | current `{a:h1}`, stored `{a:h1}` | `unchanged=(a,)` | AC-2 |
| PLAN-5 | current `{a:h2}`, stored `{a:h1}` | `updated=(a,)` | AC-2 |
| PLAN-6 | current `{a:h1}`, stored `{a:None}` | `updated=(a,)` | AC-2, AC-8 |
| PLAN-7 | current `{}`, stored `{a:h1}` | `deleted=(a,)` | AC-2 |
| PLAN-8 | mixed: c,a new; b unchanged; d deleted | `new=("a","c")`, each source in one tuple only | AC-2 |

### 6.2 INGEST (fake-embedding store)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| INGEST-1 | empty store; `x.md`, `sub/y.md`, `z.json`, `p.jpg` | `new=("data/sub/y.md","data/x.md")`; no chunks for json/jpg | AC-3 |
| INGEST-2 | run twice, no change | 2nd plan all `unchanged`; same chunk ids | AC-4 |
| INGEST-3 | edit `x.md` text, set mtime to 2000-01-01 | `updated` includes x; old text not in store | AC-5 |
| INGEST-4 | `os.utime` on `x.md` only | `unchanged` | AC-5 |
| INGEST-5 | delete `x.md` | `deleted=("data/x.md",)`; no x chunks; y chunks intact | AC-6 |
| INGEST-6 | overwrite `x.md` with `""` | no chunks with source x | AC-7 |
| INGEST-7 | store pre-seeded with chunk `{source: data/x.md, mtime: 1.0}` (no hash) | x in `updated`; after run, all x chunks have `HASH_KEY` | AC-8 |
| INGEST-8 | after ingest, read metadata | every chunk `HASH_KEY == content_hash(bytes)` | AC-9 |
| INGEST-9 | `ingest_file(store, path, 123.0)` | returns chunk count > 0; chunks carry `HASH_KEY` | AC-9 |
| INGEST-10 | store has chunks; `data_dir` holds only `a.json` | all-empty plan; chunk count unchanged | AC-10 |
| INGEST-11 | `data_dir` does not exist | `FileNotFoundError`; chunk count unchanged | AC-10 |
| INGEST-12 | real Ollama, two real data files, run twice | `new` then `unchanged` (skip if Ollama down) | AC-15 |

### 6.3 REPO (`.gitignore` and workflow)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REPO-1 | `git check-ignore --no-index` on `.chroma/chroma.sqlite3`, `data/x.md`, `data/a/b/c.md` | not ignored | AC-11 |
| REPO-2 | same on `data/recipes/recipes.json`, `data/pull_sheet/rules/food.json`, `data/pull_sheet/examples/IMG_1512.jpg`, `data/x.pdf`, `.env`, `logs/a.log` | ignored | AC-11 |
| REPO-3 | load `.github/workflows/ingest.yml` | push branches include `main`; paths include `data/**/*.md`; none contain `.chroma`; `workflow_dispatch` present | AC-12 |
| REPO-4 | same file | `permissions.contents == "write"`; concurrency group `"ingest"`, cancel-in-progress false | AC-12 |
| REPO-5 | same file | some step `run` contains `[skip ci]` | AC-12 |
