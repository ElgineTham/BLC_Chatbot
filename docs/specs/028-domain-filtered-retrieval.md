# Spec 028: Domain-filtered retrieval (food vs beverage)

- **Status:** approved
- **Date:** 2026-11-16

## 1. Goal
A food question can pull beverage-rule chunks into the top 3 just because both say "bring". In the manual chat, "Do we need to bring anything with croissants" got the croissants and preserves chunks plus the beverage "Other supplies" chunk, and the answer listed "Cocktail napkins". Give every chunk a **domain** label (`food` or `beverage`), detect which domain(s) a question is about from the item names it contains, and **search only chunks in those domains**. A question about both food and beverage searches both. A question naming no known item searches everything, as today. This is done by wrapping the store, so the planned flow, the planner and the existing tests do not change.

## 2. Out of scope
- Changes to `src/blc/flow/`, `src/blc/planner/`, the router, tools, prompts or the answer model. (A prompt line telling the model to ignore irrelevant documents is a separate spec.)
- Chunking, `TOP_K`, the embedding model, and `scripts/voice_chat.py` (it keeps the plain store).
- Synonyms not present in the documents (e.g. "jam" for "raspberry preserves"): they match no item and fall back to an unfiltered search.
- Re-grading answers with the judge (spec 027). Retrieval only.
- Running `ingest.py` or wiping `.chroma/` from a test. The planner does it by hand before the eval.

## 3. Interface contract
```python
# src/blc/retrieval/   (new package; `from blc.retrieval import ...`)
from typing import Mapping
Lexicon = Mapping[str, frozenset[str]]      # lower-case item name -> domains it belongs to

DOMAINS: tuple[str, ...] = ("food", "beverage")
OTHER_DOMAIN: str = "other"

def domain_for(source: str) -> str:
    """source is a path from the project root, e.g. 'data/pull_sheet/menu/food.md'."""

def load_lexicon(data_dir: Path = DATA_DIR) -> Lexicon:
    """Item names found in the knowledge files; reads files. DATA_DIR = ROOT / "data"."""

def detect_domains(question: str, lexicon: Lexicon) -> frozenset[str]: ...

class DomainStore:
    def __init__(self, store, lexicon: Lexicon | None = None) -> None: ...   # None -> load_lexicon()
    def similarity_search(self, query: str, k: int = 4) -> list[Document]: ...
```
`store` is any object with `similarity_search(query, k=..., filter=...)` (a Chroma store, or a fake).

```python
# scripts/ingest.py  (names unchanged; behaviour added)
def ingest_file(store: Chroma, path: Path, mtime: float) -> int
#   every stored chunk now also has metadata["domain"] == domain_for(relative_source(path))

# scripts/chat.py
def build_store() -> Chroma                 # unchanged
def build_domain_store() -> DomainStore     # DomainStore(build_store())
TOP_K: int                                  # 3, unchanged
```
`main()` in `scripts/chat.py` runs the planned flow with `build_domain_store()` instead of `build_store()`.

**Golden file (new data, written by the planner):** `evals/retrieval/domain_golden.jsonl`, one JSON object per line:
`{"id": str, "question": str, "expected_chunks": [{"source": str, "must_contain": [str, ...]}], "forbidden_sources": [str], "must_pass": bool, "notes": str}`.
**A case passes** when, for the `TOP_K` documents returned by `DomainStore(build_store()).similarity_search(question, k=TOP_K)`: every expected chunk has at least one document with that `source` whose `page_content` contains every `must_contain` string (case-insensitive), **and** no document has a source in `forbidden_sources`.
Other golden files reused: `evals/retrieval/food_golden.jsonl` (spec 025 rule) and `evals/retrieval/golden.jsonl` (spec 004 rule: expected sources in the top `TOP_K`).
**Constants (in the eval test module):** `MIN_HIT_RATE = 0.85` for `domain_golden.jsonl`; `0.90` for `food_golden.jsonl`.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `domain_for(source)` | str path | any | `"food"`, `"beverage"` or `"other"` |
| `detect_domains(question, lexicon)` | str, mapping | any (blank allowed) | set of domains whose items the question names; empty if none |
| `DomainStore.similarity_search(query, k)` | str, int | k ≥ 1 | documents ranked among chunks of the detected domains (all chunks if none detected) |
| Stored chunk metadata | dict | | now has `domain` as well as `source`, `category`, `chunk_index`, `mtime` |

## 5. Acceptance criteria
- **AC-1:** `domain_for` gives `food` for `data/pull_sheet/menu/food.md`; `beverage` for `data/pull_sheet/menu/beverages.md`, `data/pull_sheet/rules/beverages.md`, every `data/supplies/*.md` and `data/recipes/*.md`; `other` for any other path.
- **AC-2** *(integration)*: `ingest_file` into an empty temp store with real embeddings stores `metadata["domain"] == "food"` on every chunk of `data/pull_sheet/menu/food.md` and `"beverage"` on every chunk of `data/supplies/coffee.md`; the existing metadata keys are still there.
- **AC-3:** `detect_domains` matches item names as whole words or phrases, ignoring case, and tolerates a plural/singular difference. A name belonging to several domains adds all of them. Words that are not item names (e.g. "bring", "where") add nothing. Blank input gives the empty set and raises nothing. Examples in §6.2.
- **AC-4:** With the real lexicon, `detect_domains` gives `{food}` for questions naming food items only, `{beverage}` for beverage items only, both for mixed questions, and the empty set for unknown items (§6.2).
- **AC-5:** `DomainStore.similarity_search` calls the wrapped store once with `similarity_search(query, k=k, filter={"domain": {"$in": [sorted domains]}})` when domains are detected, and with `similarity_search(query, k=k)` (no `filter` argument) when none are. It returns the wrapped store's documents unchanged and in order.
- **AC-6:** If the filtered call returns no documents, `DomainStore` calls the wrapped store again without a filter and returns that result.
- **AC-7** *(eval)*: With the real, re-ingested store, the pass rate over `domain_golden.jsonl` is at least `MIN_HIT_RATE`, and every case with `must_pass` true (the two croissant questions) passes. The failure message lists each failing case: id, question, the retrieved sources with their first line, missing chunks and any forbidden source hit.
- **AC-8** *(eval)*: With `DomainStore(build_store())`, the pass rate over `food_golden.jsonl` is at least 0.90, and all 20 cases of `golden.jsonl` pass.
- **AC-9:** All existing tests still pass unchanged (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest -m "not integration and not eval"`), except tests that this spec's tester updates for the new `domain` metadata.
- **AC-10:** Eval and integration tests skip with a clear message when Ollama is not running, or when the real store has chunks without a `domain` label ("wipe `.chroma/` and re-run scripts/ingest.py").
- **AC-11** *(manual)*: Only `src/blc/retrieval/` (new), `scripts/ingest.py` and `scripts/chat.py` change; `src/blc/flow/`, `src/blc/planner/` and `data/` are untouched. Tests live in `tests/domain_retrieval/`; the `integration`/`eval` markers are used; files stay under ~400 lines; calculation code does no I/O (only `load_lexicon` reads files).

## 6. Test cases
### 6.1 DOM (domain labels)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DOM-1 | `domain_for("data/pull_sheet/menu/food.md")` | `food` | AC-1 |
| DOM-2 | `domain_for("data/pull_sheet/rules/beverages.md")`, `"data/pull_sheet/menu/beverages.md"` | `beverage` | AC-1 |
| DOM-3 | `domain_for("data/supplies/coffee.md")`, `"data/recipes/lemonade.md"` | `beverage` | AC-1 |
| DOM-4 | `domain_for("data/notes/other.md")` | `other` | AC-1 |
| DOM-5 | `ingest_file` food.md into temp store | every chunk has `domain == "food"`, plus source/category/chunk_index | AC-2 |
| DOM-6 | `ingest_file` data/supplies/coffee.md into temp store | every chunk has `domain == "beverage"` | AC-2 |

### 6.2 DET (`detect_domains`)
Custom lexicon `L = {"coffee": {beverage}, "croissants": {food}, "water": {food, beverage}, "iced tea": {beverage}}`.
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DET-1 | `"Where are the croissants?"`, L | `{food}` | AC-3 |
| DET-2 | `"I need coffee and croissants"`, L | `{food, beverage}` | AC-3 |
| DET-3 | `"WHERE IS THE COFFEE"`, L | `{beverage}` (case-insensitive) | AC-3 |
| DET-4 | `"Do we need a croissant?"`, L | `{food}` (singular matches plural) | AC-3 |
| DET-5 | `"Where is the water?"`, L | `{food, beverage}` | AC-3 |
| DET-6 | `"Where is the iced tea?"`, L | `{beverage}` (phrase); `"Where is the tea?"` gives empty | AC-3 |
| DET-7 | `"Is there a coffeehouse nearby?"`, L | empty (whole words only) | AC-3 |
| DET-8 | `"Where is the flour?"`, L; `""`; `"   "` | empty, no error | AC-3 |
Real lexicon (`load_lexicon()`):
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DET-9 | `"Do we need to bring anything with croissants"` | `{food}` ("bring" adds nothing) | AC-4 |
| DET-10 | `"Where is the Dijon mustard?"` | `{food}` | AC-4 |
| DET-11 | `"Where is the coffee?"`; `"Where is the iced tea?"` | `{beverage}` | AC-4 |
| DET-12 | `"Where are the coffee and the croissants?"` | `{food, beverage}` | AC-4 |
| DET-13 | `"Where is the bottled water?"` | contains `food` | AC-4 |
| DET-14 | `"Where is the flour?"` | empty | AC-4 |

### 6.3 STORE (`DomainStore` with a fake wrapped store that records its calls)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| STORE-1 | query with food items only, k=3 | one call: `k=3, filter={"domain": {"$in": ["food"]}}` | AC-5 |
| STORE-2 | query with food and beverage items | one call with `{"$in": ["beverage", "food"]}` | AC-5 |
| STORE-3 | query naming no known item | one call with `k=3` and **no** `filter` argument | AC-5 |
| STORE-4 | fake returns documents | same documents, same order | AC-5 |
| STORE-5 | filtered call returns `[]` | a second call without `filter`; its result is returned | AC-6 |
| STORE-6 | filtered call returns documents | no second call | AC-6 |
| STORE-7 | `DomainStore(fake, lexicon=L)` | uses `L`, not the real lexicon | AC-5 |
| STORE-8 | `similarity_search("croissants")` without `k` | wrapped store receives `k=4` | AC-5 |

### 6.4 RET (eval, real re-ingested store). Case ids are those in `domain_golden.jsonl`.
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| RET-1 | `croissants-bring-we`: "Do we need to bring anything with croissants" | food.md chunk with "Raspberry preserves"; no beverage-rules source (**must pass**) | AC-7 |
| RET-2 | `croissants-what-to-bring`: "What to bring with croissants" | same (**must pass**) | AC-7 |
| RET-3 | `mixed-coffee-croissants`: "Where are the coffee and the croissants?" | coffee.md "coffee machine" and food.md "Butter croissants" | AC-7 |
| RET-4 | `mixed-honey-syrups`: "Where is the honey and where are the syrups?" | food.md "Honey" and syrups.md "beverage cooler" | AC-7 |
| RET-5 | `mixed-bagels-coffee`: "What do I bring with the bagels, and what do I bring when coffee is ordered?" | food.md "Cream cheese" and rules/beverages.md "creamer" | AC-7 |
| RET-6 | `coffee-only`: "Where is the coffee?" | coffee.md "coffee machine"; no food.md | AC-7 |
| RET-7 | `lemons-only`: "Where are the lemons?" | lemon.md "sink"; no food.md | AC-7 |
| RET-8 | `syrups-only`: "Where are the syrups stored?" | syrups.md "beverage cooler"; no food.md | AC-7 |
| RET-9 | `dijon-no-beverage`: "Where is the Dijon mustard?" | food.md "Dijon mustard"; no beverage source | AC-7 |
| RET-10 | `honey-no-beverage`: "Where is the honey?" | food.md "Honey"; no beverage source | AC-7 |
| RET-11 | all 10 cases | pass rate ≥ `MIN_HIT_RATE`; failure message as in AC-7 | AC-7 |
| RET-12 | `food_golden.jsonl` through `DomainStore` | pass rate ≥ 0.90 | AC-8 |
| RET-13 | `golden.jsonl` (20 cases) through `DomainStore` | all pass | AC-8 |
| RET-14 | store has chunks without `domain` | eval skips: "wipe .chroma/ and re-ingest" | AC-10 |
