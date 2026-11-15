# Spec 023: Tool results go to the user word for word; the model answers only the documents part

- **Status:** approved (done: closed by the user; AC-11 test updates carried over)
- **Date:** 2026-11-15

## 1. Goal
Today every tool result goes through the answer model, which rewrites it. The 7B model drops words it shouldn't. For "How many cups for decaf, 40 guests" the tool says "Hot cups: 60 for 40 guests (40 guests plus 20 extras).", but the answer only says "60 cups". This spec stops the model from touching tool results:
- **TOOL path:** the reply is the tool texts themselves, sent to `on_token` as they are, with no model call.
- **DOCS path:** unchanged; the model answers from the documents.
- **BOTH path:** the reply is the tool texts first, word for word, then a blank line, then the model's streamed answer to the documents part only. The model never sees the tool texts.

Tool results with status `invalid` or `error` hold text meant for a machine, so the user sees a fixed friendly sentence instead.

## 2. Out of scope
- **The tools and their texts** (`blc.tools`): no change to any status, number or wording.
- **The planner, the argument check and retry (spec 021), the drink fill (spec 022) and `run`:** no change. Which calls are planned and run stays the same.
- **The old flow:** `run_turn`, `answer_turn`, the router, `scripts/trace_flow.py` and `scripts/voice_chat.py` (voice still uses the old flow).
- **`scripts/chat.py`:** it already prints whatever `on_token` receives, so it does not change.
- **Rewording tool texts for the user**, e.g. turning "Coffee: 3 gal." into a sentence. If a text reads badly, the fix belongs in the tool, in a later spec.
- **Scoring answers.** The existing evals keep their own pass rules.

## 3. Interface contract
Everything is in `src/blc/flow/` and importable with `from blc.flow import ...`. Only the items below are new or change meaning. `run_planned_turn`, `build_flow_graph`, `TurnOutcome` and every other public name keep their signatures and fields.

```python
TOOL_FAILED_REPLY = "I couldn't work that out. Try naming the drink and the number of guests or gallons."
REPLY_SEPARATOR = "\n\n"         # between two tool texts, and between the tool part and the documents part
FAILED_TOOL_STATUSES: tuple[str, ...] = ("invalid", "error")

FLOW_ANSWER_PROMPT: str          # the answer model's system prompt, now for the documents part only (AC-9)
```

- **Changed meaning:** `TurnOutcome.answered_by_model` is True exactly when the answer model was called this turn (§4).
- **How the model is used:** this does not change. The answer model is called at most once per turn, through `stream`. The first message is `SystemMessage(content=FLOW_ANSWER_PROMPT)`, the last is a `HumanMessage`, and no tools are bound.

## 4. Inputs and outputs
**The tool part** is every tool result in plan order, joined with `REPLY_SEPARATOR`. Only the text goes in. The status, tool name and arguments are never shown to the user; they stay in `TurnOutcome.tools`.
- a result whose status is not in `FAILED_TOOL_STATUSES` contributes its `text`, unchanged (`ok`, `need_info`, `not_on_menu`, `no_recipe`, or any other status);
- a result whose status is in `FAILED_TOOL_STATUSES` contributes `TOOL_FAILED_REPLY`. The sentence appears only once in the tool part, at the place of the first failed result, even when several results fail.

| Planned calls | Searches find chunks? | Reply | `on_token` receives | Model called? / `answered_by_model` |
|---|---|---|---|---|
| tools only (TOOL) | n/a | the tool part | the tool part, once | no / False |
| searches only (DOCS) | none | `NO_DOCS_REPLY` | it, once | no / False |
| searches only (DOCS) | at least one | the streamed answer (unchanged) | each streamed piece | yes / True |
| tools and searches (BOTH) | none | tool part + `REPLY_SEPARATOR` + `NO_DOCS_REPLY` | that whole text, once | no / False |
| tools and searches (BOTH) | at least one | tool part + `REPLY_SEPARATOR` + the streamed answer, outer whitespace stripped | first the tool part + `REPLY_SEPARATOR` as one piece, **before the model is called**; then each streamed piece | yes / True |

`TurnOutcome.reply` always has its outer whitespace stripped. The history gets the same reply.

**The model's input on BOTH** (last `HumanMessage`): it contains the stripped question, every planned search query, verbatim, and every document's `page_content` with its `metadata["source"]`. It does **not** contain any tool result's text, or `TOOL_FAILED_REPLY`. Non-empty history still appears verbatim, as before. The layout and wording are the developer's.

**The model's input on DOCS:** as before (spec 019 §4.4): the question, the documents with their sources, and the history.

## 5. Acceptance criteria
- **AC-1:** TOOL path: the reply is the tool part. `on_token` gets it once, the answer model's `stream` is never called and `answered_by_model` is False. Every character of an `ok` or `need_info` text is kept, e.g. "Hot cups: 60 for 40 guests (40 guests plus 20 extras)." stays exactly that.
- **AC-2:** Several tool results are joined in plan order with `REPLY_SEPARATOR`. A text's own inner newlines are kept.
- **AC-3:** Results with a status in `FAILED_TOOL_STATUSES` show `TOOL_FAILED_REPLY` in place of their text, at most once per reply. Their raw text never reaches `on_token` or `reply`. Other statuses (e.g. `not_on_menu`, `no_recipe`) show their text.
- **AC-4:** BOTH with chunks: the reply is the tool part, `REPLY_SEPARATOR`, then the stripped model answer. `on_token`'s first piece is the tool part + `REPLY_SEPARATOR`, and it arrives before `stream` is called. The model pieces follow in order, and `answered_by_model` is True.
- **AC-5:** BOTH with chunks: the answer model's messages contain no tool result text and no `TOOL_FAILED_REPLY`. The last message contains the question, each planned search query and each document's text with its source.
- **AC-6:** BOTH with no chunks: the reply is the tool part + `REPLY_SEPARATOR` + `NO_DOCS_REPLY`, sent to `on_token` once. There is no model call, and `answered_by_model` is False.
- **AC-7:** DOCS path behaves exactly as in spec 019: a streamed answer with chunks, `NO_DOCS_REPLY` without.
- **AC-8:** The constants equal the values in §3. The model is called at most once per turn, and the planner calls are unchanged (one, or two with a spec 021 retry).
- **AC-9** *(manual)*: `FLOW_ANSWER_PROMPT` is written for the documents part only. It drops the rules about tool results, still tells the model to answer only the part it is given and only from the documents, to cite only sources shown and to invent no numbers, and still contains "simple", "straightforward" and "grounded". The word checks are also unit tests.
- **AC-10** *(manual)*: Changes are limited to `src/blc/flow/` (mainly `reply.py` and `graph.py`, plus exports in `__init__.py`). There are no new dependencies, and files stay near 250 lines.
- **AC-11 (regression):** Existing unit tests in `tests/planned_flow/`, `tests/no_invented/` and `tests/drink_fill/` whose assertions encode spec 019's old reply rules are updated to the rules of §4, each still checking the behaviour it was written for. Those old rules are: the model is called on the TOOL path, tool text reaches the model's messages, and `need_info` texts are joined with `"\n"`. No other existing assertion changes. The only accepted failure in the full unit suite is `tests/test_voice_io.py::test_constants_match_contract`.
- **AC-12** *(manual, by the user)*: In `poetry run python scripts/chat.py`, "How many cups to bring for decaf, 40 guests" answers with the tool's "Hot cups: …" line word for word.

## 6. Test cases
Unit tests use the existing fakes: a scripted planner model, a fake answer model with `stream`, a fake store and fake tool runners. New tests go in `tests/tool_passthrough/` (no `__init__.py`): `conftest.py`, `test_tool.py`, `test_both.py` and `test_docs.py`.
Below, **H** stands for the exact text "Hot cups: 60 for 40 guests (40 guests plus 20 extras)."

### 6.1 TOOL
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TOOL-1 | one bev call; runner returns `ok`, H | reply is exactly H; `on_token` called once with it; `stream` never called; `answered_by_model` False | AC-1 |
| TOOL-2 | one call; `ok` text with inner newlines and a trailing newline | reply keeps the inner newlines, outer whitespace stripped | AC-1, AC-2 |
| TOOL-3 | bev `ok` "A." then recipe `ok` "B\nC." | reply `"A.\n\nB\nC."` | AC-2 |
| TOOL-4 | two `need_info` results "Which drink?" and "How many guests?" | reply `"Which drink?\n\nHow many guests?"`; no model call | AC-2, AC-11 |
| TOOL-5 | `ok` H plus `need_info` "Which drink?" | both texts, joined, plan order; no model call | AC-1, AC-2 |
| TOOL-6 | one result status `invalid`, text "invalid request: … Expected arguments: {…}" | reply == `TOOL_FAILED_REPLY`; "Expected arguments" in no `on_token` piece | AC-3 |
| TOOL-7 | runner raises `ValueError("bad")` (status `error`) | reply == `TOOL_FAILED_REPLY`; `tools[0]` still records `"error: bad"` | AC-3 |
| TOOL-8 | `ok` "A." then `invalid` then `error` | reply `"A.\n\n" + TOOL_FAILED_REPLY` (sentence once) | AC-3 |
| TOOL-9 | `not_on_menu` "mango tea is not on the beverage menu." / `no_recipe` text | shown verbatim | AC-3 |
| TOOL-10 | TOOL-1 with `on_token=None` | works; reply unchanged | AC-1 |
| TOOL-11 | constants | `TOOL_FAILED_REPLY`, `REPLY_SEPARATOR`, `FAILED_TOOL_STATUSES` equal §3 | AC-8 |

### 6.2 BOTH
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| BOTH-1 | search "where is the coffee" (2 chunks) + bev `ok` H; model streams "In the ", "pantry." | reply H + `"\n\nIn the pantry."`; `on_token` pieces H + `"\n\n"`, `"In the "`, `"pantry."`; `answered_by_model` True | AC-4 |
| BOTH-2 | BOTH-1, recording order of events | first `on_token` piece recorded before `stream` is called | AC-4 |
| BOTH-3 | BOTH-1's model messages | no message contains "Hot cups"; last message has the question, "where is the coffee" and both chunks with sources | AC-5 |
| BOTH-4 | search with chunks + `invalid` tool | reply starts with `TOOL_FAILED_REPLY + "\n\n"`; neither raw text nor `TOOL_FAILED_REPLY` in model messages | AC-3, AC-5 |
| BOTH-5 | two searches + one tool | last message contains both queries | AC-5 |
| BOTH-6 | search returns `[]` + bev `ok` H | reply H + `"\n\n"` + `NO_DOCS_REPLY`; one `on_token` call; no model call; `answered_by_model` False | AC-6 |
| BOTH-7 | model streams "  In the pantry.\n" | reply ends `"\n\nIn the pantry."`; `on_token` got the pieces as streamed | AC-4 |
| BOTH-8 | `need_info` tool + search with chunks | reply starts with the question text + `"\n\n"`; model called once | AC-4 |
| BOTH-9 | BOTH-1 with history | history contents in the model messages; `outcome.history` ends with the user question and the full reply | AC-4, AC-5 |
| BOTH-10 | any BOTH turn, with or without a spec 021 retry | `stream` called at most once; planner calls unchanged | AC-8 |

### 6.3 DOCS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DOCS-1 | one search, 2 chunks; model streams "A", "B" | reply "AB"; pieces "A", "B"; `answered_by_model` True; last message has question, chunks, sources | AC-7 |
| DOCS-2 | searches all return `[]`, no tools | `NO_DOCS_REPLY`, once; no model call | AC-7 |
| DOCS-3 | `FLOW_ANSWER_PROMPT` | first message of the answer call; contains "simple", "straightforward", "grounded" (any case) | AC-7, AC-9 |

## Closing note (2026-11-15)
Closed by the user after testing it themselves.
- **Results:** the 39 new tests in `tests/tool_passthrough/` pass, and the test-evaluator returned PASS. AC-1 to AC-8 pass on those tests.
  - The planner checked AC-9 (documents-only prompt) and AC-10 (changes only in `src/blc/flow/`) by reading the code.
  - The user checked AC-12: "How many cups to bring for decaf, 40 guests" answered "Hot cups: 60 for 40 guests (40 guests plus 20 extras)." word for word.
- **Not done (AC-11), carried to the next spec:** 13 old tests still assert spec 019's reply rules, and fail until they are updated to §4:
  - `tests/planned_flow/test_contract.py`: `test_history_reaches_planner_and_answer_messages`, `test_outcome_history_extends_input_without_mutating_it`, `test_no_history_gives_two_items` (2 params);
  - `tests/planned_flow/test_run.py`: `test_tool_turn_message_has_tool_text_and_no_source`, `test_tool_turn_outcome_fields`, `test_tool_status_and_text_are_recorded_and_shown_whatever_the_status`, `test_both_turn_runs_store_and_recipe_runner_and_shows_both`, `test_runner_that_raises_gives_error_result_and_the_turn_finishes`, `test_missing_runner_gives_no_runner_error_and_the_turn_finishes`, `test_a_failing_tool_does_not_hide_the_documents`;
  - `tests/no_invented/test_retry.py`: `test_ec21_at_most_two_planner_calls_one_answer_call`, `test_ec21_exactly_one_planner_call_without_retry`.
- **Found during the run, from spec 022's uncommitted work (not spec 023):**
  - `tests/no_invented/test_golden_eval.py` and `test_fill_report.py` fail to import `golden_fill_helpers`;
  - `tests/test_voice_io_answer_turn.py::test_chat_main_survives_a_catalog_load_failure[rulefile]` builds `RuleFileError` with too few arguments.
- **Timing (planner's scratch run):** with the model already loaded, a TOOL turn takes about 2.1–2.4 s, nearly all of it the planner call. The first question of a fresh session takes about 12 s, because it loads the model.
