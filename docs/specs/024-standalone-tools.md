# Spec 024: bev_tools and recipe_tools stand on their own; their calculations load no LangChain

- **Status:** approved (revision 2)
- **Date:** 2026-11-15

## 1. Goal
Today `bev_tools` is built on `pull_sheet`. To answer one question it turns the tool arguments into a made-up order and runs the whole pull sheet on it, and `recipe_tools` borrows `guests_to_gallons` from `pull_sheet`. Importing either tool package also loads LangChain, because the package imports its LangChain tool object eagerly. This spec turns the dependency around: the beverage rules (catalog, cambros, supplies, amounts) move into `bev_tools`, `bev_tools` and `recipe_tools` no longer use `pull_sheet` at all, and `pull_sheet` keeps its public API by importing from `bev_tools`. The tools' calculations become importable without LangChain or LangGraph, so a later pull sheet for photographed orders can be built on them. **Behaviour does not change:** every tool result, every pull sheet, and every reply stays exactly as it is today.

## 2. Out of scope
- Any change to what the tools or the pull sheet produce (statuses, texts, lines, amounts, order, reasons). The snapshot files in §3 are the definition of "the same".
- Photographed orders, food, serving or other new domains, and rebuilding `pull_sheet` around per-item calculations (later specs).
- Moving or renaming the data files in `data/pull_sheet/` or `data/recipes/`.
- Cleaning up the parts of `pull_sheet` that stay (order reading, sheet assembly, output), beyond what the move needs.
- The chat flow, planner, router, entry points in `scripts/`, and every file outside `src/blc/tools/bev_tools/`, `src/blc/tools/recipe_tools/` and `src/blc/pull_sheet/`.
- Two different packages containing the same drink (the order path adds the amounts, the tool takes the larger). The menu has one package today, so the two paths can't differ; settle it when a second package is added.
- The 17 unit tests that already fail before this round (listed in `docs/specs/024-baseline-failures.txt`; they come from specs 019, 021 and 023 and belong to a later round).

## 3. Interface contract
Everything that is public today stays importable from the same place, with the same behaviour:
- `blc.tools.bev_tools`: `BEV_TOOL_NAME`, `BEV_ITEMS`, `BEV_STATUSES`, `DrinkRequest`, `DrinkAmount`, `BevResult`, `calculate_bev_item`, `run_bev_tool`, `make_bev_tool`, `BEV_TOOL`.
- `blc.tools.recipe_tools`: `RECIPE_TOOL_NAME`, `RECIPE_STATUSES`, `RECIPES_FILE`, `RecipeFileError`, `RecipeBook`, `load_recipe_book`, `ScaledIngredient`, `RecipeResult`, `scale_recipe`, `run_recipe_tool`, `make_recipe_tool`, `RECIPE_TOOL`.
- `blc.pull_sheet`: `__all__` stays exactly this list of 24 names, in this order: `BeoError`, `RuleFileError`, `Catalog`, `load_catalog`, `menu_names`, `BeoLine`, `Beo`, `parse_beo`, `PullLine`, `Skipped`, `PullSheet`, `build_pull_sheet`, `format_pull_sheet`, `ROOT`, `DEFAULT_RULES_DIR`, `MENU_FILE`, `RULES_FILE`, `GALLON`, `EACH`, `GUESTS_PER_GALLON`, `PER_VALUES`, `TICK`, `NOT_ON_MENU`, `UNKNOWN_UNIT`. `DEFAULT_RULES_DIR` is still `<repo>/data/pull_sheet`.

Existing signatures the tests call (all unchanged by this spec):

```python
# blc.tools.bev_tools
@dataclass(frozen=True)
class DrinkRequest:
    menu: str
    quantity: float | None = None
    unit: str | None = None
def calculate_bev_item(item: str, drinks: Sequence[DrinkRequest] = (), guests: int | None = None,
                       catalog: Catalog | None = None) -> BevResult: ...   # catalog=None loads the default catalog
def run_bev_tool(args: Mapping[str, object], catalog: Catalog | None = None) -> BevResult: ...
# BevResult fields: status: str, text: str, drinks: tuple[DrinkAmount, ...], lines: tuple[PullLine, ...],
#   not_on_menu: tuple[str, ...], gallons_each: int | None, cups_each: int | None
# DrinkAmount fields: drink: str, amount: Fraction, unit: str, from_guests: bool

# blc.tools.recipe_tools
def scale_recipe(recipe: str, gallons: int | float | Fraction | None = None, guests: int | None = None,
                 book: RecipeBook | None = None) -> RecipeResult: ...      # book=None loads the default book
def run_recipe_tool(args: Mapping[str, object], book: RecipeBook | None = None) -> RecipeResult: ...
# RecipeResult fields: status: str, text: str, recipe: str | None, gallons: Fraction | None, from_guests: bool,
#   ingredients: tuple[ScaledIngredient, ...], steps: tuple[str, ...]
# ScaledIngredient fields: name: str, amount: Fraction, unit: str, fill: bool

# blc.pull_sheet
@dataclass(frozen=True)
class BeoLine:
    name: str
    qty: Fraction
    unit: str          # e.g. "Gallon", "Each", or "" (sized by guests)
@dataclass(frozen=True)
class Beo:
    guests: int
    lines: tuple[BeoLine, ...]
def parse_beo(text: str) -> Beo: ...                       # raises BeoError
def build_pull_sheet(catalog: Catalog, beo: Beo) -> PullSheet: ...
# PullSheet fields: guests: int, lines: tuple[PullLine, ...], skipped: tuple[Skipped, ...]
def format_pull_sheet(sheet: PullSheet) -> str: ...
```

Current error behaviour (unchanged, may be tested):
- `load_catalog(<folder with no menu/beverages.json>)` raises `RuleFileError` (from both import paths, since it is one function).
- `scripts/pull_sheet.py <missing file>` prints one line starting with `error: ` to stderr, nothing to stdout, and exits 1.

New public names in `blc.tools.bev_tools` (moved from `pull_sheet`; `blc.pull_sheet` re-exports the **same objects**):

```python
# blc.tools.bev_tools
class Catalog: ...                      # the validated beverage menu and rules (opaque, as today)
def load_catalog(base_dir: Path = DEFAULT_RULES_DIR) -> Catalog: ...   # raises RuleFileError, as today
class RuleFileError(ValueError): ...    # as today
@dataclass(frozen=True)
class PullLine:
    supply: str
    quantity: int | None
    reasons: tuple[str, ...]
GALLON = "gallon"
EACH = "each"
GUESTS_PER_GALLON = 25
def guests_to_gallons(guests: Fraction | int) -> Fraction:
    """max(1, round half up of guests / 25), exact. Same as today."""
```

**LangChain names.** Only `BEV_TOOL` and `make_bev_tool` (in `bev_tools`) and `RECIPE_TOOL` and `make_recipe_tool` (in `recipe_tools`) may load LangChain, and only when they are first accessed. `from blc.tools.bev_tools import BEV_TOOL` keeps working.

Files used by the tests (made before this round from the current code; read-only):
- `docs/specs/024-bev-snapshot.jsonl`: 5,085 lines, one JSON object per line: `{"input": {"item", "drinks": [{"menu", "quantity", "unit"}], "guests"}, "output": {"status", "text", "drinks": [[drink, amount as str, unit, from_guests]], "lines": [[supply, quantity, [reasons]]], "not_on_menu": [..], "gallons_each", "cups_each"}}`. Replay: `calculate_bev_item(item, [DrinkRequest(menu, quantity, unit), ...], guests)` with the default catalog; amounts compare as `str(Fraction)`. JSON types: `quantity` is a number or null, `guests`, `gallons_each`, `cups_each` and each line's `quantity` are int or null, `from_guests` is a bool, lists stand for tuples.
- `docs/specs/024-recipe-snapshot.jsonl`: 36 lines: `{"input": <args dict>, "output": {"status", "text", "recipe", "gallons" (str or null), "from_guests", "ingredients": [[name, amount as str, unit, fill]], "steps": [..]}}`. Replay: `run_recipe_tool(input)` with the default book.
- `docs/specs/024-cli-baseline/<id>.out`: stdout and stderr together of `python scripts/pull_sheet.py data/pull_sheet/examples/<id>.md`, for each of the 16 `<id>.md` examples; each exited with 0.
- `docs/specs/024-baseline-failures.txt`: the unit tests that already fail or fail to collect before this round, one pytest node ID per line.
- `docs/specs/024-make-snapshot.py`: how the snapshots were made (for regenerating them if the data files change later).

The snapshot and CLI tests read the real files in `data/` (gitignored). If `data/pull_sheet/` or `data/recipes/` is missing, those tests skip.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| Each snapshot input | as in §3 | the 5,085 + 36 recorded cases | exactly the recorded output |
| `scripts/pull_sheet.py <example>.md` | BEO markdown | the 16 examples | byte-identical output to `024-cli-baseline/<id>.out`, exit 0 |
| `import blc.tools.bev_tools` / `blc.tools.recipe_tools`, then use the calculation names | fresh Python process | — | no `langchain*`, `langgraph*` or `blc.pull_sheet*` module loaded |
| Accessing `BEV_TOOL` / `RECIPE_TOOL` | fresh Python process | — | a working LangChain tool (name `calculate_bev_item` / `scale_recipe`) |

## 5. Acceptance criteria
- **AC-1 (bev standalone):** in a fresh Python process with `src/` on the path, importing `blc.tools.bev_tools`, accessing every public name except `BEV_TOOL` and `make_bev_tool`, and calling `calculate_bev_item` and `run_bev_tool` with the default catalog leaves no module named `blc.pull_sheet` or starting with `blc.pull_sheet.` in `sys.modules`.
- **AC-2 (recipe standalone):** the same holds for `blc.tools.recipe_tools` (every public name except `RECIPE_TOOL` and `make_recipe_tool`, and calling `run_recipe_tool` and `scale_recipe` with the default book).
- **AC-3 (no LangChain in calculations):** in each of these situations (fresh process each): (a) only importing `blc.tools.bev_tools`, (b) importing it and touching every public name except the LangChain names, (c) also calling `calculate_bev_item` and `run_bev_tool`, and (a) to (c) again for `blc.tools.recipe_tools` with `run_recipe_tool` and `scale_recipe`, no module whose top-level name is `langchain`, `langchain_core`, `langchain_ollama`, `langchain_chroma`, `langgraph`, `chromadb` or `ollama` is loaded.
- **AC-4 (LangChain names still work):** `from blc.tools.bev_tools import BEV_TOOL, make_bev_tool` and `from blc.tools.recipe_tools import RECIPE_TOOL, make_recipe_tool` work; `BEV_TOOL.name == "calculate_bev_item"`, `RECIPE_TOOL.name == "scale_recipe"`; `make_bev_tool()` and `make_recipe_tool()` return tools with those names. Wrong case: accessing a name that doesn't exist on either package (e.g. `blc.tools.bev_tools.NOT_A_NAME`) still raises `AttributeError`.
- **AC-5 (public API kept):** every name listed in §3 imports from the place listed; `blc.pull_sheet.__all__` equals the 24-name list in §3, in that order; importing `blc.pull_sheet` loads no module whose top-level name is `langchain`, `langchain_core`, `langchain_ollama`, `langchain_chroma`, `langgraph`, `chromadb` or `ollama`.
- **AC-6 (pull_sheet built on bev_tools):** `blc.pull_sheet.X is blc.tools.bev_tools.X` for `Catalog`, `load_catalog`, `RuleFileError`, `PullLine`, `GALLON`, `EACH` and `GUESTS_PER_GALLON`. A catalog from either `load_catalog` works with both `calculate_bev_item` (passed as `catalog=`) and `build_pull_sheet`, giving the same result as the default catalog. Wrong case: `load_catalog` on a folder without the menu file raises `RuleFileError`, and that error is caught by `except blc.tools.bev_tools.RuleFileError` and by `except blc.pull_sheet.RuleFileError`.
- **AC-7 (guests_to_gallons):** (only valid guest counts; callers check guests first, so 0, negative or non-numeric input is out of scope) `guests_to_gallons` from `blc.tools.bev_tools` gives `Fraction` results: 1 → 1, 12 → 1, 37 → 1, 38 → 2, 50 → 2, 62 → 2, 63 → 3, 100 → 4, `Fraction(75, 2)` → 2.
- **AC-8 (same bev results):** for every line of `024-bev-snapshot.jsonl`, `calculate_bev_item` returns exactly the recorded status, text, drinks, lines (supply, quantity, reasons, in order), not_on_menu, gallons_each and cups_each.
- **AC-9 (same recipe results):** for every line of `024-recipe-snapshot.jsonl`, `run_recipe_tool` returns exactly the recorded output.
- **AC-10 (same pull sheets)** *(integration: runs the CLI in a subprocess)*: for each of the 16 examples, `scripts/pull_sheet.py` prints exactly the recorded output and exits 0. Wrong case: a BEO path that doesn't exist gives one `error: ` line on stderr, empty stdout, exit 1.
- **AC-11 (no regressions):** the whole unit suite (`-m "not integration and not eval"`) has no failing or erroring test other than those in `024-baseline-failures.txt`. No existing test file is changed.
- **AC-12 (no made-up order)** *(manual)*: `calculate_bev_item` doesn't build an order or a pull sheet to answer. It calls the beverage calculations directly, and `pull_sheet`'s `build_pull_sheet` uses those same calculations from `bev_tools` (no second copy of the cambro, supply or amount rules is left in `pull_sheet`).
- **AC-13 (layout)** *(manual)*: in each tool package, the LangChain tool lives in its own module, separate from the calculation modules, and the calculation modules never import it. Code moved into `bev_tools` follows CLAUDE.md "Code structure": modules split by purpose, no `constants.py` / `errors.py` / `models.py` / `utils.py`, about 250 lines per file, calculation modules do no I/O (loading the catalog stays in its loader).
- **AC-14 (files changed)** *(manual)*: only files under `src/blc/tools/bev_tools/`, `src/blc/tools/recipe_tools/` and `src/blc/pull_sheet/` change, plus new test files under `tests/standalone_tools/`. `scripts/`, other `src/blc/` packages and existing tests are unchanged.

## 6. Test cases
Tests go in `tests/standalone_tools/`. Import checks run in a fresh subprocess (`sys.executable -c ...`, with `src/` on the path and `PYTHONPATH` unset), so modules loaded by other tests don't affect them.

**Wrong cases.** AC-1 to AC-3 have no wrong input; their wrong cases are the controls BOUNDARY-7 and BOUNDARY-8, which prove the same detector used by the other BOUNDARY tests does report forbidden modules. AC-8 and AC-9's wrong cases are the non-`ok` lines inside the snapshots, which the replay covers. Every test must be able to fail for some implementation: no test may only compare data it built itself (e.g. a "tampered snapshot" test that never calls the code).

### 6.1 BOUNDARY
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| BOUNDARY-1 | Fresh process: import `blc.tools.bev_tools`, touch every public name except `BEV_TOOL`/`make_bev_tool` | no `blc.pull_sheet*` module loaded | AC-1 |
| BOUNDARY-2 | Fresh process: `calculate_bev_item("cambros", [DrinkRequest("Coffee", 3)])` and `run_bev_tool({"item": "cups", "guests": 30})` | both `ok`; no `blc.pull_sheet*` module loaded | AC-1 |
| BOUNDARY-3 | Fresh process: import `blc.tools.recipe_tools`, touch every public name except `RECIPE_TOOL`/`make_recipe_tool`, `run_recipe_tool({"recipe": "lemonade", "guests": 40})` and `scale_recipe("lemonade", gallons=2)` | both `ok`; no `blc.pull_sheet*` module loaded | AC-2 |
| BOUNDARY-4 | Same processes as BOUNDARY-1 to BOUNDARY-3 | no `langchain*`, `langgraph*`, `chromadb`, `ollama` module loaded | AC-3 |
| BOUNDARY-5 | Fresh process: import both packages, then access `BEV_TOOL` | LangChain now loaded; `BEV_TOOL.name == "calculate_bev_item"` | AC-3, AC-4 |
| BOUNDARY-6 | Fresh process: import `blc.pull_sheet` | none of the AC-5 modules (including `langgraph`) loaded | AC-5 |
| BOUNDARY-7 | Control, fresh process: `import blc.pull_sheet`, then run the same `blc.pull_sheet*` detector as BOUNDARY-1 to -3 | detector reports `blc.pull_sheet` (not empty) | AC-1, AC-2 |
| BOUNDARY-8 | Control, fresh process: `import langchain_core`, then run the same forbidden-module detector as BOUNDARY-4 | detector reports `langchain_core` (not empty) | AC-3 |
| BOUNDARY-9 | `blc.tools.bev_tools.NOT_A_NAME` and `blc.tools.recipe_tools.NOT_A_NAME` | each raises `AttributeError` | AC-4 |

### 6.2 API
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| API-1 | Import each name in §3 from its listed package | all import | AC-5 |
| API-2 | `blc.pull_sheet.__all__` | `==` the 24-name list in §3 (same order) | AC-5 |
| API-3 | `blc.pull_sheet.Catalog is blc.tools.bev_tools.Catalog`, and the same for the other six names | all `True` | AC-6 |
| API-4 | `calculate_bev_item("cambros", [DrinkRequest("Coffee", 3)], catalog=blc.pull_sheet.load_catalog())` vs the same call without `catalog` | equal results, status `ok`, lines not empty | AC-6 |
| API-4b | `build_pull_sheet(blc.tools.bev_tools.load_catalog(), parse_beo(<an example BEO text>))` vs with `blc.pull_sheet.load_catalog()` | equal `PullSheet`s, lines not empty | AC-6 |
| API-8 | `load_catalog(tmp_path)` (empty folder) from each package | raises `RuleFileError`; caught by `except` on either package's `RuleFileError` | AC-6 |
| API-5 | `blc.pull_sheet.DEFAULT_RULES_DIR` | `<repo>/data/pull_sheet` | AC-5 |
| API-6 | `make_bev_tool().name`, `make_recipe_tool().name`, `RECIPE_TOOL.name` | `calculate_bev_item`, `scale_recipe`, `scale_recipe` | AC-4 |
| API-7 | `guests_to_gallons` on 1, 12, 37, 38, 50, 62, 63, 100, `Fraction(75, 2)` | 1, 1, 1, 2, 2, 2, 3, 4, 2 (all `Fraction`) | AC-7 |

### 6.3 SAME
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| SAME-1 | Every line of `024-bev-snapshot.jsonl` replayed (one parametrized case per line, or one test reporting every mismatch with its input); includes the `need_info`, `invalid` and `not_on_menu` lines | output equals the recorded output field by field | AC-8 |
| SAME-2 | Every line of `024-recipe-snapshot.jsonl` replayed | output equals the recorded output | AC-9 |
| SAME-3 | Each of the 16 examples through `scripts/pull_sheet.py` | stdout + stderr byte-identical to `024-cli-baseline/<id>.out`, exit 0 | AC-10 |
| SAME-4 | `data/pull_sheet/` missing | SAME-1 and SAME-3 skip, not fail (by fixture; no dedicated test needed) | §3 |
| SAME-5 | `scripts/pull_sheet.py <tmp_path>/missing.md` | stderr is one line starting `error: `, stdout empty, exit 1 | AC-10 |

### 6.4 REGRESSION
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REGRESSION-1 | Full unit suite after the change | failures and errors are a subset of `024-baseline-failures.txt` (run by the implementation-evaluator, not a test file) | AC-11 |

## Revision history
- **Revision 1 (2026-11-15):** after the test-evaluator FAIL, §3 now lists the existing signatures the tests call (`DrinkRequest`, `calculate_bev_item`, `run_bev_tool`, `scale_recipe`, `run_recipe_tool`, `Beo`, `BeoLine`, `parse_beo`, `build_pull_sheet`, `format_pull_sheet`, result fields), the exact `blc.pull_sheet.__all__`, the snapshot JSON types and the current error behaviour (missing rules folder, missing BEO file). AC-5 adds `langgraph`; AC-6 and AC-10 get wrong cases; BOUNDARY-3 calls `scale_recipe`; API-4 is split into API-4/API-4b; new API-8 and SAME-5. No change to what the code must do.
- **Revision 2 (2026-11-15):** after the second test-evaluator FAIL: AC-3 lists its situations; AC-4 gets a wrong case (unknown name raises `AttributeError`, BOUNDARY-9); AC-7 states that invalid guests are out of scope; §6 states the wrong cases for AC-1 to AC-3 (controls BOUNDARY-7 and -8) and AC-8/AC-9 (non-ok snapshot lines), and that a test that can't fail (e.g. the tampered-snapshot test) is not allowed. No change to what the code must do.
