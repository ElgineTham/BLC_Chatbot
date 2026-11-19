# Spec 042: Serving utensils tool (`calculate_serving_utensils`)

- **Status:** approved (revision 1, done)
- **Date:** 2026-11-18 (revision 1: blank-string qty is `need_info`)

## 1. Goal
The pull sheet has a **Serving Utensils** box (small tongs, large tongs, salad tongs, dressing/sauce bowl, ladle/sauce spoon, serving spoon, spreader/knives, mayo/mustard, condiments, honey bear). How many of each to pull depends on which food items are on the BEO and how much of each is ordered. This spec adds a fourth calculator tool, `calculate_serving_utensils`, built like `calculate_bev_item` and `calculate_food_item`. It takes the food lines of an order and returns the total of each serving utensil. Which food needs which utensil, and how many, comes from a rules file, so the business rules can change without code changes.

This spec builds and unit-tests **the tool only**. It is not connected to the chatbot (follow-up spec, like 029 → 030).

## 2. Out of scope
- **Connecting the tool to the chatbot:** planner tools, `DEFAULT_TOOL_RUNNERS`, `invented_numbers`, prompts, evals.
- The **Condiments** box (mayo 12-oz, mustard 8-oz, raspberry preserves, cream cheese), the **Food Items** box (already covered by `calculate_food_item`), Service Food Items, Specialty Items, beverages, linens.
- Expanding breakfast packages (Cascade, Olympic) into their items: the caller passes the component lines, as the BEO lists them.
- Tong colour or material ("only black plastic tongs for sets").
- Reading a BEO image or text; changes to `blc.pull_sheet`, `blc.tools.bev_tools`, `blc.tools.food_tools`, `blc.tools.recipe_tools`, `blc.planner`, `blc.flow`, `backend/scripts/`, ingest, or the knowledge `.md` files.
- Units other than those in §4.2 (e.g. pounds, trays as a unit).

## 3. Interface contract

### 3.1 `backend/src/blc/tools/serv_tools/` (new feature package)
Everything is importable as `from blc.tools.serv_tools import ...`. Importing the package reads no file and does not import `langchain_core`.

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SERV_TOOL_NAME = "calculate_serving_utensils"
SERV_UTENSILS: tuple[str, ...] = (
    "small tongs", "large tongs", "salad tongs", "dressing/sauce bowl",
    "ladle/sauce spoon", "serving spoon", "spreader/knives", "mayo/mustard",
    "condiments", "honey bear",
)
SERV_UNITS: tuple[str, ...] = ("each", "dozen", "bags", "packages")
SERV_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")
SERV_RULES_FILE: Path   # <repo root>/data/pull_sheet/rules/serving_utensils.json

class ServRulesError(Exception):
    """The rules file is missing or does not follow §4.1."""

class ServRules:
    """The loaded rules. Opaque to tests: made only by load_serv_rules."""

def load_serv_rules(path: Path | None = None) -> ServRules:
    """path=None means SERV_RULES_FILE. Raises ServRulesError (§4.1)."""

@dataclass(frozen=True)
class ServResult:
    status: str                         # one of SERV_STATUSES
    text: str                           # what the tool returns to the chat model (§4.5)
    utensils: dict[str, int] | None     # "ok" only: utensil -> total, only utensils with total > 0,
                                        # keys in SERV_UTENSILS order; {} when no food needs any
    foods: tuple[str, ...] | None       # "ok" only: the canonical food name of each line, in input order

def calculate_serving_utensils(
    lines: list[tuple[str, float | None, str | None]],
    rules: ServRules | None = None,
) -> ServResult:
    """Each line is (food, qty, unit); unit None means the food's own unit (§4.2).
    rules=None means load_serv_rules(). Never raises for bad user input.
    ServRulesError from loading propagates."""

def run_serv_tool(args: Mapping[str, object], rules: ServRules | None = None) -> ServResult:
    """Run the tool on a raw argument dict as the chat model sends it (§4.3).
    Never raises for bad arguments: they give status "invalid"."""
```

### 3.2 Files
- Reads `data/pull_sheet/rules/serving_utensils.json` (format §4.1) only when `rules=None`. The planner creates the real file from Appendix B once the user confirms it; `data/` is outside the developer's write access.

## 4. Inputs and outputs

### 4.1 The rules file
```json
{
  "foods": {
    "<food name>": {
      "unit": "<one of SERV_UNITS>",
      "aliases": ["<other name>", ...],
      "utensils": [{"utensil": "<one of SERV_UTENSILS>", "count": <int>, "per": <number|null>}, ...]
    }, ...
  }
}
```
- One food line needs `count` of the utensil if `per` is `null`, else `count × ceil(qty / per)`, with qty in the food's unit. `count` defaults to 1 when left out. A food with an empty `utensils` list is a known food that needs nothing. The same utensil may appear more than once in a food's list; the entries add up (e.g. a yogurt that carries both its granola spoons and its berry spoons).
- Totals are the sums over all lines. Two lines of the same food are counted separately (each tray or platter gets its own utensils).
- `load_serv_rules` raises `ServRulesError` when: the file is missing; it is not valid JSON; `foods` is missing or empty; a food name or alias is blank, or the same name (ignoring case and spaces) appears twice across foods and aliases; `unit` is missing or not in `SERV_UNITS`; `utensils` is missing or not a list; an entry's `utensil` is not in `SERV_UTENSILS`; `count` is not a whole number ≥ 1; `per` is not `null` and not a number > 0.

### 4.2 Units
- `qty` is in the food's unit from the rules when `unit` is not given.
- `each` and `dozen` convert into each other (1 dozen = 12 each); for example, 70 croissants "each" are 70/12 dozen. Any other pair of different units (e.g. `bags` for a `dozen` food) is **invalid**.
- Unit names match ignoring case and spaces, and accept the singular, plus "dz" for dozen ("Dozen", "bag", "package", "dz").

### 4.3 Raw arguments (`run_serv_tool`) and checks
Expected shape: `{"items": [{"food": "butter croissants", "qty": 3, "unit": "dozen"}, {"food": "classic deli sandwiches", "qty": 50}]}`.
- `items`: a non-empty list of objects. A single object (not in a list) is accepted as a one-item list. Missing, `null`, empty or another type is **invalid**.
- `food`: a string matched against the food names and aliases ignoring case, surrounding and repeated spaces and punctuation-only differences (`-`, `_`, `,`). Missing, blank or unknown is **invalid**, and the text names the bad food.
- `qty`: a number > 0 (`3`, `3.0`, `"3"`, `1.5` are accepted). Missing, `null`, `0` or a blank string (`""`, `"  "`) means not given, which is `need_info`; negative or non-numeric is **invalid**.
- `unit`: optional, see §4.2.
- Unknown keys are ignored. `args` that is not a mapping is **invalid**.
- Precedence over the whole call: if any line is `invalid` the call is `invalid`; else if any line is missing qty the call is `need_info`; else `ok`. No partial totals are returned.

### 4.4 Worked examples (test rules, Appendix A)
| Lines | `utensils` |
|---|---|
| croissants 2 dozen | `{"small tongs": 2}` |
| croissants 3 dozen | `{"small tongs": 4}` |
| croissants 70 each (5.83 dozen) | `{"small tongs": 6}` |
| deli sandwiches 50 | `{"large tongs": 1, "mayo/mustard": 2}` |
| deli sandwiches 51 | `{"large tongs": 1, "mayo/mustard": 3}` |
| croissants 2 dozen + bagels 2 dozen | `{"small tongs": 3, "spreader/knives": 1}` |
| tabbouleh salad 3 | `{"salad tongs": 3, "dressing/sauce bowl": 3}` |
| trail mix 12 bags | `{}` |

### 4.5 The tool's text
Short plain English for the chat model. Tests check only the parts listed here.
- `ok`: each utensil with a total > 0 and its number (e.g. `Small tongs: 2`), in `SERV_UTENSILS` order; when `utensils` is `{}`, a sentence containing "no serving utensils".
- `need_info`: one question ending in `?`, containing "how many" and the name of the food(s) without a quantity.
- `invalid`: starts with "invalid", says what was wrong, and shows the expected format with an example call containing `"items"`, `"food"`, `"qty"` and `"unit"` (with the double quotes). For an unknown food it names that food and the word "food".

## 5. Acceptance criteria
- **AC-1:** Utensil totals follow §4.1: `per: null` gives `count` per line, else `count × ceil(qty / per)`; totals add up over lines, and repeated foods count separately. `utensils` holds only totals > 0, keys in `SERV_UTENSILS` order; `foods` holds canonical names in input order.
- **AC-2:** A known food with no utensils gives `ok` with `utensils == {}` when it is the only line.
- **AC-3:** Units follow §4.2: no unit means the food's unit; each ↔ dozen convert; any other mismatch is `invalid`; unit spellings ("Dozen", "dz", "bag") are accepted.
- **AC-4:** Food names match canonical names and aliases ignoring case, spaces and `-` / `_` / `,` (e.g. the BEO line "Butter croissants served with raspberry preserves" when it is an alias).
- **AC-5:** A line with missing, `null`, `0` or blank-string (`""`, `"  "`) qty makes the call `need_info`; nothing is guessed.
- **AC-6:** Bad input is `invalid`, never an exception: unknown or blank food; negative or non-numeric qty; unknown unit; `items` missing, empty, `null` or a string; `args` not a mapping. One bad line makes the whole call `invalid`, even if other lines are fine or lack qty (precedence `invalid` > `need_info` > `ok`).
- **AC-7:** Raw shapes: `"3"`, `3.0` and `3` are the same qty; a single item object counts as a one-item list; unknown keys are ignored.
- **AC-8:** The text follows §4.5 for `ok`, empty `ok`, `need_info` and `invalid`.
- **AC-9:** `load_serv_rules` raises `ServRulesError` for each §4.1 error case and loads Appendix A. Changing `per`, `count`, `unit` or the utensil of a food in a rules file changes the result (nothing is hard-coded).
- **AC-10:** `calculate_serving_utensils(..., rules=None)` with `SERV_RULES_FILE` monkeypatched to a missing path raises `ServRulesError`. Importing `blc.tools.serv_tools` reads no file and leaves `langchain_core` out of `sys.modules` (checked in a fresh subprocess).
- **AC-11** *(integration)*: The real file (Appendix B, once confirmed) loads, and every food in `data/pull_sheet/menu/food.md` that Appendix B lists is a known food.
- **AC-12** *(manual)*: Code structure per `CLAUDE.md`: new files only in `backend/src/blc/tools/serv_tools/`, nothing else changed; modules split by job (rules loading, calculation, units, raw arguments, text); calculation modules do no I/O; each file about 250 lines or fewer.

## 6. Test cases
Unit tests use the **test rules** (Appendix A written to `tmp_path`, loaded with `load_serv_rules`) unless stated.

### 6.1 CALC
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| CALC-1 | croissants 3 dozen | `ok`, `{"small tongs": 4}`, `foods == ("butter croissants",)` | AC-1 |
| CALC-2 | deli sandwiches 25 / 26 / 50 / 51 | mayo/mustard 1 / 2 / 2 / 3; large tongs 1 each time | AC-1 |
| CALC-3 | croissants 2 dozen + bagels 2 dozen | `{"small tongs": 3, "spreader/knives": 1}` | AC-1 |
| CALC-4 | croissants 1 dozen twice (two lines) | small tongs 4 | AC-1 |
| CALC-5 | tabbouleh salad 3 | salad tongs 3, dressing/sauce bowl 3 (`count` with `per: 1`) | AC-1 |
| CALC-6 | key order of a mixed result | follows `SERV_UTENSILS` order | AC-1 |
| CALC-7 | trail mix 12 bags only | `ok`, `utensils == {}` | AC-2 |
| CALC-8 | trail mix 12 + croissants 1 dozen | `{"small tongs": 2}` | AC-1, AC-2 |
| CALC-10 | yogurt with toppings 68 | `{"serving spoon": 4, "honey bear": 2}` (repeated utensil adds up) | AC-1 |
| CALC-9 | croissants 0.5 / 2 / 2.5 / 4 / 4.5 dozen (tray = 2 dozen, 2 tongs per tray) | small tongs 2 / 2 / 4 / 4 / 6 | AC-1 |

### 6.2 UNIT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| UNIT-1 | croissants 70, unit `each`; croissants 24 / 25, unit `each` | small tongs 6; 2 / 4 | AC-3 |
| UNIT-2 | deli sandwiches 2, unit `dozen` (food unit each, per 25) | treated as 24 each: mayo/mustard 1 | AC-3 |
| UNIT-3 | croissants 3, unit "Dozen" / "dz" / "dozens" | `ok` | AC-3 |
| UNIT-4 | croissants 3, unit `bags` | `invalid` | AC-3, AC-6 |
| UNIT-5 | croissants 3, unit "pounds" | `invalid` | AC-6 |

### 6.3 ARGS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ARGS-1 | food "BUTTER  croissants", "butter-croissants", "Butter croissants served with raspberry preserves" | `butter croissants` | AC-4 |
| ARGS-2 | qty `"3"` / `3.0` / `3` | same result | AC-7 |
| ARGS-3 | `{"items": {"food": "butter croissants", "qty": 3}}` (no list) | `ok` | AC-7 |
| ARGS-4 | extra key `"color": "red"` on args and on an item | ignored, `ok` | AC-7 |
| ARGS-5 | qty missing / `null` / `0` / `""` / `"  "` | `need_info` | AC-5 |
| ARGS-6 | food "lasagna"; food `""`; food missing | `invalid` | AC-6 |
| ARGS-7 | qty `-2` / `"three"` | `invalid` | AC-6 |
| ARGS-8 | `items` missing / `[]` / `null` / `"croissants"` | `invalid` | AC-6 |
| ARGS-9 | args a list / string / `None` | `invalid`, no exception | AC-6 |
| ARGS-10 | one line "lasagna" qty 3 + one line croissants with no qty | `invalid` (not `need_info`), `utensils` None | AC-6 |
| ARGS-11 | croissants 3 dozen + bagels with no qty | `need_info`, `utensils` None | AC-5 |

### 6.4 TEXT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TEXT-1 | croissants 2 dozen + bagels 2 dozen | contains "Small tongs" with "3" and "Spreader/knives" with "1"; no "Large tongs" | AC-8 |
| TEXT-2 | trail mix only | contains "no serving utensils" | AC-8 |
| TEXT-3 | bagels with no qty | ends with `?`, contains "how many" and "bagels" | AC-8 |
| TEXT-4 | food "lasagna" | starts with "invalid", contains "lasagna", "food", `"items"`, `"food"`, `"qty"`, `"unit"` | AC-8 |

### 6.5 FILE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FILE-1 | Appendix A loads | no error | AC-9 |
| FILE-2 | missing file; `"{"`; `{}`; `foods` empty | `ServRulesError` each | AC-9 |
| FILE-3 | unit "pounds"; utensil "spork"; `count` 0; `count` 1.5; `per` 0; `per` "ten" | `ServRulesError` each | AC-9 |
| FILE-4 | blank food name; alias equal to another food's name (different case) | `ServRulesError` each | AC-9 |
| FILE-5 | test rules with croissants `count: 1, per: 1`, croissants 3 dozen | small tongs 3 | AC-9 |
| FILE-6 | `count` left out of an entry | treated as 1 | AC-1, AC-9 |
| FILE-7 | `calculate_serving_utensils(...)` with `SERV_RULES_FILE` monkeypatched to a missing path | raises `ServRulesError` | AC-10 |
| FILE-8 | fresh subprocess: `import blc.tools.serv_tools` | no `langchain_core` in `sys.modules`; no file read | AC-10 |
| FILE-9 *(integration)* | real file | loads; known foods include the Appendix B names | AC-11 |

## Appendix A: test rules (unit tests only; not real business rules)
```json
{
  "foods": {
    "butter croissants": {
      "unit": "dozen",
      "aliases": ["Butter croissants served with raspberry preserves"],
      "utensils": [{"utensil": "small tongs", "count": 2, "per": 2}]
    },
    "assorted bagels": {
      "unit": "dozen",
      "aliases": ["bagels", "Assorted bagels with cream cheese"],
      "utensils": [
        {"utensil": "small tongs", "count": 1, "per": null},
        {"utensil": "spreader/knives", "count": 1, "per": null}
      ]
    },
    "classic deli sandwiches": {
      "unit": "each",
      "aliases": ["deli sandwiches"],
      "utensils": [
        {"utensil": "large tongs", "count": 1, "per": null},
        {"utensil": "mayo/mustard", "count": 1, "per": 25}
      ]
    },
    "quinoa-chickpea tabbouleh salad": {
      "unit": "each",
      "aliases": ["tabbouleh salad"],
      "utensils": [
        {"utensil": "salad tongs", "count": 1, "per": 1},
        {"utensil": "dressing/sauce bowl", "count": 1, "per": 1}
      ]
    },
    "yogurt with toppings": {
      "unit": "each",
      "aliases": [],
      "utensils": [
        {"utensil": "honey bear", "count": 2, "per": null},
        {"utensil": "serving spoon", "count": 2, "per": null},
        {"utensil": "serving spoon", "count": 2, "per": null}
      ]
    },
    "trail mix": {"unit": "bags", "aliases": [], "utensils": []}
  }
}
```

## Appendix B: real rules (`data/pull_sheet/rules/serving_utensils.json`): CONFIRMED
Confirmed by the user:
- **Every utensil comes in 2s** (`count: 2`), except: mayo/mustard stays at 1 per 25 as printed on the pull sheet, and granola and fresh berries get **1 serving spoon each**.
- **Tong-served food goes on trays of 2 dozen (24 pieces, sandwiches too), with 2 tongs per tray**: `count: 2, per: 2` for dozen foods, `count: 2, per: 24` for "each" foods, `count: 2, per: 1` for the fruit tray (a tray itself).
- **Dressing/sauce bowls** hold side dressings and dips (balsamic vinaigrette, hummus, baba ganoush); each bowl gets **ladle/sauce spoons**. No food on today's menu has a side dressing or dip, so no row below uses them yet.
- **Granola and fresh berries are foods of their own** with their own utensils; honey is not a food, it is the honey bear that goes with yogurt served with honey. A yogurt line that comes *with* granola/berries/honey carries their utensils too, so the line alone gives the full answer.
- Foods with no utensils: vegan yogurt, whole fresh fruit, individual GF/vegan cookie, box meals, trail mix, popcorn.
- The "condiments" utensil is not used by any food for now.

| Food (unit) | Utensils |
|---|---|
| Scrambled eggs with cheddar (each) | serving spoon 2 per line |
| Chicken-apple sausage links (each) | small tongs 2 per 24 |
| Roasted breakfast potatoes (each) | serving spoon 2 per line |
| Breakfast muffins (dozen) | small tongs 2 per 2 |
| Butter croissants (dozen) | small tongs 2 per 2; spreader/knives 2 per line (preserves) |
| Fruit danish (dozen) | small tongs 2 per 2 |
| Assorted bagels (dozen) | small tongs 2 per 2; spreader/knives 2 per line |
| Assorted scones (dozen) | small tongs 2 per 2 |
| Gluten-free vegan pastry (each) | small tongs 2 per 24 |
| Plant-based herb cream cheese (each) | spreader/knives 2 per line |
| Assorted flavored Greek yogurts (each) | none |
| Greek yogurt with honey and granola (each; Cascade) | honey bear 2; serving spoon 1 (granola) |
| Greek yogurt with granola, fresh berries and honey (each) | honey bear 2; serving spoon 1 (granola); serving spoon 1 (berries) |
| Granola (each) | serving spoon 1 per line |
| Fresh berries (each) | serving spoon 1 per line |
| Vegan yogurt (each) | none |
| Whole fresh fruit (dozen) | none |
| Market fresh fruit tray, S/M/L (each) | large tongs 2 per tray |
| Freshly cut fruit platter (each = per person, package line) | large tongs 2 per 70 people (1 tray per 70) |
| Cascade Breakfast, Olympic Breakfast (packages) | none: the package line itself is not counted; its item lines are |
| Trail mix (bags), white cheddar popcorn (dozen) | none |
| Specialty sandwich (each) | large tongs 2 per 24 |
| Classic deli sandwiches (each) | large tongs 2 per 24; mayo/mustard 1 per 25 |
| Husky wrap platter (each) | large tongs 2 per 24 |
| Quinoa-chickpea tabbouleh salad (each) | salad tongs 2 per salad; no dressing bowl (dressing is mixed in) |
| Box meals (each) | none |
| Chocolate brownies, cookie assortment, dessert bars (dozen) | small tongs 2 per 2 |
| Individual GF/vegan cookie (each) | none |
