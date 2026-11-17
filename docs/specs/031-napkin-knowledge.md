# Spec 031: Napkin knowledge for the documents path (ingest and domain retrieval)

- **Status:** approved
- **Date:** 2026-11-17

## 1. Goal
Spec 030's eval showed that napkin questions ("Should I put out cocktail napkins for breakfast?") go to the documents and get "the documents do not mention it", because no file says where the napkins are or when to bring each kind. This spec adds `data/pull_sheet/rules/napkins.md` (written by the planner from the user's facts: where cocktail and dinner napkins are kept, when to bring cocktail napkins, when to bring dinner napkins) and makes the documents path **retrieve** it.

The retriever (spec 028) searches only the domains a question is about, so a napkin file labelled `other` would be filtered out of "napkins for the iced tea" (beverage) and "napkins for the croissants" (food). The file therefore gets its **own domain, `napkin`**, and a question that names napkins searches the napkin domain **together with** any food or beverage domain it also names. Questions that do not name napkins behave exactly as today, so the napkin lines do not leak into other answers (the 028 fix stays).

This spec ingests and **measures retrieval only**. A poor hit rate is reported; chunking or retrieval changes would be a later spec (as with spec 025).

## 2. Out of scope
- Changing `scripts/ingest.py`, `scripts/chat.py`, chunking, `MAX_TOKENS`, `TOP_K`, `DomainStore`'s search logic, the embedding model, the planner, its prompt, the flow, the food tool or any other tool.
- **Answer quality.** No generation or judge eval here; whether the chat now answers napkin questions correctly end to end is a follow-up (re-run spec 030's CALL-2 and CALL-4 and add a judged set).
- **The food tool's napkin half** (spec 029, yes/no by meal type). The file and the tool agree on breakfast, reception, lunch and dinner. The file adds two rules the tool has no meal for ("any beverage" for cocktail napkins, "plated meal" for dinner napkins). Which of the two the planner uses is a later spec's decision.
- Editing `data/pull_sheet/rules/beverages.md` (it keeps its own "Cocktail napkins" line; the two files agree), `food.md`, or the existing golden files.
- Per-bullet chunking for the new file. It is under 500 tokens, so the existing chunking stores it as one chunk.
- Running `ingest.py` or touching `.chroma/` from a test. The planner runs `scripts/ingest.py` by hand before the evals.

## 3. Interface contract
```python
# src/blc/retrieval   (from blc.retrieval import ...)
NAPKIN: str = "napkin"
DOMAINS: tuple[str, ...] = ("food", "beverage", "napkin")    # was ("food", "beverage")
OTHER_DOMAIN: str = "other"                                   # unchanged

def domain_for(source: str) -> str: ...
# "data/pull_sheet/rules/napkins.md" -> "napkin"; every other source -> what it is today (§4.1)

def load_lexicon(data_dir: Path = DATA_DIR) -> Lexicon: ...
# unchanged signature; also reads <data_dir>/pull_sheet/rules/napkins.md when it exists (§4.2)

def detect_domains(question: str, lexicon: Lexicon) -> frozenset[str]: ...   # unchanged signature
class DomainStore: ...                                                       # unchanged signature
```
**Existing test that changes** (the tester updates exactly this assertion; no other existing test changes): `tests/domain_retrieval/test_domain_labels.py`, the check `tuple(DOMAINS) == ("food", "beverage")`, which becomes the three-name tuple above.

**Files (data, written by the planner, already in place):**
- `data/pull_sheet/rules/napkins.md`, content in Appendix A.
- `evals/retrieval/napkin_golden.jsonl`, 20 cases in the spec 028 golden format: `{"id", "question", "expected_chunks": [{"source", "must_contain": [...]}], "forbidden_sources": [...], "must_pass": bool, "notes"}`.

Eval pass rule and setup (same as spec 028): a case **passes** when, among the `TOP_K` documents from `DomainStore(build_store()).similarity_search(question, k=TOP_K)` (`TOP_K`, `build_store` from `scripts/chat.py`), every expected chunk has a document with that `source` whose `page_content` contains every `must_contain` string (case-insensitive), and no document has a source in `forbidden_sources`. Constant in the eval test module: `NAPKIN_MIN_HIT_RATE = 0.90`. Eval cases skip, not fail, when `.chroma/` is missing or holds no napkin chunk (the planner has not ingested yet).

## 4. Inputs and outputs

### 4.1 `domain_for`
| source | domain |
|---|---|
| `data/pull_sheet/rules/napkins.md` | `napkin` |
| `data/pull_sheet/menu/food.md` | `food` |
| `data/pull_sheet/menu/beverages.md`, `data/pull_sheet/rules/beverages.md`, any `.md` directly in `data/supplies` or `data/recipes` | `beverage` |
| `data/supplies/napkins.md` (any `.md` directly in `data/supplies` stays `beverage`) | `beverage` |
| anything else, including `data/napkins.md`, `data/pull_sheet/menu/napkins.md`, `data/pull_sheet/rules/napkins.txt`, `data/pull_sheet/rules/napkins2.md` | `other` |

### 4.2 Which questions search the napkin domain
`load_lexicon(data_dir)` adds napkin names when `<data_dir>/pull_sheet/rules/napkins.md` exists, and adds nothing when it does not. Then `detect_domains(question, lexicon)` includes `"napkin"` exactly when the question contains the word napkin or napkins (any case). Every other domain is detected as today.

| Question (lexicon from a data dir with the napkin file, a food file and a beverage file) | `detect_domains` |
|---|---|
| "Where are the napkins?" | `{"napkin"}` |
| "Do I need napkins for the iced tea?" (iced tea is a beverage name in the lexicon) | `{"napkin", "beverage"}` |
| "Which napkin do I bring with the croissants?" (croissants is a food name) | `{"napkin", "food"}` |
| "Where are the croissants?" / "What to bring with croissants" | `{"food"}` (no napkin) |
| "Where is the coffee?" | `{"beverage"}` (no napkin) |
| "NAPKINS?" / "Cocktail Napkin" | contains `"napkin"` |

`DomainStore.similarity_search` behaves as in spec 028: it filters with `{"domain": {"$in": sorted(domains)}}` when a domain is detected, and falls back to an unfiltered search when the filtered one finds nothing or no domain is detected.

## 5. Acceptance criteria
- **AC-1:** `NAPKIN == "napkin"`; `DOMAINS == ("food", "beverage", "napkin")`; `OTHER_DOMAIN == "other"`; `NAPKIN` is importable from `blc.retrieval`.
- **AC-2:** `domain_for` follows §4.1: the napkin file gives `napkin`; every other path, including near-misses, gives what it gave before.
- **AC-3:** `load_lexicon` with the napkin file present makes napkin and napkins detectable (AC-4); with the file absent the lexicon has no napkin entry and food and beverage detection is unchanged.
- **AC-4:** `detect_domains` follows §4.2: napkin alone, napkin with a beverage, napkin with a food item, and no napkin word means no napkin domain (so "Where are the croissants?" still gives only `food`).
- **AC-5:** `DomainStore` with a napkin-and-beverage question filters with `["beverage", "napkin"]`; napkin-and-food with `["food", "napkin"]`; napkin alone with `["napkin"]`; a food question without the word napkin with `["food"]` only (the napkin domain is never added by itself). The documents returned from the fake store are returned unchanged, and the unfiltered fallback still happens when the filtered search is empty.
- **AC-6** *(integration)*: `data/pull_sheet/rules/napkins.md` states where both napkin kinds are kept (the metal rack in the pull area in the service room), the three cocktail napkin cases (breakfast, reception, any beverage) and the three dinner napkin cases (lunch, dinner, plated meal) — Appendix A.
- **AC-7** *(eval)*: On the real, re-ingested store, `evals/retrieval/napkin_golden.jsonl` scores at least `NAPKIN_MIN_HIT_RATE` (0.90, 18 of 20) by the pass rule in §3.
- **AC-8** *(eval)*: No regression: `domain_golden.jsonl` still scores at least 0.85, `food_golden.jsonl` at least 0.90 (spec 028's own rules), and `evals/retrieval/golden.jsonl` at its existing rule and threshold. The spec 028 leak cases ("Do we need to bring anything with croissants", "What to bring with croissants") still return no beverage source.
- **AC-9** *(integration)*: In the real store after ingest, every chunk with `source == "data/pull_sheet/rules/napkins.md"` has `metadata["domain"] == "napkin"`, there is at least one, and no chunk with domain `napkin` has another source.
- **AC-10** *(manual)*: Only `src/blc/retrieval/` changes (domains and lexicon, plus the export), plus the one test assertion in §3. Nothing in `scripts/`, chunking, `TOP_K`, planner, flow or tools changes. Structure per `CLAUDE.md`: no catch-all modules, calculation code does no I/O.

## 6. Test cases
Unit rows use fakes and small data files written to `tmp_path` (the napkin file is Appendix A; a food file with a bold item "Butter croissants"; a beverage file such as `supplies/coffee.md`). Eval and integration rows read the real store and real data.

### 6.1 LABEL
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LABEL-1 | `NAPKIN`, `DOMAINS`, `OTHER_DOMAIN` | `"napkin"`; `("food", "beverage", "napkin")`; `"other"`; `NAPKIN` importable from `blc.retrieval` | AC-1 |
| LABEL-2 | `domain_for("data/pull_sheet/rules/napkins.md")`; also with backslashes | `"napkin"` | AC-2 |
| LABEL-3 | `domain_for` of food.md, both beverage files, `data/supplies/coffee.md`, `data/recipes/lemonade.md` | `food`, `beverage`, `beverage`, `beverage`, `beverage` (as before) | AC-2 |
| LABEL-4 | `domain_for` of `data/napkins.md`, `data/pull_sheet/rules/napkins.txt`, `data/pull_sheet/rules/napkins2.md`, `data/pull_sheet/menu/napkins.md`, `data/supplies/napkins.md` | `other`, `other`, `other`, `other`, `beverage` | AC-2 |

### 6.2 DETECT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DETECT-1 | "Where are the napkins?" | `{"napkin"}` | AC-4 |
| DETECT-2 | "Do I need napkins for the iced tea?" (beverage file names iced tea) | `{"napkin", "beverage"}` | AC-4 |
| DETECT-3 | "Which napkin do I bring with the croissants?" | `{"napkin", "food"}` | AC-4 |
| DETECT-4 | "Where are the croissants?", "What to bring with croissants", "Where is the coffee?" | `{"food"}`, `{"food"}`, `{"beverage"}`; `"napkin"` in none | AC-4 |
| DETECT-5 | "NAPKINS?", "Cocktail Napkin", "dinner napkins" | each contains `"napkin"` | AC-4 |
| DETECT-6 | lexicon from a data dir **without** the napkin file; "Where are the napkins?" | `frozenset()` (no napkin domain), and a food or beverage question is detected as before | AC-3 |
| DETECT-7 | lexicon from a data dir **with** the napkin file; "napkinsful" or "Where are the pins?" | no `"napkin"` | AC-3, AC-4 |

### 6.3 STORE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| STORE-1 | fake store; "Do I need napkins for the iced tea?" | one filtered search with `{"domain": {"$in": ["beverage", "napkin"]}}`; the fake's documents returned unchanged | AC-5 |
| STORE-2 | fake store; "Which napkins go with the croissants?" | filter `["food", "napkin"]` | AC-5 |
| STORE-3 | fake store; "Where are the napkins?" | filter `["napkin"]` | AC-5 |
| STORE-4 | fake store; "Where are the croissants?" | filter `["food"]` only (never napkin) | AC-5 |
| STORE-5 | fake store whose filtered search is empty; "Where are the napkins?" | a second, unfiltered search; its documents are returned | AC-5 |

### 6.4 FILE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FILE-1 *(integration)* | read `data/pull_sheet/rules/napkins.md` | contains "metal rack", "pull area", "service room"; the lines for cocktail napkins (breakfast, reception, beverage) and dinner napkins (lunch, dinner, plated meal) | AC-6 |
| FILE-2 *(integration)* | same file | title `# Napkins`; sections "Where the napkins are", "When to bring cocktail napkins", "When to bring dinner napkins"; fewer than 500 tokens (so it is one chunk) | AC-6 |

### 6.5 GOLD
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| GOLD-1 *(eval)* | `napkin_golden.jsonl`, 20 cases through `DomainStore(build_store())` | hit rate at least 0.90; one line per case with id, pass or fail and the returned sources; the report names every failed id | AC-7 |
| GOLD-2 *(eval)* | `domain_golden.jsonl` and `food_golden.jsonl` | hit rates at least 0.85 and 0.90; the two 028 croissants leak cases return no beverage source | AC-8 |
| GOLD-3 *(eval)* | `golden.jsonl` | its existing rule and threshold | AC-8 |
| GOLD-4 *(integration)* | the real store (`build_store()`): chunks with `source == napkins.md`; chunks with domain `napkin` | at least one of each; every napkins.md chunk has domain `napkin`; every `napkin` chunk has that source | AC-9 |

## Appendix A: `data/pull_sheet/rules/napkins.md` (the real file; the unit tests use a copy)
```markdown
# Napkins

Bay Laurel Catering uses two kinds of napkins: cocktail napkins and dinner napkins. This file says where they are kept and when to bring each kind.

## Where the napkins are
Cocktail napkins and dinner napkins are both kept on the metal rack in the pull area in the service room.

## When to bring cocktail napkins
- Bring cocktail napkins for a breakfast.
- Bring cocktail napkins for a reception.
- Bring cocktail napkins whenever any beverage is ordered.

## When to bring dinner napkins
- Bring dinner napkins for a lunch.
- Bring dinner napkins for a dinner.
- Bring dinner napkins for a plated meal.
```
