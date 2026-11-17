# Spec 030: Connect the food tool (`calculate_food_item`) to the chatbot

- **Status:** approved (done: closed by the user; CALL eval 4 of 6 and the CALL-8 prompt check carried over, see closing note)
- **Date:** 2026-11-17

## 1. Goal
Spec 029 built `calculate_food_item` (spoons, forks, knives, small and large plates by guest count; cocktail and dinner napkins yes/no by meal type) but nothing calls it. This spec connects it to the chat flow the way `calculate_bev_item` and `scale_recipe` are connected: the planner may call it, the flow runs it, and **the user gets the tool's text word for word** (spec 023): the answer model never rewrites it and the model never invents a number the user did not give (spec 021). Questions about where things are kept still go to the documents, in the same turn (BOTH) or in a follow-up.

Because the model's choices (does it call the tool? with which arguments? does it carry the guest count or meal over from earlier turns?) can only be judged with the real model, most of the test cases are **evals** on `qwen2.5:7b`, scored like spec 018. The rest are unit tests with scripted fake models. **Every eval run writes a log** (§4.3) with, for each case and follow-up: the input, what the planner called, the tools and arguments, what was retrieved and the final answer, so a failure can be read, not guessed.

## 2. Out of scope
- **The tool and its rules** (`blc.tools.food_tools`, `data/pull_sheet/rules/food.json`): no change to any status, number or wording.
- **The old flow:** `run_turn`, `answer_turn`, the router and its registry, `blc.tool_step`, `CHAT_TOOLS`, `scripts/trace_flow.py` and `scripts/voice_chat.py`. Only the planned flow (`run_planned_turn`, used by `scripts/chat.py main()`) gets the tool.
- **`scripts/chat.py`, `blc.tools.bev_tools`, `blc.tools.recipe_tools`, `blc.pull_sheet`, retrieval, `ingest.py`, the knowledge `.md` files, the judge.**
- **The wording of `TOOL_FAILED_REPLY`** ("…naming the drink and the number of guests or gallons"). It is shared and unchanged; it reads oddly for a food question and is a later spec's fix.
- **A bare "napkins"** with neither a napkin type nor a meal, and napkin questions that mix several meals: not covered by a case; behaviour is whatever the model plans (the tool is strict, spec 029).
- **A runtime log in the live chat.** The logs here are written by the evals (§4.3). The chat itself logs nothing new.
- Changing models, `TOP_K`, chunking, temperature, the answer prompt, or the argument-check retry logic.
- Fixing eval failures: they are reported, and a revision of this spec decides what to change.

## 3. Interface contract
No new names. Existing public names change as follows; everything else keeps its signature.

```python
# src/blc/planner
PLANNER_TOOLS: tuple[BaseTool, ...]
# now (SEARCH_TOOL, PLANNER_BEV_TOOL, RECIPE_TOOL, <food tool>): the first three unchanged and in
# the same order (by identity); exactly one more, last, whose .name == FOOD_TOOL_NAME
# ("calculate_food_item", from blc.tools.food_tools). The planner binds the whole tuple.

# src/blc/flow
DEFAULT_TOOL_RUNNERS: Mapping[str, ToolRunner]
# now exactly the keys "calculate_bev_item", "scale_recipe", "calculate_food_item".
# "calculate_food_item" -> run_food_tool(args) from blc.tools.food_tools (the real rules file),
# returning ToolOutput(result.status, result.text). The file is read only when the runner runs.

def invented_numbers(name, args, question, history=None) -> dict[str, tuple[object, ...]]
# unchanged signature; name == "calculate_food_item" is now checked like the other two tools:
# its `guests` values must appear as numbers in the question or the history (1 always accepted).
```
Unchanged and reused: `plan_question`, `Plan`, `PlannedCall`, `run_planned_turn`, `TurnOutcome`, `ToolOutput`, `TOOL_FAILED_REPLY`, `REPLY_SEPARATOR`, `NO_DOCS_REPLY`, `FOOD_TOOL_NAME`, `run_food_tool`, `load_food_rules`, `FOOD_RULES_FILE`.

**The planner's view of the food tool** (what the model receives through `convert_to_openai_tool(tool)["function"]` for the tool in `PLANNER_TOOLS` named `FOOD_TOOL_NAME`): `parameters.properties` has exactly the keys `item`, `guests`, `meal`, and `required == ["item"]`; no `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title` or type `"null"`; the `description` contains at least two example calls as argument dicts (one count call with `item` and `guests`, one napkin call with `item` and `meal`). The wording is the developer's.

**Existing tests that change** (the tester updates exactly these two assertions to the new lists; no other existing test changes): `tests/planner/test_plan.py` (the `PLANNER_TOOLS` identity check, 3 → 4 tools, spec 018 EC-1 and the `bind_calls` check) and `tests/planned_flow/test_contract.py` (`set(DEFAULT_TOOL_RUNNERS)`, spec 019).

**Eval setup** (eval cases only): `llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)` and `store = build_domain_store()` (both from `scripts/chat.py`, as in spec 027); the model is warmed up once. Each eval case runs the **whole planned flow**: `run_planned_turn(llm, store, question, history, on_token=...)` with every other parameter at its default (real tool runners, so the food tool reads the real `data/pull_sheet/rules/food.json`), where `history` is `None` or the case's list of `{"role", "content"}` items. Cases are scored on `outcome.plan` (§4.2) and logged from the `TurnOutcome` (§4.3). The cases skip, not fail, when Ollama is not running or `.chroma/` is missing. The eval writes only under `logs/`.

## 4. Inputs and outputs

### 4.1 Which questions go to the food tool (what the planner is expected to do)
| Question | Plan |
|---|---|
| a count of spoons, forks, knives, small plates or large plates for a number of guests | `calculate_food_item` with `item` and `guests`; no search |
| whether cocktail or dinner napkins are needed, with a meal type (breakfast, reception, lunch, dinner) | `calculate_food_item` with `item` and `meal`; no search |
| napkins asked about **with a drink and no meal type** ("napkins for the iced tea") | `search_documents` only (the beverage rules answer it, as today) |
| cups, gallons, cambros, the pull sheet | `calculate_bev_item` only, as today |
| where a food item is kept, what comes with it | `search_documents` only |
| a mix of the above | one call per part (BOTH) |
| a follow-up ("what about knives?", "and for 100 guests?", "and for a reception?") | the call the history implies: item, guest count or meal carried over from earlier turns, a changed amount replaced by the new one |
| a docs follow-up after a food calculation ("where are the croissants kept?") | `search_documents` only; no food call, and the old guest count is not reused |

### 4.2 How an eval case is scored
A case **passes** when all its checks pass. The scorer is a pure function of the case and the final `Plan` of the turn (`outcome.plan`, after the invented-number retry).
1. **Route:** `plan.route` equals the case's route.
2. **Tool calls:** the plan's tool calls (every call not named `search_documents`) match the case's expected calls **as a multiset** (order does not matter, each expected call matches exactly one actual call, no extra tool calls). Two calls match when the names are equal and, for `calculate_food_item` (rows marked "names only" compare names only):
   - `item` is equal after stripping, casefolding, treating `_` and `-` as a space, collapsing spaces, and accepting the singular ("fork" equals "forks");
   - for a **count item** (spoons, forks, knives, small plates, large plates): `guests` is equal by value (`60 == 60.0`; a numeric string counts as its number; a boolean is never a number); `meal` is not compared;
   - for a **napkin item**: `meal` is equal after stripping and casefolding; `guests` is not compared.
   A DOCS case expects zero tool calls.
3. **Search queries:** TOOL cases: no `search_documents` call. DOCS and BOTH cases: at least one `search_documents` call, and for each *keep* group at least one of its terms is a substring of the casefolded queries joined together. `LOC` = `where | locat | kept | stor | find | plac`.

**Thresholds:** CALL, ARGS, FOLLOW-TOOL and FOLLOW-DOCS each pass at **at least 5 of their 6 eval cases** (CALL-1 to 6, ARGS-1 to 6, FT-1 to 6, FD-1 to 6). ANSWER-7 must pass. Reported, not thresholded: route accuracy per area, and per case and on average the time to the first reply piece and the total time of the turn.

### 4.3 The eval log
The eval writes `logs/food_wiring_<YYYY-MM-DD_HHMMSS>.md` (the `logs/` folder is gitignored; create it if missing), one section per eval case (25 sections: CALL-1 to 6, ARGS-1 to 6, ANSWER-7, FT-1 to 6, FD-1 to 6), in case order. Follow-up cases (FT and FD) are logged exactly like single questions, with their history shown. Each section has these sub-sections, all always present (a part that does not apply says `none`):
- **Input:** id, area, the question, and the history (each turn as `role: content`, verbatim; `none` when there is no history).
- **Planner:** first plan (route and every call as name and arguments); rejected calls with their invented values; retried yes or no; final plan (route and every call as name and arguments).
- **Tools:** for each tool call that ran: name, arguments, status and text exactly as the tool returned them.
- **Retrieved:** for each search: its query and every chunk it returned, as the source path and the first 120 characters of the chunk. `none` when the plan had no search; a search with no chunks says so.
- **Answer:** the final reply verbatim; `answered_by_model` yes or no; time to first piece and total time in seconds.
- **Verdict:** pass or fail, with the names of the failed checks (`route`, `tools`, `search`) or `-`.

A case that raises while it runs, or while its section is built, is recorded as an error with its message in its section and its report line; the run goes on, and the case counts as failed. The report printed at the end has one line per case (id, pass or fail, failed checks, route) and the per-area counts of §4.2, and names the log file.

## 5. Acceptance criteria
- **AC-1:** `PLANNER_TOOLS` is the three old tools (same objects, same order) plus one tool named `FOOD_TOOL_NAME`, last. `plan_question` binds exactly `list(PLANNER_TOOLS)`.
- **AC-2:** The planner's food tool has the schema and description in §3 ("The planner's view").
- **AC-3:** When the planner model replies with a `calculate_food_item` call, `plan_question` keeps its name and arguments exactly as sent. A food call alone gives route `TOOL`; with a `search_documents` call, `BOTH`.
- **AC-4:** `DEFAULT_TOOL_RUNNERS` has exactly the three keys in §3 and every value is callable. For the food key, the runner returns `ToolOutput(status, text)` equal to `run_food_tool(args)`'s status and text for the same arguments, including an invalid and a `need_info` result. Importing `blc.flow` and calling no runner reads no rules file.
- **AC-5:** TOOL path: with a food call that is `ok`, `need_info`, or a yes/no napkin answer, the reply is the tool's text exactly (no extra words), the answer model's `stream` is never called, `answered_by_model` is False, and `on_token` gets the text once (spec 023).
- **AC-6:** A food result with status `invalid` shows `TOOL_FAILED_REPLY`, never its raw text.
- **AC-7:** `invented_numbers` flags a `calculate_food_item` call whose `guests` is not a number in the question or history, accepts one that is (question or history, including a spelled-out number), accepts 1, and never flags `item` or `meal`. In a full turn, a planner that twice sends an invented `guests` has the value dropped: `retried` is True, `rejected` names the food call, the tool runs without `guests`, and the reply is the tool's `need_info` question, which shows no number the user did not give.
- **AC-8:** BOTH with a food call and a search that finds chunks: the reply is the tool text, `REPLY_SEPARATOR`, then the model's streamed answer. The tool part reaches `on_token` first, before the model is called, and no message sent to the answer model contains the tool's text (spec 023).
- **AC-9** *(eval)*: **Model calls the tool.** In the CALL cases the model chooses the food tool for food count and napkin-by-meal questions, and does not choose it for cups or napkins-with-a-drink questions (§4.1). CALL area meets §4.2's threshold.
- **AC-10** *(eval)*: **Right arguments.** In the ARGS cases the `item`, `guests` and `meal` the model sends are right (§4.2), including two items in one question and a spelled-out number. ARGS area meets the threshold.
- **AC-11** *(eval)*: **Follow-ups with the tool.** In the FT cases the model carries the item, the guest count or the meal over from the history, uses a changed amount instead of the old one, and does not need the guests restated when they were said in an earlier user turn. FT area meets the threshold.
- **AC-12** *(eval)*: **Follow-ups with the documents.** In the FD cases a docs question after a food calculation (or after docs) plans `search_documents` only, with the subject in the query, and calls no tool. FD area meets the threshold.
- **AC-13** *(eval)*: **The answer is the tool's.** For a real-model turn on a food question (ANSWER-7), the planned flow's reply equals `run_food_tool`'s text for the arguments the model sent, and the answer model is not called.
- **AC-14:** The eval scorer (§4.2) is a pure function and is unit-tested without a model (ARGS-7).
- **AC-15:** `PLANNER_PROMPT` and the food tool's description contain none of the eval questions (CALL, ARGS, FT, FD, ANSWER-7) word for word. *(manual)* None of their examples shares an item-and-number or item-and-meal pair with any eval case.
- **AC-16** *(manual)*: Only `src/blc/planner/` and `src/blc/flow/` change (plus the two existing test assertions in §3 and the new tests). The package structure follows `CLAUDE.md`: modules split by job, no catch-all modules, calculation code does no I/O.
- **AC-17:** Nothing else regresses: the existing unit tests that passed before this spec still pass, except the two assertions in §3, which move to the new lists. (The 17 failures in `docs/specs/024-baseline-failures.txt` are not part of this.)
- **AC-18** *(eval)*: **Every run is logged.** A real eval run writes the log of §4.3: 25 sections in case order, each with all six sub-sections, a follow-up section showing its history, and the planner sub-section showing the first and the final plan. Only files under `logs/` are written.
- **AC-19:** The log writer (§4.3) works without a model, from fake `TurnOutcome` objects: a TOOL turn shows the tool's name, arguments, status and exact text and `Retrieved: none`; a DOCS or BOTH turn shows each query with its sources and 120-character previews; a retried turn shows the first plan, the rejected values and the final plan; a follow-up shows its history turns verbatim; a chunk with no `source` is shown as `unknown`; a case that raises is recorded as an error and the next case is still written.

## 6. Test cases
Unit rows use scripted fake models. For ANSWER rows the tool runner is injected: `tool_runners={"calculate_food_item": <runner built from run_food_tool(args, rules)>}` where `rules` is `load_food_rules` on the spec 029 Appendix A written to `tmp_path`. Eval rows run the real flow (§3 setup) and are all logged (§4.3). Cases are written once here; the tester copies them.

**Histories** (user turn / assistant turn pairs, in order):
- **H-FORKS:** "How many forks do I need for 70 guests?" / "Forks: 120 (70 guests + 50 extra)"
- **H-LARGE:** "How many large plates for 50 guests?" / "Large plates: 70 (50 guests + 20 extra)"
- **H-NAPKIN:** "Do I need dinner napkins for a lunch?" / "Dinner napkins for lunch: yes"
- **H-MUFFIN:** "We have 60 guests at the lunch. Where are the muffins kept?" / "The breakfast muffins are on the metal rack in the service room, near the manager's table."
- **H-BAGEL:** "Where are the bagels kept?" / "Assorted bagels are on the metal rack in the service room, near the manager's table."
- **H-YOGURT:** "How many small plates for 80 guests?" / "Small plates: 130 (80 guests + 50 extra)", then "Where is the Greek yogurt kept?" / "Greek yogurt is in the service cooler."

### 6.1 CALL (does the model call the tool?)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| CALL-1 *(eval)* | "How many forks do we need for 90 guests?" | TOOL; one `calculate_food_item`, no other tool call (names only) | AC-9 |
| CALL-2 *(eval)* | "Will we need dinner napkins for the dinner service?" | TOOL; one `calculate_food_item` (names only) | AC-9 |
| CALL-3 *(eval)* | "How many small plates for 45 people?" | TOOL; one `calculate_food_item` (names only) | AC-9 |
| CALL-4 *(eval)* | "Should I put out cocktail napkins for breakfast?" | TOOL; one `calculate_food_item` (names only); not DOCS | AC-9 |
| CALL-5 *(eval)* | "How many cups do I need for 70 guests?" | TOOL; one `calculate_bev_item` and no `calculate_food_item` | AC-9 |
| CALL-6 *(eval)* | "Do I need napkins for the iced tea?" | DOCS; a search, no tool call, no `calculate_food_item` | AC-9 |
| CALL-7 | `PLANNER_TOOLS`; the planner's food tool schema; a fake model replying with a food call (alone, then with a search) | 3 old tools + food tool last, `plan_question` binds `list(PLANNER_TOOLS)`; schema per §3; the plan keeps name and args exactly, route TOOL then BOTH | AC-1, AC-2, AC-3 |
| CALL-8 | the strings of `PLANNER_PROMPT` and of the food tool's description, against every eval question in CALL, ARGS, FT, FD and ANSWER-7 | none of the questions appears word for word (casefolded) | AC-15 |

### 6.2 ARGS (right arguments)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ARGS-1 *(eval)* | "How many spoons do I need for 45 guests?" | TOOL; `{item: spoons, guests: 45}` | AC-10 |
| ARGS-2 *(eval)* | "How many large plates for 120 people?" | TOOL; `{item: large plates, guests: 120}` | AC-10 |
| ARGS-3 *(eval)* | "How many knives and forks for 60 guests?" | TOOL; two calls: `{knives, 60}` and `{forks, 60}` | AC-10 |
| ARGS-4 *(eval)* | "Do I need dinner napkins for a lunch for 80 guests?" | TOOL; `{item: dinner napkins, meal: lunch}` (guests not compared) | AC-10 |
| ARGS-5 *(eval)* | "Do we put out cocktail napkins at a reception?" | TOOL; `{item: cocktail napkins, meal: reception}` | AC-10 |
| ARGS-6 *(eval)* | "How many small plates for fifty guests?" | TOOL; `{item: small plates, guests: 50}` (spelled number sent as 50) | AC-10 |
| ARGS-7 | the scorer on hand-made plans: "Fork" vs `forks`; `small_plate` vs `small plates`; a napkin call with a wrong `guests`; a count call with a wrong `meal`; wrong `guests`; missing `meal`; an extra tool call; a missing call; a boolean `guests` | the first four pass; the rest fail with the named check | AC-14 |

### 6.3 ANSWER (the answer is the tool's, not the model's)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ANSWER-1 | fake planner: `{forks, guests 70}`; default runner registered | reply equals the runner's text and contains "120"; `answered_by_model` False; the answer model's `stream` never called; `on_token` gets the text once; `DEFAULT_TOOL_RUNNERS` keys are the three; the default food runner returns `run_food_tool`'s status and text (FOOD_RULES_FILE pointed at the Appendix A copy) | AC-4, AC-5 |
| ANSWER-2 | fake planner: `{dinner napkins, meal lunch}` | reply equals the tool's text, with the whole word "yes"; no model call | AC-5 |
| ANSWER-3 | fake planner: `{dinner napkins}` with no meal | reply equals the tool's `need_info` text (a question ending `?` that mentions "meal"); no model call | AC-5 |
| ANSWER-4 | fake planner: `{item: chairs, guests: 10}` | reply is `TOOL_FAILED_REPLY`; the tool's raw text is in neither `reply` nor `on_token` | AC-6 |
| ANSWER-5 | question "How many forks do I need?" (no number); fake planner sends `{forks, guests 100}` both times; `invented_numbers` on the same call | `retried` True, `rejected` has the food call, final call has no `guests`, reply is the `need_info` question mentioning "guests" with no "100" or "200"; the check flags 100, accepts a number in history, accepts 1, ignores `item` and `meal` | AC-7 |
| ANSWER-6 | fake planner: `{forks, guests 70}` plus a search that finds a chunk; fake answer model replies "Kept on the rack." | reply is the tool text + `REPLY_SEPARATOR` + "Kept on the rack."; the tool part is the first `on_token` piece, before `stream` is called; no message sent to the model contains "Forks" or "120" | AC-8 |
| ANSWER-7 *(eval)* | the real flow (§3 setup, default runners, real store): "How many forks do I need for 70 guests?" | route TOOL; the reply equals `run_food_tool({"item": "forks", "guests": 70}).text` for the arguments sent; `answered_by_model` False | AC-13 |

### 6.4 FOLLOW-TOOL (follow-ups that use the tool)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FT-1 *(eval)* | H-FORKS, then "What about knives?" | TOOL; `{knives, 70}`; no search | AC-11 |
| FT-2 *(eval)* | H-FORKS, then "How many if it's 100 guests instead?" | TOOL; `{forks, 100}` (new amount replaces the old) | AC-11 |
| FT-3 *(eval)* | H-LARGE, then "And small plates?" | TOOL; `{small plates, 50}` | AC-11 |
| FT-4 *(eval)* | H-NAPKIN, then "What about cocktail napkins?" | TOOL; `{cocktail napkins, meal lunch}` | AC-11 |
| FT-5 *(eval)* | H-NAPKIN, then "And for a reception?" | TOOL; `{dinner napkins, meal reception}` | AC-11 |
| FT-6 *(eval)* | H-MUFFIN (guests said only in an earlier user turn), then "How many forks do I need?" | TOOL; `{forks, 60}`; no search | AC-11 |

### 6.5 FOLLOW-DOCS (follow-ups that use the documents)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FD-1 *(eval)* | H-FORKS, then "Where are the croissants kept?" | DOCS; no tool call; keep `croissant`, `LOC` | AC-12 |
| FD-2 *(eval)* | H-LARGE, then "Where is the cream cheese kept?" | DOCS; no tool call; keep `cream cheese`, `LOC` | AC-12 |
| FD-3 *(eval)* | H-NAPKIN, then "Where is the Greek yogurt?" | DOCS; no tool call; keep `yogurt`, `LOC` | AC-12 |
| FD-4 *(eval)* | H-FORKS, then "What comes with the croissants?" | DOCS; no tool call; keep `croissant` | AC-12 |
| FD-5 *(eval)* | H-BAGEL, then "And what comes with them?" | DOCS; no tool call; keep `bagel` or `cream cheese` | AC-12 |
| FD-6 *(eval)* | H-YOGURT, then "And the vegan one?" | DOCS; no tool call (the old 80 guests is not reused); keep `vegan` | AC-12 |

### 6.6 LOG (the eval log)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LOG-1 | fake TOOL outcome: `{forks, guests 70}`, status `ok`, text "Forks: 120 (70 guests + 50 extra)", no searches | section has Input, Planner, Tools (name, args, status, exact text), `Retrieved: none`, Answer, Verdict | AC-19 |
| LOG-2 | fake follow-up outcome: H-FORKS history, then "Where are the croissants kept?", one search with two chunks (one without `source`) | Input shows both history turns verbatim; Retrieved shows the query, each source with 120 characters, `unknown` for the missing source; Tools says `none` | AC-19 |
| LOG-3 | fake retried outcome: first plan `{forks, guests 100}`, rejected `guests (100,)`, final plan without guests | Planner shows the first plan, the rejected values, `retried: yes`, and the final plan | AC-19 |
| LOG-4 | three fake cases where the second one raises when its section is built | the second is recorded as an error with its message; the first and third sections are written; the report counts the second as failed | AC-19 |
| LOG-5 *(eval)* | the real eval run (CALL, ARGS, ANSWER-7, FT, FD) | `logs/food_wiring_<timestamp>.md` exists with 25 sections in case order, each with all six sub-sections; an FT section shows its history; nothing is written outside `logs/` | AC-18 |

### 6.7 Checks without a test row
- AC-15's second sentence and AC-16 are checked by the planner reading the changed code and prompt (manual).
- AC-17 is checked by the implementation-evaluator running the whole unit suite and comparing it with the baseline.

## Closing note (2026-11-17)
Closed by the user. The run on 2026-11-17 (`logs/food_wiring_2026-11-17_150929.md`): unit tests for this spec passed except CALL-8's prompt half; evals CALL 4/6 (below the 5 of 6 threshold), ARGS 5/6, FOLLOW-TOOL 6/6, FOLLOW-DOCS 6/6, ANSWER-7 pass. Carried over:
- **CALL-2 and CALL-4:** napkin-by-meal questions went to `search_documents` and the answer was "the documents do not mention it". The napkin facts are to be written into the documents in spec 031, so the docs route can answer them. Whether the food tool's napkin half stays in the planner is decided there.
- **CALL-8 (prompt half):** `PLANNER_PROMPT` still holds the spec 018 example "How many cups do I need for 70 guests?", which is word for word CALL-5. Not fixed.
- **Not this spec's:** `tests/test_voice_io_answer_turn.py::test_chat_main_routes_turns_through_run_planned_turn` also fails on a clean HEAD (since spec 028's `DomainStore`).
