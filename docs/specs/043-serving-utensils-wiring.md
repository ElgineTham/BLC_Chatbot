# Spec 043: Connect the serving utensils tool (`calculate_serving_utensils`) to the chatbot

- **Status:** done (revision 4)
- **Known limitations:** FOLLOW-3 (no food amount, a guest count in the history) is still planned as a search in every run, so the model answers "I don't know" instead of asking how many; the FOLLOW area still meets its threshold. The planner drink eval cases T5 and T9 (`planner/test_planner_eval.py`) fail identically on the code before this spec (`572c2a8`), so they are not a regression from it.
- **Date:** 2026-11-18 (revision 1: two more existing assertions listed in §3; INVENT-3 uses Appendix A foods. Revision 2: the description tells the two fruit items apart; CALL-2 also checks totals. Revision 3: when to send `"each"`, `"dozen"` or no unit. Revision 4: a serving-utensil question with no amount still goes to the tool, which asks how many; FOLLOW-3 accepts that)

## 1. Goal
Spec 042 built `calculate_serving_utensils`, but nothing calls it. This spec connects it to the planned chat flow the way spec 030 connected `calculate_food_item`. The planner may call it, the flow runs it, and **the user gets the tool's text word for word** (spec 023). The model never invents a quantity the user did not give (spec 021).

It also fixes a risk found while building the tool. On a breakfast package BEO, a line like "Butter croissants … 70" means 70 people, not 70 dozen. The planner is told to send `"unit": "each"` for package lines. **The tool's reply also shows how it read each line** after the label `Counted for:` (e.g. `Counted for: butter croissants 70 each`), so a wrong reading is visible in the answer.

Real-model evals check two things: that the model **calls the tool** for serving-utensil questions, and that it sends the **right arguments**. Both are judged by the totals the tool returns. Every eval run writes a log.

## 2. Out of scope
- The Condiments box (its own later spec), and any change to the rules (`data/pull_sheet/rules/serving_utensils.json`) or to `blc.tools.serv_tools` beyond the reply text in §4.1.
- Reading BEO images, and expanding packages in code. The package line itself counts for nothing (spec 042 Appendix B), and the model passes the item lines.
- `TOOL_FAILED_REPLY` wording, the answer prompt, retrieval, models, `TOP_K`, ingest, the knowledge `.md` files, `backend/scripts/`, the web page.
- Changing how the other three tools are planned or run.
- Fixing eval failures: they are reported, and a revision decides what to change.

## 3. Interface contract
No new public names outside what is listed. Unchanged and reused: `plan_question`, `Plan`, `PlannedCall`, `run_planned_turn`, `TurnOutcome`, `ToolOutput`, `TOOL_FAILED_REPLY`, `REPLY_SEPARATOR`, `SERV_TOOL_NAME`, `run_serv_tool`, `load_serv_rules`, `SERV_RULES_FILE`.

```python
# blc.planner
PLANNER_TOOLS: tuple[BaseTool, ...]
# now the four old tools (same objects, same order) plus exactly one more, last,
# whose .name == SERV_TOOL_NAME ("calculate_serving_utensils"). plan_question binds the whole tuple.

# blc.flow
DEFAULT_TOOL_RUNNERS: Mapping[str, ToolRunner]
# now exactly the keys "calculate_bev_item", "scale_recipe", "calculate_food_item",
# "calculate_serving_utensils". The new key -> run_serv_tool(args) with the real rules file,
# returned as ToolOutput(result.status, result.text). The file is read only when the runner runs.

def invented_numbers(name, args, question, history=None) -> dict[str, tuple[object, ...]]
# unchanged signature. For name == "calculate_serving_utensils", every items[*].qty is checked
# against the numbers in the question and history (1 always accepted). Invented values are
# returned under the key "qty". food and unit are never flagged.
```

**The planner's view of the tool** is the tool in `PLANNER_TOOLS` named `SERV_TOOL_NAME`. Through `convert_to_openai_tool(tool)["function"]` the model receives exactly these `parameters` (descriptions shown as `…`):
```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array", "description": "…",
      "items": {
        "type": "object",
        "properties": {
          "food": {"type": "string", "description": "…"},
          "qty":  {"type": "number", "description": "…"},
          "unit": {"type": "string", "description": "…"}
        },
        "required": ["food"]
      }
    }
  },
  "required": ["items"]
}
```
- Nothing inside `parameters` uses `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title`, `enum` or the type `"null"`.
- The `description` contains **at least three example calls** as argument dicts:
  - one with two foods;
  - one with breakfast package item lines with `"unit": "each"`, including the `"freshly cut fruit platter"`;
  - one with a `"... market fresh fruit tray"` (small, medium or large) and a number of trays (revision 2).
- Next to those examples, the description says that a fruit tray ordered on its own is a small, medium or large market fresh fruit tray counted in trays, and that `"freshly cut fruit platter"` is only the fruit line of a breakfast package (revision 2).
- The descriptions also cover these points (the wording is the developer's):
  - `qty` and `unit` are what the user or BEO wrote, never converted by the model.
  - Package item lines are a number of people, so they use `"unit": "each"`.
  - (revision 3) In a chat question, a plain count before a food with no unit word (e.g. "20 sandwiches") counts pieces, so it is sent with `"unit": "each"`. `"dozen"` is sent only when the user writes dozen, or when a BEO line's unit is dozen. The unit is left out only when there is no amount.
  - (revision 3) Every example call that has a `qty` also has a `unit`, so no example contradicts the rule above.
  - The package line itself (e.g. "Cascade Breakfast") may be left out.
  - `qty` is left out when no amount was given.

**Existing tests that change.** The tester updates only these assertions to the new lists:
- `backend/tests/planner/test_plan.py`: the `PLANNER_TOOLS` length and order check (4 → 5 tools).
- `backend/tests/food_wiring/test_planner_tools.py`: the same check.
- `backend/tests/planned_flow/test_contract.py`: `set(DEFAULT_TOOL_RUNNERS)`.
- `backend/tests/food_wiring/test_answer.py`: `test_default_runner_keys_are_exactly_the_three` (its `set(DEFAULT_TOOL_RUNNERS)` check, now four keys).
- `backend/tests/food_wiring/test_planner_tools.py`: the bound-tools check that the food tool is the last bound tool. The food tool is now at index 3 and the serving tool is last.

**Eval setup** (eval cases only):
- The model and store are set up as in the spec 030 eval: `build_chat_model(temperature=CHAT_TEMPERATURE)` and `build_domain_store()` from `chat.py`.
- The cases skip, not fail, when `ANTHROPIC_API_KEY` or `GOOGLE_API_KEY` is unset, when `.chroma/` is missing, or when the real rules file is missing.
- Each case runs `run_planned_turn(llm, store, question, history)` with default runners, so the tool reads the real rules file.
- The eval writes only under `logs/`.

## 4. Inputs and outputs

### 4.1 The reading in the tool's text (change to spec 042 §4.5)
For status `ok`, the text always ends with a line that starts with the label `Counted for:` (exactly, with that capitalisation). It shows how each input line was read: the canonical food name, the quantity and the unit used.
- When no unit was given, the unit shown is the food's own unit.
- Whole numbers are shown without a decimal (`70`, not `70.0`). Other numbers are shown with up to 2 decimals (`2.5`).
- One line per input line, in input order. Example for the 70-guest Cascade lines:
  ```
  Small tongs: 6
  Large tongs: 2
  Spreader/knives: 2
  Honey bear: 2
  Serving spoon: 1
  Counted for: butter croissants 70 each; freshly cut fruit platter 70 each; greek yogurt with honey and granola 70 each; cascade breakfast 70 packages
  ```
  Apart from the `Counted for:` label, the exact layout is the developer's. Every spec 042 text rule still holds. Error and `need_info` texts have no `Counted for:` line.

### 4.2 Which questions go to the tool (what the planner is expected to do)
| Question | Plan |
|---|---|
| which or how many serving utensils (tongs, serving spoons, spreaders, honey bears, salad tongs, ladles) for foods with amounts, or for a BEO's food lines | `calculate_serving_utensils` with every food line in one call |
| forks, spoons, knives, plates, napkins by guests or meal | `calculate_food_item`, as today |
| cups, gallons, cambros, drinks | `calculate_bev_item` / `scale_recipe`, as today |
| where something is kept, what comes with a food | `search_documents` only |
| a follow-up ("what about 6 dozen instead?") | the call the history implies, with the changed amount |
| (revision 4) which or how many serving utensils for a food with **no amount** in the question or history ("which tongs for the tabbouleh?") | `calculate_serving_utensils` with that food and `qty` left out, so the tool asks how many (`need_info`). Never `search_documents` alone. |

A guest count in the history is not turned into a food quantity by any rule in this spec; the model may use it or leave `qty` out (revision 4).

### 4.3 Invented quantities
- If `qty` in a planned serving call is not a number in the question or history, the planner is asked once more (spec 021).
- If the second plan still invents it, the turn behaves like this:
  - the invented `qty` is removed from **that item only**;
  - the item itself and the other items with their quantities stay;
  - the tool then returns its `need_info` question.

### 4.4 How an eval case is scored
A case passes when all its checks pass. Every check reads the final plan (`outcome.plan`).
1. **Route** equals the case's route.
2. **Tool names:** the names of the plan's tool calls (not `search_documents`) equal the case's list as a multiset.
3. **Totals** (CALL-2, ARGS, and the FOLLOW cases with totals, except FOLLOW-3): the serving call's arguments, run through `run_serv_tool` with the real rules, give status `ok` and `utensils` equal to the case's expected dict. Matching on the result, not the raw arguments, means any food alias or unit spelling that gives the right totals passes. A package line read as dozens gives the wrong totals and fails.
4. **Search** (DOCS cases): at least one `search_documents` call, whose query contains the case's keyword.
5. **Totals or ask** (FOLLOW-3 only, revision 4): the serving call's arguments, run through `run_serv_tool` with the real rules, give either status `ok` with `utensils` equal to the case's expected dict, or status `need_info`. Any other result fails.

**Thresholds:** CALL, ARGS and FOLLOW each pass at **at least 3 of their 4 cases**. Also reported: per-case pass or fail, route, and the time of the turn.

### 4.5 The eval log
- Each run writes `logs/serv_wiring_<YYYY-MM-DD_HHMMSS>.md`, with one section per eval case (12) in case order.
- Each section has the same six sub-sections as spec 030 §4.3: Input (with history), Planner (first plan, rejected values, retried, final plan), Tools (name, args, status, exact text), Retrieved, Answer, and Verdict (failed checks).
- A case that raises is recorded as an error and the run goes on.

## 5. Acceptance criteria
- **AC-1:** `PLANNER_TOOLS` is the four old tools (same objects, same order) plus one tool named `SERV_TOOL_NAME`, last. `plan_question` binds exactly `list(PLANNER_TOOLS)`.
- **AC-2:** The planner's serving tool has the schema and description of §3.
- **AC-3:** A planner reply with a `calculate_serving_utensils` call keeps its name and arguments exactly. That call alone gives route `TOOL`; with a search, route `BOTH`.
- **AC-4:** `DEFAULT_TOOL_RUNNERS` has exactly the four keys of §3.
  - The serving runner returns the same status and text as `run_serv_tool(args)`, for `ok`, `need_info` and `invalid` results.
  - Importing `blc.flow` without calling a runner reads no rules file.
- **AC-5:** On the TOOL path, a serving call with an `ok` or `need_info` result works like this:
  - the reply is the tool's text exactly;
  - the answer model is never called;
  - `answered_by_model` is False;
  - `on_token` gets the text once.
- **AC-6:** A serving result with status `invalid` shows `TOOL_FAILED_REPLY`, never the raw text.
- **AC-7:** BOTH with a serving call and a search that finds chunks gives this reply: the tool text, then `REPLY_SEPARATOR`, then the model's streamed answer. The tool part reaches `on_token` first, and no message to the answer model contains the tool text.
- **AC-8:** `invented_numbers` checks `items[*].qty` as §3 says:
  - It flags a `qty` that is not in the question or history.
  - It accepts a `qty` that is there (including a spelled-out number) and accepts 1.
  - It never flags `food` or `unit`.

  In a full turn where the planner twice sends an invented `qty`, §4.3 applies: `retried` is True, and only the invented `qty` is dropped. The reply is the tool's `need_info` question, with no invented number in it.
- **AC-9:** The `ok` text has a `Counted for:` line (§4.1), and a `need_info` or `invalid` text has none. The line shows each line's canonical food, its quantity formatted as §4.1, and the unit used (the food's own unit when none was given). Every spec 042 text test still passes.
- **AC-10** *(eval)*: **Tool calling.** The CALL cases meet §4.4's threshold. The model calls the serving tool for serving-utensil questions, and not for a cutlery question or a where-is-it question.
- **AC-11** *(eval)*: **Right arguments.** The ARGS cases meet the threshold. This includes several foods in one question, a quantity given as single pieces of a dozen food, and a breakfast package for a number of people.
- **AC-12** *(eval)*: **Follow-ups.** The FOLLOW cases meet the threshold. They cover a changed amount, an amount said in an earlier turn, a serving-utensil question with no amount of food (revision 4: it calls the serving tool, which either uses the history's count or asks how many, and never only searches), and a where-is-it question after a utensil answer, which is a search with no tool call.
- **AC-13** *(eval)*: Every eval run writes the log of §4.5, with 12 sections and all six sub-sections each. Only `logs/` is written.
- **AC-14:** The `PLANNER_PROMPT` text and the serving tool's descriptions contain none of the eval questions word for word. *(manual)* No example in them uses the same food-and-number pair as an eval case. *(manual, revision 3)* The descriptions state the unit rule of §3 (plain count → `"each"`; `"dozen"` only when written; no unit only when no amount), and every example call with a `qty` has a `unit`. *(manual, revision 4)* `PLANNER_PROMPT` or the serving tool's description says a serving-utensil question with no amount still calls `calculate_serving_utensils`, with `qty` left out, so the tool asks how many.
- **AC-15** *(manual)*: Only these change:
  - `backend/src/blc/planner/`;
  - `backend/src/blc/flow/`;
  - the reply text module of `backend/src/blc/tools/serv_tools/`;
  - the existing test assertions listed in §3;
  - the new tests.

  The code follows `CLAUDE.md`.
- **AC-16:** Nothing else regresses. The unit tests that passed before this spec still pass, except the assertions listed in §3, which move to the new lists.

## 6. Test cases
- **Unit rows** use scripted fake models. Their tool runner is built from `run_serv_tool(args, rules)`, with `rules` loaded from the spec 042 Appendix A copy in `tmp_path`.
- (revision 4) A unit test of the eval scorer that runs calls through the Appendix A rules takes its expected totals from Appendix A too, never from the real-rule totals in the eval tables (e.g. 30 classic deli sandwiches under Appendix A give `{"large tongs": 1, "mayo/mustard": 2}`). The real-rule totals in §6 are used only by the eval run.
- **Eval rows** run the real flow (§3 setup) with the real rules, are scored by §4.4, and are logged by §4.5.

**Histories:**
- **H-MUFFIN:** "What serving utensils do I need for 4 dozen muffins?" / "Small tongs: 4. Counted for: breakfast muffins 4 dozen"
- **H-DELI:** "Utensils for 50 classic deli sandwiches?" / "Large tongs: 6. Mayo/mustard: 2. Counted for: classic deli sandwiches 50 each"
- **H-LUNCH:** "We have 30 guests for lunch tomorrow." / "Got it, 30 guests for lunch."

### 6.1 CALL (does the model call the tool?)
| ID | Input | Expected | Covers |
|---|---|---|---|
| CALL-1 *(eval)* | "What serving utensils do I need for 4 dozen muffins?" | TOOL; tools `[calculate_serving_utensils]` | AC-10 |
| CALL-2 *(eval)* | "How many tongs should I pull for 3 large fruit trays?" | TOOL; tools `[calculate_serving_utensils]`; totals `{"large tongs": 6}` (3 trays, not the per-person platter) | AC-10 |
| CALL-3 *(eval)* | "How many forks for 60 guests?" | TOOL; tools `[calculate_food_item]` (no serving call) | AC-10 |
| CALL-4 *(eval)* | "Where are the scones kept?" | DOCS; no tool call; query contains "scone" | AC-10 |
| CALL-5 | `PLANNER_TOOLS`; the serving tool's schema; a fake planner replying with a serving call (alone, then with a search) | 4 old tools + serving tool last; schema per §3; the description has at least three example calls, one with `"freshly cut fruit platter"` and one with a `"market fresh fruit tray"` food; name and args kept exactly; route TOOL, then BOTH | AC-1, AC-2, AC-3 |
| CALL-6 | the text of `PLANNER_PROMPT` and of the serving tool's descriptions, checked against every eval question | no eval question appears in them word for word (casefolded) | AC-14 |

### 6.2 ARGS (right arguments, judged by totals)
| ID | Input | Expected `utensils` (real rules) | Covers |
|---|---|---|---|
| ARGS-1 *(eval)* | "What serving utensils for 2 dozen bagels and 50 classic deli sandwiches?" | `{"small tongs": 2, "large tongs": 6, "spreader/knives": 2, "mayo/mustard": 2}` | AC-11 |
| ARGS-2 *(eval)* | "We have a Cascade Breakfast for 70 guests: butter croissants, a freshly cut fruit platter and Greek yogurt with honey and granola. What serving utensils do I pull?" | `{"small tongs": 6, "large tongs": 2, "spreader/knives": 2, "serving spoon": 1, "honey bear": 2}` | AC-11 |
| ARGS-3 *(eval)* | "Serving utensils for 36 croissants?" | `{"small tongs": 4, "spreader/knives": 2}` (36 each = 3 dozen = 2 trays) | AC-11 |
| ARGS-4 *(eval)* | "What utensils do I need for scrambled eggs and roasted breakfast potatoes for 40 guests?" | `{"serving spoon": 4}` | AC-11 |

### 6.3 FOLLOW (follow-ups)
| ID | Input | Expected | Covers |
|---|---|---|---|
| FOLLOW-1 *(eval)* | H-MUFFIN, then "What about 6 dozen instead?" | TOOL; `{"small tongs": 6}` | AC-12 |
| FOLLOW-2 *(eval)* | H-DELI, then "And for 100 sandwiches?" | TOOL; `{"large tongs": 10, "mayo/mustard": 4}` | AC-12 |
| FOLLOW-3 *(eval)* | H-LUNCH, then "What serving utensils do I need for the classic deli sandwiches?" | TOOL; tools `[calculate_serving_utensils]`; totals-or-ask (§4.4 check 5): `{"large tongs": 4, "mayo/mustard": 2}` (30 from history) **or** status `need_info` (revision 4) | AC-12 |
| FOLLOW-4 *(eval)* | H-MUFFIN, then "Where are the muffins kept?" | DOCS; no tool call; query contains "muffin" | AC-12 |

### 6.4 ANSWER (the reply is the tool's)
| ID | Input | Expected | Covers |
|---|---|---|---|
| ANSWER-1 | fake planner: serving call, croissants 3 dozen | reply equals the runner's text exactly; `stream` never called; `answered_by_model` False; `on_token` once. `DEFAULT_TOOL_RUNNERS` has the four keys; the default serving runner gives `run_serv_tool`'s status and text (`SERV_RULES_FILE` pointed at the Appendix A copy) | AC-4, AC-5 |
| ANSWER-2 | fake planner: croissants with no qty | reply is the tool's `need_info` question; no model call | AC-5 |
| ANSWER-3 | fake planner: food "lasagna", qty 3 | reply is `TOOL_FAILED_REPLY`; raw text in neither `reply` nor `on_token` | AC-6 |
| ANSWER-4 | fake planner: serving call + a search that finds a chunk; fake answer model says "On the rack." | tool text + `REPLY_SEPARATOR` + "On the rack."; tool part first, before `stream`; no message to the model contains the tool text | AC-7 |
| ANSWER-5 | `import blc.flow` with `SERV_RULES_FILE` pointed at a missing path, no runner called | no error | AC-4 |

### 6.5 INVENT (invented quantities)
| ID | Input | Expected | Covers |
|---|---|---|---|
| INVENT-1 | `invented_numbers` for the question "Utensils for 4 dozen muffins": `qty` 4 / 48 / 1; `qty` "four" when the question says "four dozen"; `qty` 30 with H-LUNCH as history | not flagged / `{"qty": (48,)}` / not flagged / not flagged / not flagged | AC-8 |
| INVENT-2 | `invented_numbers` with an odd `food` or `unit`, e.g. food "7 layer bars" | `food` and `unit` are never flagged | AC-8 |
| INVENT-3 | full turn: "Utensils for bagels and 2 dozen croissants?"; the fake planner twice sends bagels `qty` 48 and croissants `qty` 2 | `retried` True; the final call has bagels with no `qty` key and croissants `qty` 2; the reply is the `need_info` question naming the bagels, with no "48" | AC-8 |

### 6.6 TEXT (the reading)
| ID | Input (Appendix A rules) | Expected | Covers |
|---|---|---|---|
| TEXT-1 | croissants 70, unit each | text contains `Counted for:`, then "butter croissants" (case-insensitive) and "70 each" after it | AC-9 |
| TEXT-5 | croissants with no qty (`need_info`); food "lasagna" (`invalid`) | neither text contains `Counted for:` | AC-9 |
| TEXT-2 | croissants 3, no unit | text contains "3 dozen" | AC-9 |
| TEXT-3 | croissants 2.5 dozen; croissants 70.0 each | "2.5 dozen"; "70 each", not "70.0" | AC-9 |
| TEXT-4 | trail mix 12 + croissants 1 dozen | the trail mix and croissant lines are both in the reading, in input order | AC-9 |

### 6.7 LOG
| ID | Input | Expected | Covers |
|---|---|---|---|
| LOG-1 | the log writer on fake outcomes: one TOOL turn, one retried turn, one DOCS follow-up, and one case that raises | six sub-sections each; the retried turn shows the first plan, the rejected values and the final plan; the follow-up shows its history; the raising case is an error and the next case is still written | AC-13 |
| LOG-2 *(eval)* | the real eval run | `logs/serv_wiring_<timestamp>.md` with 12 sections in case order | AC-13 |

### 6.8 Checks without a test row
- AC-14's second sentence and AC-15 are checked by the planner, who reads the changed code and prompt.
- AC-16 is checked by the implementation-evaluator, who runs the whole unit suite.
