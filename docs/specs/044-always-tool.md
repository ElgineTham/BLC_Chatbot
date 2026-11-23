# Spec 044: "Always" items tool (`calculate_always_items`)

- **Status:** done
- **Date:** 2026-11-23

## 1. Goal
The pull sheet has an **Always** box: bus tubs, towels, black linens (85x85), black napkins for drip trays and purple napkins for spots. Bus tubs and towels go on every pull. The other three are counted from the number of tables (read from the BEO's Special Instructions) and the number of drip trays. This spec adds a fifth calculator tool, `calculate_always_items`, built like `calculate_serving_utensils`. It takes those two numbers and returns the Always box. The formulas are fixed and printed on the pull sheet, so they live in code (no rules file).

This spec builds and unit-tests **the tool only**. It is not connected to the chatbot (follow-up spec, like 042 → 043).

## 2. Out of scope
- **Connecting the tool to the chatbot:** planner tools, `DEFAULT_TOOL_RUNNERS`, `invented_numbers`, prompts, evals.
- Reading the table count from BEO text or images (the caller passes the number).
- Working out the number of drip trays from the beverages (the caller passes the number; a future spec may compute it).
- Table sizes or kinds (6-ft, cocktail, round): every table counts the same.
- A rules file; changes to any existing package (`blc.tools.bev_tools`, `food_tools`, `serv_tools`, `recipe_tools`, `blc.planner`, `blc.flow`, `blc.pull_sheet`), `backend/scripts/`, ingest, `data/` or the knowledge `.md` files.

## 3. Interface contract

### 3.1 `backend/src/blc/tools/always_tools/` (new feature package)
Everything is importable as `from blc.tools.always_tools import ...`. Importing the package reads no file and does not import `langchain_core`.

```python
from collections.abc import Mapping
from dataclasses import dataclass

ALWAYS_TOOL_NAME = "calculate_always_items"
ALWAYS_CHECK_ITEMS: tuple[str, ...] = ("bus tubs", "towels")
ALWAYS_COUNT_ITEMS: tuple[str, ...] = ("black linens", "black napkins", "purple napkins")
ALWAYS_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")

@dataclass(frozen=True)
class AlwaysResult:
    status: str                        # one of ALWAYS_STATUSES
    text: str                          # what the tool returns to the chat model (§4.3)
    checks: tuple[str, ...] | None     # "ok" only: always == ALWAYS_CHECK_ITEMS
    counts: dict[str, int] | None      # "ok" only: every key of ALWAYS_COUNT_ITEMS, in that order,
                                       # including zeros

def calculate_always_items(tables: int | None, drip_trays: int | None) -> AlwaysResult:
    """None means not given (need_info). Never raises for bad input: negative gives "invalid"."""

def run_always_tool(args: Mapping[str, object]) -> AlwaysResult:
    """Run the tool on a raw argument dict as the chat model sends it (§4.2).
    Never raises for bad arguments: they give status "invalid"."""
```

### 3.2 Files
None read or written.

## 4. Inputs and outputs

### 4.1 Counts
| Item | Count |
|---|---|
| bus tubs, towels | always brought; a check mark, no number |
| black linens | `tables × 2 + 1` when `tables ≥ 1`; `0` when `tables == 0` |
| purple napkins | `tables × 2` |
| black napkins | `drip_trays × 1` |

| tables | drip_trays | `counts` |
|---|---|---|
| 1 | 0 | `{"black linens": 3, "black napkins": 0, "purple napkins": 2}` |
| 2 | 3 | `{"black linens": 5, "black napkins": 3, "purple napkins": 4}` |
| 3 | 1 | `{"black linens": 7, "black napkins": 1, "purple napkins": 6}` |
| 0 | 0 | `{"black linens": 0, "black napkins": 0, "purple napkins": 0}` |
| 0 | 2 | `{"black linens": 0, "black napkins": 2, "purple napkins": 0}` |

### 4.2 Raw arguments (`run_always_tool`) and checks
Expected shape: `{"tables": 2, "drip_trays": 3}`.
- `tables`, `drip_trays`: each a whole number ≥ 0. `2`, `2.0` and `"2"` (also `" 2 "`) are accepted and mean the same.
- Missing, `null`, or a blank string (`""`, `"  "`) means not given, which is `need_info`. Note `0` is a valid value, **not** "not given".
- Negative, a fraction (`2.5`, `"2.5"`), non-numeric (`"two"`), a boolean (`true`/`false`), a list or a dict is **invalid**.
- Unknown keys are ignored. `args` that is not a mapping is **invalid**.
- Precedence over the whole call: if either value is invalid the call is `invalid`; else if either is not given the call is `need_info`; else `ok`. No partial counts: `checks` and `counts` are `None` unless `ok`.
- `calculate_always_items` follows the same rules for its two arguments (`None` = not given; negative = `invalid`).

### 4.3 The tool's text
Short plain English for the chat model. Tests check only the parts listed here.
- `ok`: mentions "Bus tubs" and "Towels", then each count item with its number (e.g. `Black linens: 5`, `Black napkins: 3`, `Purple napkins: 4`), in `ALWAYS_COUNT_ITEMS` order. Zero counts are listed too (e.g. `Black napkins: 0`).
- `need_info`: one question ending in `?`, containing "how many" and the missing item(s): "tables" when tables is missing, "drip trays" when drip_trays is missing (both when both are missing).
- `invalid`: starts with "invalid", names the bad field (`tables` or `drip_trays`), and shows the expected format with an example call containing `"tables"` and `"drip_trays"` (with the double quotes).

## 5. Acceptance criteria
- **AC-1:** Counts follow §4.1: black linens `tables × 2 + 1` for tables ≥ 1, purple napkins `tables × 2`, black napkins `drip_trays`. `counts` always has all three keys in `ALWAYS_COUNT_ITEMS` order; `checks == ALWAYS_CHECK_ITEMS` on every `ok`.
- **AC-2:** `tables == 0` gives 0 black linens and 0 purple napkins (not 1 linen); `drip_trays == 0` gives 0 black napkins; both are `ok`, not `need_info`.
- **AC-3:** A missing, `null` or blank-string value makes the call `need_info`; nothing is guessed and `checks`/`counts` are `None`.
- **AC-4:** Bad input is `invalid`, never an exception: negative, fraction, non-numeric, boolean, list or dict values; `args` not a mapping. Precedence `invalid` > `need_info` > `ok` (one invalid value with the other missing is `invalid`).
- **AC-5:** Raw shapes: `2`, `2.0`, `"2"` and `" 2 "` are the same value; unknown keys are ignored.
- **AC-6:** `calculate_always_items` gives the same results as `run_always_tool` for the same values (`None` = not given; negative = `invalid`).
- **AC-7:** The text follows §4.3 for `ok` (including zero counts), `need_info` (each of the three missing combinations) and `invalid`.
- **AC-8:** Importing `blc.tools.always_tools` leaves `langchain_core` out of `sys.modules` (checked in a fresh subprocess).
- **AC-9** *(manual)*: Code structure per `CLAUDE.md`: new files only in `backend/src/blc/tools/always_tools/`, nothing else changed; modules split by job (counting, raw arguments, text); the formulas are named constants in the counting module, with no rules file; no I/O; each file about 250 lines or fewer.

## 6. Test cases

### 6.1 CALC
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| CALC-1 | tables 2, drip_trays 3 | `ok`, `{"black linens": 5, "black napkins": 3, "purple napkins": 4}` | AC-1 |
| CALC-2 | tables 1 / 3 / 10, drip_trays 1 | black linens 3 / 7 / 21; purple napkins 2 / 6 / 20 | AC-1 |
| CALC-3 | tables 0, drip_trays 0 | `ok`, all counts 0 | AC-2 |
| CALC-4 | tables 0, drip_trays 2 | black linens 0, purple napkins 0, black napkins 2 | AC-2 |
| CALC-5 | tables 4, drip_trays 0 | black napkins 0, black linens 9, purple napkins 8 | AC-1, AC-2 |
| CALC-6 | any `ok` result | `checks == ("bus tubs", "towels")`; `list(counts)` == `ALWAYS_COUNT_ITEMS` | AC-1 |
| CALC-7 | `calculate_always_items(2, 3)`, `(None, 3)`, `(-1, 3)` | `ok` (as CALC-1), `need_info`, `invalid` | AC-6 |

### 6.2 ARGS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ARGS-1 | tables `2` / `2.0` / `"2"` / `" 2 "` with drip_trays 3 | same result as CALC-1 | AC-5 |
| ARGS-2 | extra key `"guests": 70` | ignored, `ok` | AC-5 |
| ARGS-3 | tables missing / `null` / `""` / `"  "` (drip_trays 3) | `need_info`, `counts` None | AC-3 |
| ARGS-4 | drip_trays missing (tables 2); both missing (`{}`) | `need_info` | AC-3 |
| ARGS-5 | tables `-1` / `2.5` / `"2.5"` / `"two"` / `true` / `[2]` / `{"n": 2}` | `invalid` each | AC-4 |
| ARGS-6 | drip_trays `-1` / `"three"` / `false` | `invalid` each | AC-4 |
| ARGS-7 | tables `"two"`, drip_trays missing | `invalid` (not `need_info`) | AC-4 |
| ARGS-8 | args a list / string / `None` | `invalid`, no exception | AC-4 |

### 6.3 TEXT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TEXT-1 | tables 2, drip_trays 3 | contains "Bus tubs", "Towels", "Black linens" with "5", "Black napkins" with "3", "Purple napkins" with "4" | AC-7 |
| TEXT-2 | tables 1, drip_trays 0 | contains "Black napkins" with "0" | AC-7 |
| TEXT-3 | tables missing / drip_trays missing / both missing | ends with `?`, contains "how many" and "tables" / "drip trays" / both | AC-7 |
| TEXT-4 | tables `"two"` | starts with "invalid", contains `tables`, `"tables"`, `"drip_trays"` | AC-7 |

### 6.4 PKG
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PKG-1 | fresh subprocess: `import blc.tools.always_tools` | no `langchain_core` in `sys.modules` | AC-8 |
| PKG-2 | constants | `ALWAYS_TOOL_NAME == "calculate_always_items"`; `ALWAYS_STATUSES == ("ok", "need_info", "invalid")` | AC-1 |
