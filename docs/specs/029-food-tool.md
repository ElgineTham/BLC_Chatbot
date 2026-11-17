# Spec 029: Food supplies tool (`calculate_food_item`)

- **Status:** approved (revision 1, done)
- **Date:** 2026-11-17 (70-guest examples corrected, same day)

## 1. Goal
Staff ask how many forks, spoons, knives or plates to bring for a guest count, and whether an event needs cocktail or dinner napkins. Today the 7B model would have to add the spare amounts itself. This spec adds a third calculator tool, `calculate_food_item`, built like `calculate_bev_item` and `scale_recipe`: **one** tool is shown to the model, and the code works out which calculation the arguments need. It answers three kinds of question: a utensil count (spoons, forks, knives), a plate count (small, large), and a yes/no for cocktail napkins or dinner napkins by meal type.

This spec builds and unit-tests **the tool only**. It is not connected to the chatbot: the router, tool step and chat flow stay as they are (follow-up spec).

## 2. Out of scope
- **Connecting the tool to the chatbot:** router registry, classifier prompt, tool step, `scripts/chat.py`, the argument check (`blc.tool_step`), and real-model evals.
- Any change to `src/blc/pull_sheet/`, `src/blc/tools/bev_tools/`, `src/blc/tools/recipe_tools/`, `src/blc/router/`, `scripts/`, `ingest.py`, or the knowledge `.md` files.
- Several items in one call (the model calls the tool once per item).
- Meal types other than those in §4.1 (e.g. "brunch" is invalid, not guessed), napkin counts (napkins are yes/no only), other utensils or serving ware, per-guest amounts other than 1.
- Reading a BEO to get guests or meal type.

## 3. Interface contract

### 3.1 The tool: `src/blc/tools/food_tools/` (new feature package)
Everything below is importable as `from blc.tools.food_tools import ...`. Importing the package reads no file and does not import `langchain_core` (the LangChain tool is built lazily; `FOOD_TOOL` and `make_food_tool` are the only way to get it).

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from langchain_core.tools import BaseTool

FOOD_TOOL_NAME = "calculate_food_item"
FOOD_ITEMS: tuple[str, ...] = (
    "spoons", "forks", "knives", "small plates", "large plates",
    "cocktail napkins", "dinner napkins",
)
FOOD_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")
FOOD_RULES_FILE: Path   # <repo root>/data/pull_sheet/rules/food.json

class FoodRulesError(Exception):
    """The rules file is missing or does not follow §4.1."""

class FoodRules:
    """The loaded rules. Opaque to tests: made only by load_food_rules."""

def load_food_rules(path: Path | None = None) -> FoodRules:
    """path=None means FOOD_RULES_FILE. Raises FoodRulesError (§4.1)."""

@dataclass(frozen=True)
class FoodResult:
    status: str            # one of FOOD_STATUSES
    text: str              # what the tool returns to the chat model (§4.6)
    item: str | None       # the item as one of FOOD_ITEMS when it was understood; else None
    guests: int | None     # guests used for a count item with status "ok"; else None
    extra: int | None      # spare pieces added, for a count item with status "ok"; else None
    count: int | None      # guests + extra, for a count item with status "ok"; else None
    answer: bool | None    # yes/no for a napkin item with status "ok"; else None
    meal: str | None       # the meal type (lower case, as in the rules file) for a napkin item with status "ok"; else None

def calculate_food_item(
    item: str,
    guests: int | None = None,
    meal: str | None = None,
    rules: FoodRules | None = None,
) -> FoodResult:
    """Pure calculation. rules=None means load_food_rules(). Never raises for bad user
    input (status "invalid" or "need_info"). FoodRulesError from loading propagates."""

def run_food_tool(args: Mapping[str, object], rules: FoodRules | None = None) -> FoodResult:
    """Run the tool on a raw argument dict as the chat model sends it (§4.4).
    Never raises for bad arguments: they give status "invalid"."""

def make_food_tool(rules: FoodRules | None = None) -> BaseTool:
    """A LangChain tool named FOOD_TOOL_NAME with the schema in §3.2. Invoking it with an
    argument dict returns run_food_tool(args, rules).text. rules=None means the real file,
    loaded when the tool runs, not when it is made."""

FOOD_TOOL: BaseTool   # make_food_tool(): the tool the chatbot will use
```

### 3.2 What the model receives (tool schema)
`convert_to_openai_tool(tool)["function"]`, for `FOOD_TOOL` and any `make_food_tool(rules)`, has `name == FOOD_TOOL_NAME`, a `description`, and exactly these `parameters` (descriptions shown as `…`):
```json
{
  "type": "object",
  "properties": {
    "item":   {"type": "string", "description": "…"},
    "guests": {"type": "integer", "minimum": 1, "description": "…"},
    "meal":   {"type": "string", "description": "…"}
  },
  "required": ["item"]
}
```
- Each property has exactly the keys shown. Nothing inside `parameters` uses `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title`, `enum` or the type `"null"`.
- The tool `description` says it works out spoons, forks, knives, small plates, large plates (a count for a number of guests) and cocktail or dinner napkins (yes or no for a meal type), that the model must use it instead of calculating, and contains **at least two example calls** as argument dicts: one count call (`item` and `guests`) and one napkin call (`item` and `meal`).
- `item`: one of the seven names in `FOOD_ITEMS`. `guests`: the guest count the user said, left out when none was given. `meal`: breakfast, reception, lunch or dinner, only for napkin items. (Wording is the developer's.)

### 3.3 Files
- Reads `data/pull_sheet/rules/food.json` (format in §4.1; the real file's content is Appendix A) only when `rules=None`. No unit test needs the real file except where stated. `data/` is outside the developer's write access: the planner creates the real file.

## 4. Inputs and outputs

### 4.1 The rules file
```json
{
  "extras": [{"guests_up_to": <int>, "extra": <int>}, ..., {"guests_up_to": null, "extra": <int>}],
  "napkins": {"<meal>": {"cocktail": <bool>, "dinner": <bool>}, ...}
}
```
`load_food_rules` raises `FoodRulesError` when: the file is missing; it is not valid JSON; `extras` is missing, empty, or has an entry with a missing or negative `extra`, a non-increasing `guests_up_to`, or a last entry whose `guests_up_to` is not `null` (or an earlier one that is `null`); `napkins` is missing, empty, or a meal lacks a boolean `cocktail` or `dinner`; a meal name is blank. Meal names are matched ignoring case and surrounding spaces; the canonical name is the file's name lower-cased and stripped.

### 4.2 Count items (spoons, forks, knives, small plates, large plates)
All five follow the same rule: `count = guests + extra`, where `extra` comes from the tier containing `guests` (`guests ≤ guests_up_to`; the `null` tier takes the rest). This is the beverage cup rule: 1 per guest plus 10 (up to 20 guests), 20 (21 to 50), 50 (51 to 100), 100 (more than 100).

### 4.3 Napkin items (cocktail napkins, dinner napkins)
`answer` is the file's `cocktail` (or `dinner`) boolean for the meal. Real file: breakfast and reception get cocktail napkins and no dinner napkins; lunch and dinner get dinner napkins and no cocktail napkins.

### 4.4 Raw arguments (`run_food_tool`) and checks
Expected shape: `{"item": "forks", "guests": 70}` or `{"item": "dinner napkins", "meal": "lunch"}`.
- `item`: a string, or a list of exactly one string. Matched ignoring case, surrounding and repeated spaces, and treating `_` and `-` as a space; the singular is accepted too ("fork", "small plate", "cocktail napkin", "knife"). A list of two or more, a missing, null, blank or unknown item is **invalid**.
- `guests` (count items only; ignored for napkin items, even if bad): `null` or `0` mean not given; otherwise a whole number ≥ 1 (`70`, `70.0`, `"70"` are all 70); anything else (`-5`, `2.5`, `"seventy"`) is **invalid**.
- `meal` (napkin items only; ignored for count items, even if unknown): a string, or a list of exactly one string; `null`, blank or missing mean not given. Matched ignoring case and surrounding spaces; a name not in the rules is **invalid**.
- Unknown extra keys are ignored. `args` that is not a mapping is **invalid**.
- A count item without guests, or a napkin item without a meal, is `need_info`.

Status precedence (both functions): `invalid`, then `need_info`, else `ok`.

### 4.5 Tier boundaries (guests → extra → count)
1 → 10 → 11 · 20 → 10 → 30 · 21 → 20 → 41 · 50 → 20 → 70 · 51 → 50 → 101 · 100 → 50 → 150 · 101 → 100 → 201 · 150 → 100 → 250.

### 4.6 The tool's text
Short plain English for the chat model. Tests check only the parts listed here, never the full wording.
- `ok`, count item: the item name (e.g. "Forks"), the count, the guests and the extra, e.g. `Forks: 120 (70 guests + 50 extra)`.
- `ok`, napkin item: the item name, the meal, and the word "yes" or "no" (as a whole word, lower case, and not both), e.g. `Dinner napkins for lunch: yes`.
- `need_info`: one question ending in `?`; for a count item it contains "guests", for a napkin item "meal" and the meal names from the rules.
- `invalid`: starts with "invalid", says what was wrong, and shows the expected format with an example call. It contains `"item"`, `"guests"` and `"meal"` (with the double quotes), and for an unknown item every name in `FOOD_ITEMS`.

## 5. Acceptance criteria
- **AC-1:** For each of the five count items, `count = guests + extra` with the tier extras in §4.5, including every boundary listed there. `item` is the canonical name, `guests`, `extra` and `count` are set, `answer` and `meal` are `None`.
- **AC-2:** All five count items give the same numbers for the same guests (spoons, forks, knives, small plates and large plates are not different from each other).
- **AC-3:** For napkin items, `answer` follows the rules file's table for the meal: with the real rules, breakfast and reception give cocktail `True` / dinner `False`; lunch and dinner give cocktail `False` / dinner `True`. `item`, `answer` and `meal` are set; `guests`, `extra` and `count` are `None`.
- **AC-4:** Meal names ignore case and spaces ("Lunch", " DINNER "). Item names ignore case, spaces, `_` / `-`, and accept the singular (§4.4).
- **AC-5:** A count item with no, `null` or `0` guests is `need_info`; a napkin item with no, `null` or blank meal is `need_info`. Nothing is guessed.
- **AC-6:** Bad values are `invalid`, never an exception: unknown, missing or blank item; guests `-5`, `2.5`, `"seventy"` for a count item; a meal not in the rules for a napkin item; two items in a list; `args` not a mapping. Precedence: `invalid` before `need_info`.
- **AC-7:** `guests` is ignored for napkin items and `meal` is ignored for count items, even when bad (never `invalid` because of them). Extra keys are ignored.
- **AC-8:** Raw-argument shapes: `"70"`, `70.0` and `70` are the same guests; a one-item list for `item` or `meal` is that item.
- **AC-9:** The text follows §4.6 (ok for both kinds, `need_info`, `invalid`). Every `invalid` text contains `"item"`, `"guests"` and `"meal"`; the unknown-item text lists all of `FOOD_ITEMS`.
- **AC-10:** `make_food_tool(rules)` and `FOOD_TOOL` have the schema in §3.2. Invoking the tool with an argument dict returns `run_food_tool(args, rules).text`. The tool description has the two example calls.
- **AC-11:** `load_food_rules` raises `FoodRulesError` for each §4.1 error case and loads Appendix A. Changing the tiers or the napkin table in a rules file changes the answers (nothing is hard-coded to Appendix A's numbers). A rules file with a meal "brunch" makes "brunch" valid.
- **AC-12:** `calculate_food_item(..., rules=None)` with `FOOD_RULES_FILE` monkeypatched to a missing path raises `FoodRulesError`. Importing `blc.tools.food_tools` reads no file and leaves `langchain_core` out of `sys.modules` (checked in a fresh subprocess).
- **AC-13** *(integration)*: With the real file (Appendix A), `calculate_food_item("forks", guests=70)` gives 120; `("small plates", guests=101)` gives 201; `("dinner napkins", meal="Dinner")` is `answer=True`; `("cocktail napkins", meal="lunch")` is `answer=False`.
- **AC-14** *(manual)*: Code structure per `CLAUDE.md`: files only in `src/blc/tools/food_tools/` (new) and nothing else changed; modules split by job (e.g. rules loading, counts, napkins, raw arguments, text, the LangChain tool), no catch-all modules; calculation modules do no I/O (only the rules loader reads the file); each file about 250 lines or fewer.

## 6. Test cases
Unit tests use the **test rules** (Appendix A written to `tmp_path`, loaded with `load_food_rules`) unless stated.

### 6.1 COUNT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| COUNT-1 | `forks`, guests 1 / 20 / 21 / 50 | count 11 / 30 / 41 / 70 | AC-1 |
| COUNT-2 | `forks`, guests 51 / 100 / 101 / 150 | count 101 / 150 / 201 / 250 | AC-1 |
| COUNT-3 | `forks`, guests 70 | extra 50, count 120, `guests=70`, `item="forks"`, `answer` and `meal` None | AC-1 |
| COUNT-4 | each of the five count items, guests 70 | all count 120 | AC-1, AC-2 |
| COUNT-5 | `spoons`, guests 0 / none | `need_info`, `count` None | AC-5 |
| COUNT-6 | `knives`, guests -5 / 2.5 | `invalid` | AC-6 |
| COUNT-7 | `forks`, guests 70, meal "brunch" (unknown) | `ok`, count 120 (meal ignored) | AC-7 |

### 6.2 NAPKIN
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| NAPKIN-1 | `cocktail napkins` for breakfast / reception / lunch / dinner | True / True / False / False | AC-3 |
| NAPKIN-2 | `dinner napkins` for breakfast / reception / lunch / dinner | False / False / True / True | AC-3 |
| NAPKIN-3 | `dinner napkins`, meal "Lunch", " DINNER " | same as lower case; `meal` is `"lunch"` / `"dinner"` | AC-4 |
| NAPKIN-4 | `dinner napkins`, no meal / `None` / `"  "` | `need_info`, `answer` None | AC-5 |
| NAPKIN-5 | `dinner napkins`, meal "brunch" | `invalid` | AC-6 |
| NAPKIN-6 | `cocktail napkins`, meal "lunch", guests -5 | `ok`, `answer` False (guests ignored) | AC-7 |
| NAPKIN-7 | napkin result fields | `guests`, `extra`, `count` None; `answer` is a bool | AC-3 |

### 6.3 ARGS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ARGS-1 | items "Fork", "SMALL  plate", "small_plates", "large-plates", "Cocktail Napkin", "knife" | the canonical item, with guests 70 or meal "lunch" | AC-4 |
| ARGS-2 | `{"item": "forks", "guests": "70"}` / `70.0` / `70` | all count 120 | AC-8 |
| ARGS-3 | `{"item": ["forks"], "guests": 70}`; `{"item": "dinner napkins", "meal": ["lunch"]}` | `ok` | AC-8 |
| ARGS-4 | item missing / `None` / `""` / "chairs" | `invalid` | AC-6 |
| ARGS-5 | `{"item": ["forks", "knives"], "guests": 70}` | `invalid` | AC-6 |
| ARGS-6 | `{"item": "forks", "guests": "seventy"}` | `invalid` | AC-6 |
| ARGS-7 | args is a list / string / `None` | `invalid`, no exception | AC-6 |
| ARGS-8 | `{"item": "forks", "guests": 70, "color": "red"}` | `ok`, count 120 | AC-7 |
| ARGS-9 | `{"item": "chairs", "guests": -5}` | `invalid` (not `need_info`) | AC-6 |
| ARGS-10 | `{"item": "forks"}` | `need_info` | AC-5 |

### 6.4 TEXT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TEXT-1 | forks, guests 70 | text contains "Forks", "120", "70 guests", "50 extra" | AC-9 |
| TEXT-2 | dinner napkins, lunch | text contains "Dinner napkins", "lunch" and the whole word "yes", not "no" | AC-9 |
| TEXT-3 | cocktail napkins, lunch | contains the whole word "no", not "yes" | AC-9 |
| TEXT-4 | count item, no guests | ends with `?`, contains "guests" | AC-9 |
| TEXT-5 | napkin item, no meal | ends with `?`, contains "meal" and each of breakfast, reception, lunch, dinner | AC-9 |
| TEXT-6 | item "chairs" | starts with "invalid", contains `"item"`, `"guests"`, `"meal"` and all seven `FOOD_ITEMS` names | AC-9 |
| TEXT-7 | guests -5 for forks | starts with "invalid", contains `"item"`, `"guests"`, `"meal"` | AC-9 |

### 6.5 TOOL
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TOOL-1 | `convert_to_openai_tool(FOOD_TOOL)["function"]` | name `FOOD_TOOL_NAME`; `parameters` exactly §3.2 (keys, `required`, no banned keywords) | AC-10 |
| TOOL-2 | description | contains two example calls: one with `item` and `guests`, one with `item` and `meal` | AC-10 |
| TOOL-3 | `make_food_tool(rules).invoke({"item": "forks", "guests": 70})` | the `.text` of `run_food_tool` for the same args | AC-10 |
| TOOL-4 | `make_food_tool(rules).invoke({"item": "dinner napkins", "meal": "lunch"})` | text with "yes" | AC-10 |
| TOOL-5 | `make_food_tool()` built, with `FOOD_RULES_FILE` monkeypatched to a missing path | no error when made; error only when invoked | AC-10, AC-12 |

### 6.6 FILE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FILE-1 | Appendix A loads | no error | AC-11 |
| FILE-2 | missing file; `"{"`; `{}`; `extras` empty; `napkins` empty | `FoodRulesError` each | AC-11 |
| FILE-3 | `extras` with decreasing `guests_up_to`; last tier not `null`; an early tier `null`; negative `extra` | `FoodRulesError` each | AC-11 |
| FILE-4 | a meal with no `dinner` key; a non-boolean `cocktail`; a blank meal name | `FoodRulesError` each | AC-11 |
| FILE-5 | rules with tiers `[{"guests_up_to": 10, "extra": 1}, {"guests_up_to": null, "extra": 2}]`, forks guests 10 / 11 | count 11 / 13 | AC-11 |
| FILE-6 | rules adding meal "brunch" with cocktail True, dinner False | cocktail napkins for "brunch": `ok`, True | AC-11 |
| FILE-7 | `calculate_food_item("forks", guests=70)` with `FOOD_RULES_FILE` monkeypatched to a missing path | raises `FoodRulesError` | AC-12 |
| FILE-8 | fresh subprocess: `import blc.tools.food_tools`; then check `sys.modules` | no `langchain_core`; no file read | AC-12 |
| FILE-9 *(integration)* | real file: forks 70; small plates 101; dinner napkins "Dinner"; cocktail napkins "lunch" | 120; 201; True; False | AC-13 |

## Appendix A: rules file (`data/pull_sheet/rules/food.json`, and the test rules)
```json
{
  "extras": [
    {"guests_up_to": 20, "extra": 10},
    {"guests_up_to": 50, "extra": 20},
    {"guests_up_to": 100, "extra": 50},
    {"guests_up_to": null, "extra": 100}
  ],
  "napkins": {
    "breakfast": {"cocktail": true,  "dinner": false},
    "reception": {"cocktail": true,  "dinner": false},
    "lunch":     {"cocktail": false, "dinner": true},
    "dinner":    {"cocktail": false, "dinner": true}
  }
}
```
