# Spec 047: Linen colours (black by default, white too)

- **Status:** done, with known gaps
- **Closed** (2026-11-26): closed by the user with AC-8 not met. The whole unit suite passed (3579 passed, 0 failed), and spec 045's always evals and spec 046's NOTEXT evals passed. AC-10 was checked by the planner.
  - **AC-8 not met:** LINEN scored 3 of 5 (the threshold is 4), the same in two runs. LINEN-2, LINEN-3 and LINEN-4 passed. LINEN-1 ("how many linens") and LINEN-5 ("How many white linens do I need?") failed because the planner model replied with text (asking for the table count itself), and that text became a fallback search.
  - **AC-9 not verified:** the five planner eval suites of spec 046 AC-7 were not run in this round.
  - **Known limit, not fixed here:** probes against the real model showed that `tool_choice="any"` in `plan_question` fixes the text replies. On its own, though, it routes "How many purple napkins" to `about: "drip_trays"`, which matches a mix-up the user saw in the web chat. A sentence in the always tool's descriptions that purple napkins are always about tables fixed that in the probes. Neither change was made.
- **Date:** 2026-11-23

## 1. Goal
Staff ask about "linens" without a colour ("how many linens"), and the chatbot answers "I don't know". At Bay Laurel, **linens with no colour mean black linens**. **White linens** are counted the same way as black linens (`tables × 2 + 1`), and an event can need both colours. Purple napkins go on every table whatever its linen colour.

This spec:
- adds white linens to `calculate_always_items`;
- teaches the planner that bare "linens" or "tablecloths" mean black linens;
- fixes a leak found in testing: the planner copied the "9 tables" from a tool-description example into a real call. The invented-number check caught it, but would not have if a 9 had appeared anywhere in the chat.

## 2. Out of scope
- Any other linen colour, size or kind.
- Napkins: a bare "how many napkins" stays as it is (a search). No knowledge-file note.
- Drip trays and black napkins (unchanged).
- Other tools, `plan_question`, the flow (other than the invented-number check of §3.3), retrieval and `data/`.
- Spec 045's EVAL-7, which is still a known limit.

## 3. Interface contract
Unchanged unless listed: `ALWAYS_TOOL_NAME`, `ALWAYS_CHECK_ITEMS`, `ALWAYS_COUNT_ITEMS` (still `("black linens", "black napkins", "purple napkins")`), `ALWAYS_TABLE_ITEMS`, `ALWAYS_DRIP_TRAY_ITEMS`, `ALWAYS_SCOPES`, `ALWAYS_STATUSES`, `AlwaysResult`, and the meaning of `tables` (now: **black-linen tables**).

### 3.1 `blc.tools.always_tools`
```python
ALWAYS_WHITE_LINENS: str = "white linens"
ALWAYS_COUNT_ORDER: tuple[str, ...] = ("black linens", "white linens", "black napkins", "purple napkins")
# every `counts` dict is in this order (keys that are absent are skipped)

def calculate_always_items(
    tables: int | None,
    drip_trays: int | None,
    about: str = "both",
    white_tables: int | None = None,
) -> AlwaysResult: ...

def run_always_tool(args: Mapping[str, object]) -> AlwaysResult: ...
# raw args gain "white_tables", with the same value rules as "tables" (spec 044 §4.2)
```

### 3.2 The planner's view (`blc.planner`)
The always tool's `parameters` become exactly:
```json
{
  "type": "object",
  "properties": {
    "about":        {"type": "string",  "description": "…"},
    "tables":       {"type": "integer", "description": "…"},
    "white_tables": {"type": "integer", "description": "…"},
    "drip_trays":   {"type": "integer", "description": "…"}
  },
  "required": ["about"]
}
```
The spec 045 rules still hold: no banned keywords; at least three question → call examples covering the three scopes; at least one example with a number left out. The descriptions also say (the wording is the developer's):
- `tables` is the number of tables with **black** linens. Linens, tablecloths or a table count with no colour are black.
- `white_tables` is the number of tables with **white** linens. Send it only when the user says white.
- Questions about white linens are `about: "tables"` (or `"both"` by the existing rules).
- **Example numbers:** every number in an example call is **31 or more**, and no number appears in more than one example. This makes a copied example number easy to spot and unlikely to match a real chat. One example uses `white_tables`.

`PLANNER_PROMPT`'s `calculate_always_items` bullet gains one sentence: linens or tablecloths with no colour are black linens, and white linens go in `white_tables`. The rest of the spec 046 Appendix A text is unchanged, including the 11 examples and their order.

### 3.3 `blc.flow`
`invented_numbers` for the always tool also checks `white_tables`, by the same rule as `tables`: it must be a number in the question or history, and 1 and 0 get no free pass. Invented values go under the key `"white_tables"`.

### 3.4 Existing tests that change
The tester updates only these:
- `backend/tests/always_wiring/test_plan.py`, `test_plan_3_schema_matches_contract`: the expected schema gains `"white_tables": {"type": "integer"}` (§3.2).
- Any spec 045 test that pins one of the three old example calls word for word (the old examples change under §3.2).

No other existing test should change. If one fails, the implementation-evaluator reports it as a spec question.

## 4. Inputs and outputs

### 4.1 Counts in the tables part (scope `tables` or `both`)
| `tables` (black) | `white_tables` | counts (tables part) |
|---|---|---|
| 4 | – | `black linens 9, purple napkins 8` (unchanged) |
| – | 5 | `white linens 11, purple napkins 10` |
| 3 | 2 | `black linens 7, white linens 5, purple napkins 10` |
| 0 | 2 | `black linens 0, white linens 5, purple napkins 4` |
| – | 0 | `white linens 0, purple napkins 0` |
| – | – | none: `need_info`, asks "tables" (unchanged) |

- Each colour's linens: `n × 2 + 1` when `n ≥ 1`, and `0` when `n == 0`. A colour appears in `counts` only when its number was given.
- Purple napkins: `(tables + white_tables) × 2`, counting only the given ones. They appear whenever at least one of the two was given.
- **Missing numbers:** the tables part needs only one of the two. If either is given, a missing one is never asked for. If both are missing, the tool asks for "tables", as today.
- `white_tables` follows `tables`' value rules: invalid gives `invalid`, and it is ignored when scope is `drip_trays`.
- Text: the line for white linens reads `White linens: <n>`, in the §3.1 order.

### 4.2 What the planner is expected to send
| Question | Call |
|---|---|
| "how many linens" / "how many tablecloths" | `about: "tables"`, no numbers → asks how many tables |
| "linens for 6 tables" | `about: "tables", tables: 6` |
| "white linens for 5 tables" | `about: "tables", white_tables: 5` (no `tables`) |
| "3 tables with black linens and 2 with white" | `about: "tables", tables: 3, white_tables: 2` |

### 4.3 How an eval case is scored
Same as spec 045 §4.6:
- the route must match;
- the tool names must match;
- the always call's arguments, run through `run_always_tool`, must give the case's status and `counts`;
- for `need_info`, the text must contain the case's missing item.

**Threshold:** LINEN passes at **at least 4 of its 5** cases.

## 5. Acceptance criteria
- **AC-1:** Counts follow §4.1 for every row, in the `ALWAYS_COUNT_ORDER` order. Black-only results are identical to spec 045's.
- **AC-2:** If either `tables` or `white_tables` is given, a missing one is never asked for. If both are missing, the tool asks for "tables". `white_tables` is ignored in scope `drip_trays`.
- **AC-3:** `white_tables` takes the same raw values as `tables`: `5`, `5.0`, `"5"` and `" 5 "` are accepted, and missing, `null` or blank means not given. An in-scope invalid value makes the call `invalid`, and nothing raises. `calculate_always_items(..., white_tables=…)` matches `run_always_tool`.
- **AC-4:** The text shows `White linens: <n>` when white linens are in `counts`, and never otherwise. Bus tubs and towels are listed as before.
- **AC-5:** The planner schema is §3.2 exactly. The description has a `white_tables` example. Every number in every always-tool example call is ≥ 31 and used only once.
- **AC-6:** `invented_numbers` flags an invented `white_tables`, including 1 and 0, and accepts one that is in the question or history. Its handling of `tables` and `drip_trays` is unchanged.
- **AC-7:** All spec 044, 045 and 046 tests still pass, except the §3.4 updates. The whole unit suite passes.
- **AC-8** *(eval)*: The LINEN cases (§6.4) meet §4.3's threshold.
- **AC-9** *(eval)*: No regressions. Spec 045's always evals (with ASK at least 2 of 3), spec 046's NOTEXT evals and the five planner eval suites of spec 046 AC-7 still meet their thresholds.
- **AC-10** *(manual)*: Only these change:
  - `backend/src/blc/tools/always_tools/`;
  - `backend/src/blc/planner/always_view.py`;
  - the always bullet of `backend/src/blc/planner/prompt.py` (one added sentence);
  - `backend/src/blc/flow/invented.py`;
  - the §3.4 tests and the new tests.

  The prompt otherwise matches spec 046 Appendix A.

## 6. Test cases

### 6.1 COLOUR (the tool)
| ID | Input | Expected | Covers |
|---|---|---|---|
| COLOUR-1 | about "tables", white_tables 5 | `ok`, `{"white linens": 11, "purple napkins": 10}` | AC-1 |
| COLOUR-2 | about "tables", tables 3, white_tables 2 | `ok`, `{"black linens": 7, "white linens": 5, "purple napkins": 10}`, keys in that order | AC-1 |
| COLOUR-3 | about "tables", tables 0, white_tables 2 / white_tables 0 only | `{"black linens": 0, "white linens": 5, "purple napkins": 4}` / `{"white linens": 0, "purple napkins": 0}` | AC-1 |
| COLOUR-4 | about "both", white_tables 5, drip_trays 3 | `ok`, `{"white linens": 11, "black napkins": 3, "purple napkins": 10}` | AC-1 |
| COLOUR-5 | about "both", white_tables 5, no drip_trays | `need_info`, `{"white linens": 11, "purple napkins": 10}`, asks drip trays and not tables | AC-2 |
| COLOUR-6 | about "tables", neither / about "drip_trays", drip_trays 3, white_tables 5 | `need_info` asking "tables" / `ok`, `{"black napkins": 3}` | AC-2 |
| COLOUR-7 | white_tables `"5"`, `" 5 "`, `5.0` / `null`, `""` / `-1`, `"five"`, `true` (about "tables") | as COLOUR-1 / not given (asks tables) / `invalid` | AC-3 |
| COLOUR-8 | `calculate_always_items(3, None, "tables", 2)` | equals `run_always_tool({"about": "tables", "tables": 3, "white_tables": 2})` | AC-3 |
| COLOUR-9 | COLOUR-1 text; spec 045 SCOPE-1 text | contains `White linens: 11` / contains no "White linens" | AC-4 |
| COLOUR-10 | constants | `ALWAYS_WHITE_LINENS == "white linens"`; `ALWAYS_COUNT_ORDER` as §3.1; `ALWAYS_COUNT_ITEMS` unchanged | AC-1 |

### 6.2 PLAN
| ID | Input | Expected | Covers |
|---|---|---|---|
| PLAN-1 | the always tool's `parameters` | equal to §3.2 (descriptions aside); no banned keywords | AC-5 |
| PLAN-2 | the always tool's description | has an example call with `"white_tables"`; every integer in an example call dict is ≥ 31; no integer repeats across examples | AC-5 |
| PLAN-3 | `PLANNER_PROMPT` | still contains spec 046's 11 examples in order; contains "white_tables" | AC-7, AC-10 |

### 6.3 GUARD
| ID | Input | Expected | Covers |
|---|---|---|---|
| GUARD-1 | "White linens for 5 tables?": white_tables 5 / 6 / 1 / 0 | not flagged / `{"white_tables": (6,)}` / `{"white_tables": (1,)}` / `{"white_tables": (0,)}` | AC-6 |
| GUARD-2 | "five" in the question, white_tables 5; "5" only in history, white_tables 5 | not flagged | AC-6 |
| GUARD-3 | full turn "How many white linens?"; fake planner twice sends about "tables", white_tables 37 | `retried` True; the final call has no `white_tables`; the reply asks how many tables | AC-6 |

### 6.4 LINEN (eval, real model; scored by §4.3)
| ID | Question | Expected | Covers |
|---|---|---|---|
| LINEN-1 *(eval)* | "how many linens" | TOOL; `[calculate_always_items]`; `need_info`, `{}`, text has "tables" | AC-8 |
| LINEN-2 *(eval)* | "How many tablecloths for 6 tables?" | TOOL; `ok`, `{"black linens": 13, "purple napkins": 12}` | AC-8 |
| LINEN-3 *(eval)* | "White linens for 5 tables?" | TOOL; `ok`, `{"white linens": 11, "purple napkins": 10}` | AC-8 |
| LINEN-4 *(eval)* | "We have 3 tables with black linens and 2 with white linens. How many linens?" | TOOL; `ok`, `{"black linens": 7, "white linens": 5, "purple napkins": 10}` | AC-8 |
| LINEN-5 *(eval)* | "How many white linens do I need?" | TOOL; `[calculate_always_items]`; `need_info`, `{}`, text has "tables" | AC-8 |

### 6.5 Existing suites (run by the implementation-evaluator)
| ID | Suite | Expected | Covers |
|---|---|---|---|
| SUITE-1 | whole unit suite | passes (with the §3.4 updates) | AC-7 |
| SUITE-2 *(eval)* | `always_wiring/test_eval.py`, `planner_prompt/test_notext_eval.py` and the five suites of spec 046 AC-7 | each meets its thresholds | AC-9 |

### 6.6 Checks without a test row
AC-10 is checked by the planner.
