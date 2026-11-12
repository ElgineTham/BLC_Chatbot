# Spec 015: Recipe scaling tool (`scale_recipe`)

- **Status:** approved (revision 1)
- **Date:** 2026-11-12 (revision 1: 2026-11-12)

## 1. Goal
Staff ask how much of each ingredient goes into a batch ("how much lemon concentrate for 6 gallons of lemonade?"). Today these go to the documents, and the 7B model must multiply the 1-gallon recipe itself. This spec adds a second calculator tool, `scale_recipe`, built like `calculate_bev_item` (spec 005): a pure calculation over a JSON recipe book, a flat schema a 7B model can fill in, lenient raw arguments, and a short text for the model to repeat. The tool returns the scaled ingredients **and** the method steps (written without amounts), so the answer never copies the 1-gallon amounts from `lemonade.md`. There is one recipe now (Lemonade); more recipes are added later by adding entries to the JSON file, with no code change.

This spec builds and unit-tests **the tool only**. It is not connected to the chatbot yet: the router's `scale_recipe` row stays `available=False`, so the chat flow behaves exactly as today. Wiring it in (router, tool step, chat flow) and the real-model evals are a follow-up spec (016).

## 2. Out of scope
- **Connecting the tool to the chatbot** (spec 016): making the router's `scale_recipe` row available, the classifier prompt, the tool step running the router's chosen tool, `scripts/chat.py` (`CHAT_TOOLS`, tool-step prompts), and updating spec 005 T3 and spec 013 K27 to K29.
- **Running the pipeline:** no test runs `run_turn` or the chat flow, with a fake or a real model, and there are no evals in this spec.
- Recipes whose yield is not in gallons (food, pans, servings), unit conversion (oz to cups or quarts), and several recipes in one tool call.
- Any change to `data/recipes/lemonade.md`, to `scripts/ingest.py`, or to `src/blc/pull_sheet/`. The JSON file is not ingested (`ingest.py` reads only `.md`).
- Adding lemon concentrate to the beverage pull sheet.
- A plain "how do I make lemonade?" with no amount: it stays a documents question (spec 013's rule: TOOL only when the answer depends on a quantity).
- Any change to `src/blc/router/` or `scripts/`.
- Streaming, timing and the judge (other specs).

## 3. Interface contract

### 3.1 The tool: `src/blc/tools/recipe_tools/` (new feature package)
Everything below is importable as `from blc.tools.recipe_tools import ...`.

```python
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from langchain_core.tools import BaseTool

RECIPE_TOOL_NAME = "scale_recipe"
RECIPE_STATUSES: tuple[str, ...] = ("ok", "need_info", "no_recipe", "invalid")
RECIPES_FILE: Path   # <repo root>/data/recipes/recipes.json

class RecipeFileError(Exception):
    """The recipe file is missing or does not follow §4.1."""

class RecipeBook:
    """The loaded recipes. Opaque to tests: made only by load_recipe_book."""

def load_recipe_book(path: Path | None = None) -> RecipeBook:
    """path=None means RECIPES_FILE. Raises RecipeFileError (§4.1)."""

@dataclass(frozen=True)
class ScaledIngredient:
    name: str          # as written in the file, e.g. "Lemon concentrate"
    amount: Fraction   # scaled amount; for a fill ingredient: the batch size in gallons
    unit: str          # as written in the file, e.g. "oz"; "gallon" for a fill ingredient
    fill: bool         # True for "fill to the batch size" (e.g. Water)

@dataclass(frozen=True)
class RecipeResult:
    status: str                               # one of RECIPE_STATUSES
    text: str                                 # what the tool returns to the chat model (§4.6)
    recipe: str | None                        # the recipe's display name when it was found; else None
    gallons: Fraction | None                  # batch size used; None unless status is "ok"
    from_guests: bool                         # True if gallons were worked out from guests
    ingredients: tuple[ScaledIngredient, ...] # in file order; () unless status is "ok"
    steps: tuple[str, ...]                    # the file's steps, in order; () unless status is "ok"

def scale_recipe(
    recipe: str,
    gallons: int | float | Fraction | None = None,
    guests: int | None = None,
    book: RecipeBook | None = None,
) -> RecipeResult:
    """Pure calculation. book=None means load_recipe_book(). Never raises for bad user
    input (status "invalid"). RecipeFileError from loading the book propagates."""

def run_recipe_tool(args: Mapping[str, object], book: RecipeBook | None = None) -> RecipeResult:
    """Run the tool on a raw argument dict as the chat model sends it (§4.5).
    Never raises for bad arguments: they give status "invalid"."""

def make_recipe_tool(book: RecipeBook | None = None) -> BaseTool:
    """A LangChain tool named RECIPE_TOOL_NAME with the schema in §3.3. Invoking it with an
    argument dict returns run_recipe_tool(args, book).text. book=None means the real file,
    loaded when the tool runs, not when it is made (importing the package reads no file)."""

RECIPE_TOOL: BaseTool   # make_recipe_tool(): the tool the chatbot uses
```

### 3.2 The argument check: `src/blc/tool_step/` (spec 009, extended)
```python
def check_arguments(args: Mapping[str, object], question: str, tool: str = "calculate_bev_item") -> str | None:
    """Unchanged for tool="calculate_bev_item". For tool="scale_recipe" only the number
    rule applies (§4.7). Never raises.
    The chat flow does not call it with tool="scale_recipe" yet (spec 016)."""
```

### 3.3 What the model receives (tool schema)
`convert_to_openai_tool(tool)["function"]`, for `RECIPE_TOOL` and any `make_recipe_tool(book)`, has `name == RECIPE_TOOL_NAME`, a `description`, and exactly these `parameters` (descriptions shown as `…`):
```json
{
  "type": "object",
  "properties": {
    "recipe":  {"type": "string", "description": "…"},
    "gallons": {"type": "number", "exclusiveMinimum": 0, "description": "…"},
    "guests":  {"type": "integer", "minimum": 1, "description": "…"}
  },
  "required": ["recipe"]
}
```
- Each property has exactly the keys shown. Nothing inside `parameters` uses `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title` or the type `"null"`.
- The tool `description` says it scales a recipe's ingredient amounts to a batch size, that the model must use it instead of calculating, and contains **at least two example calls** as argument dicts: one with `gallons`, one with `guests`.
- `recipe`: the drink's name as the user said it. `gallons`: the batch size the user said, left out when none was given, never worked out from guests. `guests`: left out when no guest or people count was given. (Wording is the developer's.)

### 3.4 Files
- Reads `data/recipes/recipes.json` (format in §4.1; the real file's content is Appendix A) only when `book=None`. No test in this spec needs the real file. `data/` is outside the developer's write access, so the planner or the user creates it (needed by spec 016).

## 4. Inputs and outputs

### 4.1 The recipe file
```json
{
  "recipes": {
    "<display name>": {
      "also_written_as": ["<other name>", ...],
      "yield_gallons": <number > 0>,
      "ingredients": [
        {"name": "<name>", "amount": <number > 0>, "unit": "<unit>"},
        {"name": "<name>", "fill": true}
      ],
      "steps": ["<step without amounts>", ...]
    }
  }
}
```
`load_recipe_book` raises `RecipeFileError` when: the file is missing; it is not valid JSON; `recipes` is missing or not an object; a recipe has a missing, zero or negative `yield_gallons`; an ingredient has neither (`amount` > 0 and a non-empty `unit`) nor `"fill": true`; `ingredients` or `steps` is missing, empty, or not a list (of objects or of non-empty strings, respectively); two names (display names or `also_written_as`, ignoring case) are the same across the book. `also_written_as` may be missing (= none).

### 4.2 Finding the recipe
A requested name matches a recipe's display name or one of its `also_written_as` names, **ignoring case, surrounding spaces and repeated spaces, a leading "the" and a trailing word "recipe"**. No partial matches: "lemon" and "lemonades" match nothing. A blank name is **invalid**. A name that matches nothing gives status `no_recipe`.

### 4.3 Batch size
1. **`gallons` given:** must be > 0, else **invalid**. A float is taken as its decimal value (2.5 is exactly 5/2). `from_guests=False`. If `guests` is also given, `gallons` wins.
2. **Only `guests` given:** must be an integer ≥ 1, else **invalid**. Gallons come from guests by the pull sheet rule (25 guests per gallon, a half rounds up, minimum 1), the same as `calculate_bev_item`'s `gallons_each`. `from_guests=True`.
3. **Neither:** status `need_info`.

### 4.4 Scaling
For a recipe with `yield_gallons` Y and a batch of G gallons, each measured ingredient's amount is `amount × G / Y` (exact `Fraction`), with its unit unchanged. A fill ingredient gets `amount = G`, `unit = "gallon"`, `fill=True`. `steps` are the file's steps unchanged.

### 4.5 Raw arguments (`run_recipe_tool`)
Expected shape: `{"recipe": "lemonade", "gallons": 6}` or `{"recipe": "lemonade", "guests": 90}`.
- `recipe`: a string; a list of exactly one string is that string. If `recipe` is missing, null or blank, the first of `drink`, `drinks` or `name` that holds a string (or a list of exactly one string) is used. Otherwise **invalid**. A list of two or more names is **invalid**.
- `gallons`: a number or a numeric string (`"6"`, `"2.5"`); a list of exactly one such value is that value. `null`, `0` and `[]` mean not given. Negative, non-numeric (`"six"`, `"6 gal"`) or a list of two or more values is **invalid**.
- `guests`: `null` or `0` mean not given; otherwise a whole number ≥ 1 (`90`, `90.0`, `"90"` are all 90); anything else (`-5`, `2.5`, `"ninety"`) is **invalid**.
- Unknown extra keys are ignored. `args` that is not a mapping is **invalid**.

Status precedence (both functions): `invalid`, then `no_recipe`, then `need_info`, else `ok`.

### 4.6 The tool's text
Short plain English for the chat model. Tests check only the parts listed here, never the full wording.
- `ok`: the recipe's display name; the batch size in gallons, plus "from N guests" when `from_guests`; each ingredient as `<name>: <amount> <unit>` (e.g. `Lemon concentrate: 42 oz`); each fill ingredient as `<name>: fill to <G> gallons` (e.g. `Water: fill to 6 gallons`); then every step, in order, numbered from 1.
- **Numbers in `text`:** a whole number has no decimals (`42`, not `42.0`); otherwise at most two decimals with trailing zeros dropped (`17.5`, `2.33`, `0.75`). An amount of exactly 1 gallon is singular: `text` never contains "1 gallons" as whole words.
- `need_info`: one question ending in `?` that contains "gallons" and "guests".
- `no_recipe`: the requested name (stripped), the words "no recipe", and the display name of every recipe in the book.
- `invalid`: starts with "invalid", says what was wrong, and shows the expected format with an example call. It contains `"recipe"`, `"gallons"` and `"guests"` (with the double quotes).

Illustrative example (`recipe="lemonade"`, `guests=120`; not compared word for word):
```
Lemonade for 5 gallons (from 120 guests):
Lemon concentrate: 35 oz
Water: fill to 5 gallons
Steps: 1. Pour the lemon concentrate into a clean container that holds the whole batch. 2. ...
```

### 4.7 Argument check for `scale_recipe`
`check_arguments(args, question, tool="scale_recipe")` returns a reason starting with `REJECTED_PREFIX` when a `gallons` or `guests` value (number, numeric string, or list of them) is not a number in the question, exactly as spec 009's number rule does for the beverage tool. Spec 009's "item must be everything" rule **never** applies to `scale_recipe`. Calls with `tool` omitted behave exactly as before (spec 009). (Row 4's question must not contain a pull sheet supply word such as "lemon": then the question's items are not only `everything` and spec 009's rule does not fire.)

| args | question | result |
|---|---|---|
| `{"recipe": "lemonade", "guests": 90}` | How do I make lemonade for 90 guests? | `None` |
| `{"recipe": "lemonade", "gallons": 4}` | How do I make lemonade for 90 guests? | starts with `REJECTED_PREFIX`, mentions `gallons` |
| `{"recipe": "lemonade", "gallons": ["6"]}` | Concentrate for six gallons of lemonade? | `None` (spelled numbers count, spec 009) |
| `{"recipe": "lemonade", "guests": 70}` | What concentrate do I pack for lemonade for 70 guests? | `None` (with `tool` omitted the same args give the "everything" reason) |
| `{"recipe": "lemonade", "gallons": 1}` | How much concentrate for lemonade for 40 guests? | `None` (the number 1 is always accepted, spec 009) |

## 5. Edge cases
Unit tests use the **test book** (Appendix A plus Appendix B, written to `tmp_path`) unless stated.

**Recipe file (unit):**
- EC-1: Appendix A alone and Appendix A+B load without error. Each §4.1 error case raises `RecipeFileError`: missing file, `"{"`, `{}`, `{"recipes": []}`, `yield_gallons` 0 or −1 or missing, an ingredient `{"name": "X", "amount": 5}` (no unit), `{"name": "X", "amount": 0, "unit": "oz"}`, `{"name": "X"}`, empty `ingredients`, empty `steps`, a step `""`, and two recipes where one's `also_written_as` equals the other's name in a different case.
- EC-2: `scale_recipe("lemonade", gallons=1, book=<book>)` reads no other file, and `scale_recipe(..., book=None)` with `RECIPES_FILE` monkeypatched to a missing path raises `RecipeFileError`.

**Scaling (unit, exact):**
- EC-3: Lemonade, gallons 6 → `ok`, `recipe="Lemonade"`, `gallons=6`, ingredients `(Lemon concentrate, 42, "oz", False)`, `(Water, 6, "gallon", True)`; `steps` equal Appendix A's four steps; `from_guests=False`.
- EC-4: Lemonade, gallons 1 → 7 oz, water 1; 2.5 → `Fraction(35, 2)` oz; `Fraction(1, 3)` → `Fraction(7, 3)` oz; 0.25 → `Fraction(7, 4)`.
- EC-5: Lemonade by guests → gallons, concentrate: 1 → 1, 7; 25 → 1, 7; 37 → 1, 7; 38 → 2, 14; 70 → 3, 21; 75 → 3, 21; 120 → 5, 35. `from_guests=True`.
- EC-6: gallons 4 and guests 120 → gallons 4, 28 oz, `from_guests=False`.
- EC-7 (yield ≠ 1, Appendix B): Fruit punch, gallons 3 → Orange concentrate 15 oz, Simple syrup `Fraction(9, 2)` oz, Water fill 3; gallons 1 → 5 oz, `Fraction(3, 2)` oz; guests 70 → 3 gallons, same as gallons 3.
- EC-8: names: "Lemonade", " lemonade ", "LEMONADE", "lemonade recipe", "the lemonade", "Fresh  lemonade" → Lemonade; "punch" → Fruit punch. "lemon", "lemonades", "iced tea" → `no_recipe`, `recipe=None`, no ingredients.
- EC-9: Lemonade with no gallons and no guests → `need_info`, `recipe="Lemonade"`, `gallons=None`, `ingredients=()`, `steps=()`. "iced tea" with no amounts → `no_recipe` (precedence).
- EC-10: invalid, no raise: recipe `""` or `"   "`; gallons 0 or −2; guests 0, −5 or 2.5; "iced tea" with gallons −2 → `invalid` (precedence over `no_recipe`).

**Text (unit):**
- EC-11: EC-3's text contains "Lemonade", "Lemon concentrate: 42 oz", "Water: fill to 6 gallons", and each Appendix A step with "1." before the first step and "4." before the fourth. EC-5's 120-guest text contains "35 oz", "5 gallons" and "from 120 guests".
- EC-12: number format: gallons 2.5 → text contains "17.5 oz" and "2.5 gallons"; `Fraction(1, 3)` → "2.33 oz"; gallons 6 → "42 oz", never "42.0". Gallons 1 → text contains "1 gallon" and not "1 gallons".
- EC-13: `need_info` text ends with `?` and contains "gallons" and "guests"; `no_recipe` for " Iced tea " contains "Iced tea", "no recipe", "Lemonade" and "Fruit punch"; each EC-10 and EC-16 `invalid` text starts with "invalid" and contains `"recipe"`, `"gallons"` and `"guests"`.

**Raw arguments (unit):**
- EC-14: `{"recipe": "lemonade", "gallons": 6}`, `"gallons": "6"`, `"gallons": [6]`, `"gallons": 6.0`, `{"recipe": ["lemonade"], "gallons": 6}`, `{"drinks": ["lemonade"], "gallons": 6}`, `{"name": "lemonade", "gallons": 6}`, and `{"recipe": "lemonade", "gallons": 6, "item": "cambros"}` → all equal EC-3.
- EC-15: `{"recipe": "lemonade", "guests": 70}`, `"guests": "70"`, `"guests": 70.0`, `{"recipe": "lemonade", "gallons": null, "guests": 70}`, `{"recipe": "lemonade", "gallons": 0, "guests": 70}`, `{"recipe": "lemonade", "gallons": [], "guests": 70}` → 3 gallons, 21 oz, `from_guests=True`. `{"recipe": "lemonade"}`, `{"recipe": "lemonade", "guests": 0}`, `{"recipe": "lemonade", "guests": null}` → `need_info`.
- EC-16: invalid, no raise: `{}`; `{"recipe": null}`; `{"recipe": 5}`; `{"recipe": ["lemonade", "fruit punch"], "gallons": 2}`; `{"recipe": "lemonade", "gallons": -2}`; `"gallons": "six"`; `"gallons": "6 gal"`; `"gallons": [6, 2]`; `"guests": -5`; `"guests": 2.5`; `"guests": "ninety"`; `args` = `["lemonade"]` (not a mapping).

**Tool object and schema (unit):**
- EC-17: `convert_to_openai_tool(RECIPE_TOOL)["function"]["parameters"]` and the same for `make_recipe_tool(<test book>)` equal §3.3 exactly (descriptions aside) and contain none of the forbidden keys or `"null"` anywhere (checked recursively). `RECIPE_TOOL.name == RECIPE_TOOL_NAME`. The tool's `description` contains at least two `{` and the words "recipe", "gallons" and "guests".
- EC-18: `make_recipe_tool(<test book>).invoke({"recipe": "lemonade", "gallons": 6})` equals `run_recipe_tool(same, <test book>).text`; `.invoke({"recipe": "lemonade", "gallons": -1})` returns a text starting with "invalid" and does not raise. Importing `blc.tools.recipe_tools` and calling `make_recipe_tool()` read no file.

**Argument check (unit):**
- EC-19: every row of §4.7. `{"recipe": "lemonade", "guests": [90]}` with "lemonade for 90 guests" → `None`; `{"recipe": "lemonade"}` (no numbers) → `None` for any question. Odd args (`{"gallons": object()}`) never raise.
- EC-20: spec 009's existing `check_arguments(args, question)` cases give the same results with `tool` omitted and with `tool="calculate_bev_item"`.

## 6. Acceptance criteria
- **AC-1 (recipe file):** EC-1 and EC-2.
- **AC-2 (scaling):** `scale_recipe` gives the results in EC-3 to EC-10 (status, `recipe`, `gallons`, `from_guests`, `ingredients`, `steps`).
- **AC-3 (text):** EC-11 to EC-13.
- **AC-4 (raw arguments):** EC-14 to EC-16; `run_recipe_tool` never raises.
- **AC-5 (tool object):** EC-17 and EC-18.
- **AC-6 (argument check):** EC-19 and EC-20.
- **AC-7 (regression):** all existing unit tests (specs 001 to 014) pass **unchanged**; no existing test file is edited. The router still sends recipe questions to DOCS (spec 013 K27 to K29 unchanged).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | The scaling code does no I/O except loading the book through `load_recipe_book`; it prints nothing and calls no model. Importing the package reads no file. | unit (EC-18) and manual (code review) |
| NFR-3 | No recipe knowledge in code: names, yields, amounts and steps come only from the JSON file. Adding a recipe with a gallon yield to the file needs no code change (EC-7 shows this with Appendix B). The guests-to-gallons rule comes from the pull sheet package, not a second copy. | unit (EC-7) and manual (code review) |
| NFR-4 | The package mirrors `bev_tools`: modules split by job (book loading, scaling, raw arguments, text, LangChain tool), about 250 lines each, no catch-all modules. | manual (code review) |
| NFR-5 | All tests in this spec are unit tests: they need no Ollama and no network, and read nothing under `data/` (the test book is written to `tmp_path`). | unit (review by test-evaluator) |
| NFR-6 | The tool and property descriptions and the `invalid` text contain no question from earlier specs' evals word for word, and no example uses Lemonade with 3, 5 or 6 gallons or 90 guests (amounts used by spec 005 T3 and spec 013 K27 to K29, and kept free for spec 016's evals). | manual (code review) |
| NFR-7 | No file under `src/blc/router/`, `scripts/` or `tests/` (outside `tests/recipe_tools/`) changes. | manual (`git diff` review) |

Tests go in `tests/recipe_tools/` (no `__init__.py`): `conftest.py` (Appendix A+B written to `tmp_path`), `test_recipe_book.py` (AC-1), `test_recipe_scaling.py` (AC-2), `test_recipe_text.py` (AC-3), `test_recipe_args.py` (AC-4), `test_recipe_tool.py` (AC-5), `test_recipe_check.py` (AC-6). AC-7 is checked by running the existing unit suite.

## Appendix A: `data/recipes/recipes.json` (the real file, created for spec 016; also part of the test book)
```json
{
  "recipes": {
    "Lemonade": {
      "also_written_as": ["Fresh lemonade"],
      "yield_gallons": 1,
      "ingredients": [
        {"name": "Lemon concentrate", "amount": 7, "unit": "oz"},
        {"name": "Water", "fill": true}
      ],
      "steps": [
        "Pour the lemon concentrate into a clean container that holds the whole batch.",
        "Add water until the total volume reaches the batch size.",
        "Stir well until fully mixed.",
        "Taste and adjust if needed before service."
      ]
    }
  }
}
```

## Appendix B: test-only recipe (added to the test book, never to `data/`)
Inside `"recipes"` of the test book, next to Lemonade:
```json
"Fruit punch": {
  "also_written_as": ["Punch"],
  "yield_gallons": 2,
  "ingredients": [
    {"name": "Orange concentrate", "amount": 10, "unit": "oz"},
    {"name": "Simple syrup", "amount": 3, "unit": "oz"},
    {"name": "Water", "fill": true}
  ],
  "steps": [
    "Pour the orange concentrate and simple syrup into a clean container.",
    "Add water up to the batch size and stir."
  ]
}
```

## Revision history
- **Revision 1 (2026-11-12)**, after the first run (190 of 192 spec 015 tests passed; both failures were in the tests or the spec, not the code). **No code change.**
  - **§4.7 row 4:** the question was "What lemon concentrate do I pack …". "lemon" is a pull sheet supply word, so with `tool` omitted spec 009's "everything" rule does not fire and the row's note was wrong. The question is now "What concentrate do I pack for lemonade for 70 guests?".
  - **§4.7 new row 5:** `gallons: 1` is always accepted (spec 009), also for `scale_recipe`.
  - **Tests to change** (in `tests/recipe_tools/` only; no assertion weakened):
    - `test_recipe_text.py::test_gallons_text_has_no_from_guests`: it calls `gallons=6, guests=120` but asserts "4 gallons". Make the call and the assertion agree with EC-6 (`gallons=4, guests=120` → text contains "4 gallons" and not "from 120 guests").
    - `test_recipe_check.py::test_row4_everything_rule_does_not_apply`: use the new row 4 question. Add a test for row 5.
    - Every test that monkeypatches `RECIPES_FILE` (in `test_recipe_book.py` and `test_recipe_tool.py`) must point it at a path under `tmp_path` and **assert that the patch reached the loader** (e.g. `load_recipe_book()` with a valid book written to the patched path loads it, or with a missing patched path raises `RecipeFileError`), so the tests stay meaningful once the real `data/recipes/recipes.json` exists.
    - `test_recipe_args.py::test_odd_values_never_raise`: `{"recipe": "lemonade", "guests": {"a": 1}}` and `{"recipe": {"x": 1}, "gallons": 2}` must give status `invalid` (§4.5: anything else is invalid), not just "any status". Shapes the spec does not define may keep the "never raises" check only.
    - `test_recipe_scaling.py::test_invalid_guests_with_valid_gallons`: its name and docstring say "invalid guests" but it checks valid guests. Rename it to say what it checks, or delete it if it only repeats EC-6.
