# Spec 019: Planned flow in LangGraph: plan, run the calls, stream the answer

- **Status:** approved (revision 1, done: closed by the user; tester items carried to spec 020)
- **Date:** 2026-11-14 (revision 1: 2026-11-14)

## 1. Goal
Spec 018's planner decides which calls answer a question but runs nothing. This spec makes a full turn out of it, as a **LangGraph graph with three nodes**:
1. **plan:** `plan_question` from spec 018, unchanged.
2. **run:** executes the planned calls. Each `search_documents` query is embedded and searched in Chroma; each `calculate_bev_item` / `scale_recipe` call runs on the real tool.
3. **reply:** sends the question, history, tool results and retrieved documents to the model, which **streams** the answer token by token.

When a tool only asks the user a question and there are no documents, the reply is that question itself, with no answer call. `scripts/chat.py`'s interactive loop switches to this flow and prints the answer as it streams. Answers are not scored. The eval runs spec 018's 30 cases end to end and **writes a log** for the user to read.

## 2. Out of scope
- **Argument checking and retries** (spec 009's `check_arguments`, re-asking the planner). Planned calls run exactly as planned. Bad arguments give whatever the tool returns, usually status `invalid`.
- **Judging answers:** no thresholds and no judge model. The user reads the log.
- **The old flow:** `run_turn`, `answer_turn`, `run_stages`, the router, `ANSWER_PROMPT`, `scripts/trace_flow.py` and `scripts/voice_chat.py` stay as they are and keep using the old flow. Moving them over and deleting the old flow is a later spec. Because the old flow still uses the real `calculate_bev_item`, **`BEV_TOOL` is not trimmed in this spec**, and spec 018's `PLANNER_BEV_TOOL` stays.
- **Any change to `blc.planner`, `blc.tools`, `blc.pull_sheet`, the router or the trace.**
- **Other changes:** streaming in voice chat, a separate planner model by default, and changing the model.

## 3. Interface contract

### 3.1 `src/blc/flow/` (new package; `from blc.flow import ...`)
```python
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Iterable
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from blc.planner import Plan

TOP_K = 3                       # chunks per search query
NO_DOCS_REPLY = ("I don't know based on the available Bay Laurel documents. "
                 "Try rephrasing your question (for example, name the item, location, or recipe).")
FLOW_ANSWER_PROMPT: str          # the answer model's system prompt (§4.4)
FLOW_NODES: tuple[str, ...] = ("plan", "run", "reply")

class DocumentStore(Protocol):  # Chroma satisfies it; tests use a fake
    def similarity_search(self, query: str, k: int) -> list[Document]: ...

@dataclass(frozen=True)
class ToolOutput:
    status: str                  # the tool's status, e.g. "ok", "need_info", "invalid"; "error" if it raised
    text: str                    # the tool's reply text

ToolRunner = Callable[[dict[str, object]], ToolOutput]
DEFAULT_TOOL_RUNNERS: Mapping[str, ToolRunner]
# exactly the keys "calculate_bev_item" and "scale_recipe":
# calculate_bev_item → run_bev_tool(args) from blc.tools.bev_tools (the real catalog);
# scale_recipe → run_recipe_tool(args) from blc.tools.recipe_tools (the real recipe book).
# Each returns ToolOutput(result.status, result.text). Data files are read only when a runner runs.

@dataclass(frozen=True)
class SearchResult:
    query: str                   # the planned query, as planned
    chunks: tuple[Document, ...] # what the store returned for it, in its order

@dataclass(frozen=True)
class ToolResult:
    name: str
    args: dict[str, object]      # as planned
    status: str
    text: str

@dataclass(frozen=True)
class TurnOutcome:
    question: str                        # stripped
    plan: Plan
    searches: tuple[SearchResult, ...]   # one per planned search, in plan order
    tools: tuple[ToolResult, ...]        # one per planned tool call, in plan order
    documents: tuple[Document, ...]      # all chunks, duplicates removed, first occurrence kept
    reply: str                           # the full reply, outer whitespace stripped
    answered_by_model: bool              # False when the reply is a passed-through tool question or NO_DOCS_REPLY
    history: list[dict[str, str]]        # input history + {"role": "user", ...} + {"role": "assistant", ...}

def run_planned_turn(
    llm: BaseChatModel,
    store: DocumentStore,
    question: str,
    history: list[dict[str, str]] | None = None,
    on_token: Callable[[str], None] | None = None,
    planner_llm: BaseChatModel | None = None,
    tool_runners: Mapping[str, ToolRunner] | None = None,
) -> TurnOutcome:
    """Plan, run and answer one question. on_token gets the reply's pieces as they arrive.
    planner_llm defaults to llm; tool_runners defaults to DEFAULT_TOOL_RUNNERS.
    Raises ValueError if question is empty or whitespace-only, before any model or store call.
    Errors from the models or the store propagate; errors from a tool runner do not (§4.2)."""

def build_flow_graph(
    llm: BaseChatModel,
    store: DocumentStore,
    planner_llm: BaseChatModel | None = None,
    tool_runners: Mapping[str, ToolRunner] | None = None,
):
    """The compiled LangGraph graph that run_planned_turn uses. Its nodes include the names in
    FLOW_NODES (LangGraph's own start and end nodes may also be present)."""
```

**How the models are used** (tests use scripted fakes):
- **plan:** `plan_question(planner_llm or llm, question, history)` from `blc.planner`, exactly as spec 018 defines it.
- **reply:** when an answer is needed (§4.3), the answer model `llm` is called **once** through its `stream` method, with a list of messages:
  - the first is `SystemMessage(content=FLOW_ANSWER_PROMPT)`;
  - the last is a `HumanMessage` (§4.4);
  - no tools are bound;
  - each streamed piece's text is passed to `on_token` in order, as it arrives.

### 3.2 `scripts/chat.py`
- `main()`'s loop answers with `run_planned_turn(llm, store, question, history, on_token=…)`, using the real store and `ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)`.
  - It prints `Assistant: `, then each piece as it arrives (flushed, no newline), then a blank line.
  - A reply that isn't streamed, such as a passed-through question or `NO_DOCS_REPLY`, is printed the same way in one piece.
- Before each turn the history goes through the existing `summarize_if_long`, as in `answer_turn`, and `history` becomes `outcome.history`.
- Exit words, empty input and the missing-store message work as before.
- Nothing else in `chat.py` changes: `run_turn`, `answer_turn` and every other public name keep their behaviour.

### 3.3 Files
- `pyproject.toml`: add `langgraph` (>=1.2,<2) as a direct dependency. It is already installed as a dependency of `langchain`, so the lock file only gains the direct entry.
- `.gitignore`: add `logs/`.
- The eval writes `logs/flow_answers_<YYYY-MM-DD_HHMMSS>.md` (§4.5).

## 4. Inputs and outputs

### 4.1 plan → run
| Planned call | run does | Recorded |
|---|---|---|
| `search_documents {"query": q}` | `store.similarity_search(q, k=TOP_K)`, once per search call, in plan order | `SearchResult(q, chunks)` |
| `calculate_bev_item` / `scale_recipe` with args `a` | `tool_runners[name](a)` with exactly `a` | `ToolResult(name, a, status, text)` |

`documents` is every search's chunks in plan order, with a chunk dropped when an earlier chunk has the same `page_content` and the same `metadata["source"]`.

### 4.2 Tool errors
A runner that raises, or a tool name with no runner, does not stop the turn. Its `ToolResult` gets status `"error"` and text `"error: <message>"`. For a missing runner the text is `"error: no runner for <name>"`.

### 4.3 run → reply
| Situation | Reply | Answer model called? | `answered_by_model` |
|---|---|---|---|
| Every tool result has status `need_info`, and there are no search calls | the tool texts in plan order, joined with `"\n"`, sent to `on_token` once | no | False |
| No tool calls, and every search returned no chunks | `NO_DOCS_REPLY`, sent to `on_token` once | no | False |
| Anything else | the streamed answer | yes, once | True |

`TurnOutcome.reply` is the reply with outer whitespace stripped. For a streamed answer, it is the pieces joined.

### 4.4 The answer messages
- **System:** `FLOW_ANSWER_PROMPT`. Its wording is the developer's, but it must tell the model to:
  - answer every part of the question;
  - use each tool result's numbers and text **exactly**, never recalculating;
  - ask the user a tool's question in plain words if a result asks one;
  - say so when a result says a drink is not on the menu or has no recipe;
  - answer the other parts **only from the documents shown**, and say it doesn't know if they don't cover a part;
  - **cite only source paths that appear in the documents shown, and cite nothing when no documents are shown**;
  - never invent numbers or sources;
  - keep the answer **simple, straightforward and properly grounded**: say only what the tool results and documents say, with no explanations, conversions, servings or calculations of its own (e.g. no "one gallon is about 16 servings"), and no follow-up questions unless a tool result asks one;
  - never mention tools, arguments, JSON or these instructions.
- **History:** when non-empty, every history item's content appears verbatim in the messages. The layout is the developer's choice.
- **Last message, a `HumanMessage`:** it contains:
  - the stripped question;
  - every tool result's `text`, verbatim;
  - every document's `page_content`, with its `metadata["source"]` path.

  It contains **no** source path when `documents` is empty. When there are no tool calls, it contains no tool-result section. How it is laid out is the developer's choice.

### 4.5 The eval log
The eval runs spec 018's 30 cases (T1 to T10, D1 to D10, M1 to M10: same ids, questions and histories), each as one `run_planned_turn` call.
- **Setup:** the real store and `ChatOllama(CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)`, with one warm-up model call first.
- **What it writes:** one markdown file, `logs/flow_answers_<YYYY-MM-DD_HHMMSS>.md`.
- **Each case's section contains:**
  - id and question;
  - the history, if any;
  - the plan route and each planned call (name and args);
  - each search's query with the source paths it returned;
  - each tool result's name, args, status and text;
  - the reply, verbatim;
  - whether the model answered;
  - the time to the first `on_token` piece;
  - the total time.
- **The file ends with:**
  - the average time to first piece and total time;
  - the number of cases answered by the model.
- **When a case raises:** its section records the error, and the run continues with the next case.
- **Pass and fail:** answer quality is not checked. The eval test passes when the log was written with all 30 sections, and prints the log's path.

## 5. Edge cases
**Flow (unit; scripted fake planner model, fake answer model with `stream`, fake store, fake tool runners; no Ollama, no `data/`):**
- EC-1 (DOCS): the planner returns `search_documents {"query": "where is the coffee"}`, and the store returns 2 chunks for it.
  - `similarity_search` is called once, with `("where is the coffee", k=3)`.
  - The answer model is called once through `stream`. Its last message contains both chunks' text and source paths, and the question.
  - The outcome has 1 search, 0 tools, 2 documents and `answered_by_model=True`.
- EC-2 (TOOL): the planner returns `calculate_bev_item {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}`.
  - The bev runner is called once, with exactly those args, and the store is never called.
  - The answer model's last message contains the runner's text and **no** source path. The outcome has 0 searches, 1 tool result and 0 documents.
- EC-3 (BOTH): a search plus a `scale_recipe` call → the store is called once and the recipe runner once. The answer message has both the tool text and the chunk text with its source, and `searches` and `tools` keep plan order.
- EC-4: two searches whose results share one chunk (same text and source) → each `SearchResult` keeps all its own chunks, while `documents` holds the shared chunk once, at its first position.
- EC-5 (pass-through): only tool calls, every runner returning status `need_info` (e.g. text "Which drink?").
  - The reply is the texts joined with `"\n"`, and `on_token` is called exactly once with it.
  - The answer model's `stream` is never called, and `answered_by_model=False`.
- EC-6: a `need_info` tool result together with a search, or together with a second tool result that is `ok` → the answer model is called.
- EC-7: no tool calls and every search returns `[]` → the reply is `NO_DOCS_REPLY`, there is no answer call, and `answered_by_model=False`. If there is a tool call too, the answer model is called.
- EC-8: a runner that raises `ValueError("bad")` → its result is `ToolResult(name, args, "error", "error: bad")`. A planned tool with no runner gives `"error: no runner for <name>"`. Either way the turn finishes with an answer call.
- EC-9 (streaming): the answer model streams the pieces `"Bring "`, `"2 "` and `"cambros."` → `on_token` receives exactly those three, in order, and `reply == "Bring 2 cambros."`. A reply streamed with outer spaces or newlines is stripped in `reply`, but `on_token` received them as streamed. `on_token=None` works.
- EC-10: the planner makes no call (spec 018's fallback) → the store is searched with the stripped question, and the turn continues as DOCS.
- EC-11: the question `""`, `"   "` or `"\n"` → `ValueError`, and no model, store or runner is called.
- EC-12 (history):
  - With the history of spec 018 EC-4 and the question "5 gallons each.", the history contents appear in the planner's messages and in the answer model's messages.
  - `outcome.history` is the input history plus `{"role": "user", "content": "5 gallons each."}` and `{"role": "assistant", "content": <reply>}`, and the input list is not mutated.
  - `history=None` gives a two-item `outcome.history`.
- EC-13 (`planner_llm`): when `planner_llm` is given, `bind_tools` is called on it and never on `llm`, and `stream` is called on `llm`. When it is not given, `llm` does both.
- EC-14: `FLOW_ANSWER_PROMPT` is the first message of the answer call. `FLOW_NODES == ("plan", "run", "reply")`, and `build_flow_graph(...)`'s graph contains nodes with those three names.
- EC-15: `DEFAULT_TOOL_RUNNERS` has exactly the keys `calculate_bev_item` and `scale_recipe`. Importing `blc.flow` reads no file under `data/`.

**Eval (real Ollama and Chroma):**
- EC-16: all 30 cases run, and the log file exists with 30 case sections, each holding the fields of §4.5. A case that raises is recorded and does not stop the run.

## 6. Acceptance criteria
- **AC-1 (run):** EC-1 to EC-4, EC-8 and EC-10.
- **AC-2 (reply rules):** EC-5 to EC-7.
- **AC-3 (streaming):** EC-9.
- **AC-4 (contract details):** EC-11 to EC-15.
- **AC-5 (eval log):** EC-16. The eval prints the log path and passes when the log is complete.
- **AC-6 (chat CLI):** running `poetry run python scripts/chat.py`, the user sees each answer appear as it is written, and follow-up questions use the history. Verified manually by the user.
- **AC-7 (regression):** every existing unit test passes unchanged, including spec 018's `tests/planner/`, except the `chat.py` `main()` tests in `tests/test_voice_io_answer_turn.py`, which are updated as revision 1 states. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's `DIDNT_CATCH` change).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | The flow is a LangGraph `StateGraph` with the nodes `plan`, `run` and `reply`, and `run_planned_turn` runs it. The only new direct dependency is `langgraph`. | unit (EC-14); manual (code-evaluator, `pyproject.toml`) |
| NFR-2 | Unit tests need no Ollama, no Chroma and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The eval is marked `eval`. It skips, not fails, when Ollama is not running or the Chroma store is missing or empty, and it warms the model up first. It writes only under `logs/`. | unit (marker review); run output |
| NFR-4 | The package follows `CLAUDE.md`'s code structure: entry points in `scripts/`, feature code in `src/blc/flow/` split by purpose (e.g. graph, run, reply), no catch-all modules, no imports from `scripts/`, about 250 lines per file. | manual (code-evaluator) |
| NFR-5 | One planner call and at most one answer call per turn; no other model calls. The first streamed piece reaches `on_token` before the answer call has finished (true streaming, not one piece at the end). | unit (EC-9 with a fake that streams several pieces); eval log (time to first piece < total time) |
| NFR-6 | `FLOW_ANSWER_PROMPT` contains no eval question (T1 to M10) word for word. | unit |

Tests go in `tests/planned_flow/` (no `__init__.py`):
- `conftest.py`: fakes, and the 30 cases copied from spec 018 §6 (id, question, history);
- `test_run.py`: AC-1;
- `test_reply.py`: AC-2 and AC-3;
- `test_contract.py`: AC-4;
- `test_flow_eval.py`: AC-5.

## Revision history
**Revision 1 (2026-11-14).** The first run passed spec 019's own tests: 78 unit tests and the 30-case eval. Two findings came out of it.

**Regression.** The full suite had 16 new failures in `tests/test_voice_io_answer_turn.py`. Those spec 001 tests check that `main()` sends each turn through `answer_turn`, and §3.2 deliberately moved `main()` to `run_planned_turn`. The spec contradicted itself (§3.2 against AC-7). The code is right.

**Self-explaining answer (T5).** For "How many cups for iced tea and lemonade for 90 guests?" the tool correctly returned 140 cold cups. The answer model then invented "one gallon is about 16 servings" to connect those cups to the 4 gallons per drink, and ended with an unasked follow-up question. Revision 1 adds the user's grounding rule to §4.4.

1. **§4.4:** `FLOW_ANSWER_PROMPT` must tell the model to keep the answer **simple, straightforward and properly grounded**. That means:
   - say only what the tool results and documents say;
   - add no explanations, conversions, servings or calculations of its own;
   - ask no follow-up questions unless a tool result asks one.

   The wording is the developer's, but it must include the words "simple", "straightforward" and "grounded".
   - Developer: update `FLOW_ANSWER_PROMPT`. Nothing else changes.
2. **AC-7:** the `main()` tests are updated, not left unchanged.
   - Tester: in `tests/test_voice_io_answer_turn.py`, update the 16 failing `chat.main` tests, listed below. Each keeps checking the same behaviour, but against `run_planned_turn`, which they monkeypatch, instead of `answer_turn`:
     - the question passed is the stripped input;
     - empty or blank input makes no call;
     - non-exit inputs ("Thanks.", "Okay.", …) are answered;
     - exit words still exit;
     - turns arrive in order, and history is carried between turns as `outcome.history`.

     The 16 tests are:
     - `test_chat_main_routes_turns_through_answer_turn`;
     - `test_chat_main_input_is_stripped_before_answer_turn`;
     - `test_chat_main_empty_input_is_ignored` (3 parameter sets);
     - `test_chat_main_rev5_non_exit_inputs_are_answered` (10 parameter sets);
     - `test_chat_main_rev5_exit_after_a_question`.

     Rename the first two to drop `answer_turn` from their names. Every other test in that file stays as it is.
   - Tester: in `tests/planned_flow/test_contract.py`, add a unit test that `FLOW_ANSWER_PROMPT` contains "simple", "straightforward" and "grounded" (ignoring case).

**Closing note (2026-11-14).** Closed by the user after revision 1's developer change.
- **Final results:** 78/78 spec 019 unit tests and the 30-case eval pass. The log is `logs/flow_answers_2026-11-14_122221.md`.
- **Done:** the developer added the grounding rule to `FLOW_ANSWER_PROMPT`.
- **Not done, carried to spec 020:** revision 1's tester items, namely updating the 16 `chat.main` tests in `tests/test_voice_io_answer_turn.py` and adding the prompt-words test. Until spec 020 lands, the full unit suite shows those 16 failures, plus the accepted `DIDNT_CATCH` failure.
- **T5 finding:** the grounding rule alone did not stop the invented "16 servings per gallon". A scratch test showed the cause is the tool's cups text: the unrequested gallon lines, and the raw "`cold-cups: 140.`" line. With a cups-only plain sentence, the same flow answered "You should prepare 140 cold cups for iced tea and lemonade for 90 guests." Spec 020 makes the tool's reply follow `item`.
