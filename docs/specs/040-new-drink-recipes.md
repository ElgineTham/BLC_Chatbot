# Spec 040: New drink recipes (lemonades, iced teas, punch, cider) and tea-bag counting

- **Status:** done (closed by the user on 2026-11-18). Verified: 142/142 spec 040 unit tests and 193/193 spec 015 tests pass with the standard command; AC-13 checked by the planner. Not verified: AC-9 (DOCS-1/2 skip on an outdated "Ollama not running" guard; embeddings are Google since spec 037). Known failures: AC-12 `peach-juice-partial` and `mango-juice-partial` (planned follow-up: TOP_K 3→5); domain and food hit-rate evals failed before this spec. Known risk: bag counting slows down for very large batches (no speed AC). Revised twice (see Revision history)
- **Date:** 2026-11-18 (revision 1: 2026-11-18)

## 1. Goal
The kitchen binder has eight more drink cards (photos in `data/recipes/examples/`): Strawberry, Pomegranate, Lavender and Mango Lemonade; Mango and Raspberry Iced Tea; Citrus Fruit Punch; Apple Cider with Ginger. They become recipes of the existing `scale_recipe` tool (spec 015) by adding entries to `data/recipes/recipes.json`. They also become one markdown file each, ingested into Chroma, so "how do I make mango lemonade?" can be answered from the documents. Every amount scales linearly from the card's **1-gallon** amount. The cards' printed 4-gallon amounts for the lemonades are 3× the 1-gallon amounts, not 4×, and are treated as a card error (decided with the user). The iced teas use sized tea bags, which cannot be scaled by multiplying. The tool therefore gains one new ingredient kind, **counted bags**, which picks the fewest bags for the batch.

## 2. Out of scope
- New tools: all eight drinks go through the existing `scale_recipe` tool. Its name, schema, description and argument rules (spec 015 §3.3, §4.5) are unchanged.
- Any change to the planner, router, flow, answer prompts or `check_arguments`; new evals for the chat flow (a follow-up spec if the model fails to use the new recipes).
- Changing the existing **Lemonade** recipe (7 oz lemon concentrate per gallon). It stays as it is, even though the new cards use 25 oz *lemonade* concentrate.
- Adding the new drinks to the beverage pull sheet (`data/pull_sheet/`) or to `data/supplies/`.
- Unit conversion (oz to cups/quarts), and recipes whose yield is not in gallons.
- Ingesting the photos themselves; `ingest.py` still reads only `.md`.
- **Data files** (`recipes.json` entries, the eight `.md` files) are written by the planner after this spec is approved (one-off exception, as in spec 033). Content: Appendix A and B.

## 3. Interface contract
Unchanged from spec 015 §3.1 except for the additions below. Everything is importable as `from blc.tools.recipe_tools import ...`.

```python
BAG_UNIT = "bag"   # ScaledIngredient.unit for a counted-bag line
```
- A **counted-bag ingredient** in the file (§4.1) turns into one `ScaledIngredient` per bag size that is used (count ≥ 1), in the file's order of sizes and at the ingredient's position in the recipe: `name` = the size's name (e.g. `"3-gallon tea bag"`), `amount` = `Fraction(count)`, `unit = BAG_UNIT`, `fill = False`. Sizes with count 0 produce no `ScaledIngredient`.
- `load_recipe_book` raises `RecipeFileError` for a malformed counted-bag ingredient (§4.1).
- DOCS tests use the existing `chat` entry point (specs 004, 025, 028), unchanged: `retrieve(store, question) -> list[Document]`, `build_store() -> Chroma`, `CHROMA_DIR: Path`. Each returned `Document`'s `metadata["source"]` ends with the file's repo-relative path (e.g. `data/recipes/flavored_lemonades.md`).

### 3.1 Files
- `data/recipes/recipes.json`: gains the eight recipes in Appendix A (planner writes it). Tests that use the real file **skip** when it does not exist.
- `data/recipes/<slug>.md`: four new files (Appendix B), ingested by the existing `backend/scripts/ingest.py`.

## 4. Inputs and outputs

### 4.1 Counted-bag ingredient (new file format)
Allowed inside a recipe's `ingredients` list, next to the spec 015 kinds:
```json
{"bags": [
  {"name": "3-gallon tea bag", "brews_from": 3, "brews_to": 4},
  {"name": "1-gallon tea bag", "brews_from": 1, "brews_to": 1}
]}
```
A size brews any whole number of gallons from `brews_from` to `brews_to`. `RecipeFileError` when: `bags` is empty or not a list; a size has a missing or blank `name`; `brews_from` or `brews_to` is missing, not a whole number, or below 1; `brews_from` > `brews_to`; two sizes share a name; or no size has `brews_from` = `brews_to` = 1 (this guarantees every batch can be brewed). All spec 015 §4.1 errors still apply.

### 4.2 Choosing bags
- The batch is rounded **up** to a whole number of gallons for the bags only (2.5 → 3, 0.5 → 1); every other ingredient still scales from the exact batch.
- Choose a count for each size so that the total gallons brewed equals the rounded batch, where each bag brews between its `brews_from` and `brews_to` gallons. Use the **fewest bags in total**. On a tie, use the **fewest bags of the size with the smallest `brews_to`** (with the tea sizes: fewer 1-gallon bags).
- With the tea sizes above:

| Rounded batch (gal) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3-gallon bags | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 2 | 3 | 3 | 3 | 3 | 4 |
| 1-gallon bags | 1 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### 4.3 Text for bag lines
Each bag line in `RecipeResult.text` is `<size name>: <count> bag` when the count is 1, else `<size name>: <count> bags` (e.g. `3-gallon tea bag: 1 bag`, `1-gallon tea bag: 2 bags`). The text never contains "1 bags" or a line for a size with count 0. All other spec 015 §4.6 text rules are unchanged.

### 4.4 The real recipes
Appendix A is the source of truth for names, aliases, amounts and steps. Name matching (spec 015 §4.2), the guests rule (§4.3) and the statuses are unchanged.

## 5. Acceptance criteria
- **AC-1:** The real `recipes.json` loads and holds exactly nine recipes: Lemonade plus the eight in Appendix A, with their display names as written there.
- **AC-2:** The four lemonades scale linearly from 1 gallon: 25 oz Lemonade concentrate, plus 7 oz of the flavour syrup (8 oz Pomegranate juice), plus Water filled to the batch. 4 gallons gives 100 oz and 28 oz (32 oz juice), not the card's 75 oz and 20 oz.
- **AC-3:** The two iced teas scale the syrup linearly (8 oz per gallon), fill Water to the batch, and pick tea bags by §4.2.
- **AC-4:** Citrus Fruit Punch scales 25 oz each of Pineapple juice concentrate, Lemonade concentrate and Orange juice concentrate, plus 24 oz Sprite per gallon, with Water filled to the batch. Apple Cider with Ginger scales 0.75 cups Grated fresh ginger per gallon, with Apple cider filled to the batch.
- **AC-5:** Every display name and alias in Appendix A finds its recipe (with spec 015's case, spacing, "the" and "recipe" rules). Names of drinks that have no card (e.g. "raspberry lemonade") and partial names (e.g. "mango") give `no_recipe`, and the text lists all nine display names.
- **AC-6:** The counted-bag format in §4.1 loads, and every malformed case listed there raises `RecipeFileError`. Every spec 015 file error still raises.
- **AC-7:** Bag lines in `ingredients` and `text` follow §3 and §4.3.
- **AC-8:** `run_recipe_tool` and `RECIPE_TOOL.invoke` work with the new recipes, including the guests path. They never raise.
- **AC-9** *(integration)*: After `ingest.py` has run on the real data, `retrieve(store, question)` (from `chat`) returns the drink's `.md` file among its documents for "How do I make strawberry lemonade?" and "How do I make raspberry iced tea?". Skip if Ollama is not running. Positive cases only: no wrong or boundary case is required for this AC.
- **AC-10:** Real-file tests skip when `data/recipes/recipes.json` is missing. Counted-bag format and rule tests (BAGS) use a test book written to `tmp_path` and read nothing under `data/`.
- **AC-11:** All existing unit tests pass **unchanged**, including spec 015's (`backend/tests/recipe_tools/`). No existing test file is edited. New tests go in `backend/tests/new_recipes/` and must be collected by the standard command (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest`, which uses `--import-mode=importlib` and `pythonpath = ["backend/scripts", "backend/src"]`). A test module may not import a sibling helper module from its own test folder; shared helpers and constants live in that folder's `conftest.py` (as fixtures) or in the test modules themselves.
- **AC-12** *(eval)*: The existing retrieval eval golden sets still meet their thresholds after re-ingest. This includes `mango-juice-partial` and `concentrates-flavors` in `evals/retrieval/golden.jsonl`. It is verified by re-running the **existing** `@pytest.mark.eval` tests in `backend/tests/domain_retrieval/test_retrieval_eval.py` and `backend/tests/test_retrieval_eval.py`, with their existing thresholds. No new test is written for this AC.
- **AC-13** *(manual)*: No recipe knowledge in code: drink names, amounts, bag sizes and bag ranges come only from the JSON file, and the bag rule does not mention tea. Only `backend/src/blc/tools/recipe_tools/` changes. Modules are split by job, about 250 lines each. No new dependencies. The tool's schema and description are unchanged.

## 6. Test cases

### 6.1 REAL: the eight new recipes on the real `recipes.json` (`scale_recipe` unless stated; skip if the file is missing)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REAL-1 | "Strawberry Lemonade", gallons 1 | `ok`; Lemonade concentrate 25 oz, Strawberry syrup 7 oz, Water fill 1 gallon (in that order) | AC-2 |
| REAL-2 | "strawberry lemonade", gallons 4 | Lemonade concentrate 100 oz, Strawberry syrup 28 oz, Water fill 4 (not 75 / 20) | AC-2 |
| REAL-3 | "Pomegranate Lemonade", gallons 4 | Lemonade concentrate 100 oz, Pomegranate juice 32 oz, Water fill 4 | AC-2 |
| REAL-4 | "Lavender Lemonade", gallons 2.5 | 125/2 oz concentrate, 35/2 oz Lavender syrup; text has "62.5 oz", "17.5 oz", "2.5 gallons" | AC-2 |
| REAL-5 | "Mango Lemonade", guests 100 | gallons 4, `from_guests` True; 100 oz concentrate, 28 oz Mango syrup | AC-2 |
| REAL-6 | "Mango Iced Tea", gallons 1 | ingredients: 1-gallon tea bag 1 bag, Mango syrup 8 oz, Water fill 1; no 3-gallon bag line | AC-3, AC-7 |
| REAL-7 | "Mango Iced Tea", gallons 4 | 3-gallon tea bag 1 bag (no 1-gallon line), Mango syrup 32 oz, Water fill 4; text has "3-gallon tea bag: 1 bag", not "1 bags" | AC-3, AC-7 |
| REAL-8 | "Raspberry Iced Tea", gallons 5 | 3-gallon tea bag 1, then 1-gallon tea bag 1; Raspberry syrup 40 oz | AC-3 |
| REAL-9 | "Raspberry Iced Tea", gallons 9 | 3-gallon tea bag 3, no 1-gallon line (tie rule); Raspberry syrup 72 oz | AC-3 |
| REAL-10 | "Raspberry Iced Tea", gallons 2 | 1-gallon tea bag 2, no 3-gallon line; syrup 16 oz; text has "1-gallon tea bag: 2 bags" | AC-3, AC-7 |
| REAL-11 | "Mango Iced Tea", gallons 2.5 | 3-gallon tea bag 1 (batch rounded to 3 for bags only); Mango syrup 20 oz; Water fill 2.5 | AC-3 |
| REAL-12 | "Mango Iced Tea", gallons 7 | 3-gallon tea bag 2, no 1-gallon line; Mango syrup 56 oz | AC-3 |
| REAL-13 | "Citrus Fruit Punch", gallons 4 | Pineapple juice concentrate, Lemonade concentrate and Orange juice concentrate 100 oz each, Water fill 4, Sprite 96 oz (file order). Wrong case: Sprite is **not** 100 oz (it does not share the concentrates' 25 oz/gal), and there is no bag line | AC-4 |
| REAL-14 | "Citrus Fruit Punch", gallons 1.5 | each concentrate 75/2 oz, Sprite 36 oz; text has "37.5 oz" | AC-4 |
| REAL-15 | "Apple Cider with Ginger", gallons 1 and 4 | Apple cider fill 1 / 4; Grated fresh ginger 3/4 / 3 cups; 1-gal text has "0.75 cups". Wrong case: Apple cider is a fill line (`fill` True, unit "gallon"), **not** an oz or cups amount; at 4 gal the text has "Apple cider: fill to 4 gallons" and no "oz" on the ginger line | AC-4 |
| REAL-16 | `run_recipe_tool({"recipe": "raspberry iced tea", "guests": 130})` and `RECIPE_TOOL.invoke` with the same args | gallons 5, `from_guests` True; bags 1 + 1; syrup 40 oz; `invoke` returns the same text | AC-8 |
| REAL-17 | names: "STRAWBERRY LEMONADE recipe", "the mango tea", "Raspberry tea", "citrus punch", "fruit punch", "Punch", "ginger apple cider", "apple cider", "Fresh-pressed WA apple cider with ginger" | each finds its Appendix A recipe (`recipe` = display name) | AC-5 |
| REAL-18 | "raspberry lemonade", gallons 2; "mango", gallons 2 | `no_recipe`; text lists all nine display names | AC-1, AC-5 |
| REAL-19 | "Lemonade", gallons 6 (old recipe, real file) | Lemon concentrate 42 oz, Water fill 6 (unchanged) | AC-1, AC-11 |
| REAL-20 | "Mango Iced Tea", gallons 6: text | contains "3-gallon tea bag: 2 bags", "Mango syrup: 48 oz", "Water: fill to 6 gallons", "1." to "4." before the steps; no "1-gallon tea bag" | AC-3, AC-7 |

### 6.2 BAGS: counted-bag format and rule (test book in `tmp_path`, with the two tea sizes of §4.1 unless stated)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| BAGS-1 | A book with one counted-bag recipe (sizes as §4.1, plus a syrup and Water fill) | loads; scaling works | AC-6 |
| BAGS-2 | Malformed: `"bags": []`; `"bags": "x"`; size without name; blank name; `brews_from` 0; `brews_from` 2.5; `brews_from` 4 > `brews_to` 3; duplicate size names; only a 3–4 size (no 1–1 size) | each raises `RecipeFileError` | AC-6 |
| BAGS-3 | Batches 1 to 13 whole gallons | bag counts exactly as the §4.2 table | AC-3 |
| BAGS-4 | Batches 0.5, 3.2 | 0.5 → one 1-gallon bag; 3.2 → one 3-gallon bag (rounded to 4) | AC-3 |
| BAGS-5 | guests 38 | gallons 2 → two 1-gallon bags, `from_guests` True | AC-3, AC-8 |
| BAGS-6 | Bag `ScaledIngredient` fields | `unit == BAG_UNIT == "bag"`, `fill` False, `amount` a whole `Fraction` | AC-7 |
| BAGS-7 | Spec 015 file errors (e.g. ingredient `{"name": "X"}`, `yield_gallons` 0) in a book that also has a valid counted-bag recipe | still raise `RecipeFileError` | AC-6 |

### 6.3 DOCS: ingested markdown (integration, real store)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DOCS-1 | `retrieve(store, "How do I make strawberry lemonade?")` | a document with source ending `data/recipes/flavored_lemonades.md` is returned | AC-9 |
| DOCS-2 | `retrieve(store, "How do I make raspberry iced tea?")` | a document with source ending `data/recipes/flavored_iced_teas.md` is returned | AC-9 |

## Appendix A: entries added to `data/recipes/recipes.json` (written by the planner)
```json
"Strawberry Lemonade": {
  "yield_gallons": 1,
  "ingredients": [
    {"name": "Lemonade concentrate", "amount": 25, "unit": "oz"},
    {"name": "Strawberry syrup", "amount": 7, "unit": "oz"},
    {"name": "Water", "fill": true}
  ],
  "steps": [
    "Pour the lemonade concentrate and strawberry syrup into a clean bucket that holds the whole batch.",
    "Add water to fill the rest of the bucket to the batch size.",
    "Stir well until fully mixed."
  ]
},
"Pomegranate Lemonade": { same shape, second ingredient {"name": "Pomegranate juice", "amount": 8, "unit": "oz"} },
"Lavender Lemonade":    { same shape, second ingredient {"name": "Lavender syrup", "amount": 7, "unit": "oz"} },
"Mango Lemonade":       { same shape, second ingredient {"name": "Mango syrup", "amount": 7, "unit": "oz"} },
"Mango Iced Tea": {
  "also_written_as": ["Mango tea"],
  "yield_gallons": 1,
  "ingredients": [
    {"bags": [
      {"name": "3-gallon tea bag", "brews_from": 3, "brews_to": 4},
      {"name": "1-gallon tea bag", "brews_from": 1, "brews_to": 1}
    ]},
    {"name": "Mango syrup", "amount": 8, "unit": "oz"},
    {"name": "Water", "fill": true}
  ],
  "steps": [
    "Place the tea bags in a sanitized bucket.",
    "Add the mango syrup.",
    "Pour hot water to cover the tea bags and let steep for 10 minutes.",
    "Take out the spent bags and fill the rest with cold water to the batch size."
  ]
},
"Raspberry Iced Tea": { as Mango Iced Tea, alias "Raspberry tea", syrup {"name": "Raspberry syrup", "amount": 8, "unit": "oz"} },
"Citrus Fruit Punch": {
  "also_written_as": ["Citrus punch", "Fruit punch", "Punch"],
  "yield_gallons": 1,
  "ingredients": [
    {"name": "Pineapple juice concentrate", "amount": 25, "unit": "oz"},
    {"name": "Lemonade concentrate", "amount": 25, "unit": "oz"},
    {"name": "Orange juice concentrate", "amount": 25, "unit": "oz"},
    {"name": "Water", "fill": true},
    {"name": "Sprite", "amount": 24, "unit": "oz"}
  ],
  "steps": [
    "Pour the pineapple, lemonade and orange juice concentrates into a clean bucket.",
    "Add water to fill the rest of the bucket to the batch size and stir.",
    "Add the Sprite just before the punch is served."
  ]
},
"Apple Cider with Ginger": {
  "also_written_as": ["Fresh-pressed WA apple cider with ginger", "Ginger apple cider", "Apple cider", "Ginger cider"],
  "yield_gallons": 1,
  "ingredients": [
    {"name": "Apple cider", "fill": true},
    {"name": "Grated fresh ginger", "amount": 0.75, "unit": "cups"}
  ],
  "steps": [
    "Get the apple cider (ask culinary where it is) and fresh ginger from the produce walk-in.",
    "Add the grated ginger to the apple cider.",
    "Let the ginger macerate in the cider for at least 30 minutes.",
    "Strain through a cone sieve, pressing on the ginger solids."
  ]
}
```
The four lemonades use the same three steps with their own syrup or juice named in step 1. The real file is written in full JSON; the shorthand above is for review only.

## Appendix B: markdown files (written by the planner, then ingested)
`data/recipes/flavored_lemonades.md` (all four lemonades in one table), `flavored_iced_teas.md` (both teas), `citrus_fruit_punch.md`, `apple_cider_ginger.md`. They give the 1-gallon amounts from Appendix A, the method and "scale linearly". The lemonades and teas are merged so that near-identical files do not crowd older documents out of the top 3 results (revision 2). The iced-tea notes give the bag rule: a 3-gallon bag brews 3–4 gallons and a 1-gallon bag brews 1 gallon. The punch notes give the Sprite timing. The cider file gives where the ingredients are kept. The cards' 4-gallon amounts are **not** copied.

## Revision history
- **Revision 1 (2026-11-18)**, after the test-evaluator's first audit (FAIL on missing case types; all spec cases were covered). **No code change.**
  - **AC-4:** REAL-13 and REAL-15 gain wrong cases (Sprite not 100 oz, no bag line on the punch; cider is a fill line, not an oz/cups amount). Tests to add in `backend/tests/new_recipes/`.
  - **AC-9:** positive cases only; no wrong or boundary case required.
  - **AC-12:** verified by re-running the named existing eval tests; no new test.
  - **§3:** names the `chat` entry-point items the DOCS tests use (`retrieve`, `build_store`, `CHROMA_DIR`) and the `source` metadata format.
- **Revision 2 (2026-11-18)**, after the implementation-evaluator's run (142/142 new unit tests pass with a pythonpath workaround; 193/193 spec 015 tests pass). **No code change.**
  - **Test bug:** `backend/tests/new_recipes/` imported a sibling module (`bag_helpers`), which fails under `--import-mode=importlib`. AC-11 now says helpers live in `conftest.py` or the test modules. Tests to change: move `bag_helpers.py`'s content into `conftest.py` (fixtures) or the test modules, and delete `bag_helpers.py`.
  - **Data:** the four lemonade files and the two iced-tea files are merged into `flavored_lemonades.md` and `flavored_iced_teas.md` (Appendix B). DOCS-1 and DOCS-2 now expect those sources. `recipes.json` is unchanged.
  - **Recorded as pre-existing, not part of this spec** (user decision): `test_domain_hit_rate` and `test_food_golden_hit_rate_through_domain_store` failing (food-only questions; food search never returns recipe files).
  - **AC-12 known failures** (user decision): after the merge, `lemonade-scale-10gal` passes, but `peach-juice-partial` and `mango-juice-partial` still miss `data/supplies/syrups.md` in the top 3 (recipe files outrank it on "how do I make … juice?"). They are recorded here and fixed in a follow-up spec that raises retrieval `TOP_K` from 3 to 5. The golden file is not edited.
