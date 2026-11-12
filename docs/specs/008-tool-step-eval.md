# Spec 008: Tool-step eval (does the model call the tool, with the right arguments?)

- **Status:** approved
- **Date:** 2026-11-11

## 1. Goal
Spec 005's tool-choice eval runs the whole flow (router, tool step, final call), so when a case fails we cannot tell which stage was wrong. This spec adds an eval of the **tool step alone**: each case is a question a router would label TOOL, handed straight to the tool step with the real model. It measures two things, and nothing else:
1. **Does the model call `calculate_bev_item` at all** when it is given a TOOL question?
2. **Are the arguments right** (`item`, `drinks`, `gallons`, `guests`)? Checked by running the calculator on the call's arguments and comparing the result with what the question needs.

The result is a baseline on `qwen2.5:7b` (temperature 0). **It is expected that some cases fail on the current code.** A failing case is a finding, not a defect of this spec: the findings decide what the next spec (changes to the tool step) must fix. This spec changes no source code.

## 2. Out of scope
- Any change to `scripts/chat.py`, `src/blc/` or `data/`. No developer round: only tests are added.
- The router (spec 006/007), retrieval, the final call and the answer text. The eval never calls `route_question`, `retrieve` or `answer_with_tools`.
- Setting a pass threshold or fixing failures: that is the next spec, after the first run.
- Changing `CHAT_MODEL`; the eval uses whatever `chat.CHAT_MODEL` is (now `qwen2.5:7b`).

## 3. Interface contract
Names that already exist in `scripts/chat.py` (spec 006 flow) and are used by the tests; nothing is added or changed:

```python
# scripts/chat.py  (import with `from chat import ...`)
CHAT_MODEL: str
TOOL_LIMIT_REPLY: str

@dataclass(frozen=True)
class ToolCallRecord:
    name: str                  # tool name the model asked for
    args: dict[str, object]    # arguments exactly as the model sent them
    result: str                # text returned to the model

@dataclass(frozen=True)
class StepOutcome:
    records: tuple[ToolCallRecord, ...]   # every call made, in order; () if none
    tool_text: str | None                 # None: the model made no call (the part would fall back to DOCS)
    retried: bool                         # True if the model was asked again because it made no call

def run_tool_step(
    bound: "Runnable",                    # llm.bind_tools(list(tools))
    tools: "Sequence[BaseTool]",
    part: "RoutedPart",                   # RoutedPart("TOOL", question) from blc.router
) -> StepOutcome:
    """Runs the tool step for one TOOL part. Prints nothing."""
```
```python
# src/blc/tools/bev_tools  (from blc.tools.bev_tools import ...)
BEV_TOOL: BaseTool            # the real tool (reads the real menu and rules under data/pull_sheet/)
BEV_TOOL_NAME: str            # "calculate_bev_item"
def run_bev_tool(args: Mapping[str, object]) -> BevResult
# BevResult.status: "ok" | "need_info" | "not_on_menu" | "invalid"
# BevResult.drinks: tuple of items with .drink (display name, str), .amount (number or None),
#                   .from_guests (bool); () unless status is "ok"; also () for an "ok" result
#                   whose drinks have no amount (supplies without guests)
# BevResult.text: str   (the tool's plain-English answer; names every resolved drink)
```
```python
# src/blc/router  (from blc.router import RoutedPart)
RoutedPart(route="TOOL", text=<question>)
```
How the tests set up one case: `llm = ChatOllama(model=CHAT_MODEL, temperature=0)`, `bound = llm.bind_tools([BEV_TOOL])`, `outcome = run_tool_step(bound, (BEV_TOOL,), RoutedPart("TOOL", case_text))`.

Tests go in `tests/tool_step/` (new, no `__init__.py`): `conftest.py` (the Ollama skip, the model, the cases) and `test_tool_step_eval.py`.

## 4. Inputs and outputs

### 4.1 What is checked for each case
Let `outcome` be the result of `run_tool_step` for the case's question, and `status`, `drinks` come from `run_bev_tool(call.args)` for each call.
1. **Called:** `outcome.records` is not empty and `outcome.tool_text` is not `None`. (Unlike spec 005, a TOOL question that gets no call is a failure here, for every case.)
2. **Right tool:** every call has `name == BEV_TOOL_NAME`.
3. **Right item:** every call's `args["item"]` equals the case's **item**.
4. **Right result:** for **every** call, `run_bev_tool(call.args)` gives the case's **status** (default `ok`) and, when the status is `ok`, the case's **drinks** (display names, compared as resolved by the calculator; amounts compare as numbers; `from_guests` where listed), and the case's **guests** (the call's `guests`, read as an integer, is the listed number; "no guests" means missing, null or 0).
5. **Not stuck:** `outcome.tool_text != TOOL_LIMIT_REPLY`.

**Drinks without an amount (revision 1).** For a case whose question names a drink but gives no amount (S16, S19, S25), the calculator's structured `BevResult.drinks` is empty, so it is not used: each listed drink's display name must instead appear in the result's text (`BevResult.text`, ignoring case). All other cases compare `BevResult.drinks` as above.

**No invented amounts (revision 1).** For a case whose question contains no number (S3, S6, S16, S19, S25), every call must pass neither `guests` nor `gallons` (missing, null, 0 or an empty list all count as "not given"). This catches a model that invents an amount even when the calculator would still answer `ok`.

Every call is checked, so a call that is wrong and then corrected on a retry still **fails** the case: the eval measures what the model gets right on the first try. A question that the model splits into several calls fails a multi-drink case, because each call must give the case's full drinks list; that is deliberate.

A failing case's message must show: the case id, the question, every call's `name` and `args`, the status and resolved drinks the calculator gave for each, `outcome.retried`, and which of the five checks failed.

### 4.2 Cases
Notation as spec 005 §6: `Lemonade 7` means 7 gallons; `3 from guests` means the amount came from the guest count; `any of` means any one option is fine; `no guests` means not given.

| id | question (the TOOL part) | item | status | drinks | guests |
|---|---|---|---|---|---|
| S1 | How many cambros do I need to bring for 7 gallons of lemonade? | cambros | ok | Lemonade 7 | no guests |
| S2 | How many gallons of coffee do I need for 75 people? | gallons | ok | any of: (Coffee 3 from guests), (no drinks) | 75 |
| S3 | How many cambros do I need for coffee and lemonade? | cambros | need_info | (not checked) | no guests |
| S4 | How many cambros for 5 gallons of coffee and 5 gallons of lemonade? | cambros | ok | Coffee 5, Lemonade 5 | no guests |
| S5 | I need 5 gallons of coffee and lemonade. How many cambros? | cambros | ok | Coffee 5, Lemonade 5 | no guests |
| S6 | How many cups do I need for coffee? | cups | need_info | (not checked) | no guests |
| S7 | 5 gallons of coffee and 3 gallons of lemonade, how many cambros? | cambros | ok | Coffee 5, Lemonade 3 | no guests |
| S8 | Coffee and lemonade for 70 guests, how many cups? | cups | ok | Coffee, Lemonade (any amount) | 70 |
| S9 | How many cambros for lemonade for 70 guests? | cambros | ok | Lemonade 3 from guests | 70 |
| S10 | How many cambros for 4 gallons of hot chocolate? | cambros | not_on_menu | (not checked) | no guests |
| S11 | How many cambros for 7 gallons of fresh-brewed coffee? | cambros | ok | Coffee 7 | no guests |
| S12 | We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros? | cambros | ok | Coffee, Decaf, Hot water, Iced water, Orange juice, each 3 from guests | 70 |
| S13 | What do I put 7 gallons of lemonade in? | cambros | ok | Lemonade 7 | no guests |
| S14 | Seven gallons of lemonade, which containers do I bring? | cambros | ok | Lemonade 7 | no guests |
| S15 | What do I need to bring for coffee for 50 guests? | everything | ok | Coffee 2 from guests | 50 |
| S16 | Do I need sugar for coffee? | supplies | ok | Coffee | no guests |
| S17 | How many gallons do I make for 25 people? | gallons | ok | no drinks | 25 |
| S18 | How many hot cups do I need for 40 guests? | cups | ok | any of: (no drinks), (only hot drinks: Coffee, Decaf, Hot water, Brewed hot cider, Ginger Honeycrisp apple cider) | 40 |
| S19 | How many napkins should I grab for the iced tea station? | supplies | ok | Iced tea | no guests |
| S20 | Which jugs do I fill with 9 gallons of iced water? | cambros | ok | Iced water 9 | no guests |
| S21 | Brewed hot cider for 100 people, what goes on the pull sheet? | everything | ok | Brewed hot cider 4 from guests | 100 |
| S22 | Do I bring lemon tongs for hot water for 30 guests? | supplies | ok | Hot water 1 from guests | 30 |
| S23 | What should I pack for orange juice for 40 guests? | everything | ok | Orange juice 2 from guests | 40 |
| S24 | How many cold cups for 55 guests? | cups | ok | any of: (no drinks), (only cold drinks: Iced water, Iced tea, Orange juice, Lemonade, Peach tea) | 55 |
| S25 | Do I need creamer for decaf? | supplies | ok | Decaf | no guests |
| S26 | How many cambros do I need for 3 gallons of peach tea and 6 gallons of orange juice? | cambros | ok | Peach tea 3, Orange juice 6 | no guests |
| S27 | How many gallons of lemonade do I make for 90 people? | gallons | ok | any of: (Lemonade 4 from guests), (no drinks) | 90 |
| S28 | How many cups for 20 guests of coffee? | cups | ok | Coffee (any amount) | 20 |

S1 to S21 are the TOOL parts of spec 005's T cases (T2, T4, T5 to T14, T18 to T26) with T6's follow-up already rewritten as a router would. S22 to S28 are new and aim at known weak spots: a supply with guests, "pack" and "pull sheet" wording, cold cups, a different amount per drink, an amount in guests with a named drink.

## 5. Edge cases
- EC-1: **Skip, not fail:** if Ollama is not running, or `CHAT_MODEL` is not installed, every case is skipped.
- EC-2: **No data written:** the eval reads the real menu and rules under `data/pull_sheet/`, writes nothing, and does not read or need `.chroma/`.
- EC-3: **A `need_info` case (S3, S6)** passes only if a call was made and the calculator asks for the missing information; a model that invents guests or gallons so that the status becomes `ok` fails check 4.
- EC-4: **A `not_on_menu` case (S10)** passes only if a call was made whose result is `not_on_menu`; the model answering without a call fails check 1.
- EC-5: **"No guests" cases** fail if the call passes any guest count, even when the status is still `ok` (an invented amount).
- EC-6: **A retried call:** if the first reply had no call and the retry made a correct call, `retried` is `True`, the case can pass, and the failure message of other cases shows `retried`.
- EC-7: **Several calls for one question:** each call is checked on its own against checks 2 to 4, so identical correct calls pass, but splitting a multi-drink question into one call per drink fails (S4, S5, S7, S26, S8).
- EC-8 (revision 1): **No-amount cases (S3, S6, S16, S19, S25):** a call that passes `guests` or `gallons` fails, even when the status is `ok` and the drinks are right.
- EC-9 (revision 1): **Names-only drinks (S16, S19, S25):** a call with the right item and drink and no amounts passes; the drink is looked for in the result text, not in `BevResult.drinks`.

## 6. Acceptance criteria
- **AC-1 (one test per case):** each of S1 to S28 is its own test, so a run lists each case as passed, failed or skipped.
- **AC-2 (checks):** each case applies checks 1 to 5 of §4.1 with the real model (`ChatOllama(model=CHAT_MODEL, temperature=0)`), the real tool and the real menu and rules.
- **AC-3 (readable failures):** a failing case's message has everything listed at the end of §4.1.
- **AC-4 (isolation):** the tests call only `run_tool_step` (with `bind_tools([BEV_TOOL])`) and `run_bev_tool` on the real model, and do not call `route_question`, `retrieve` or `answer_with_tools`.
- **AC-5 (skip):** EC-1.
- **AC-6 (revision 1):** EC-8 and EC-9 hold in the checks.
- **Pass threshold: none.** This spec is a baseline run; failing cases are reported to the planner. The next spec sets the threshold once the first results are known.

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies and no change outside `tests/tool_step/`. | manual (review of the diff) |
| NFR-2 | All tests are marked `eval` and skip, not fail, when Ollama or the model is missing; no test writes to `.chroma/` or `data/`. | unit (marker and fixture review by test-evaluator) |
| NFR-3 | The cases' expected values come from the spec's table (§4.2) and the calculator's own result (`run_bev_tool`), not from numbers copied out of the pull sheet rules. | manual (review by test-evaluator) |
| NFR-4 | A full run takes under about 5 minutes. | manual (timed by the planner) |
| NFR-5 | Each test file stays about 400 lines or fewer; shared helpers and the case table live in `conftest.py`. | manual (review) |
