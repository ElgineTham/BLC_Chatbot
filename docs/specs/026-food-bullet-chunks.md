# Spec 026: One chunk per bullet for the food menu

- **Status:** complete (all tests pass; food hit rate 90%, 27/30; verified manually by the user 2026-11-16)
- **Date:** 2026-11-16

## 1. Goal
Spec 025 measured food-menu retrieval at 86.67% (26/30) against a 90% bar. The misses (e.g. "Where is dijon mustard" ranks the Lunch chunk 8th) come from large section chunks in which one item is a few lines among many. Split `data/pull_sheet/menu/food.md` into **one chunk per bullet**, and give every chunk its **context**: the file's `# title` line and its `## section` heading, so a bullet such as "in the hot box" is never stored without knowing which item and section it belongs to. Then re-measure with the spec 025 eval.

## 2. Out of scope
- Changing `TOP_K`, `retrieve`, `chat.py`, the embedding model, `MAX_TOKENS`, or the prompt.
- Bullet chunking for any file other than `food.md` (the other files keep today's chunks). Extending it later is a new spec.
- Fixing the intro (preamble) chunk, list questions ("what's in the hot box?") needing several chunks, or phrasing fragility. If the 90% bar is not reached, the result is reported and the next step is decided with the user.
- Editing `food.md`, the golden files, or the spec 025 `RET`/`GOLD` tests.
- Running `ingest.py` on the real store from a test. The planner wipes `.chroma/` and re-ingests by hand before the eval.

## 3. Interface contract
```python
# scripts/ingest.py   (feature code may live in src/blc/ingest/ and be re-exported here)
PER_BULLET_SOURCES: tuple[str, ...]   # == ("data/pull_sheet/menu/food.md",)

def chunk_markdown(text: str, per_bullet: bool = False) -> list[str]:
    """per_bullet=False behaves exactly as before this spec."""

def ingest_file(store: Chroma, path: Path, mtime: float) -> int:
    """Signature unchanged. A file whose relative_source(path) is in PER_BULLET_SOURCES is chunked
    with per_bullet=True; every other file with per_bullet=False. Returns chunks written."""
```
Unchanged and still used by tests: `ROOT`, `DATA_DIR`, `COLLECTION_NAME`, `EMBED_MODEL`, `MAX_TOKENS`, `relative_source`, and from `scripts/chat.py` `CHROMA_DIR`, `TOP_K`, `build_store`, `retrieve`.

A **bullet** is a line starting with `- `, together with any indented continuation lines directly under it. **Context** of a chunk is the document's `# ` title line and the `## ` heading of the section it came from.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `chunk_markdown(text, per_bullet=True)` | markdown str | any | one chunk per bullet, each with context; other text kept |
| `chunk_markdown(text)` | markdown str | any | same output as before this spec |
| `ingest_file(store, food.md path, mtime)` | temp Chroma, Path, float | real embeddings | one stored document per chunk of the per-bullet chunking |

## 5. Acceptance criteria
- **AC-1:** With `per_bullet=True`, each bullet line of a section is in **exactly one** chunk, and that chunk holds no other bullet of the section.
- **AC-2:** With `per_bullet=True`, every chunk that comes from a `## ` section contains the document's `# ` title line, then the section's `## ` heading line, then its content, in that order.
- **AC-3:** A bullet's continuation lines stay in the same chunk as the bullet.
- **AC-4:** With `per_bullet=True`, non-bullet text is not lost: every non-blank line of the input appears (after stripping) in at least one chunk, including text under a section that has no bullets and text before the first `## `.
- **AC-5:** `per_bullet=True` splits a document even if it is shorter than `MAX_TOKENS` tokens.
- **AC-6:** With `per_bullet=False`, behaviour is unchanged: on `food.md` each of its nine `## ` sections heads exactly one chunk and no chunk has two `## ` headings (spec 025 ING-3, ING-4 now apply to this call).
- **AC-7** *(integration)*: `ingest_file` of `data/pull_sheet/menu/food.md` into an empty temp store returns `len(chunk_markdown(text, per_bullet=True))`; stored documents have `source == "data/pull_sheet/menu/food.md"`, `category == "pull_sheet"`, `chunk_index` `0..n-1`; a second ingest leaves the count unchanged. `ingest_file` of `data/supplies/coffee.md` stores `len(chunk_markdown(text))` documents.
- **AC-8** *(eval)*: After the planner wipes `.chroma/` and re-ingests, spec 025's `test_food_hit_rate` passes (pass rate ≥ 0.90), and all 20 cases in `tests/test_retrieval_eval.py` still pass. If the food rate is below 0.90, the failing cases are reported and nothing is weakened.
- **AC-9** *(manual)*: Only `scripts/ingest.py` and an optional new `src/blc/ingest/` package change in the implementation; `chat.py`, `data/`, golden files and the spec 025 `RET`/`GOLD` tests are untouched. The tester updates only `tests/food_retrieval/test_ingest.py` (spec 025 ING-3..ING-5 as noted in AC-6/AC-7) and adds new tests in `tests/food_retrieval/`.

## 6. Test cases
Example used below (call it `DOC`):
```
# Menu

Intro line.

## Bakery
- **Bagels**: on the rack.
  Served with cream cheese.
- **Cream cheese**: in the cooler.

## Notes
Plain paragraph.
```

### 6.1 CHUNK (unit, `chunk_markdown`)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| CHUNK-1 | `DOC`, `per_bullet=True` | Bagels and Cream cheese bullets are in different chunks; each bullet line in exactly one chunk | AC-1 |
| CHUNK-2 | `DOC`, `per_bullet=True`, chunk with Bagels | contains `# Menu`, then `## Bakery`, then the bullet | AC-2 |
| CHUNK-3 | `DOC`, `per_bullet=True`, Notes chunk | contains `# Menu`, `## Notes`, `Plain paragraph.` | AC-2, AC-4 |
| CHUNK-4 | `DOC`, `per_bullet=True` | "Served with cream cheese." is in the same chunk as the Bagels bullet and not in the Cream cheese chunk | AC-3 |
| CHUNK-5 | `DOC`, `per_bullet=True` | "Intro line." appears in some chunk; no non-blank line of `DOC` is lost | AC-4 |
| CHUNK-6 | `DOC` (a few tokens), `per_bullet=True` | still more than one chunk | AC-5 |
| CHUNK-7 | `DOC`, default call | same result as `per_bullet=False` | AC-6 |
| CHUNK-8 | `food.md`, `per_bullet=False` | nine headings each head exactly one chunk; no chunk has two `## ` | AC-6 |
| CHUNK-9 | `food.md`, `per_bullet=True` | each `- ` line of the file is in exactly one chunk | AC-1 |
| CHUNK-10 | `food.md`, `per_bullet=True`, chunk with `**Dijon mustard**` | has title, `## Lunch`, and no other item's bullet (e.g. not `Mayonnaise`) | AC-1, AC-2 |
| CHUNK-11 | `food.md`, `per_bullet=True` | every non-blank line is in some chunk; every `**item**` name is in some chunk | AC-4 |
| CHUNK-12 | `PER_BULLET_SOURCES` | equals `("data/pull_sheet/menu/food.md",)` | AC-7 |

### 6.2 STORE (integration, temp store, real embeddings)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| STORE-1 | `ingest_file` food.md | returns `len(chunk_markdown(text, per_bullet=True))` | AC-7 |
| STORE-2 | stored metadata | source, category `pull_sheet`, chunk_index `0..n-1` | AC-7 |
| STORE-3 | ingest food.md twice | stored count unchanged | AC-7 |
| STORE-4 | `ingest_file` data/supplies/coffee.md | stored count = `len(chunk_markdown(text))` | AC-7 |
| STORE-5 | Ollama not running | integration tests skip | AC-7 |

### 6.3 EVAL (real store, after planner re-ingest)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| EVAL-1 | spec 025 `test_food_hit_rate` | pass rate ≥ 0.90 | AC-8 |
| EVAL-2 | `tests/test_retrieval_eval.py` | all 20 cases pass | AC-8 |
| EVAL-3 | previously missed `dijon-mustard`, `danish-beo`, `tabbouleh-serves`, `service-room-rack` | reported individually (pass or fail) in the failure message / run output | AC-8 |
