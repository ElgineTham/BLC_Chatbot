# Spec 009: Tool step argument check

- **Status:** approved
- **Date:** 2026-11-11

## 1. Goal
Spec 008's baseline on `qwen2.5:7b` (24 of 28) showed the tool step always calls the tool, but sometimes with **wrong arguments that the calculator still accepts**: it invented a guest count (`guests: 50` for "How many cups do I need for coffee?", and for "How many napkins should I grab for the iced tea station?") and picked the wrong item (`supplies` for "What do I need to bring for coffee for 50 guests?", which asks for `everything`). The calculator cannot tell, so a made-up number reaches the user. This spec adds two things to the tool step:
1. an **argument check** in code that compares a call's arguments with the question and refuses the call, with a one-line reason the model can act on, before the calculator runs;
2. a better **tool prompt** (minimal-pair examples) and temperature 0 for chat, so the model gets it right the first time more often.

The check reuses the retry loop that already exists (a refused call is an "invalid" result: the model is asked again, up to `MAX_TOOL_ROUNDS`).

## 2. Out of scope
- The router and the router's rewriting of questions (a diagnostic found it changes meaning: it splits "coffee and lemonade" into two parts, drops a package name, and rewrites "what goes on the pull sheet" as a gallons question). That is spec 010.
- Retrieval, the final call, `answer_turn`, the calculator and `src/blc/pull_sheet/`.
- Structured-output (JSON schema) tool arguments: spec 008 showed no case where the model failed to call the tool.
- Checking drink names (the calculator already resolves names, and a wrong name is not what failed).

## 3. Interface contract

### 3.1 The check: `src/blc/tool_step/` (new feature package)
Importable as `from blc.tool_step import REJECTED_PREFIX, check_arguments`.

```python
from collections.abc import Mapping

REJECTED_PREFIX: str = "invalid (check): "

def check_arguments(args: Mapping[str, object], question: str) -> str | None:
    """None if the arguments agree with the question. Otherwise one sentence that starts
    with REJECTED_PREFIX and says what to change. Never raises (for any args or question).
    No I/O. Prints nothing."""
```

### 3.2 The tool step: `scripts/chat.py`
`run_tool_step(bound, tools, part)`, `StepOutcome`, `ToolCallRecord`, `TOOL_LIMIT_REPLY`, `MAX_TOOL_ROUNDS` keep their signatures and meaning (spec 006/008). New or changed:

```python
CHAT_TEMPERATURE: float = 0     # NEW: the temperature main() creates the chat model with (was 0.1)
```
**Behaviour added to `run_tool_step`:** for every requested call whose `name == BEV_TOOL_NAME`, `check_arguments(call.args, part.text)` is applied **before** the tool runs. If it returns a reason, the tool is **not invoked** for that call; the call is recorded as `ToolCallRecord(name, args, result=reason)` and the reason goes back to the model as that call's `ToolMessage`, as any "invalid" result does (spec 006 §4.3: a round with an "invalid" result is asked again, at most `MAX_TOOL_ROUNDS` rounds, then `tool_text == TOOL_LIMIT_REPLY`). Calls to other names are handled as before. The check never changes `retried`. Within a round, `records` and the tool messages follow the order of the model's calls (revision 1).

`TOOL_PROMPT` stays a module constant of `scripts/chat.py` (wording: Appendix A).

## 4. Inputs and outputs

### 4.1 What `check_arguments` refuses
Only `guests`, `gallons` and `item` are looked at; other keys and wrong types are ignored (the calculator reports those).

**A. Numbers must come from the question.** Every number in `guests` and every number in `gallons` (a single number or a list) must appear in the question. Never work-out amounts: "70 guests" does not allow `gallons: [3]`.
- A number appears when the question contains it as digits (`50`, `2.5`, `1,000` counts as 1000), or spelled out in words from "zero" to "one hundred" (`seven`, `twelve`, `twenty-five`, `one hundred`), ignoring case.
- **Whole matches only (revision 1):** a spelled number counts only as a whole word (`seven` is not found in "seventeen", `ten` is not found in "often"), and digits count only as a whole run of digits (`50` is found in "50-guest" and "$50", but not in "500" or "150"). "twenty five" (with a space) counts like "twenty-five".
- A number given as text (`"50"`) or as a float with no fraction (`50.0`) counts as that number.
- The number **1** is always accepted.
- A value that is not a number (text that is not numeric, `None`, a list inside a list, a missing key) is ignored by this check.
- The reason names the argument (`guests` or `gallons`) and the refused number as written in `args`, and says to use only amounts the user gave and to leave the argument out when the user gave none.

**B. The item `everything`.** If the only pull sheet item in the question is `everything` (as `blc.router.pull_sheet_items_in(question) == ("everything",)`), then `args["item"]` must be `"everything"` (ignoring case and surrounding spaces). A missing item, a non-text item or any other text is refused (revision 1). If the question mentions any other item of `PULL_SHEET_ITEMS` (cambros, cups, gallons, a supply and so on) this rule does not apply. The reason contains the words `item` and `everything`.

If several things are wrong the reason may mention any or all of them; it is still one string starting with `REJECTED_PREFIX`.

### 4.2 Examples (question → args → result)
| Question | Args | Result |
|---|---|---|
| How many cups do I need for the mocha? | `{"item":"cups","drinks":["coffee"],"guests":50}` | refused: `guests`, `50` |
| How many cups do I need for the mocha? | `{"item":"cups","drinks":["coffee"]}` | `None` |
| What do I need to bring for decaf for 85 guests? | `{"item":"supplies","drinks":["decaf"],"guests":85}` | refused: `item`, `everything` |
| What do I need to bring for decaf for 85 guests? | `{"item":"everything","drinks":["decaf"],"guests":85}` | `None` |
| Do I bring sugar for the chai station? | `{"item":"supplies","drinks":["hot water"]}` | `None` (sugar is another item, so rule B does not apply) |
| Which cambros for 12 gallons of decaf? | `{"item":"cambros","drinks":["decaf"],"gallons":[12]}` | `None` |
| Which cambros for 12 gallons of decaf? | `{"item":"cambros","drinks":["decaf"],"gallons":[10,2]}` | refused: `gallons`, `10` |
| Decaf for 70 guests, which cambros? | `{"item":"cambros","drinks":["decaf"],"gallons":[3],"guests":70}` | refused: `gallons`, `3` |
| Seven gallons of decaf, which containers? | `{"item":"cambros","drinks":["decaf"],"gallons":[7]}` | `None` |
| What do I put 8 gallons of decaf in? | `{"item":"cambros","drinks":["decaf"],"gallons":[8]}` | `None` (gallons is another item, so rule B does not apply) |

## 5. Edge cases
**`check_arguments` (unit, no model):**
- EC-1: every row of §4.2.
- EC-2: digits, a decimal (`2.5`), a number with a comma (`1,000`), words (`seven`, `twelve`, `twenty-five`, `one hundred`) and different case (`SEVEN`) all count as appearing; a number only part of another number does not (`5` is not in "a 50 guest event"; `50` is not in "a 500 guest event").
- EC-3: `guests` as `"50"` or `50.0` is the number 50; `"seventy"`, `None`, `[]` and a missing key are ignored by this check.
- EC-4: a list in `gallons` is checked number by number (`[5, 3]` for "5 gallons of one and 3 of the other" gives `None`; `[5, 4]` is refused naming `4`).
- EC-5: the number 1 is accepted whatever the question says.
- EC-6: unusual input never raises: `args` with extra keys, wrong types (`item` a number, `drinks` a dict), an empty question, or a very long question.
- EC-7: the reason starts with `REJECTED_PREFIX` and never contains a newline.
- EC-8: rule B applies only when `everything` is the **only** item found in the question (a question with "pull sheet" and "cups" is not constrained).

**`run_tool_step` (unit, scripted fake model, tool from `make_bev_tool` on the spec 005 Appendix A catalog):**
- EC-9: the model's first call has an invented guest count, the second leaves it out → the tool runs once (for the second call); `records` has two entries, the first with `result` starting with `REJECTED_PREFIX`; `tool_text` is the second call's result; the second round's messages include the reason as the first call's tool message.
- EC-10: the model keeps sending refused calls → after `MAX_TOOL_ROUNDS` rounds `tool_text == TOOL_LIMIT_REPLY`, and the tool was never invoked.
- EC-11: a call with correct arguments is not refused and runs as before (`records` has one entry whose result is the tool's).
- EC-12: a refused call and a good call in the same round → the good one runs, the refused one does not; the round counts as failed (asked again).
- EC-13: `CHAT_TEMPERATURE == 0`.
- EC-14 (revision 1): **Whole matches:** with the question "Which cambros for 17 gallons of decaf?", `gallons: [7]` is refused and `[17]` is not; with "often 10 guests", `guests: 10` is accepted; with "150 guests", `guests: 50` is refused; with "a 50-guest event", `guests: 50` is accepted; "seventeen" does not allow 7; "twenty five" allows 25.
- EC-15 (revision 1): **Round boundary:** the model sends `MAX_TOOL_ROUNDS - 1` rounds of refused calls and then a good call → the tool runs once, `tool_text` is its result (not `TOOL_LIMIT_REPLY`) and `records` has one entry per call made. With `MAX_TOOL_ROUNDS` rounds of refused calls the result is `TOOL_LIMIT_REPLY` (EC-10).

## 6. Acceptance criteria
- **AC-1 (check):** `check_arguments` gives the results in §4.2 and EC-2 to EC-8 and EC-14.
- **AC-2 (tool step):** EC-9 to EC-12 and EC-15.
- **AC-3 (temperature):** the unit test checks the constant (EC-13); that `main()` creates the chat model with it is verified by code review (the unit tests do not run `main()`). The tests and the eval build their model from `CHAT_TEMPERATURE`, not a typed number.
- **AC-4 (spec 006 regression):** spec 006 and 007 flow and router tests still pass.
- **AC-5 (tool-step eval, real model):** spec 008's eval, run on the new code, with these changes made to its tests by the tester of this spec: a record whose `result` starts with `REJECTED_PREFIX` is **not** checked as a call (checks 2 to 4 apply to the calls the tool actually ran, and check 1 and check 5 apply as before), and the failure message lists the refused calls with their reasons. **Pass threshold: all 28 cases S1 to S28.**
- **AC-6 (whole-flow tool choice):** spec 005's AC-10 table (T1 to T26) is **not** a gate here (the router rewrite, spec 010, still affects T6, T7, T14 and T26); the planner runs it only to report the count.

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-4 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The AC-5 eval is marked `eval` and skips, not fails, when Ollama is missing. | unit (marker review) |
| NFR-4 | `TOOL_PROMPT` contains no question from spec 008 §4.2, spec 005 §6 or spec 006 §6, and no example uses their drinks together with their amounts. | manual (code review) |
| NFR-5 | The argument check is separate from the loop: `check_arguments` takes data and returns data (no I/O, no model); `run_tool_step` only applies it. | manual (code review) |
| NFR-6 | The check adds no model call: a correct call costs the same as before; a refused call costs one more round. | manual (review) |
| NFR-7 | Files stay about 250 lines each, split by job. | manual (code review) |

Tests go in `tests/tool_step/` (shared with spec 008): `test_argument_check.py` (AC-1), `test_tool_step_check.py` (AC-2, AC-3), and the updated `test_tool_step_eval.py` and `conftest.py` (AC-5).

## Appendix A: Tool prompt guidance (for the developer; wording is not tested)
Keep the existing `TOOL_PROMPT` rules. Add:
- **One rule, stated first:** use only amounts that are written in the question. A guest count or gallons that is not in the question is left out, even if it would be a sensible number. Never use a number you worked out.
- **`everything` versus `supplies`:** `everything` is for "what do I bring / pack / what goes on the pull sheet" for a drink; `supplies` is only for a named supply (napkins, creamer, sugar, stir sticks, lemons, lemon tongs, tea packets).
- **Examples** (question → arguments). Use these only; they follow NFR-4.
```text
How many cups for the Ginger Honeycrisp apple cider?
{"item": "cups", "drinks": ["Ginger Honeycrisp apple cider"]}          (no number in the question: no guests)

What goes on the pull sheet for decaf for 85 guests?
{"item": "everything", "drinks": ["decaf"], "guests": 85}

What do I need to bring for iced water and hot water for 140 guests?
{"item": "everything", "drinks": ["iced water", "hot water"], "guests": 140}

Do I bring sugar for hot water for 35 guests?
{"item": "supplies", "drinks": ["hot water"], "guests": 35}

How many cambros for 10 gallons of orange juice and 2 gallons of decaf?
{"item": "cambros", "drinks": ["orange juice", "decaf"], "gallons": [10, 2]}

How many gallons for 130 people?
{"item": "gallons", "guests": 130}
```
