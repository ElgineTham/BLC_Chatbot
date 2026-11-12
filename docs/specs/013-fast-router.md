# Spec 013: Router with a tool lookup table (one model call, no rewriting)

- **Status:** approved
- **Date:** 2026-11-12

## 1. Goal
The router decides TOOL, DOCS or BOTH for a question, and for each TOOL part says **which tool**. This spec sets **no time limit**: every test reports how long each stage took, so speed can be improved later.

**The rule.** A part is **TOOL** when its answer is an amount or count **calculated from a quantity** the user gives or must give (how many cambros, cups or gallons; whether and how much of a supply to bring; what goes on the pull sheet; later, how much of each ingredient for N gallons). It is **DOCS** when its answer is text already in a document (where things are, what something is, flavors, cleaning, policies, a recipe as written). One part of each kind makes **BOTH**. Whether the answer *depends on the number* decides it, not whether a number appears ("Where do the 5 gallon cambros go?" is DOCS).

**The design.** The old router asked the model to write the parts' text as JSON; the 7B model changed the user's words (spec 010) and was slow (measured 1.4 to 2.9 s against 0.2 to 0.3 s for a one-word reply). The new router makes **at most one model call per question**, and the model writes only letters:
1. **Code** cuts the question into parts (pieces of the user's own words) and joins a follow-up like "5 gallons each." to the user's previous message. The model never rewrites text.
2. A part with no number and no pull sheet word is DOCS **without the model**.
3. The parts that remain go to the model in **one call**, which answers one letter per part: `T` (TOOL) or `D` (DOCS).
4. **Code picks the tool** for each TOOL part from a **lookup table** (name, one-line purpose, keywords, available or not). Adding a tool later means adding a row.

## 2. Out of scope
- The recipe tool itself (a later spec). Its table row exists with `available=False`, so recipe questions stay DOCS until it is built; flipping the row switches the routing.
- The tool step using the router's tool name (spec 014); streaming, per-stage timing and the 60-test eval (spec 015); judging answers (spec 012); retrieval after routing; the "regular coffee" alias.
- Deleting the old router code (`route_question`, `route_faithfully`, the fidelity check): it stays, unused by the chat flow, with its tests.

## 3. Interface contract

### 3.1 `src/blc/router/` (new modules; `from blc.router import ...`)
```python
from dataclasses import dataclass
from blc.router import RouteDecision, RoutedPart

# RoutedPart gains one field WITH a default (so existing code and tests keep working):
#   tool: str | None = None     # the tool's name for a TOOL part; None for a DOCS part

@dataclass(frozen=True)
class ToolEntry:
    name: str                    # the tool's name as the chat model sees it
    purpose: str                 # one line: what the tool does
    keywords: tuple[str, ...]    # lower case words or phrases that point at this tool
    available: bool              # False: the tool is not built yet; the router never picks it

TOOL_REGISTRY: tuple[ToolEntry, ...] = (
    ToolEntry("scale_recipe",
              "Scales a recipe's ingredient amounts to a number of gallons or guests.",
              ("recipe", "ingredient", "ingredients", "concentrate", "oz", "ounce", "ounces",
               "how to make", "how do i make", "how do we make", "how can i make"),
              False),
    ToolEntry("calculate_bev_item",
              "Calculates beverage pull sheet amounts (gallons, cambros, cups, supplies) for drinks and guest counts.",
              <every word of every item in PULL_SHEET_ITEMS (spec 007), as one flat tuple>,
              True),
)

def pick_tool(text: str, registry: tuple[ToolEntry, ...] = TOOL_REGISTRY) -> str | None: ...
def classifier_prompt(registry: tuple[ToolEntry, ...] = TOOL_REGISTRY) -> str: ...

CLASSIFIER_MAX_TOKENS: int = 8
QUESTION_STARTERS: tuple[str, ...] = (
    "how", "what", "where", "which", "when", "who", "whom", "whose", "why",
    "do", "does", "did", "is", "are", "can", "could", "should", "would", "will", "may",
)
def split_clauses(question: str) -> tuple[str, ...]: ...        # §4.1; () for blank text
def is_follow_up(history: list[dict[str, str]], question: str) -> bool: ...   # §4.2
def quick_label(text: str) -> str | None: ...                    # §4.3: "DOCS" or None
def route_fast(llm, history: list[dict[str, str]], question: str) -> RouteDecision: ...   # §4.5
```
All of these never raise (except `route_fast` on a blank question: `ValueError`, before any model call), do no I/O, and print nothing. Each model call of `route_fast` is one `llm.invoke(messages, **options)`, where every option is a keyword argument (provider options only, e.g. an output limit of `CLASSIFIER_MAX_TOKENS`) and `messages` is `[SystemMessage(classifier_prompt()), HumanMessage(<the clauses, one per line as "1. text">)]`. **No other method of `llm` is called** (no `bind`, `bind_tools`, `with_structured_output`). Test fakes accept extra keyword arguments.

### 3.2 `scripts/chat.py`
```python
CHAT_KEEP_ALIVE: str = "30m"   # main() and scripts/trace_flow.py create the chat model with keep_alive=CHAT_KEEP_ALIVE
```
`answer_with_tools` and `run_turn` (through `run_stages`) get their `RouteDecision` from `route_fast(llm, history, question)` instead of `route_faithfully`. Their signatures and everything after the router are unchanged.

## 4. Inputs and outputs

### 4.1 `split_clauses`
A boundary is allowed in exactly three cases (ignoring case): (1) after a question mark followed by a space and more text; (2) at a semicolon; (3) at the word `and` or `also` (or `and also`, with or without a comma before it) when the text after it begins with a word of `QUESTION_STARTERS` **and the text so far starts with a word of `QUESTION_STARTERS`** (the left side is itself a question). A full stop or `!` is never a boundary: a statement before a question stays attached. Pieces are stripped of spaces and of leading or trailing commas and semicolons, and a leading `and` or `also` is removed; a piece that is empty after that is dropped. Every piece occurs inside the original question.

| Question | Parts |
|---|---|
| Where is the coffee? | (Where is the coffee?) |
| Where is the coffee, and how many gallons of coffee do I need for 75 people? | (Where is the coffee), (how many gallons of coffee do I need for 75 people?) |
| How do I clean a cambro? How many cambros for 8 gallons of iced tea? | (How do I clean a cambro?), (How many cambros for 8 gallons of iced tea?) |
| What flavors of syrup do we have; do I bring sugar for hot water for 30 guests? | (What flavors of syrup do we have), (do I bring sugar for hot water for 30 guests?) |
| I need 5 gallons of coffee and lemonade. How many cambros? | one part: the whole question |
| I need 9 gallons of decaf and hot water, how many containers? | one part (the left side is a statement) |
| How many cambros for coffee and lemonade? | one part (`lemonade` is not a starter) |
| What is the recipe for iced tea for 120 people, and how much do I need? | (What is the recipe for iced tea for 120 people), (how much do I need?) |
| (blank) | () |

### 4.2 `is_follow_up`
`True` when `history` has at least one item with role `user` and non-blank content **and** either the question (ignoring a leading `and`, `also`, `so` or `then`) contains **no** word of `QUESTION_STARTERS` as a whole word, **or** it starts with `what about` or `how about`. Otherwise `False`.

| History | Question | Result |
|---|---|---|
| none | 5 gallons each. | False |
| user: How many cambros do I need for hot water and decaf? / assistant: How many gallons of each drink, or how many guests? | 4 gallons each. | True |
| (same) | 85 guests. | True |
| (same) | And for the orange juice? | True |
| (same) | What about 6 gallons? | True |
| (same) | How many hot cups do I need for 130 guests? | False |
| (same) | I need 9 gallons of decaf. How many cambros? | False |
| only an assistant item | 85 guests. | False |

### 4.3 `quick_label`
`"DOCS"` when the text has **no number** (digits, or spelled out from zero to one hundred as in spec 009 §4.1) **and no word of the pull sheet item set** (`pull_sheet_items_in(text) == ()`, spec 007); otherwise `None`.

| Text | Result |
|---|---|
| Where is the coffee? / What syrup flavors do we have? / Thanks! | `"DOCS"` |
| How many cups do I need for the iced water? / What do I need to bring? / When does setup start for the 6 pm event? | `None` |

### 4.4 The lookup table and `pick_tool`
`pick_tool(text, registry)` looks only at entries with `available=True`, and keywords match as whole words or phrases, ignoring case:
1. If the text contains a keyword of the **scale_recipe** entry: return `"scale_recipe"` if that entry is available, else `None`.
2. Else if it contains a keyword of the **calculate_bev_item** entry: return `"calculate_bev_item"` if available, else `None`.
3. Else `None`.
(With more tools later, step 1 and 2 become a ranking. Entries are looked at in table order; a text that matches an unavailable tool never falls through to another.)

| Text | Result (default table) |
|---|---|
| How many cambros do I need for 7 gallons of lemonade? | `calculate_bev_item` |
| Do I bring sugar for hot water? | `calculate_bev_item` |
| How do I make 3 gallons of lemonade? | `None` (recipe words, tool not available) |
| How much concentrate for 6 gallons of lemonade? | `None` |
| Where is the coffee? | `None` |
| the same "How do I make 3 gallons of lemonade?" with `scale_recipe` available | `scale_recipe` |

`classifier_prompt(registry)` is a non-empty string of at most 1500 characters that contains the `purpose` of every available entry and of no unavailable entry, and the letters `T` and `D`.

### 4.5 `route_fast`
1. **Parts.** If `is_follow_up(history, question)`: one part, the text of the **last user item of the history**, a space, then the question (stripped). Otherwise `split_clauses(question)`.
2. **Quick labels.** `quick_label(part)` gives DOCS to parts that need no model.
3. **One model call** for all the other parts, in order: `HumanMessage` has one line `"{i}. {text}"` per such part, where `i` counts only the parts sent to the model, starting at 1. No call if there are none.
4. **Reading the reply.** Split `.content` on anything that is not a letter, then read tokens in order until one label per sent part is collected: a token made only of the letters `t` and `d` (any case) gives one label per letter (`TD` is T, D); a token that starts with `tool` gives T; a token that starts with `doc` gives D; any other token makes the reply unreadable. Extra tokens after enough labels are ignored. If fewer labels than parts are found, or the reply is unreadable, every part that was sent is DOCS and the decision's `fallback` is `True`.
5. **Tool.** For each TOOL part, `tool = pick_tool(text)`. If it is `None`, the part becomes DOCS. A DOCS part has `tool=None`.
6. **Decision.** `parts` in question order (`RoutedPart(route, text, tool)`); `kind` follows `kind_of`; `unfaithful=False`; `fallback` as in step 4.
At most **one** model call is made per question.

| Question (history none unless noted) | Reply | Decision |
|---|---|---|
| Where is the coffee? | (no call) | DOCS: (DOCS, "Where is the coffee?", None) |
| How many cambros do I need for 7 gallons of lemonade? | `T` or ` Tool.` | TOOL: (TOOL, the question, `calculate_bev_item`) |
| Where is the coffee, and how many cups do I need for 55 guests? | `T` (only the second part is sent) | BOTH: (DOCS, "Where is the coffee"), (TOOL, "how many cups do I need for 55 guests?", `calculate_bev_item`) |
| Where is the creamer kept, and how many cups do I need for 55 guests? | `DT` or `D T` or `DOCS TOOL` | BOTH (both parts are sent: `creamer` and `cups` are item words) |
| (same) | `T` | `fallback=True`, both parts DOCS (one label for two parts) |
| How many cups for 45 guests? | `maybe` | (DOCS, …), `fallback=True` |
| How do I make 3 gallons of lemonade? | `T` | (DOCS, …): `pick_tool` is `None` (recipe tool not available) |
| 4 gallons each. with history (user: How many cambros do I need for hot water and decaf?; assistant: …) | `T` | one TOOL part, text "How many cambros do I need for hot water and decaf? 4 gallons each.", `calculate_bev_item` |
| history (user: Where is the coffee stored?; assistant: …), question And the syrups? | (no call) | one DOCS part "Where is the coffee stored? And the syrups?" |

## 5. Edge cases
**Pure functions (unit):** EC-1 every row of §4.1; EC-2 a question mark at the very end is not a boundary; EC-3 several boundaries give several parts in order; EC-4 extra spaces, newlines and repeated punctuation are stripped; EC-5 every part occurs inside the original question (except stripped ends and a removed leading `and`/`also`); EC-6 `AND` and `HOW` count as the words; EC-7 odd input never raises; EC-8 every row of §4.2; EC-9 history items with blank or non-text `content` or no `role` never raise, and a history of only `summary` items is not a follow-up context; EC-10 every row of §4.3; EC-11 spelled numbers and digits stop the shortcut; EC-12 every word of every item stops the shortcut; EC-13 blank text gives `"DOCS"`; EC-14 every row of §4.4; EC-15 the default table has `scale_recipe` with `available=False` and `calculate_bev_item` with `available=True`, every entry has a non-empty one-line `purpose` (no newline), and `calculate_bev_item`'s keywords equal the words of `PULL_SHEET_ITEMS`; EC-16 `pick_tool` with a custom registry (an extra available entry, or `scale_recipe` available) behaves as §4.4; EC-17 `classifier_prompt` with a custom registry contains its purposes and no unavailable entry's purpose.

**`route_fast` (unit, scripted fake model that records its calls):** EC-18 every row of §4.5; EC-19 at most one model call per question (also with 3 parts to label); EC-20 the call's messages are `[SystemMessage(non-empty), HumanMessage]` with one numbered line per sent part, and the keyword arguments are only provider options; a fake with only `invoke` works; EC-21 blank question raises `ValueError`, no call; EC-22 reply reading: `"TD"`, `"T D"`, `"t,d"`, `"TOOL DOCS"`, `"Tool, docs"`, `"TD because it asks"` all read as T, D; `""`, `"yes"`, `"The answer is T"`, a single letter for two parts, and `"TX"` are unreadable; EC-23 the history is never changed; EC-24 a TOOL part with no item word and no recipe word becomes DOCS (`pick_tool` is `None`); EC-25 `RoutedPart("DOCS", "x")` and `RoutedPart("TOOL", "x")` (two arguments) still work, with `tool=None`.

**Flow (unit, scripted fake model):** EC-26 `answer_with_tools` and `run_turn` call `route_fast` (a scripted first reply `T` makes a tool step); EC-27 a standalone DOCS question with no item word makes no router call; EC-28 `CHAT_KEEP_ALIVE == "30m"`.

## 6. Acceptance criteria
- **AC-1:** `split_clauses`, `is_follow_up`, `quick_label`: §4.1 to §4.3 and EC-1 to EC-13.
- **AC-2 (lookup table):** `TOOL_REGISTRY`, `pick_tool`, `classifier_prompt`: §4.4 and EC-14 to EC-17.
- **AC-3 (router):** `route_fast`: §4.5 and EC-18 to EC-25.
- **AC-4 (flow):** EC-26 to EC-28. The tests of `tests/router/test_answer_flow.py` and `tests/flow/` that script the router's reply are updated by the tester of this spec: the scripted router reply becomes a letter reply where a part needs the model and is dropped where it needs none; **no assertion is weakened and nothing else is changed**. `tests/router/test_flow_fidelity.py` (spec 010's tests that `answer_with_tools` retries and falls back through `route_faithfully`) is **deleted**: the flow no longer uses that router, so that behaviour is replaced by this spec. `route_faithfully`'s own unit tests (`test_router_faithful.py`, `test_router_fidelity.py` and the others that call the old router functions directly) stay.
- **AC-5 (regression):** the spec 004, 006, 007, 009, 010 and 011 unit tests (including the old router tests, which test code that stays, but not the deleted flow test of AC-4) still pass; spec 001's five known `answer_turn` failures and its voice constant failure are the only accepted failures.
- **AC-6 (router eval, real model, timings reported):** with `ChatOllama(model=CHAT_MODEL, temperature=0, keep_alive=CHAT_KEEP_ALIVE)`, after one warm-up call, `route_fast` runs on each case K1 to K31 below, timing each call. **Accuracy:** at least 28 of the 31 cases give the listed kind (and for TOOL parts the listed tool), with the listed number of parts. **Timing:** no limit; the output prints each case's time, parts and tools.

**Cases K** (history none unless listed; the tool for every TOOL part is `calculate_bev_item`)

| id | history | question | kind |
|---|---|---|---|
| K1 | | Where do we keep the napkins? | DOCS |
| K2 | | What does Oatmilk come in? | DOCS |
| K3 | | How do I clean the coffee urn? | DOCS |
| K4 | | When does setup start for the 6 pm event? | DOCS |
| K5 | | Where do the 5 gallon cambros go? | DOCS |
| K6 | | How many cambro sizes do we have? | DOCS |
| K7 | | What's in the coffee, decaf, tea, iced water & juice package? | DOCS |
| K8 | | Thanks! | DOCS |
| K9 | | How many gallons of decaf should I make for 110 people? | TOOL |
| K10 | | Which cambros hold 9 gallons of orange juice? | TOOL |
| K11 | | How many cold cups do I need for 65 guests? | TOOL |
| K12 | | Do I bring creamer for the coffee? | TOOL |
| K13 | | What goes on the pull sheet for peach tea for 45 guests? | TOOL |
| K14 | | How many cups do I need for the iced water? | TOOL |
| K15 | | How many gallons do I make for about 50 people? | TOOL |
| K16 | | What do I need to bring? | TOOL |
| K17 | | Where is the creamer kept, and how many cups do I need for 55 guests? | BOTH: DOCS, TOOL |
| K18 | | How do I clean a cambro? How many cambros do I need for 8 gallons of iced tea? | BOTH: DOCS, TOOL |
| K19 | | What flavors of syrup do we have; do I bring sugar for hot water for 30 guests? | BOTH: DOCS, TOOL |
| K20 | | I need 6 gallons of coffee and orange juice. How many cambros? | TOOL (one part) |
| K21 | | The coffee, decaf, tea, iced water & juice package is for 85 guests. How many cups? | TOOL (one part) |
| K22 | user: How many cambros do I need for hot water and decaf? / assistant: How many gallons of each drink, or how many guests? | 4 gallons each. | TOOL (one part; text contains "hot water", "decaf" and "4 gallons each") |
| K23 | user: How many cups do I need for the orange juice? / assistant: How many guests? | 75 guests. | TOOL (one part; text contains "cups" and "75") |
| K24 | user: Where is the lemon stored? / assistant: In the beverage cooler. | And the syrups? | DOCS (one part; text contains "lemon" and "syrups") |
| K25 | user: Where is the coffee? / assistant: Under the coffee machine in the beverage room. | How many hot cups do I need for 40 guests? | TOOL (one part; text equals the question) |
| K26 | | How do I make lemonade? | DOCS |
| K27 | | How do I make 3 gallons of lemonade? | DOCS (`scale_recipe` is not available) |
| K28 | | How much lemon concentrate do I need for 6 gallons of lemonade? | DOCS (same) |
| K29 | | How do I make lemonade for 90 guests? | DOCS (same) |
| K30 | | How many cambors do I need for 7 gallons of lemonade? | TOOL (a typo; the item word `gallons` is present) |
| K31 | | What is the difference between regular and decaf coffee? | DOCS |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-5 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The AC-6 eval is marked `eval`, skips when Ollama is missing, warms the model first and prints each case's time. | unit (marker review); run output |
| NFR-4 | The classifier prompt contains no question from §6 or from the earlier specs' evals (005 to 011), and no example uses their drinks together with their amounts. | manual (code review) |
| NFR-5 | The pure functions take data and return data (no I/O, no model); `route_fast` only orders them and makes the one call. | manual (code review) |
| NFR-6 | The table is the single source of tool names and purposes: the classifier prompt and `pick_tool` are built from it, not typed twice. | manual (code review) |
| NFR-7 | Times are measured with the model loaded (a warm-up call first); no time limit applies. | manual (planner reads the run output) |
| NFR-8 | Files stay about 250 lines each, split by job (table, clauses, labelling, routing). | manual (code review) |

Tests go in `tests/router/`: `test_clauses.py` (AC-1), `test_registry.py` (AC-2), `test_route_fast.py` (AC-3), `test_route_fast_flow.py` (AC-4, plus the edits to `test_answer_flow.py` and to the scripted routers in `tests/flow/`), `test_fast_router_eval.py` and `conftest.py` additions (AC-6).

## Appendix A: classifier prompt (for the developer; wording not tested)
Built by `classifier_prompt()` from the table (the tool purposes come from it). Keep it **simple and short** (under 1500 characters), plain words, letters only for the reply. A first version with a general definition of T ("calculated from a quantity") got 26 of 31 on the real model: it called some clear tool questions D (a "which cambros hold N gallons" question, a "do I bring a supply" question, a "what goes on the pull sheet" question, a package-for-N-guests question). So the T line should **name the kinds of question**, and a few short examples should show them. Suggested shape:

```text
Label each numbered line. Reply with one letter per line, like TD.
T = a number, or a yes/no about what to bring, worked out by a tool:
{one line per AVAILABLE tool: its purpose}
Use T for: how many cambros, cups or gallons; which cambros hold N gallons; whether to bring a supply (sugar, creamer, napkins); what to bring or what goes on the pull sheet.
D = a lookup in the documents: where things are, what something is, flavors, cleaning, schedules, how something is made or done. A number that does not change the answer is still D.
Examples:
Which cambros hold 12 gallons of hot water? T
Do I need napkins for the cider? T
What goes on the pull sheet for decaf for 80 people? T
Where is the tea kept? D
What does "iced tea with lemon wedges" mean? D
Letters only.
```
Do not use a question or a drink with an amount from the eval cases or from earlier specs' evals in the examples (NFR-4). K16 ("What do I need to bring?", no drink and no quantity) is an edge case: do not bend the prompt to fix it alone.
