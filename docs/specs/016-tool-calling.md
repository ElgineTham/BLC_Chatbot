# Spec 016: Connect the recipe tool, and evaluate tool calling (20 cases per tool)

- **Status:** approved (revision 1, done)
- **Date:** 2026-11-12 (revision 1: 2026-11-13)

## 1. Goal
Spec 015 built `scale_recipe` but left it unconnected. This spec connects it: the router's `scale_recipe` row becomes available, and the tool step runs **the tool the router picked** for each TOOL part, with that tool's own prompt. The main deliverable is an **eval of tool calling** with the real model: 20 questions for `calculate_bev_item` and 20 for `scale_recipe`. Each case checks that the agent calls **the right tool** with **the right arguments**. The eval runs the router and the tool step (`run_turn(..., generate=False)`) but not the final answer, and it reports which stage caused each failure (router or tool step).

## 2. Out of scope
- Judging the final answer text, timing, and streaming. The eval never generates a reply.
- Any change to the calculators' behaviour (`blc.tools.bev_tools`, `blc.tools.recipe_tools`), to `blc.pull_sheet`, to the router's keywords, `split_clauses`, `is_follow_up` or `quick_label`.
- New recipes. Unit conversion.
- Fixing failures the first eval run finds: they are findings for a revision of this spec.

## 3. Interface contract

### 3.1 The chat flow: `scripts/chat.py`
```python
from blc.tools.recipe_tools import RECIPE_TOOL, RECIPE_TOOL_NAME

CHAT_TOOLS: tuple[BaseTool, ...] = (BEV_TOOL, RECIPE_TOOL)
TOOL_PROMPT: str            # unchanged: the calculate_bev_item tool-step prompt
RECIPE_TOOL_PROMPT: str     # NEW: the scale_recipe tool-step prompt
TOOL_PROMPTS: dict[str, str] = {BEV_TOOL_NAME: TOOL_PROMPT, RECIPE_TOOL_NAME: RECIPE_TOOL_PROMPT}
```
`run_turn`, `run_stages`, `run_tool_step`, `run_part`, `build_final_messages` and the trace types (`TurnTrace`, `ToolStage`, `ToolCallLog`, spec 011) keep their signatures and fields. Behaviour changes are in §4.1.

`RECIPE_TOOL_PROMPT` tells the model to always call `scale_recipe`, to pass the recipe name as the user said it, to pass `gallons` only when the user gave a batch size and `guests` only when the user gave a guest or people count, never to work one out from the other, and contains at least two example questions with their argument dicts (wording is the developer's; NFR-4). `ANSWER_PROMPT` additionally tells the model to give a recipe tool result's amounts and steps as given, and to say there is no recipe when the result says so (wording is the developer's; not tested).

### 3.2 The router: `src/blc/router/registry.py`
- `TOOL_REGISTRY`'s `scale_recipe` entry becomes `available=True`. Its name, purpose and keywords are unchanged, and so is the table order.
- `classifier_prompt()` (default table) contains both entries' purposes, `T` and `D`, and stays ≤ 1500 characters. It must lead the model to label "how much of an ingredient, or how to make something, **for a given number of gallons or guests**" as T, and "how something is made" with no amount as D. Wording is the developer's; the evals check it.

### 3.3 Files
- `data/recipes/recipes.json` must exist with the content of spec 015 Appendix A. **The planner creates it** before the developer starts (agents cannot write under `data/`).

## 4. Inputs and outputs

### 4.1 The tool step runs the router's tool
For each TOOL part, in order:
- **Which tool:** the tool in `chat.CHAT_TOOLS` (read when the turn runs, so tests can monkeypatch it) whose `name == part.tool`. A TOOL part with `tool=None` uses `calculate_bev_item` (as before).
- **Model:** `llm.bind_tools([that tool])`, only that one tool, and that part's tool step uses the object it returns. The tool-step messages are `[SystemMessage(TOOL_PROMPTS[name]), HumanMessage(part.text)]`. The reminder sent when the model makes no call names that tool.
- **Calls:** a call to a name not among the step's tools gets `"error: unknown tool <name>"` (as today). **Only** calls whose name equals the part's tool (`calculate_bev_item` when `part.tool` is `None`) are checked; a call to any other tool among the step's tools runs unchecked, as in spec 009 (e.g. `run_tool_step(bound, (other_tool,), RoutedPart("TOOL", text))`: a call to `other_tool` runs and returns its own result). Every call to the part's tool goes through `check_arguments(args, part.text, tool=name)` before it runs (spec 009 and spec 015 §4.7: a refused call is recorded with `refused=True` and the model is asked again, at most `MAX_TOOL_ROUNDS` rounds).
- **Tool not in `CHAT_TOOLS`:** no `bind_tools` and no model call for that part. The part is answered from the documents, the same as when the model makes no call (`tool_text=None`).
- A turn with no TOOL part never calls `bind_tools` (as today). Everything else about the flow is unchanged.

### 4.2 How an eval case is scored
Each case runs `run_turn(store, llm, history, question, generate=False)` with `llm = ChatOllama(model=CHAT_MODEL, temperature=0, keep_alive=CHAT_KEEP_ALIVE)`, the real store, and the real `CHAT_TOOLS`. A case lists one or more **expected tool calls**, in order. It passes when all of these hold:
1. **Right tool (router):** the route's TOOL parts, in order, have `tool` equal to the expected tools, one TOOL part per expected call. DOCS parts are ignored.
2. **A call was made:** each of those parts' `ToolStage` has at least one call, and every call in it is to that part's tool.
3. **Right arguments (tool step):** the stage's **accepted call** is its last call that was not refused and whose result does not start with `invalid` or `error`. Running the tool on the accepted call's args (`run_bev_tool(args)` or `run_recipe_tool(args)`, with the real data) gives the expected values in the table:
   - `calculate_bev_item`: `item`; status (default `ok`); the resolved drinks as a set of (display name, amount, `from_guests`) where amounts are listed ("any amount" = not compared); `not_on_menu` where listed; `guests` as `run_bev_tool` reads it ("no guests" = not given).
   - `scale_recipe`: status (default `ok`); `recipe` display name; `gallons`; `from_guests`; `guests` where listed.
   - "any of: (A), (B)" means either is accepted.
   - **A drink listed with no amount and no guests** (B12, B13): the calculator returns no resolved drinks in that case, so the drink is checked on the call's `drinks` argument instead: it holds exactly that drink's name (stripped, ignoring case). In addition, the tool's result text contains the supply the question asks about (B12: "Stir sticks"; B13: "Tea packets").

A case that fails is reported with its **stage**: `router` (rule 1), `no call` (rule 2), or `arguments` (rule 3). A case that passes after a refused or invalid first call is reported as `corrected`.

**Thresholds:** at least **18 of 20** `calculate_bev_item` cases (B1 to B20) and at least **18 of 20** `scale_recipe` cases (R1 to R20) pass. Also reported, with no threshold: how many cases passed on the **first** call.

## 5. Edge cases
**Router (unit, no model):**
- EC-1: default `TOOL_REGISTRY`: `scale_recipe` then `calculate_bev_item`, both `available=True`; names, purposes and keywords as spec 013 §3.1.
- EC-2: `pick_tool`: "How do I make 3 gallons of lemonade?" → `scale_recipe`; "How much concentrate for 6 gallons of lemonade?" → `scale_recipe`; "How many oz of lemon concentrate for 40 guests?" → `scale_recipe`; "How many cambros do I need for 7 gallons of lemonade?" → `calculate_bev_item`; "Where is the coffee?" → `None`.
- EC-3: `classifier_prompt()` contains both purposes, the letters `T` and `D` as whole words (not just inside other words), and is ≤ 1500 characters. A custom registry with an unavailable entry still leaves that entry's purpose out.
- EC-4: `route_fast` with a scripted reply `T` on "How do I make 3 gallons of lemonade?" → one part (TOOL, the question, `scale_recipe`). "How do I make lemonade?" → DOCS with no model call.

**Flow (unit, scripted fake model; `chat.CHAT_TOOLS` monkeypatched to `make_bev_tool(<spec 005 Appendix A catalog>)` and `make_recipe_tool(<spec 015 test book>)`):**
- EC-5: "How much lemon concentrate do I need for 4 gallons of lemonade?", router reply `T`, tool-step call `scale_recipe {"recipe": "lemonade", "gallons": 4}` → `bind_tools` is called once, with exactly the recipe tool; the tool step's first message is a `SystemMessage` equal to `RECIPE_TOOL_PROMPT` and its second is the part's text; the trace has one tool stage with one call named `scale_recipe` whose result contains "28 oz".
- EC-6: "How many cambros for 10 gallons of iced tea?", reply `T` → `bind_tools` with exactly the beverage tool; first tool-step message `TOOL_PROMPT`.
- EC-7: "How many cambros for 6 gallons of lemonade; how much concentrate for 6 gallons of lemonade?", reply `TT` → two TOOL parts, in order `calculate_bev_item` then `scale_recipe`; each part's tool step is bound with only its own tool and uses its own prompt; two tool stages, in order.
- EC-8: in a `scale_recipe` step the model calls `calculate_bev_item` → that call's result is `"error: unknown tool calculate_bev_item"`, no raise.
- EC-9: for "How do I make lemonade for 90 guests?" the model first calls `scale_recipe {"recipe": "lemonade", "gallons": 4}` → recorded with `refused=True` and a result starting with `REJECTED_PREFIX`; the model is asked again; its second call `{"recipe": "lemonade", "guests": 90}` gives the stage's `tool_text` (contains "28 oz" and "90 guests").
- EC-10: `chat.CHAT_TOOLS` monkeypatched to only the beverage tool, and a part routed to `scale_recipe` → no `bind_tools` call for it, its stage has no calls and `tool_text=None`, and (with `generate=True`) the final messages include the documents.
- EC-11: a TOOL part with `tool=None` (`chat.route_fast` monkeypatched to return it) runs `calculate_bev_item` as before.
- EC-12: unpatched `chat.CHAT_TOOLS` contains `BEV_TOOL` and `RECIPE_TOOL`; `TOOL_PROMPTS` has exactly the two keys of §3.1; `RECIPE_TOOL_PROMPT` contains `scale_recipe` and at least two `{`.

**Scorer (unit, no model):** the eval's scoring of §4.2 is itself unit-tested on hand-made traces:
- EC-13: a trace matching a case passes; one whose TOOL part has the other tool fails with stage `router`; one with no TOOL part fails with stage `router`; one whose stage has no calls fails with stage `no call`; one whose accepted call gives other gallons fails with stage `arguments`; one with a refused first call and a right second call passes as `corrected`; one whose only call was refused fails with stage `arguments`.

## 6. Acceptance criteria
- **AC-1 (router):** EC-1 to EC-4.
- **AC-2 (flow):** EC-5 to EC-12.
- **AC-3 (scorer):** EC-13.
- **AC-4 (existing tests updated, nothing weakened):** the tester of this spec updates only these, and only as stated:
  - spec 013 unit tests (`tests/router/test_registry.py`, `tests/router/test_route_fast.py`): recipe questions with an amount ("How do I make 3 gallons of lemonade?", "How much concentrate for 6 gallons of lemonade?") now expect `scale_recipe` / TOOL; `scale_recipe` is now `available=True`; the "an unavailable entry's purpose is not in the prompt" test uses a custom registry.
  - spec 013 router eval (`tests/router/test_fast_router_eval.py`): K27, K28 and K29 now expect TOOL with tool `scale_recipe`. Threshold unchanged (28 of 31).
  - (revision 1) `tests/bev_tools/test_answer_loop.py::test_constants_match_contract`: `chat.CHAT_TOOLS == (BEV_TOOL, RECIPE_TOOL)`.
  - (revision 1) `tests/router/test_answer_flow.py::test_ec7_two_tool_parts`: two TOOL parts now give **one `bind_tools` call per TOOL part** (two calls), each with only that part's tool (§4.1). Its other assertions are unchanged.
  - (revision 1) spec 011 flow eval case E2 (`tests/flow/conftest.py`, "How do I make 5 gallons of lemonade?"): expected kind becomes TOOL (tool `scale_recipe`) instead of DOCS. Its other expectations are unchanged.
  - spec 005 tool-choice eval (`tests/bev_tools/test_tool_choice_eval.py`): T3 now expects "scale_recipe: Lemonade 5 gal" (a `scale_recipe` call whose args give `ok`, Lemonade, 5 gallons; no `calculate_bev_item` call). Its answer reference (35 oz) is unchanged.
- **AC-5 (regression):** every other unit test passes unchanged. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's uncommitted `DIDNT_CATCH` change).
- **AC-6 (tool-calling eval, beverage):** at least 18 of B1 to B20 pass (§4.2).
- **AC-7 (tool-calling eval, recipe):** at least 18 of R1 to R20 pass (§4.2).
- **AC-8 (eval report):** the eval prints one line per case: id, pass/fail, stage (`router`, `no call`, `arguments` or `corrected`), the route's parts with tools, and every call's name and args. It ends with the pass counts per tool and the first-call pass counts.

### Cases B: `calculate_bev_item`
History is none unless listed. Amounts are gallons. "from guests" means `from_guests=True`.

| id | question | expected call |
|---|---|---|
| B1 | How many cambros for 8 gallons of peach tea? | cambros: Peach tea 8; no guests |
| B2 | Which cambros should hold 4 gallons of decaf? | cambros: Decaf 4; no guests |
| B3 | How many cambros for 6 gallons of coffee and 2 gallons of hot water? | cambros: Coffee 6, Hot water 2; no guests |
| B4 | I have 3 gallons each of iced tea and lemonade, how many cambros? | cambros: Iced tea 3, Lemonade 3; no guests |
| B5 | How many cambros for brewed hot cider for 60 guests? | cambros: Brewed hot cider 2 from guests; guests 60 |
| B6 | What containers do I need for eleven gallons of orange juice? | cambros: Orange juice 11; no guests |
| B7 | How many gallons of iced tea for 110 guests? | gallons: any of: (Iced tea 4 from guests), (no drinks); guests 110 |
| B8 | How many gallons should we make for 65 people? | gallons: no drinks; guests 65 |
| B9 | How many cups for iced water and orange juice for 45 guests? | cups: Iced water, Orange juice (any amount); guests 45 |
| B10 | How many hot cups for 90 guests? | cups: any of: (no drinks), (only hot drinks, any amount); guests 90 |
| B11 | Cups for the ginger honeycrisp apple cider, 35 guests? | cups: Ginger Honeycrisp apple cider (any amount); guests 35 |
| B12 | Do I need stir sticks for decaf? | supplies: Decaf (checked on the `drinks` argument, §4.2); result contains "Stir sticks"; no guests |
| B13 | Should I bring tea packets for hot water? | supplies: Hot water (checked on the `drinks` argument, §4.2); result contains "Tea packets"; no guests |
| B14 | Do we need lemons for the iced tea for 80 guests? | supplies: Iced tea 3 from guests; guests 80 |
| B15 | What do I need to bring for peach tea for 30 guests? | everything: Peach tea 1 from guests; guests 30 |
| B16 | What goes on the pull sheet for 5 gallons of decaf? | everything: Decaf 5; no guests |
| B17 | The coffee, decaf, tea, iced water & juice package for 120 guests, what do I bring? | everything: Coffee, Decaf, Hot water, Iced water, Orange juice, each 5 from guests; guests 120 |
| B18 | How many cambros for 3 gallons of hot chocolate? | cambros, status `not_on_menu`, `not_on_menu` = ("hot chocolate", any case); no guests |
| B19 | How many cambros for the coffee? | cambros, status `need_info`: Coffee (no amount); no gallons; no guests |
| B20 | history: user "How many cambros do I need for decaf and iced tea?" / assistant "How many gallons of each drink, or how many guests?"; question "45 guests." | cambros: Decaf 2 from guests, Iced tea 2 from guests; guests 45 |

### Cases R: `scale_recipe`
The recipe is Lemonade unless listed.

| id | question | expected call(s) |
|---|---|---|
| R1 | How much lemon concentrate for 3 gallons of lemonade? | gallons 3 |
| R2 | How many oz of concentrate do I need for 10 gallons of lemonade? | gallons 10 |
| R3 | How do I make 5 gallons of lemonade? | gallons 5 |
| R4 | How do I make lemonade for 60 guests? | gallons 2 from guests; guests 60 |
| R5 | How much concentrate for lemonade for 150 guests? | gallons 6 from guests; guests 150 |
| R6 | How many ounces of lemon concentrate go into 1.5 gallons of lemonade? | gallons 1.5 |
| R7 | What's the lemonade recipe for 4 gallons? | gallons 4 |
| R8 | How do we make twelve gallons of lemonade? | gallons 12 |
| R9 | Ingredients for 7 gallons of fresh lemonade? | gallons 7 |
| R10 | How can I make lemonade for 35 people? | gallons 1 from guests; guests 35 |
| R11 | How much concentrate do I need to make 2.5 gallons of lemonade? | gallons 2.5 |
| R12 | Lemonade for 200 guests, how much concentrate? | gallons 8 from guests; guests 200 |
| R13 | How many oz of concentrate for a 20 gallon batch of lemonade? | gallons 20 |
| R14 | Recipe for 8 gallons of lemonade please | gallons 8 |
| R15 | How do I make 3 gallons of iced tea? | status `no_recipe` (recipe as given: "iced tea", any case) |
| R16 | history: user "How do I make lemonade?" / assistant "Pour 7 oz of lemon concentrate into a clean 1-gallon container, add water to 1 gallon and stir."; question "And for 7 gallons?" | gallons 7 |
| R17 | history: user "How much lemon concentrate do I need for 4 gallons of lemonade?" / assistant "28 oz of lemon concentrate."; question "What about 9 gallons?" | gallons 9 (not 4) |
| R18 | Where are the concentrates kept, and how many ounces of lemon concentrate go into 6 gallons of lemonade? | one TOOL part: gallons 6 (the DOCS part is ignored) |
| R19 | How much lemon concentrate for 4 gallons of lemonade; which cambros hold 4 gallons of lemonade? | two TOOL parts, in order: `scale_recipe` gallons 4; `calculate_bev_item` cambros: Lemonade 4, no guests |
| R20 | How do I make 6 gallons of lemonade for 140 guests? | gallons 6, `from_guests=False` (the user's gallons win; `guests` may be passed or left out) |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-5 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The eval (AC-6 to AC-8) is marked `eval` and skips, not fails, when Ollama is not running, the store is empty, or `data/recipes/recipes.json` is missing. It warms the model up with one call first. No test writes to `data/` or `.chroma/`. | unit (marker review); run output |
| NFR-4 | `RECIPE_TOOL_PROMPT`, `TOOL_PROMPT`, the classifier prompt and the tool descriptions contain no question from B1 to B20 or R1 to R20 (or earlier specs' evals) word for word, and no example uses Lemonade with an amount used in R1 to R20. | manual (code review) |
| NFR-5 | Tool selection in the tool step is driven by `part.tool` and the `TOOL_PROMPTS` table: adding a third tool needs a new package, a registry row, a `CHAT_TOOLS` entry and a `TOOL_PROMPTS` entry, and no change to the flow's logic. | manual (code review) |
| NFR-6 | The eval's scorer (§4.2) is a pure function on a `TurnTrace` and the case's expectation, so it is unit-tested (EC-13) without a model. | unit (EC-13) |

Tests go in `tests/tool_calling/` (no `__init__.py`): `conftest.py` (the catalogs and test book in `tmp_path`, the scripted fake model, the B and R cases, the scorer), `test_router_recipe.py` (AC-1), `test_tool_step_wiring.py` (AC-2), `test_scorer.py` (AC-3), `test_tool_calling_eval.py` (AC-6 to AC-8). AC-4 edits the listed existing files.

## Revision history
- **Revision 1 (2026-11-13)**, after the first run. The eval met both thresholds (beverage 18 of 20, recipe 20 of 20); 3 unit tests failed besides the accepted voice failure.
  - **Code to change (§4.1):** the argument check ran on calls to *any* tool among the step's tools, so spec 009's `test_other_tool_names_not_checked` failed. Only calls to the part's tool are checked.
  - **Scoring (§4.2, B12, B13):** the model's calls were right (`supplies`, `["decaf"]` / `["hot water"]`) but the scorer looked for the drink in the calculator's resolved drinks, which is empty when no amount and no guests are given. Now the drink is checked on the `drinks` argument and the result must contain the asked-about supply.
  - **Tests to change:** the three revision-1 items in AC-4; the scorer and B12/B13 expectations; the EC-3 test must check `T` and `D` as whole words (a bare `"T" in prompt` passes for any text); the EC-11 test patches `chat.route_fast`. No other assertion is weakened.
