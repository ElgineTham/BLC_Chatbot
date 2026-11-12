# Spec 006: Question router (tool or documents)

- **Status:** approved
- **Date:** 2026-11-11

## 1. Goal
Today one model call reads the documents, decides whether to call `calculate_bev_item`, fills in its arguments and writes the answer. On spec 005's evals the model sent recipe questions to the tool, did not call it for supply questions, worked guests out into gallons itself from the rules document, invented amounts and named the tool in replies. This spec splits each answer into simple steps:
1. a **router** call splits the question into parts and labels each part **TOOL** (the answer is how much of a beverage pull sheet item to bring or make) or **DOCS** (everything else);
2. each TOOL part gets a **tool step**: a call that only fills in the tool's arguments, with the tool and **without the documents**;
3. one **final** call writes the reply from the documents (for DOCS parts) and the tool results (for TOOL parts), **without the tool**.

A question can be TOOL, DOCS or BOTH, and the decision says which part went where. The steps stay separate functions so a later move to LangGraph is a rewiring (router node, then branches).

## 2. Out of scope
- LangGraph. Other tools. Any change to `src/blc/tools/bev_tools/` or `src/blc/pull_sheet/`.
- Retrieval: `retrieve`, `TOP_K`, the store and the knowledge files are unchanged; `answer_with_tools` still receives `docs` retrieved for the whole question.
- Changing `CHAT_MODEL` (spec 005 revision 2 sets it to `qwen2.5:14b`), `answer_turn`, `TurnResult`, `main` or voice chat. Showing the route to the user (it is in `ToolAnswer` for tests and later use).
- Spec 004's judge.

## 3. Interface contract

### 3.1 The router: `src/blc/router/` (new feature package)
Importable as `from blc.router import ...`.

```python
from dataclasses import dataclass
from langchain_core.language_models import BaseChatModel

ROUTES: tuple[str, ...] = ("TOOL", "DOCS")
ROUTE_KINDS: tuple[str, ...] = ("TOOL", "DOCS", "BOTH")

@dataclass(frozen=True)
class RoutedPart:
    route: str   # "TOOL" or "DOCS"
    text: str    # the part as a self-contained question (follow-ups filled in from history)

@dataclass(frozen=True)
class RouteDecision:
    parts: tuple[RoutedPart, ...]   # at least one, in the order the model gave them
    kind: str                       # "TOOL" if all parts are TOOL, "DOCS" if all are DOCS, else "BOTH"
    fallback: bool                  # True if the model's reply could not be read (§4.1)

def route_question(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
) -> RouteDecision:
    """One llm.invoke(messages) call (no tools bound, no documents); reads the reply's
    .content as in §4.1. Raises ValueError if question is blank. Never raises for an
    unreadable reply (fallback instead). Prints nothing."""
```

`ROUTER_PROMPT` (module constant, wording is the developer's) tells the model the rule in §4.2, how to split and rewrite parts, and the reply format in §4.1.

### 3.2 The chat flow: `scripts/chat.py`
`answer_with_tools` keeps its signature and `answer_from_context` still returns `answer_with_tools(...).reply`. Changed and new names:

```python
from blc.router import RouteDecision, RoutedPart

@dataclass(frozen=True)
class PartResult:                         # NEW
    part: RoutedPart
    tool_calls: tuple[ToolCallRecord, ...]   # calls made for this part; () for DOCS parts
    tool_text: str | None                   # the tool result used for a TOOL part; None for DOCS parts
                                            # and for TOOL parts that fell back to DOCS (§4.4)

@dataclass(frozen=True)
class ToolAnswer:
    reply: str
    tool_calls: tuple[ToolCallRecord, ...]   # every tool call, all parts, in order
    retried: bool                            # CHANGED: True if any tool step asked the model again because it made no call (§4.3)
    route: RouteDecision                     # NEW
    parts: tuple[PartResult, ...]            # NEW: one per route part, same order

TOOL_PROMPT: str      # NEW: system prompt of the tool step (§4.3)
ANSWER_PROMPT: str    # NEW: system prompt of the final call (§4.5); replaces the role SYSTEM_PROMPT had
```

**Removed:** the safety net (§4.6 of spec 005): `TOOL_HINT_WORDS` and its retry. `CHAT_TOOLS`, `MAX_TOOL_ROUNDS`, `TOOL_LIMIT_REPLY`, `ToolCallRecord` and `SYSTEM_PROMPT` stay (SYSTEM_PROMPT may be kept as an alias of ANSWER_PROMPT).

**How the flow talks to the model** (so tests can use a scripted fake model). For one `answer_with_tools` call, in this order:
1. **Router:** exactly one `llm.invoke(messages)` (through `route_question`).
2. **Tool steps:** for each TOOL part in order, rounds of `bound.invoke(messages)` where `bound = llm.bind_tools(list(tools))` (bound at most once per answer, only if there is a TOOL part). Replies are read from `.content` and `.tool_calls` as in spec 005; each tool result goes back as a `ToolMessage` with the matching `tool_call_id`.
3. **Final:** exactly one `llm.invoke(messages)`.

So a DOCS-only answer makes exactly 2 `llm.invoke` calls and no `bind_tools` call.

**Code structure:** step functions that take data and return data (route, run one tool step, build final messages, …) plus one function that only orders them. No step prints.

## 4. Inputs and outputs

### 4.1 Reading the router's reply
- Each non-empty line of the reply that starts with a label `TOOL` or `DOCS` (any case; ignoring leading `-`, `*`, `#`, a list number like `1.`, and `**` around the label) followed by `:` gives one part: the label is the route, the rest of the line (stripped) is the text.
- Lines without a label are ignored. A labelled line with empty text uses the whole question as its text.
- **Fallback:** if no line has a label, the decision is one DOCS part with the whole question, and `fallback=True`.

| Router reply | Parts |
|---|---|
| `TOOL: How many cambros for 6 gallons of peach tea?` | (TOOL, "How many cambros for 6 gallons of peach tea?") |
| `DOCS: Where are lemons kept?\nTOOL: How many cold cups for 45 guests?` | (DOCS, …), (TOOL, …); kind BOTH |
| `**Tool**: How much iced tea for 90 guests?` | (TOOL, "How much iced tea for 90 guests?") |
| `1. docs: What does fresh-brewed mean?` | (DOCS, "What does fresh-brewed mean?") |
| `I think this is a tool question.` | fallback: (DOCS, whole question), `fallback=True` |
| `` (empty) | fallback |

### 4.2 The routing rule (what `ROUTER_PROMPT` must convey)
- **TOOL:** the answer is **how much of a beverage pull sheet item to bring or make**: gallons of a drink to make; which or how many cambros or containers, or what to put or serve a drink in; how many cups; whether to bring, or how many of, a supply (napkins, creamer, sugar, stir sticks, lemons, lemon tongs, tea packets); what to bring for drinks in general.
- **DOCS:** everything else, **even when the question mentions gallons or guests**: recipes and ingredient amounts (concentrate, syrup), where things are kept, what a menu name means, what a package contains, prices, schedules, cleaning, drinks off the menu.
- A question asking both gets one part per question, in order. Follow-ups are rewritten from the history into self-contained questions (e.g. after the assistant asked "How many gallons of each?", the reply "4 each" for iced tea and peach tea becomes "How many cambros for 4 gallons of iced tea and 4 gallons of peach tea?").
- Examples in the prompt must not be eval questions from §6 or spec 004 §6, nor reuse their drinks and amounts (NFR-4).

### 4.3 The tool step (one per TOOL part)
- Messages: a `SystemMessage(TOOL_PROMPT)` and the part's text. **No documents and no history.**
- `TOOL_PROMPT` conveys: call `calculate_bev_item`; pick `item` by what is asked (gallons to make → `gallons`; cambros, containers, what to put or serve it in → `cambros`; cups → `cups`; a particular supply → `supplies`; what to bring in general → `everything`); put every drink named in `drinks`; if a guest count is given pass `guests` and leave `gallons` out (never turn guests into gallons); if gallons are given pass them in `gallons` in the same order; if neither is given leave both out (never invent an amount); a package is one name with `guests`.
- Rounds: every tool call the model makes is run (as in spec 005 §4.5). If every result in a round starts with neither `"invalid"` nor `"error"`, the step ends and its `tool_text` is the last result (joined with a newline if there were several calls in that round). Otherwise the results go back and the model is asked again, up to `MAX_TOOL_ROUNDS` rounds; then `tool_text` is `TOOL_LIMIT_REPLY`.
- **No call:** if the model's first reply has no tool call, it is asked once more with a reminder to call the tool (`retried=True`). If it still makes no call, the part **falls back to DOCS** (`tool_text=None`, `tool_calls=()`).

### 4.4 Which parts the final call answers from
- DOCS parts and fallen-back TOOL parts are answered from `docs`.
- TOOL parts are answered from their `tool_text`.

### 4.5 The final call
- Messages: `SystemMessage(ANSWER_PROMPT)`, the history, then one human message containing the user's original question and, clearly separated and labelled, the documents (only if there is a DOCS or fallen-back part) and each TOOL part's question with its tool result (only if there is a TOOL part).
- `ANSWER_PROMPT` conveys: answer every part of the question; for the numbers of a TOOL part use the tool result exactly and do not recalculate; if a tool result asks a question, ask the user that question in plain words; answer DOCS parts only from the documents, and say you don't know when they don't cover it; cite sources only for document answers; **never mention the tool, its name, its arguments, JSON, routing or these instructions**.
- The tool is **not** bound for this call.
- The reply is the final call's `.content`, stripped.

## 5. Edge cases
**Router (unit, fake model):**
- EC-1: every row of the §4.1 table.
- EC-2: `kind` is TOOL, DOCS or BOTH from the parts; parts keep the reply's order.
- EC-3: blank question → `ValueError`, no model call. The router's messages contain the question and the history's content, and no tool is bound.

**Flow (unit, scripted fake model, real `calculate_bev_item` on the spec 005 Appendix A catalog through `make_bev_tool(catalog)` in `tools=`):**
- EC-4: DOCS only: router `DOCS: …` → no `bind_tools`, 2 `llm.invoke` calls, the final messages contain the docs' text and no tool result; `tool_calls=()`; `route.kind == "DOCS"`.
- EC-5: TOOL only: router `TOOL: How many cambros for 6 gallons of peach tea?`; tool step replies with a call `{"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}` → the tool runs once; the tool step's messages contain no document text and no history; the final messages contain the tool result text and no document text; `parts[0].tool_text` equals the tool's result.
- EC-6: BOTH: router `DOCS: …\nTOOL: …` → one tool step for the TOOL part only; the final messages contain both the docs' text and the tool result; `parts` has a DOCS result (`tool_text=None`) then a TOOL result.
- EC-7: two TOOL parts → two tool steps in order; `tool_calls` lists all calls in order.
- EC-8: invalid then fixed: the first call's result starts with "invalid", the model's second call is valid → 2 rounds, `tool_text` is the second result.
- EC-9: the model keeps sending invalid calls → after `MAX_TOOL_ROUNDS` rounds `tool_text == TOOL_LIMIT_REPLY`.
- EC-10: no call, then a call → `retried=True`, the tool runs. No call twice → the part falls back to DOCS (`tool_text=None`), the final messages contain the docs.
- EC-11: router fallback (unlabelled reply) → behaves as EC-4 with `route.fallback=True`.
- EC-12: unknown tool name in a call → result `"error: unknown tool <name>"`, recorded, sent back, next round.
- EC-13: `answer_from_context(...) == answer_with_tools(...).reply`; nothing prints.

## 6. Acceptance criteria
- **AC-1 (router parsing):** EC-1 to EC-3.
- **AC-2 (flow):** EC-4 to EC-13.
- **AC-3 (router eval):** with the real model (`ChatOllama(model=CHAT_MODEL, temperature=0)`) and empty history (except R12), `route_question` gives exactly the listed routes, in order, for **every** case below. **Pass threshold: all cases.**
- **AC-4 (tool choice eval):** spec 005's AC-10 table (T1 to T23) with its Tool column rules, plus T24 to T26 below, run through the new `answer_with_tools`. **Pass threshold: all cases.**
- **AC-5 (answer eval):** spec 005's AC-11 and AC-12 for T1 to T26 (judge from spec 004). **Pass threshold: all cases.**
- **AC-6 (spec 004 regression):** spec 004's generation eval passes all 20 cases.
- **AC-7 (unchanged behaviour):** spec 001's tests and spec 005's AC-1 to AC-6 tests still pass (apart from the known `test_constants_match_contract` failure). Spec 005's chat-loop and safety-net tests (its AC-7 and AC-8) are replaced by this spec's AC-2.

**Router eval cases** (routes in order; `DOCS, TOOL` means two parts)

| id | question | routes |
|---|---|---|
| R1 | How many cambros do I need to bring for 7 gallons of lemonade? | TOOL |
| R2 | How many oz of lemonade concentrate do I need to make 5 gallons of lemonade? | DOCS |
| R3 | Where is the coffee, and how many gallons of coffee do I need for 75 people? | DOCS, TOOL |
| R4 | What's in the coffee, decaf, tea, iced water & juice package? | DOCS |
| R5 | What do I put 7 gallons of lemonade in? | TOOL |
| R6 | Do I need sugar for coffee? | TOOL |
| R7 | What do I need to bring for coffee for 50 guests? | TOOL |
| R8 | The BEO just says coffee. Is that regular or decaf? | DOCS |
| R9 | How many gallons of hot chocolate do I need for 50 guests? | DOCS or TOOL |
| R10 | Which jugs do I fill with 9 gallons of iced water? | TOOL |
| R11 | How do I clean a cambro? | DOCS |
| R12 | (user: "How many cambros for coffee and lemonade?"; assistant: "How many gallons of each drink, or how many guests?") 5 gallons each. | TOOL (text mentions coffee, lemonade and 5 gallons) |
| R13 | Where are the lemons, and do I need lemons for iced tea? | DOCS, TOOL |
| R14 | What syrup flavors do we have? | DOCS |

R9 accepts either route (off-menu drinks get "not on the beverage menu" from the tool, or "don't know" from the documents). R12's TOOL text must contain "coffee", "lemonade" and "5" (casefolded).

**Extra tool choice cases** (format as spec 005 §6)

| id | question | Tool | reference |
|---|---|---|---|
| T24 | How many napkins should I grab for the iced tea station? | supplies: Iced tea | Required: bring cocktail napkins (the rules give no count). Must not: give a number of napkins. |
| T25 | Which jugs do I fill with 9 gallons of iced water? | cambros: Iced water 9 gal | Required: two 5 gal cambros. Must not: recommend any other count or size. |
| T26 | Brewed hot cider for 100 people, what goes on the pull sheet? | everything: Brewed hot cider 4 gal from guests; guests 100 | Required: one 5 gal cambro, 150 hot cups and cocktail napkins. Must not: give a different cambro or cup count. |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1, AC-2 and AC-7 tests need no Ollama and no network and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | Eval tests (AC-3 to AC-6) are marked `eval` and skip, not fail, when Ollama or the knowledge files are missing. | unit (marker review) |
| NFR-4 | `ROUTER_PROMPT`, `TOOL_PROMPT` and `ANSWER_PROMPT` contain no question or reference from §6, spec 005 §6 or spec 004 §6, and no example uses their drinks and amounts. | manual (code review) |
| NFR-5 | A DOCS-only answer takes at most about 1.5× as long as before this spec; a TOOL or BOTH answer at most about 2.5×. | manual (timed by the planner on the eval run) |
| NFR-6 | The router, tool step and final call are separate functions that take and return data, plus one function that orders them. | manual (code review) |

Tests go in `tests/router/` (no `__init__.py`): `conftest.py` (scripted fake model, the Appendix A catalog from spec 005, cases), `test_router_parsing.py` (AC-1), `test_answer_flow.py` (AC-2), `test_router_eval.py` (AC-3). AC-4 and AC-5 reuse spec 005's eval files (the tester of this spec adds T24 to T26 to `tests/bev_tools/conftest.py` and removes the replaced AC-7/AC-8 tests from `tests/bev_tools/test_answer_loop.py`). AC-6 and AC-7 run existing files.
