# Spec 025: Ingest the food menu and test its retrieval

- **Status:** approved
- **Date:** 2026-11-16

## 1. Goal
`data/pull_sheet/menu/food.md` lists the food items the pull crew pulls, how each appears on a BEO, and where it is stored. It must be ingested into the vector store with the **existing** chunking and parameters, and a golden set of 30 questions must show whether the right part of the file comes back for each question. If the numbers are poor, a later spec will change chunking or retrieval; this one only measures.

## 2. Out of scope
- Any change to `scripts/ingest.py`, `scripts/chat.py`, `TOP_K`, chunk sizes, the embedding model or the prompt. Poor results are reported, not fixed here.
- Answer quality (generation, judge). Only which chunks are retrieved.
- Out-of-scope / abstain questions, multi-turn questions, and the router or tools.
- Editing `food.md` (the user owns it) and the existing `evals/retrieval/golden.jsonl` and `tests/test_retrieval_eval.py`.
- Running `scripts/ingest.py` on the real store from a test. The planner runs it by hand before the eval.

## 3. Interface contract
All names below exist already and are **unchanged**; tests only use them.

```python
# scripts/ingest.py
ROOT: Path; DATA_DIR: Path          # DATA_DIR = ROOT / "data"
COLLECTION_NAME: str                # "blc_knowledge"
EMBED_MODEL: str                    # "nomic-embed-text"
MAX_TOKENS: int                     # 500
def chunk_markdown(text: str) -> list[str]: ...
def ingest_file(store: Chroma, path: Path, mtime: float) -> int: ...   # returns number of chunks written
def relative_source(path: Path) -> str: ...

# scripts/chat.py
CHROMA_DIR: Path
TOP_K: int                          # 3
def build_store() -> Chroma: ...    # opens the real .chroma/
def retrieve(store: Chroma, question: str) -> list[Document]: ...
```

Each stored/retrieved `Document` has `metadata["source"]` (path from project root), `metadata["category"]`, `metadata["chunk_index"]` and `page_content` (the chunk text).

**Golden file (new data, written by the planner):** `evals/retrieval/food_golden.jsonl`, one JSON object per line:
`{"id": str, "question": str, "expected_source": "data/pull_sheet/menu/food.md", "expected_chunks": [{"heading": str, "must_contain": [str, ...]}, ...], "notes": str}`.
Each expected chunk names a `## ` heading of `food.md` (exact text, e.g. `"Bakery"`) and the item names (`must_contain`, non-empty, text as written in `food.md`) the chunk must carry. A chunk **has heading H** when its `page_content` contains a line equal to `## H`.

**Case passes** when, for every entry in `expected_chunks`, at least one of the `TOP_K` documents returned by `retrieve(store, question)` has `metadata["source"] == expected_source`, has that entry's heading, and its `page_content` contains every `must_contain` string (case-insensitive). So a case checks both that the right section came back and that it holds the asked item.

**Eval threshold constant** (defined in the test module): `MIN_HIT_RATE = 0.90`.

Files read: `data/pull_sheet/menu/food.md`, `evals/retrieval/food_golden.jsonl`, the real `.chroma/`. Tests write nothing outside pytest temp dirs.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `chunk_markdown(food.md text)` | str | the file's content | list of chunk strings |
| `ingest_file(tmp_store, food.md path, mtime)` | temp Chroma, Path, float | real embeddings | chunks stored with source, category, chunk_index |
| Golden question | str | 30 cases in §6.3 | `TOP_K` retrieved docs from the real store |

## 5. Acceptance criteria
- **AC-1** *(manual)*: `scripts/ingest.py` and `scripts/chat.py` are unchanged by this spec's round; no file outside `tests/food_retrieval/` and `evals/retrieval/food_golden.jsonl` is added or changed by the tester.
- **AC-2:** `chunk_markdown` on `food.md` returns non-blank chunks, and every bolded item name in the file (text between `**` `**`) appears in at least one chunk (nothing is lost).
- **AC-3:** Each of the nine `## ` sections of `food.md` (Storage locations, Hot breakfast, Bakery, Yogurt, Fruit, Snacks, Lunch, Desserts and cookies, Breakfast packages) is the heading of exactly one chunk, and no chunk has two `## ` headings.
- **AC-4** *(integration)*: `ingest_file` into an empty temp store with real embeddings returns the chunk count of `chunk_markdown`; the stored documents all have `source == "data/pull_sheet/menu/food.md"`, `category == "pull_sheet"` and `chunk_index` values `0..n-1`; ingesting the same file a second time leaves the same number of stored documents.
- **AC-5:** The golden file has 20–30 cases, unique non-empty ids, non-empty questions, `expected_source` equal to the food.md path, and at least one expected chunk per case, each with a non-empty `must_contain`; every expected heading is a real `## ` heading in `food.md`, and every `must_contain` string appears (case-insensitive) in the section of `food.md` under that heading; at least 3 cases expect two or more chunks.
- **AC-6** *(eval)*: Against the real store, the fraction of golden cases that pass is at least `MIN_HIT_RATE`. The failure message lists every failing case: id, question, expected chunks, and for each retrieved document its heading and which `must_contain` strings it lacks.
- **AC-7** *(eval)*: Each case is run with `retrieve(store, question)` only (no rewriting, no tools). Cases are reported individually (their ids are visible in the output) but only the overall rate is asserted.
- **AC-8:** Integration and eval tests skip with a clear message when Ollama is not running, or (eval only) when the real store has no documents with the food.md source ("run scripts/ingest.py first").
- **AC-9** *(manual)*: Tests live in `tests/food_retrieval/`, integration and eval tests carry the `integration` / `eval` markers, files stay under ~400 lines, and tests import only the names in §3.

## 6. Test cases
### 6.1 ING (chunking and ingest)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ING-1 | `chunk_markdown(food.md)` | all chunks non-blank | AC-2 |
| ING-2 | every `**item**` in food.md | each found in some chunk | AC-2 |
| ING-3 | the nine `## ` headings | each heads exactly one chunk | AC-3 |
| ING-4 | all chunks | none contains two `## ` headings | AC-3 |
| ING-5 | `ingest_file` into temp store | returns `len(chunk_markdown(text))` | AC-4 |
| ING-6 | stored metadata | source, category `pull_sheet`, chunk_index `0..n-1` | AC-4 |
| ING-7 | ingest the same file twice | stored count unchanged | AC-4 |
| ING-8 | Ollama not running | integration tests skip | AC-8 |

### 6.2 GOLD (golden file validity)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| GOLD-1 | load `food_golden.jsonl` | 20–30 cases, unique ids | AC-5 |
| GOLD-2 | each case's fields | question, source, chunks and non-empty `must_contain` present and valid | AC-5 |
| GOLD-3 | each expected heading and its `must_contain` | heading exists in food.md and its section contains each string | AC-5 |
| GOLD-4 | cases with 2+ expected chunks | at least 3 | AC-5 |

### 6.3 RET (retrieval, real store)
Case ids are the ids in the golden file. Overall pass rate must be at least `MIN_HIT_RATE` (AC-6); the table is what each case expects.

| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| RET-1 | `eggs-where`: "Where are the scrambled eggs?" | top-3 has Hot breakfast chunk with Scrambled eggs | AC-6, AC-7 |
| RET-2 | `eggs-beo`: "The BEO says "Organic, cage-free eggs scrambled with cheddar cheese". Where do I find it?" | top-3 has Hot breakfast chunk with Organic, cage-free eggs | AC-6, AC-7 |
| RET-3 | `sausage-where`: "Where do I find the chicken apple sausage?" | top-3 has Hot breakfast chunk with Chicken-apple sausage | AC-6, AC-7 |
| RET-4 | `muffins-where`: "Where are the breakfast muffins?" | top-3 has Bakery chunk with Breakfast muffins | AC-6, AC-7 |
| RET-5 | `croissants-where`: "Where are the butter croissants?" | top-3 has Bakery chunk with Butter croissants | AC-6, AC-7 |
| RET-6 | `preserves-jam`: "Where is the raspberry jam that goes with the croissants?" | top-3 has Bakery chunk with Raspberry preserves | AC-6, AC-7 |
| RET-7 | `danish-beo`: "BEO line: Fruit danish assortment. Where is it?" | top-3 has Bakery chunk with Fruit danish | AC-6, AC-7 |
| RET-8 | `bagels-cream-cheese`: "Where are the bagels and the cream cheese?" | top-3 has Bakery chunk with Assorted bagels, Cream cheese | AC-6, AC-7 |
| RET-9 | `gf-pastry`: "Where is the gluten-free vegan pastry?" | top-3 has Bakery chunk with Gluten-free vegan pastry | AC-6, AC-7 |
| RET-10 | `greek-yogurt`: "Where is the Greek yogurt?" | top-3 has Yogurt chunk with Greek yogurt | AC-6, AC-7 |
| RET-11 | `vegan-yogurt-beo`: "BEO line: Vegan Yogurt - coconut vanilla. Where do I get it?" | top-3 has Yogurt chunk with Vegan yogurt | AC-6, AC-7 |
| RET-12 | `honey-parfait`: "Where is the honey for the yogurt?" | top-3 has Yogurt chunk with Honey | AC-6, AC-7 |
| RET-13 | `granola-berries`: "Where do I find the granola and the fresh berries?" | top-3 has Yogurt chunk with Granola, Fresh berries | AC-6, AC-7 |
| RET-14 | `fruit-tray`: "Where is the medium market fresh fruit tray?" | top-3 has Fruit chunk with Market fresh fruit tray | AC-6, AC-7 |
| RET-15 | `whole-fruit`: "Where can I get whole fresh fruit for a fruit basket?" | top-3 has Fruit chunk with Whole fresh fruit | AC-6, AC-7 |
| RET-16 | `trail-mix`: "Where is the trail mix?" | top-3 has Snacks chunk with Trail mix | AC-6, AC-7 |
| RET-17 | `popcorn-bags`: "Where are the bags of white cheddar popcorn?" | top-3 has Snacks chunk with White cheddar popcorn | AC-6, AC-7 |
| RET-18 | `deli-sandwiches`: "Where are the classic deli sandwiches?" | top-3 has Lunch chunk with Classic deli sandwiches | AC-6, AC-7 |
| RET-19 | `tabbouleh-serves`: "How many people does the quinoa chickpea tabbouleh salad serve?" | top-3 has Lunch chunk with Quinoa-chickpea tabbouleh | AC-6, AC-7 |
| RET-20 | `box-meals`: "Where do I find the boxed lunches?" | top-3 has Lunch chunk with Box meals | AC-6, AC-7 |
| RET-21 | `bottled-water`: "We need bottled waters for the boxed lunches. Where are they?" | top-3 has Lunch chunk with Bottled water | AC-6, AC-7 |
| RET-22 | `dijon-mustard`: "Where is the Dijon mustard?" | top-3 has Lunch chunk with Dijon mustard | AC-6, AC-7 |
| RET-23 | `brownies-petite`: "Where are the petite chocolate brownies?" | top-3 has Desserts and cookies chunk with Chocolate brownies | AC-6, AC-7 |
| RET-24 | `dessert-bars`: "Where are the gourmet dessert bars?" | top-3 has Desserts and cookies chunk with Gourmet dessert bars | AC-6, AC-7 |
| RET-25 | `cascade-contents`: "What is in the Cascade Breakfast?" | top-3 has Breakfast packages chunk with Cascade Breakfast | AC-6, AC-7 |
| RET-26 | `olympic-vs-cascade`: "What is the difference between the Olympic and Cascade breakfast packages?" | top-3 has Breakfast packages chunk with Cascade Breakfast, Olympic Breakfast | AC-6, AC-7 |
| RET-27 | `hot-box-contents`: "What is kept in the hot box?" | top-3 has Hot breakfast chunk with Scrambled eggs, Chicken-apple sausage, Roasted breakfast potatoes | AC-6, AC-7 |
| RET-28 | `service-room-rack`: "What is on the metal rack in the service room near the manager's table?" | top-3 has Bakery chunk with Breakfast muffins and Snacks chunk with Trail mix | AC-6, AC-7 |
| RET-29 | `croissant-and-yogurt`: "Where are the croissants and the Greek yogurt?" | top-3 has Bakery chunk with Butter croissants and Yogurt chunk with Greek yogurt | AC-6, AC-7 |
| RET-30 | `freshly-cut-platter`: "Where do I find the freshly cut fruit platter for the Olympic breakfast?" | top-3 has Fruit chunk with Market fresh fruit tray and Breakfast packages chunk with Olympic Breakfast | AC-6, AC-7 |
| RET-31 | whole golden set | pass rate ≥ `MIN_HIT_RATE`; failure message lists failing cases with retrieved headings | AC-6, AC-7 |
| RET-32 | real store has no food.md documents | eval skips with "run scripts/ingest.py first" | AC-8 |
