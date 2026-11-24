# Spec 045: Always items by scope, wired into the chatbot

- **Status:** done. AC-16 was not met in this spec's own runs, and spec 046's prompt restructure met it (ASK at least 2/3; EVAL-7 is still a known limit).
- **Date:** 2026-11-23
- **Revision 2** (2026-11-23, after the first eval run): §3.2 and §4.4 now say which scope wins when a question matches two rows (naming the Always items, Always box or a pull sheet is `"both"`, even with only a table count). An item question with no number still calls the tool, never a search alone. New AC-22 *(manual)*. Tests are unchanged.
- **Revision 3** (2026-11-23, after the second eval run, where ASK was still 1/3): `PLANNER_PROMPT` gets worked examples for the always tool, and Rule 1 says Always items are TOOL even with no amount. New AC-23 *(manual)*. Tests are unchanged.
- **Revision 4** (2026-11-23, after the third eval run, where ASK was still 1/3): the always tool's descriptions are rewritten. They now open with when to use the tool, give the scope as an ordered decision, and show question → call examples. The bare `{"about": "both"}` example is removed (it matched EVAL-6), and the repeated always text in `PLANNER_PROMPT` is cut back (§3.2 revision 4). New AC-24 *(manual)*. Tests are unchanged.
- **Revision 5** (2026-11-23, after the fourth eval run, where ASK was 0/3): a user-requested experiment. Rule 1 of `PLANNER_PROMPT` gets one more always-tool example, about black linens with no number. It shares EVAL-5's scope-and-number pair (`tables`, no number), so AC-19's pair rule makes an exception for this one example only. New AC-25 *(manual)*. Tests are unchanged.
- **Closed** (2026-11-23): every AC except AC-16 is met. The whole unit suite passes (3451 passed), and the SCOPE (4/4) and MIX (3/3) evals pass. AC-16 failed for two reasons:
  - **EVAL-5:** the planner model replied with text (asking for the table count itself) instead of calling a tool, and `plan_question` turned that into a search.
  - **EVAL-6 and EVAL-7:** the prompt's TOOL/DOCS framing sent them the wrong way.

  Spec 046 restructures the planner prompt and replaces revisions 3 and 5's prompt text.

## 1. Goal
Spec 044 built `calculate_always_items`, but it answers all-or-nothing and nothing calls it. This spec does two things:
1. **Scope.** The tool gets an `about` argument. A question about **tables** is answered with black linens and purple napkins. A question about **drip trays** is answered with black napkins. A question about **both**, or about the Always box in general, is answered with all three. A missing number is asked for only when its scope was asked about, and the counts that can be given are given straight away. **Bus tubs and towels are listed in every reply**, including the ones that ask a question.
2. **Wiring.** The planner may call the tool, the flow runs it, and the user gets the tool's text word for word (spec 023). The model never invents a table or drip-tray count. Unlike the other tools, the number 1 is **not** accepted for free (spec 021), so a guessed "1 table" becomes a question.

Real-model evals check that the model calls the tool, picks the right scope and sends the right numbers, judged by the tool's result. Every eval run writes a log.

## 2. Out of scope
- The formulas of spec 044 §4.1, which are unchanged.
- Working out drip trays from the beverages, and reading BEO images.
- Reading "no", "none" or "a" as a number. The user types a number (`0`, `zero`, `1`, `one`).
- Changing how the other four tools are planned, run or checked for invented numbers.
- `TOOL_FAILED_REPLY` wording, the answer prompt, retrieval, models, ingest, `data/`, the knowledge `.md` files, `backend/scripts/` and the web page.
- Fixing eval failures. They are reported, and a later revision decides what to change.

## 3. Interface contract
No new public names outside what is listed. Unchanged and reused: `ALWAYS_TOOL_NAME`, `ALWAYS_CHECK_ITEMS`, `ALWAYS_COUNT_ITEMS`, `ALWAYS_STATUSES`, `AlwaysResult` (same fields), `plan_question`, `Plan`, `PlannedCall`, `run_planned_turn`, `TurnOutcome`, `ToolOutput`, `TOOL_FAILED_REPLY`, `REPLY_SEPARATOR`.

### 3.1 `blc.tools.always_tools` (changed)
Importing the package still reads no file and does not import `langchain_core`.
```python
ALWAYS_SCOPES: tuple[str, ...] = ("tables", "drip_trays", "both")
ALWAYS_TABLE_ITEMS: tuple[str, ...] = ("black linens", "purple napkins")
ALWAYS_DRIP_TRAY_ITEMS: tuple[str, ...] = ("black napkins",)

# AlwaysResult fields unchanged, but their meaning widens (§4.2):
#   checks: ALWAYS_CHECK_ITEMS on "ok" AND "need_info"; None only on "invalid".
#   counts: on "ok" and "need_info", exactly the in-scope items whose number is known,
#           in ALWAYS_COUNT_ITEMS order ({} when none is known); None only on "invalid".

def calculate_always_items(
    tables: int | None, drip_trays: int | None, about: str = "both"
) -> AlwaysResult:
    """None = not given. Never raises. Negative in-scope value = "invalid"."""

def run_always_tool(args: Mapping[str, object]) -> AlwaysResult:
    """Raw argument dict as the chat model sends it (§4.1). Never raises."""
```

### 3.2 `blc.planner`
```python
PLANNER_TOOLS: tuple[BaseTool, ...]
# the five current tools (same objects, same order) plus exactly one more, last,
# whose .name == ALWAYS_TOOL_NAME ("calculate_always_items"). plan_question binds the whole tuple.
```
Through `convert_to_openai_tool(tool)["function"]` the model receives exactly these `parameters` (descriptions shown as `…`):
```json
{
  "type": "object",
  "properties": {
    "about":      {"type": "string",  "description": "…"},
    "tables":     {"type": "integer", "description": "…"},
    "drip_trays": {"type": "integer", "description": "…"}
  },
  "required": ["about"]
}
```
- Nothing inside `parameters` uses `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title`, `enum` or the type `"null"`.
- The tool's `description` contains **at least three example calls** as argument dicts: one each with `"about": "tables"`, `"about": "drip_trays"` and `"about": "both"`, and at least one of them with a number left out.
- The descriptions also cover these points (the wording is the developer's):
  - Black linens and purple napkins are about tables, and black napkins are about drip trays. A question about the Always items, the Always box or a pull sheet, or one that names neither, is `"both"`.
  - `tables` and `drip_trays` are numbers the user or BEO wrote. Leave one out when it wasn't given in the question or chat history, and never guess 1 or 0.
  - Bus tubs and towels always come and need no number.
  - (revision 2) **Which scope wins:** a question that names the Always items, the Always box or a pull sheet is `"both"`, even when it gives only a table count or only a drip-tray count ("Always items for 4 tables?" is `{"about": "both", "tables": 4}`, so the tool asks for drip trays). `"tables"` or `"drip_trays"` is used only when the question names the items themselves (black linens, purple napkins, black napkins) or only the tables or drip trays.
  - (revision 2) **Item questions with no number:** a question about black linens, purple napkins or black napkins with no number in the question or history still calls `calculate_always_items` with the number left out, so the tool asks how many. It is never `search_documents` alone, and never the napkins-by-guest-count tool or the written napkin rule.
- **(revision 4) How the descriptions are laid out.** The points above stay; this sets their order and shape. The wording is the developer's.
  1. **The tool's `description` opens with when to use it:** any question about black linens, purple napkins, black napkins, or the Always items, Always box or a pull sheet, **with or without a number**. It does not open with "the Always box" as the only cue.
  2. **Next, `about` as an ordered decision, first match wins:**
     1. the question names the Always items, Always box or a pull sheet → `"both"`, even with only one count;
     2. else black linens, purple napkins, or only tables → `"tables"`;
     3. else black napkins, or only drip trays → `"drip_trays"`;
     4. else (names neither) → `"both"`.

     No sentence before this decision tells the model to pick `"tables"` for "a number of tables" without the step 1 exception.
  3. **Then the number rule:** leave out any number the user did not write, never guess 1 or 0, and the tool asks for it. Bus tubs and towels always come.
  4. **Then the examples, as question → call pairs, exactly these three:**
     - `"Black linens for 9 tables?"` → `{"about": "tables", "tables": 9}`
     - `"How many black napkins should I pull?"` → `{"about": "drip_trays"}`
     - `"Always items for 7 drip trays?"` → `{"about": "both", "drip_trays": 7}`

     No other example call. In particular, the bare `{"about": "both"}` example is gone.
  5. **Napkin wording:** the description contains no sentence telling the model not to use the tool for "napkins" without naming which napkins (forks, plates, and cocktail or dinner napkins by guest count may still be excluded by name).
  6. **The `about` field's description** gives the same four-step order in one or two sentences.
  7. **`PLANNER_PROMPT`'s always text** is cut to:
     - one sentence that sends these questions to `calculate_always_items`, with or without a number (Rule 1);
     - the Rule 2 exclusion of AC-23;
     - the two AC-23 examples.

     The scope rules and number rules are not repeated in the prompt. They live in the tool's descriptions.

### 3.3 `blc.flow`
```python
DEFAULT_TOOL_RUNNERS: Mapping[str, ToolRunner]
# exactly the keys "calculate_bev_item", "scale_recipe", "calculate_food_item",
# "calculate_serving_utensils", "calculate_always_items". The new key ->
# run_always_tool(args), returned as ToolOutput(result.status, result.text).

def invented_numbers(name, args, question, history=None) -> dict[str, tuple[object, ...]]
# unchanged signature. For name == "calculate_always_items", "tables" and "drip_trays"
# are checked against the numbers in the question and history. 1 is NOT always accepted
# for this tool. Invented values are returned under their own key ("tables" / "drip_trays").
# "about" is never flagged.
```

### 3.4 Existing tests that change
The tester updates only these assertions:
- `backend/tests/planner/test_plan.py`: the `PLANNER_TOOLS` length and order check (5 → 6, always tool last).
- `backend/tests/serv_wiring/test_planner.py`: `test_planner_tools_are_old_four_plus_serv_last` (6 tools, serving tool at index 4, always tool last), `test_exactly_one_serv_tool_and_no_duplicate_names` (6 names), and `test_plan_question_binds_exactly_the_tuple` (serving tool at bound index 4, not last).
- `backend/tests/food_wiring/test_planner_tools.py`: the length check (5 → 6).
- `backend/tests/planned_flow/test_contract.py`, `backend/tests/serv_wiring/test_answer.py`, `backend/tests/food_wiring/test_answer.py`: the `set(DEFAULT_TOOL_RUNNERS)` checks (add `"calculate_always_items"`).
- `backend/tests/always_tools/`: the `need_info` assertions that `checks` and `counts` are `None` now expect §4.2 (`checks == ALWAYS_CHECK_ITEMS`; `counts` as the known in-scope items). Every other spec 044 test still holds, because `about` defaults to `"both"`.

### 3.5 Eval setup (eval cases only)
- Same as spec 043: `build_chat_model(temperature=CHAT_TEMPERATURE)` and `build_domain_store()` from `chat.py`. Each case runs `run_planned_turn(llm, store, question, history)` with the default runners.
- The cases skip, not fail, when `ANTHROPIC_API_KEY` or `GOOGLE_API_KEY` is unset or `.chroma/` is missing.
- The eval writes only under `logs/`.

## 4. Inputs and outputs

### 4.1 Raw arguments
Expected shape: `{"about": "tables", "tables": 4}`.
- `about`: `"tables"`, `"drip_trays"` or `"both"`. Case and surrounding spaces are ignored, and `"drip trays"` (with a space) means `"drip_trays"`. Missing, `null`, blank, any other string, or a non-string means `"both"`. It is never `invalid`.
- `tables` and `drip_trays`: the spec 044 §4.2 rules (whole number ≥ 0; `2`, `2.0`, `"2"` and `" 2 "` are the same; missing, `null` or blank means not given; negative, fraction, non-numeric, boolean, list or dict is invalid).
- **Out-of-scope values are ignored entirely.** With `about: "tables"`, any `drip_trays` value, even `"two"` or `-1`, has no effect. The same goes the other way round.
- Precedence over the in-scope values: any invalid value makes the call `invalid`; otherwise any missing value makes it `need_info`; otherwise it is `ok`.
- `args` that is not a mapping is `invalid`. Unknown keys are ignored.
- `calculate_always_items` follows the same rules (`None` = not given; negative = invalid; `about` parsed as above).

### 4.2 Results by scope
| `about` | tables | drip_trays | status | `counts` |
|---|---|---|---|---|
| tables | 4 | – | ok | `{"black linens": 9, "purple napkins": 8}` |
| tables | – | 3 | need_info (asks tables) | `{}` |
| drip_trays | – | 3 | ok | `{"black napkins": 3}` |
| drip_trays | 4 | – | need_info (asks drip trays) | `{}` |
| both | 2 | 3 | ok | `{"black linens": 5, "black napkins": 3, "purple napkins": 4}` |
| both | 4 | – | need_info (asks drip trays) | `{"black linens": 9, "purple napkins": 8}` |
| both | – | 3 | need_info (asks tables) | `{"black napkins": 3}` |
| both | – | – | need_info (asks both) | `{}` |
| tables | 0 | – | ok | `{"black linens": 0, "purple napkins": 0}` |

`checks == ALWAYS_CHECK_ITEMS` in every `ok` and `need_info` row.

### 4.3 The tool's text
Short plain English. Tests check only the parts listed here.
- **`ok` and `need_info`:** the text mentions "Bus tubs" and "Towels". Then each item in `counts` with its number (e.g. `Black linens: 9`), in `ALWAYS_COUNT_ITEMS` order, zeros included. **Out-of-scope items are not named** ("Black napkins" is absent when `about` is `"tables"`).
- **`need_info` also:** ends with one question ending in `?`, containing "how many" and the missing in-scope item(s): "tables", "drip trays", or both. An out-of-scope field is never asked for.
- **`invalid`:** as spec 044 §4.3.

### 4.4 Which questions go to the tool (what the planner is expected to do)
| Question | Plan |
|---|---|
| the Always items or Always box, or a pull sheet, **whatever counts it gives** (revision 2: this row wins over the two below) | `calculate_always_items`, `about: "both"` (with the other tools a pull sheet needs) |
| black linens or purple napkins, or "for N tables" (not naming the Always items) | `calculate_always_items`, `about: "tables"` |
| black napkins, or "for N drip trays" (not naming the Always items) | `calculate_always_items`, `about: "drip_trays"` |
| both tables and drip trays | `calculate_always_items`, `about: "both"` |
| (revision 2) black linens, purple napkins or black napkins with **no number** in the question or history | `calculate_always_items` with the scope's number left out, so the tool asks. Never `search_documents` alone. |
| forks, spoons, knives, plates or napkins by guest count | `calculate_food_item`, as today |
| an answer to the tool's question ("6 tables and 2 drip trays") | `calculate_always_items` with the scope the history implies |

### 4.5 Invented numbers
- `tables` or `drip_trays` that is not a number in the question or history (1 and 0 included) gets the planner asked once more (spec 021).
- If the second plan still invents it, that key is removed, `about` and the other key stay, and the tool then asks its `need_info` question.

### 4.6 How an eval case is scored
A case passes when all its checks pass. Every check reads the final plan (`outcome.plan`).
1. **Route** equals the case's route.
2. **Tool names:** the plan's tool-call names (not `search_documents`) equal the case's list as a multiset.
3. **Result** (cases with an always call): the always call's arguments, run through `run_always_tool`, give the case's status and `counts` exactly. For `need_info`, the text also contains the case's missing item(s). The `about` value itself is not compared, only its result.

**Thresholds:** SCOPE passes at **at least 3 of its 4** cases, ASK at **at least 2 of 3**, MIX at **at least 2 of 3**. Per-case pass or fail, route and turn time are also reported.

### 4.7 The eval log
Each run writes `logs/always_wiring_<YYYY-MM-DD_HHMMSS>.md` with one section per eval case (10) in case order. Each section has the six sub-sections of spec 043 §4.5 (Input with history, Planner, Tools, Retrieved, Answer, Verdict). A case that raises is recorded as an error and the run goes on.

## 5. Acceptance criteria
- **AC-1:** Scope follows §4.1 and §4.2. `counts` holds exactly the in-scope items whose number is known, in `ALWAYS_COUNT_ITEMS` order, and the counts are spec 044's formulas.
- **AC-2:** A missing in-scope number gives `need_info` with the known in-scope counts filled in (`{}` when none is known). A missing out-of-scope number never causes `need_info`.
- **AC-3:** `checks == ALWAYS_CHECK_ITEMS` on every `ok` and `need_info` result, whatever the scope. `checks` and `counts` are `None` only on `invalid`.
- **AC-4:** `about` parsing follows §4.1: case and spaces are ignored and `"drip trays"` is accepted. Missing, `null`, blank, unknown or non-string means `"both"`, never `invalid`.
- **AC-5:** Out-of-scope values are ignored, even invalid ones. In-scope precedence is `invalid` > `need_info` > `ok`. A non-mapping `args` is `invalid`, and nothing raises.
- **AC-6:** `calculate_always_items(tables, drip_trays, about)` gives the same results as `run_always_tool` for the same values. Leaving out `about` behaves as `"both"`.
- **AC-7:** The text follows §4.3. Bus tubs and towels appear in every `ok` and `need_info` text, and out-of-scope items are neither named nor asked for. A `need_info` text lists the known counts and ends with the question.
- **AC-8:** All spec 044 tests still pass, except the `need_info` assertions listed in §3.4. Importing `blc.tools.always_tools` still leaves `langchain_core` out of `sys.modules`.
- **AC-9:** `PLANNER_TOOLS` is the five current tools (same objects, same order) plus the always tool, last. `plan_question` binds exactly `list(PLANNER_TOOLS)`. A planner reply with a `calculate_always_items` call keeps its name and arguments exactly: alone it gives route `TOOL`, and with a search it gives `BOTH`.
- **AC-10:** The planner's always tool has the schema and the example calls of §3.2.
- **AC-11:** `DEFAULT_TOOL_RUNNERS` has exactly the five keys of §3.3, and the always runner returns `run_always_tool`'s status and text for `ok`, `need_info` and `invalid`.
- **AC-12:** On the TOOL path, an always call with an `ok` or `need_info` result gives a reply that is the tool's text exactly. The answer model is not called, `answered_by_model` is False, and `on_token` gets the text once. An `invalid` result shows `TOOL_FAILED_REPLY` and never the raw text.
- **AC-13:** `invented_numbers` for the always tool:
  - It flags a `tables` or `drip_trays` value that is not in the question or history, **including 1 and 0**.
  - It accepts a value that is there, including a spelled-out one ("four") and one from history.
  - It never flags `about`.
  In a full turn where the planner twice invents `tables`, `retried` is True and the final call has no `tables` key but keeps `about`. The reply is the tool's `need_info` question, which names bus tubs and towels and contains no invented number.
- **AC-14:** The other four tools' invented-number checks are unchanged, and the serving tool still accepts 1.
- **AC-15** *(eval)*: **Scope and numbers.** The SCOPE cases meet §4.6's threshold. The model calls the always tool with the right scope and numbers for each scope, and doesn't call it for a cutlery question.
- **AC-16** *(eval)*: **Asking.** The ASK cases meet the threshold. With a number missing, the model leaves it out (no 1 or 0 guessed), and the reply asks for it while giving what it can.
- **AC-17** *(eval)*: **Follow-ups and traps.** The MIX cases meet the threshold: an answer to the tool's question, a guest count next to a table count, and a "6-ft" table size in a BEO line.
- **AC-18** *(eval)*: Every eval run writes the log of §4.7, with 10 sections and all six sub-sections each. Only `logs/` is written.
- **AC-19** *(manual)*: The `PLANNER_PROMPT` and the always tool's descriptions contain no eval question word for word, and no example in them uses the same scope-and-number pair as an eval case. The descriptions cover every point of §3.2.
- **AC-20** *(manual)*: Only these change: `backend/src/blc/tools/always_tools/`, `backend/src/blc/planner/`, `backend/src/blc/flow/`, the existing test assertions of §3.4 and the new tests. The code follows `CLAUDE.md`, and the scope item lists are named constants in the tool package.
- **AC-21:** Nothing else regresses. The unit tests that passed before this spec still pass, except the assertions listed in §3.4.
- **AC-22** *(manual, revision 2)*: `PLANNER_PROMPT` or the always tool's description states both revision 2 points of §3.2: the "which scope wins" rule and the "item questions with no number" rule. No existing napkin rule in `PLANNER_PROMPT` sends a black linen, purple napkin or black napkin question to `search_documents` or `calculate_food_item`. The example calls still match no eval case (AC-19).
- **AC-23** *(manual, revision 3)*: `PLANNER_PROMPT` meets all three of these:
  - **Examples:** it has `Example:` lines for `calculate_always_items` in the same format as the other tools' examples, including exactly these two:
    - `"How many black napkins should I pull?"` → `calculate_always_items {"about": "drip_trays"}`
    - `"What goes in the Always box for 7 drip trays?"` → `calculate_always_items {"about": "both", "drip_trays": 7}`

    Any other always-tool example matches no eval case's question or scope-and-number pair (AC-19).
  - **Rule 1:** Rule 1 (TOOL) says that the Always items (black linens, purple napkins, black napkins, the Always box) are TOOL even when no amount is given, so the tool asks.
  - **Rule 2:** Rule 2's "whether to bring a supply when no count is needed" does not cover them.

  The other tools' rules and examples are unchanged.
- **AC-24** *(manual, revision 4)*: The always tool's descriptions and `PLANNER_PROMPT` follow §3.2 revision 4, points 1 to 7. The schema, the tool name and every other tool's text are unchanged. Where revision 4 cuts text that AC-22 required, AC-22 is still met through the tool's descriptions.
- **AC-25** *(manual, revision 5)*: `PLANNER_PROMPT`'s Rule 1 examples include exactly this line, in the same format as the other `Example:` lines, next to the two AC-23 examples:
  - `"How many black linens do I need?"` → `calculate_always_items {"about": "tables"}`

  Nothing else in the prompt, the tool descriptions or the code changes. This example is the only exception to AC-19's scope-and-number rule. It is still not an eval question word for word.

## 6. Test cases
- **Unit rows** use `run_always_tool` / `calculate_always_items` directly, or scripted fake models with the default runners. The always tool reads no file.
- **Eval rows** run the real flow (§3.5), are scored by §4.6, and are logged by §4.7.

**History:**
- **H-ASK:** "What always items do I need?" / "Bus tubs: check\nTowels: check\nPlease tell me how many tables and drip trays there are?"

### 6.1 SCOPE (the tool by scope)
| ID | Input | Expected | Covers |
|---|---|---|---|
| SCOPE-1 | about "tables", tables 4 | `ok`, counts `{"black linens": 9, "purple napkins": 8}` | AC-1 |
| SCOPE-2 | about "drip_trays", drip_trays 3 | `ok`, counts `{"black napkins": 3}` | AC-1 |
| SCOPE-3 | about "both", tables 2, drip_trays 3 | `ok`, the spec 044 CALC-1 counts | AC-1 |
| SCOPE-4 | about "tables", tables 0 | `ok`, `{"black linens": 0, "purple napkins": 0}` | AC-1 |
| SCOPE-5 | about "tables", no tables, drip_trays 3 / about "drip_trays", no drip_trays, tables 4 | `need_info`, counts `{}` each | AC-2 |
| SCOPE-6 | about "both", tables 4 only / drip_trays 3 only / neither | `need_info`; counts `{"black linens": 9, "purple napkins": 8}` / `{"black napkins": 3}` / `{}` | AC-2 |
| SCOPE-7 | each row of SCOPE-1 to SCOPE-6 | `checks == ("bus tubs", "towels")`; `list(counts)` follows `ALWAYS_COUNT_ITEMS` order | AC-3 |
| SCOPE-8 | about `"TABLES"` / `" drip trays "` / `"Both"` | read as tables / drip_trays / both | AC-4 |
| SCOPE-9 | about missing / `null` / `""` / `"linens"` / `3`, with tables 2, drip_trays 3 | `ok` with all three counts (treated as both) | AC-4 |
| SCOPE-10 | about "tables", tables 4, drip_trays `"two"` / `-1` | `ok`, counts as SCOPE-1 (out-of-scope ignored) | AC-5 |
| SCOPE-11 | about "tables", tables `"two"` / `-1` / `2.5` | `invalid`; `checks` and `counts` None | AC-5 |
| SCOPE-12 | about "both", tables `"two"`, drip_trays missing | `invalid` (not `need_info`) | AC-5 |
| SCOPE-13 | `calculate_always_items(4, None, "tables")`, `(None, None, "drip_trays")`, `(2, 3)` | same as `run_always_tool` for those values; the last as SCOPE-3 | AC-6 |
| SCOPE-14 | the spec 044 suite with the §3.4 updates; fresh subprocess import | passes; no `langchain_core` | AC-8 |

### 6.2 TEXT
| ID | Input | Expected | Covers |
|---|---|---|---|
| TEXT-1 | about "tables", tables 4 | has "Bus tubs", "Towels", "Black linens" with "9", "Purple napkins" with "8"; no "Black napkins" | AC-7 |
| TEXT-2 | about "drip_trays", drip_trays 3 | has "Bus tubs", "Towels", "Black napkins" with "3"; no "Black linens", no "Purple napkins" | AC-7 |
| TEXT-3 | about "both", tables 4, no drip_trays | has "Bus tubs", "Towels", "Black linens" with "9", "Purple napkins" with "8"; ends with `?`; has "how many" and "drip trays" | AC-7 |
| TEXT-4 | about "tables", no tables, drip_trays 3 | has "Bus tubs", "Towels"; ends with `?`; has "how many" and "tables"; no "drip trays" | AC-7 |
| TEXT-5 | about "both", neither | has "Bus tubs", "Towels"; question has "tables" and "drip trays" | AC-7 |

### 6.3 PLAN
| ID | Input | Expected | Covers |
|---|---|---|---|
| PLAN-1 | `PLANNER_TOOLS`; `plan_question` with a fake model | 5 current tools by identity and order, then the always tool last; no duplicate names; binds `list(PLANNER_TOOLS)` once | AC-9 |
| PLAN-2 | fake planner replies with an always call, then the same call plus a search | name and args kept exactly; route TOOL, then BOTH | AC-9 |
| PLAN-3 | the always tool's `parameters` via `convert_to_openai_tool` | equal to §3.2 (descriptions aside); none of the banned keywords | AC-10 |
| PLAN-4 | the always tool's description | at least three argument-dict examples, with `"about": "tables"`, `"about": "drip_trays"` and `"about": "both"`; at least one has no `tables` or no `drip_trays` key | AC-10 |
| PLAN-5 | `PLANNER_PROMPT` and the always tool's descriptions, against every eval question | no eval question word for word (casefolded) | AC-19 |

### 6.4 FLOW
| ID | Input | Expected | Covers |
|---|---|---|---|
| FLOW-1 | `DEFAULT_TOOL_RUNNERS`; the always runner on the SCOPE-1, SCOPE-6 (tables 4 only) and SCOPE-11 args | five keys exactly; status and text equal `run_always_tool`'s | AC-11 |
| FLOW-2 | fake planner: always call, about "tables", tables 4 | reply equals the tool text; `stream` never called; `answered_by_model` False; `on_token` once | AC-12 |
| FLOW-3 | fake planner: always call, about "both", tables 4 | reply is the `need_info` text with the linen counts and the drip-tray question; no model call | AC-12 |
| FLOW-4 | fake planner: always call, about "tables", tables `"two"` | reply is `TOOL_FAILED_REPLY`; raw text in neither `reply` nor `on_token` | AC-12 |

### 6.5 GUARD (invented numbers)
| ID | Input | Expected | Covers |
|---|---|---|---|
| GUARD-1 | question "Linens for 4 tables?": tables 4 / tables 5 / tables 1 / tables 0 | not flagged / `{"tables": (5,)}` / `{"tables": (1,)}` / `{"tables": (0,)}` | AC-13 |
| GUARD-2 | "Linens for four tables?", tables 4; "6 tables" in history, tables 6; "Linens for 1 table?", tables 1 | not flagged each | AC-13 |
| GUARD-3 | "Black napkins please", drip_trays 2; any `about` value | `{"drip_trays": (2,)}`; `about` never flagged | AC-13 |
| GUARD-4 | full turn "How many purple napkins do I need?"; fake planner twice sends about "tables", tables 1 | `retried` True; final call has `about` "tables" and no `tables` key; reply has "Bus tubs", "Towels", asks how many tables, and has no "1" count | AC-13 |
| GUARD-5 | serving call, qty 1, question with no "1"; food call, guests 70 not in the question | serving qty 1 not flagged; food guests 70 flagged as before | AC-14 |

### 6.6 LOG
| ID | Input | Expected | Covers |
|---|---|---|---|
| LOG-1 | the log writer on fake outcomes: one ok turn, one retried turn, one follow-up with history, one case that raises | six sub-sections each; the retried turn shows the first plan, rejected values and final plan; the history is shown; the raising case is an error and the next is still written | AC-18 |
| LOG-2 *(eval)* | the real eval run | `logs/always_wiring_<timestamp>.md` with 10 sections in case order | AC-18 |

### 6.7 EVAL (real model; scored by §4.6)
| ID | Area | Input | Expected | Covers |
|---|---|---|---|---|
| EVAL-1 *(eval)* | SCOPE | "How many black linens and purple napkins for 4 tables?" | TOOL; `[calculate_always_items]`; `ok`, `{"black linens": 9, "purple napkins": 8}` | AC-15 |
| EVAL-2 *(eval)* | SCOPE | "How many black napkins do I need for 3 drip trays?" | TOOL; `[calculate_always_items]`; `ok`, `{"black napkins": 3}` | AC-15 |
| EVAL-3 *(eval)* | SCOPE | "What always items do I pull for 5 tables and 2 drip trays?" | TOOL; `[calculate_always_items]`; `ok`, `{"black linens": 11, "black napkins": 2, "purple napkins": 10}` | AC-15 |
| EVAL-4 *(eval)* | SCOPE | "How many forks for 60 guests?" | TOOL; `[calculate_food_item]` (no always call) | AC-15 |
| EVAL-5 *(eval)* | ASK | "How many purple napkins do I need?" | TOOL; `[calculate_always_items]`; `need_info`, `{}`, text has "tables" | AC-16 |
| EVAL-6 *(eval)* | ASK | "What are the always items?" | TOOL; `[calculate_always_items]`; `need_info`, `{}`, text has "tables" and "drip trays" | AC-16 |
| EVAL-7 *(eval)* | ASK | "Always items for 4 tables?" | TOOL; `[calculate_always_items]`; `need_info`, `{"black linens": 9, "purple napkins": 8}`, text has "drip trays" | AC-16 |
| EVAL-8 *(eval)* | MIX | H-ASK, then "6 tables and 2 drip trays" | TOOL; `[calculate_always_items]`; `ok`, `{"black linens": 13, "black napkins": 2, "purple napkins": 12}` | AC-17 |
| EVAL-9 *(eval)* | MIX | "We have 50 guests and 3 tables. How many purple napkins?" | TOOL; `[calculate_always_items]`; `ok`, `{"black linens": 7, "purple napkins": 6}` | AC-17 |
| EVAL-10 *(eval)* | MIX | "Special instructions: set up 2 6-ft tables by the bar, 1 drip tray. What goes in the Always box?" | TOOL; `[calculate_always_items]`; `ok`, `{"black linens": 5, "black napkins": 1, "purple napkins": 4}` | AC-17 |

### 6.8 Checks without a test row
- AC-19's second and third sentences, AC-20, AC-22, AC-23, AC-24 and AC-25 are checked by the planner, who reads the changed code and descriptions.
- AC-21 is checked by the implementation-evaluator, who runs the whole unit suite.
