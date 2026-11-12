# Spec 011: End-to-end flow trace and stage eval

- **Status:** approved
- **Date:** 2026-11-12

## 1. Goal
Today nobody can see what the chatbot did with a question: which route the router chose, which chunks were retrieved, which tool call was made. Each earlier eval tested one stage on its own questions. This spec makes the **real chat flow log every stage**, and adds an end-to-end eval that checks each stage on real questions:
1. **prompt:** what the user asked (and the history used);
2. **route:** did the router decide TOOL, DOCS or BOTH;
3. **retrieval:** for a DOCS part, were the right chunks retrieved;
4. **tool:** for a TOOL part, was the right tool called with the right arguments;
5. **both:** for BOTH, stages 3 and 4 must both hold.

The flow gets one core function, `run_turn`, that returns a **trace** of the stages and also logs each stage. `answer_turn` is built on it, so the trace is of the code that really runs, not a copy. A CLI prints the trace for one question. The end-to-end eval uses `run_turn` without the final answer call.

**Out of scope: whether the generated answer is faithful (spec 012).** The final call stays as it is; this spec only records its reply.

## 2. Out of scope
- Judging the final reply (faithfulness, correctness, leaked instructions): spec 012.
- Changing behaviour: the router, retrieval (still `retrieve(store, question)` on the whole question, before routing, `TOP_K` chunks), the tool step, the argument check and the final call all behave as before. `answer_turn`'s signature, its `TurnResult` and its replies do not change.
- Fixing any failure the eval finds. The first run is a baseline; findings decide later specs.
- `scripts/voice_chat.py`, ingestion, the knowledge files.

## 3. Interface contract

### 3.1 The trace types: `src/blc/trace/` (new feature package)
Importable as `from blc.trace import ...`.

```python
from dataclasses import dataclass
from blc.router import RouteDecision

STAGE_NAMES: tuple[str, ...] = ("prompt", "route", "retrieval", "tool", "reply")

@dataclass(frozen=True)
class RetrievedChunk:
    rank: int      # 1-based position in the retrieval result
    source: str    # the chunk's metadata "source" (path as stored, e.g. "data/supplies/coffee.md"); "unknown" if missing
    text: str      # the chunk's page content

@dataclass(frozen=True)
class RetrievalStage:
    query: str                           # the text searched
    k: int                               # how many chunks were asked for
    chunks: tuple[RetrievedChunk, ...]   # in rank order; () if nothing was found

@dataclass(frozen=True)
class ToolCallLog:
    name: str                  # tool name the model asked for
    args: dict[str, object]    # arguments exactly as the model sent them
    result: str                # text returned to the model
    refused: bool              # True if the argument check refused the call (spec 009): the tool did not run

@dataclass(frozen=True)
class ToolStage:                         # one per TOOL part of the route, in order
    part: str                            # the TOOL part's text
    calls: tuple[ToolCallLog, ...]       # every call made for this part, in order; () if none
    tool_text: str | None                # the text used for the answer; None if the part fell back to DOCS
    retried: bool                        # the model was asked again because it made no call

@dataclass(frozen=True)
class TurnTrace:
    question: str                                # the question as run (stripped)
    history: tuple[dict[str, str], ...]          # the history the flow used (after summarising, if any)
    retrieval: RetrievalStage | None             # None if retrieval was not run
    route: RouteDecision | None                  # None if the router was not run
    tools: tuple[ToolStage, ...]                 # one per TOOL part; () if none
    reply: str | None                            # the final reply; None if not generated

def format_trace(trace: TurnTrace) -> str:
    """The trace as readable text (§4.2). Never raises. Prints nothing."""

def trace_to_dict(trace: TurnTrace) -> dict:
    """The trace as plain data that json.dumps accepts (§4.3). Never raises."""
```

### 3.2 The flow: `scripts/chat.py`
```python
def run_turn(
    store,                                   # any object with similarity_search(query, k=...) -> list[Document]
    llm,                                     # a chat model as spec 006 §3.2 uses (invoke, bind_tools)
    history: list[dict[str, str]],
    question: str,
    generate: bool = True,
) -> TurnTrace:
    """Runs one turn through the real flow and returns its trace. Raises ValueError if
    question is blank, before any store or model call. With generate=False the final
    answer call is not made and trace.reply is None. Logs each stage (§4.1). Prints nothing."""
```
`answer_turn(store, llm, history, question)` keeps its signature, its `TurnResult` and its behaviour (spec 001 and 004 tests still pass); it is built on `run_turn(..., generate=True)`.

### 3.3 The CLI: `scripts/trace_flow.py` (new)
`main(argv: list[str] | None = None) -> int`. Usage: `poetry run python scripts/trace_flow.py "question" [--history PATH] [--generate] [--json]`. It prints `format_trace` of the run (or `trace_to_dict` as JSON with `--json`) to stdout. `--history PATH` reads a JSON list of `{"role", "content"}` items. The final answer call is made only with `--generate`. Returns 1 with a message on stderr if the Chroma store does not exist. The entry point holds only the CLI; the work is in the packages.

## 4. Inputs and outputs

### 4.1 The stage log
`run_turn` writes one `logging` record at INFO level to the logger named `"blc.flow"` as each stage finishes, in **execution order**: `prompt`, `retrieval`, `route`, then one `tool` record per TOOL part, then `reply` (only if generated). A stage that is not run writes no record. Each record's message starts with the stage name in square brackets (`[prompt]`, `[retrieval]`, `[route]`, `[tool]`, `[reply]`) and carries the same text as that stage's section in `format_trace`. Nothing is printed to the screen.

### 4.2 `format_trace`
One section per stage, in this order: `prompt`, `route`, `retrieval`, `tool` (one section per `ToolStage`, or one section that says `no tool call` if `tools` is empty), `reply` (only if `reply` is not `None`). Each section starts with a line `== <name> ==`. A stage with `None` has its header and the line `not run`. The sections show:
- **prompt:** the question, and the number of history items.
- **route:** the kind, then one line per part as `TOOL: <text>` or `DOCS: <text>`; the words `fallback` or `unfaithful` appear when those flags are set.
- **retrieval:** the query, `k`, then one line per chunk with its rank and source and the start of its text (long text may be shortened).
- **tool:** the part's text; one line per call with the name, the arguments and the result, marked `(refused)` when refused; the `tool_text` (or `fell back to docs`); `retried` when true.
- **reply:** the reply text.

### 4.3 `trace_to_dict`
A dict with the keys `question`, `history`, `retrieval`, `route`, `tools`, `reply` (the same names as the fields). `retrieval` is `None` or `{"query", "k", "chunks": [{"rank", "source", "text"}]}`; `route` is `None` or `{"kind", "fallback", "unfaithful", "parts": [{"route", "text"}]}`; `tools` is a list of `{"part", "calls": [{"name", "args", "result", "refused"}], "tool_text", "retried"}`. `json.dumps` of the result works for any trace that holds JSON-friendly arguments.

### 4.4 What each stage must show for the real flow
| Situation | `retrieval` | `route` | `tools` | `reply` |
|---|---|---|---|---|
| Retrieval finds chunks | set | set | one per TOOL part | text, or `None` if `generate=False` |
| Retrieval finds nothing (empty store) | set, `chunks == ()` | `None` | `()` | the unknown-retrieval reply, or `None` if `generate=False` |
| `generate=False` | as above | as above | as above | `None` and the final model call is not made |

`refused` is `True` exactly for calls the argument check of spec 009 refused (their `result` starts with `REJECTED_PREFIX`).

### 4.5 The end-to-end eval (real model, real store)
For each case, the test builds the real store (`chat.build_store()`) and the real model (`ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE)`) and runs `run_turn(store, llm, history, question, generate=False)` **once**; the stage tests of a case share that trace. A case lists the expected **kind** (`DOCS`, `TOOL` or `BOTH`), for DOCS and BOTH the **expected sources** and **must include** words, and for TOOL and BOTH the **expected tool call**.

**Stage checks** (each is its own test, so a run shows which stage failed):
- **Stage 1, prompt:** `trace.question` equals the case's question (stripped) and `trace.history` equals the case's history.
- **Stage 2, route:** `trace.route` is not `None`, and `trace.route.kind` equals the expected kind. The failure message shows the parts and the `fallback` and `unfaithful` flags.
- **Stage 3, retrieval** (cases of kind DOCS or BOTH that list expected sources): `trace.retrieval` is not `None`; every expected source is among the chunks' sources; every must-include word (ignoring case) occurs in the texts of the retrieved chunks taken together.
- **Stage 4, tool** (cases of kind TOOL or BOTH): `trace.tools` has **exactly one** `ToolStage`; its `tool_text` is not `None` and is not `TOOL_LIMIT_REPLY`; and every call that was **not refused** passes: its name is `BEV_TOOL_NAME`, its `item` is the listed item, and `run_bev_tool(call.args)` gives the listed status and (for status `ok`) the listed drinks (display names, amounts as numbers, `from_guests` where listed) and the listed guests (missing, null or 0 means "no guests"). For a case with no number in its question (E12, E17, E20) the call must pass neither `guests` nor `gallons`. For a "names only" drink list the names must appear in `BevResult.text` (ignoring case) instead of in `BevResult.drinks`.
- **Stage 5, both** (cases of kind BOTH): passes only if stage 3 and stage 4 both pass.
Every failure message includes `format_trace(trace)`.

### 4.6 Cases
Sources are the path strings stored in the index. `Coffee 3 g` means 3 gallons from guests; "no guests" means not given; "names only" means check the names in the text.

| id | history | question | kind | sources and must include | tool call |
|---|---|---|---|---|---|
| E1 | none | Where is the coffee? | DOCS | `data/supplies/coffee.md`; coffee machine, beverage room | |
| E2 | none | How do I make 5 gallons of lemonade? | DOCS | `data/recipes/lemonade.md`; 35 oz | |
| E3 | none | What syrup flavors do we have? | DOCS | `data/supplies/syrups.md`; Mango, Strawberry, Peach | |
| E4 | none | If there are no lemons by the sink, where else can I look? | DOCS | `data/supplies/lemon.md`; cooler, dish room | |
| E5 | none | What concentrate flavors do we carry? | DOCS | `data/supplies/concentrates.md`; Pomegranate, Lemonade, Orange | |
| E6 | none | What's in the coffee, decaf, tea, iced water & juice package? | DOCS | `data/pull_sheet/menu/beverages.md`; orange juice | |
| E7 | none | Where is the flour? | DOCS | (none expected: stage 3 not applicable) | |
| E8 | none | How many cambros do I need to bring for 7 gallons of lemonade? | TOOL | | cambros, ok, Lemonade 7, no guests |
| E9 | none | How many cambros for lemonade for 70 guests? | TOOL | | cambros, ok, Lemonade 3 g, guests 70 |
| E10 | none | We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros? | TOOL | | cambros, ok, Coffee, Decaf, Hot water, Iced water, Orange juice each 3 g, guests 70 |
| E11 | none | What do I need to bring for coffee for 50 guests? | TOOL | | everything, ok, Coffee 2 g, guests 50 |
| E12 | none | Do I need sugar for coffee? | TOOL | | supplies, ok, Coffee (names only), no guests |
| E13 | none | How many gallons do I make for 25 people? | TOOL | | gallons, ok, no drinks, guests 25 |
| E14 | none | Brewed hot cider for 100 people, what goes on the pull sheet? | TOOL | | everything, ok, Brewed hot cider 4 g, guests 100 |
| E15 | user: "How many cambros do I need for coffee and lemonade?"; assistant: "How many gallons of each drink, or how many guests?" | 5 gallons each. | TOOL | | cambros, ok, Coffee 5, Lemonade 5, no guests |
| E16 | none | I need 5 gallons of coffee and lemonade. How many cambros? | TOOL | | cambros, ok, Coffee 5, Lemonade 5, no guests |
| E17 | none | How many cups do I need for coffee? | TOOL | | cups, need_info, no guests |
| E18 | none | How many cambros for 4 gallons of hot chocolate? | TOOL | | cambros, not_on_menu, no guests |
| E19 | none | Where is the coffee, and how many gallons of coffee do I need for 75 people? | BOTH | `data/supplies/coffee.md`; coffee machine, beverage room | gallons, ok, guests 75, drinks: either (Coffee 3 g) or no drinks |
| E20 | none | Where are the lemons, and do I need lemons for iced tea? | BOTH | `data/supplies/lemon.md`; sink | supplies, ok, Iced tea (names only), no guests |
| E21 | none | What syrup flavors do we have, and how many cups do I need for 45 guests? | BOTH | `data/supplies/syrups.md`; Mango, Strawberry, Peach | cups, ok, guests 45 (drinks not checked) |

## 5. Edge cases
**Trace types and formatting (unit, no model):**
- EC-1: `format_trace` of a full trace (retrieval, route BOTH, one tool stage with a refused and a run call, reply) has the headers `== prompt ==`, `== route ==`, `== retrieval ==`, `== tool ==`, `== reply ==` in that order; the question, the route's `TOOL:` and `DOCS:` lines, each chunk's source, the call's name and arguments, the `(refused)` mark and the reply text appear.
- EC-2: with `retrieval=None` and `route=None` the sections show `not run`; with `tools=()` the tool section says `no tool call`; with `reply=None` there is no `== reply ==` section.
- EC-3: `trace_to_dict` follows §4.3 and `json.dumps` of it works; `route=None`, `retrieval=None` and `reply=None` become `None`.
- EC-4: `format_trace` and `trace_to_dict` never raise on odd traces (empty strings, very long text, empty history, non-text values inside `args`).

**`run_turn` (unit, fake store and scripted fake model as spec 006 §5):**
- EC-5: DOCS question: `retrieval` holds the fake store's chunks with ranks 1.. and their `source` values (`"unknown"` when a chunk has no source), `query` is the question, `k` is `TOP_K`; `route.kind == "DOCS"`; `tools == ()`; `reply` is the final model reply.
- EC-6: TOOL question (router reply `TOOL: …`, tool step calls the real `make_bev_tool` tool on the spec 005 Appendix A catalog): `tools` has one `ToolStage` whose `calls` hold the call as sent, its `result`, `refused=False`, and `tool_text` equal to the tool's result.
- EC-7: BOTH question: `retrieval` set, `route.kind == "BOTH"`, one `ToolStage`.
- EC-8: a call the argument check refuses (spec 009) is in `calls` with `refused=True`, and the corrected call after it has `refused=False`.
- EC-9: `generate=False`: `reply is None`, and the model was invoked only for the router and the tool steps (no final call).
- EC-10: an empty store (no chunks): `route is None`, `tools == ()`, `retrieval.chunks == ()`, the model is never invoked, and `reply` is the unknown-retrieval reply (`None` with `generate=False`).
- EC-11: a TOOL part that fell back to DOCS has `tool_text is None` and its `calls` as made.
- EC-12: blank question → `ValueError` before any store or model call.
- EC-13: a long history that is summarised: `trace.history` is the history after summarising.
- EC-14: logging: with `caplog` at INFO, one record per stage on logger `"blc.flow"`, in execution order (`[prompt]`, `[retrieval]`, `[route]`, one `[tool]` per TOOL part, `[reply]` when generated), each message starting with its bracketed name; no `[reply]` record with `generate=False`; nothing printed (`capsys`).
- EC-15: `answer_turn` returns the same `TurnResult` as before for a DOCS, a TOOL and an empty-store question (reply, history, docs), so spec 001 and 004 tests still pass.

**End-to-end eval (real model, real store):** §4.5 and §4.6.

## 6. Acceptance criteria
- **AC-1 (trace types):** `format_trace` and `trace_to_dict` behave as §4.2, §4.3 and EC-1 to EC-4.
- **AC-2 (flow):** `run_turn` behaves as §4.4 and EC-5 to EC-13, and `answer_turn` as EC-15.
- **AC-3 (logging):** EC-14.
- **AC-4 (regression):** spec 001 tests, spec 004 tests, and the spec 006, 007, 009 and 010 unit tests still pass (apart from nothing new).
- **AC-5 (end-to-end eval):** each case E1 to E21 is run once, and its applicable stage checks (§4.5) are reported as separate tests: `stage1` and `stage2` for every case, `stage3` for cases with expected sources, `stage4` for TOOL and BOTH cases, `stage5` for BOTH cases. All are marked `eval` and skip, not fail, when Ollama or the Chroma store is missing. **Pass threshold: none.** This is a baseline: failing stages are findings, reported by case and stage, with the trace.
- **AC-6 (CLI, manual):** the planner runs `scripts/trace_flow.py` on a DOCS, a TOOL and a BOTH question and confirms the stages are printed.

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-4 tests need no Ollama, no network and no Chroma store, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The eval is marked `eval`, builds the store and model once per run, runs each case once (stage tests share the trace) and takes under about 5 minutes. | unit (marker review); manual (planner times the run) |
| NFR-4 | The stage logging uses the `logging` module, never `print`. | unit (EC-14) |
| NFR-5 | The trace code is separate from the flow: the types and formatters take data and return data (no I/O, no model); `run_turn` orders the stages; the CLI holds only argument handling and printing. | manual (code review) |
| NFR-6 | Expected values in the eval come from the table in §4.6 and the calculator's own result, not from numbers copied out of the rules. | manual (review by test-evaluator) |
| NFR-7 | Files stay about 250 lines each, split by job. | manual (code review) |

Tests go in `tests/flow/` (new, no `__init__.py`): `conftest.py` (fakes, the Appendix A catalog, the cases), `test_trace_format.py` (AC-1), `test_run_turn.py` (AC-2, AC-3), `test_flow_eval.py` (AC-5). AC-4 runs the existing files.

## Closure note (2026-11-12)
The user accepted this spec as passed. State at closing, from the implementation-evaluator's run:
- **Met:** AC-1 to AC-3 (74 unit tests); the eval ran as a baseline (AC-5: 82 of 89 stage tests passed, no threshold); the spec 004, 006, 007, 009 and 010 unit tests still pass.
- **Known and accepted, not fixed:** five spec 001 `answer_turn` tests in `tests/test_voice_io_answer_turn.py` fail because `run_stages` no longer calls `answer_from_context` or `maybe_summarize`, which those tests replace with fakes. The chatbot itself is not affected. `test_constants_match_contract` (voice) was already failing.
- **Baseline findings for later specs:** E13 ("How many gallons do I make for 25 people?") and E14 (the cider "pull sheet" question) were routed to DOCS; E21 (a BOTH question) lost its docs chunk (`syrups.md`) because retrieval runs on the whole question; E2 expects "35 oz" in a retrieved chunk, which cannot be met (the recipe is per gallon): the expectation should be "7 oz".
- **Not done:** AC-6 (CLI check by the planner) and the spec revision for the tool-injection hook and the `[reply]` record on an empty store.
