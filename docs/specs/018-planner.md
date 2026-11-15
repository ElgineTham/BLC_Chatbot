# Spec 018: Planner: one model call decides TOOL, DOCS or BOTH, and fills the calls

- **Status:** approved (revision 3, done: accepted by the user below the eval thresholds)
- **Date:** 2026-11-14 (revisions 1 to 3: 2026-11-14)

## 1. Goal
Today the router splits the question in code, labels each piece, and a separate tool step fills each piece's arguments seeing only that piece. Context is lost across the split (e.g. "what stuffs do I need to bring" loses "3 gallons of coffee"). This spec builds a **planner**: **one model call** that sees the whole question, the recent chat history and three tools (`search_documents`, `calculate_bev_item`, `scale_recipe`), and answers with tool calls. The calls are the plan. Code derives the route from them: only searches give DOCS, only tools give TOOL, both give BOTH. For BOTH, each call carries its own part: the search query holds the documents part, and the tool arguments hold the tool part. **Nothing is run**: no retrieval, no tool execution, no answer. The deliverable is the planner function plus an **eval of 30 questions (10 per path)** that checks the route, the tools and arguments, and that each part keeps its meaning.

## 2. Out of scope
- Running anything the planner asks for: retrieval, tool execution, the argument check (spec 009), retries, the final answer. These come in a later spec (wiring the planner into a LangGraph flow).
- Any change to `scripts/chat.py`, the chat flow, the router (`blc.router`), the tools (`blc.tools`, including `BEV_TOOL` and its description), the trace, or any existing test outside `tests/planner/`. The planner is not used by the chat yet. (Trimming the real `calculate_bev_item` to match `PLANNER_BEV_TOOL`, and deleting `PLANNER_BEV_TOOL`, is spec 019's job, once the chat uses the planner.)
- A pull sheet chat tool (`make_pull_sheet`), and supply questions answered by a calculator: supply questions are DOCS.
- LangGraph and any new dependency.
- Fixing failures the eval finds: they are findings for a revision of this spec.

## 3. Interface contract

### 3.1 `src/blc/planner/` (new package; `from blc.planner import ...`)
```python
from dataclasses import dataclass
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from blc.tools.bev_tools import BEV_TOOL
from blc.tools.recipe_tools import RECIPE_TOOL

SEARCH_TOOL_NAME = "search_documents"
SEARCH_TOOL: BaseTool
# name == SEARCH_TOOL_NAME; a non-empty description; its argument schema has exactly one
# argument, "query" (a string, required). SEARCH_TOOL.invoke({"query": "x"}) returns ""
# (a placeholder: retrieval is a later spec). What invoke does with other input is unspecified.

PLANNER_BEV_TOOL: BaseTool
# The planner's own view of calculate_bev_item (temporary; deleted in spec 019). It is never run
# by the planner; what invoke does is unspecified. It is a different object from BEV_TOOL, and:
# - name == BEV_TOOL.name ("calculate_bev_item"), so a planned call can later run on the real tool;
# - its argument schema has exactly the properties "item", "drinks", "gallons", "guests";
#   "item" is required and its enum is exactly ["gallons", "cambros", "cups", "everything"]
#   ("supplies" is left out); "drinks", "gallons" and "guests" have the same types as in BEV_TOOL;
# - its description and argument descriptions say: gallons = how many gallons of a drink to make;
#   cambros = which cambros or containers; cups = how many cups; everything = the full pull sheet
#   for drinks with an amount. They never present supply questions or "what to bring" as this
#   tool's job (they contain neither "whether to bring" nor "what to bring"), and they say that
#   how much of an ingredient a batch needs is scale_recipe's job. Any example call in them has no
#   "supplies" item and no amount the example's question didn't give.
# BEV_TOOL itself is unchanged.

PLANNER_TOOLS: tuple[BaseTool, ...] = (SEARCH_TOOL, PLANNER_BEV_TOOL, RECIPE_TOOL)
# in this order; RECIPE_TOOL is the very object from blc.tools.recipe_tools

PLAN_ROUTES: tuple[str, ...] = ("TOOL", "DOCS", "BOTH")

PLANNER_PROMPT: str
# the planner's system prompt (§3.2)

@dataclass(frozen=True)
class PlannedCall:
    name: str                  # one of the PLANNER_TOOLS names
    args: dict[str, object]    # the arguments, as the model sent them (§4.2)

@dataclass(frozen=True)
class Plan:
    route: str                       # one of PLAN_ROUTES
    calls: tuple[PlannedCall, ...]   # never empty
    fallback: bool                   # True when the model made no usable call (§4.2)

def plan_question(
    llm: BaseChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> Plan:
    """Plan one question. Raises ValueError if question is empty or whitespace-only,
    before any call on llm. Errors raised by the model propagate unchanged."""
```

**How the model is used** (tests use a scripted fake model):
- `plan_question` calls `llm.bind_tools(list(PLANNER_TOOLS))` **exactly once** and calls `invoke` on the object it returns **exactly once**, with a list of messages.
- That list's first message is `SystemMessage(content=PLANNER_PROMPT)`, and its last message is a `HumanMessage` whose content contains the question with its leading and trailing whitespace removed.
- When `history` is non-empty, the content of every history item (`{"role": "user" | "assistant" | "summary", "content": str}`) appears verbatim somewhere in the messages. How the history is laid out is the developer's choice.
- The model's reply is normally an `AIMessage`. The planner reads only its `tool_calls` attribute (a list of `{"name", "args", "id"}` dicts): those calls are the plan. Any object with that attribute must work, including ones whose `args` is not a dict (EC-9). Any text content is ignored.

### 3.2 `PLANNER_PROMPT`
The prompt is short and has **three rules, in this order, each followed by its two examples**. The wording around them is the developer's, but the three rules must say what is below, and the **six example questions must appear verbatim**, each with the call(s) shown.

1. **TOOL: the answer has to be worked out or calculated** (a number from an amount, or a recipe scaled or given). Use `calculate_bev_item` or `scale_recipe`.
   - "How many cups do I need for 70 guests?" → `calculate_bev_item {"item": "cups", "guests": 70}`
   - "How much lemon concentrate for 8 gallons of lemonade?" → `scale_recipe {"recipe": "lemonade", "gallons": 8}`
2. **DOCS: the answer can be looked up, because it is written down.** Use `search_documents`.
   - "Where are the lemons kept?" → `search_documents {"query": "where are the lemons kept"}`
   - "Should I bring creamer for decaf?" → `search_documents {"query": "should I bring creamer for decaf"}`
3. **BOTH: one call per part. Label each part as TOOL or DOCS, and make sure no part loses its meaning.** A search query must stand on its own: it carries the drink or thing the part is about, even when the user only wrote it in another part, but not the tool part's amounts.
   - "How many cambros for 4 gallons of coffee and what to bring?" → `calculate_bev_item {"item": "cambros", "drinks": ["coffee"], "gallons": [4]}` and `search_documents {"query": "what to bring for coffee"}`
   - "Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?" → `search_documents {"query": "where is the orange juice concentrate"}` and `scale_recipe {"recipe": "orange juice", "gallons": 8}` (the tool part's "how much" means the concentrate named in the other part, so it is `scale_recipe`, not `calculate_bev_item` item `gallons`)

The prompt also states, briefly, the argument rules of §4.1 (context, no invented amounts, guests stay guests). It also states, under Rule 1, this **"how much" rule**: "how much … for N gallons of a drink" asks for ingredient amounts, so it is `scale_recipe`, even when the ingredient is named only in another part or in the history. `calculate_bev_item` item `gallons` answers only "how many gallons to make". "What goes on the pull sheet" with an amount is item `everything`. No new example question is added for this rule.

No CLI, no files read or written, no environment variables.

## 4. Inputs and outputs

### 4.1 What the planner must decide
The planner decides by **whether a part's answer must be worked out or can be looked up**, not by the topic it mentions. The eval checks these choices:

| Kind of question | Path | Call |
|---|---|---|
| A number worked out from an amount: gallons to make, cambros, cups | TOOL | `calculate_bev_item` (item `gallons` / `cambros` / `cups`) |
| The full pull sheet for drinks **with an amount** | TOOL | `calculate_bev_item` item `everything` |
| How to make a drink, or ingredient amounts for a batch (with or without an amount), including "how much do I need for N gallons of a drink" | TOOL | `scale_recipe` |
| Where something is kept or goes | DOCS | `search_documents` |
| What something is: menu, package contents, flavors | DOCS | `search_documents` |
| How to do something: clean, set up, pull stock, serve | DOCS | `search_documents` |
| Written rules and facts, including **what to bring** and **whether to bring a supply**, when no count is needed ("Should I bring lemons for the iced tea?", "When do we bring hot cups?", "What supplies do I need for coffee and hot water?") | DOCS | `search_documents` |

Rules the plan must follow:
- **One call per part asked.** No part is dropped, and nothing that wasn't asked is added. Two TOOL parts give two tool calls.
- **Context:** drinks, recipes and amounts come from the whole question and the recent history, not only from the words of one part. For example, "how many cambros do I need for **it**" uses the drink named earlier, and "5 gallons each." uses the drinks of the previous user message. The same holds for search queries: "and what to bring?" after "4 gallons of coffee" searches "what to bring for coffee".
- **No invented amounts:** only amounts the user wrote. A guest count is passed as `guests`, never turned into gallons. A part with no amount leaves `gallons` and `guests` out. A cups question with no drink named passes no drinks.
- **Separate parts in BOTH:** the search query carries the documents part's meaning and key words (it may be reworded), and none of the tool part's amounts. The tool arguments carry the tool part's drinks and amounts.

### 4.2 From the model's reply to a `Plan`
| Model reply | `Plan` |
|---|---|
| Only `search_documents` calls | `route="DOCS"`, the calls in order, `fallback=False` |
| Only `calculate_bev_item` / `scale_recipe` calls | `route="TOOL"`, the calls in order, `fallback=False` |
| At least one search and at least one tool call | `route="BOTH"`, the calls in order, `fallback=False` |
| No calls, or only calls whose name is not a `PLANNER_TOOLS` name | `route="DOCS"`, `calls=(PlannedCall("search_documents", {"query": <question, stripped>}),)`, `fallback=True` |

- Calls with a name that is not a `PLANNER_TOOLS` name are **dropped**. The others are kept in the model's order. Duplicate calls are kept.
- A call whose `args` is not a dict gets `{}`.
- A `search_documents` call's args are always exactly `{"query": <text>}`, and any other keys are dropped. `<text>` is the query as the model sent it when that is a non-blank string; otherwise (missing, not a string, blank, or `args` not a dict) it is the question, stripped. Repairing a query does not make it a fallback: `fallback` stays False.
- `calculate_bev_item` and `scale_recipe` args are kept **exactly as the model sent them**, including values the tools would reject (e.g. `"gallons": []`, `"guests": 0`). Checking them is a later spec.

### 4.3 How an eval case is scored
Each case runs `plan_question(llm, question, history)` with `llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)` (constants imported from `chat`). The scorer is a pure function of the case and the returned `Plan`. A case **passes** when all three checks pass:

1. **Route:** `plan.route` equals the case's route.
2. **Tool calls:** the plan's tool calls (all calls not named `search_documents`) match the case's expected calls **as a multiset**: the order doesn't matter, each expected call matches exactly one actual call, and there are no extra tool calls. A DOCS case expects zero tool calls. Two calls match when the names are equal and:
   - **`calculate_bev_item`:**
     - `item` is equal.
     - **Drinks:** compared as a multiset of names, stripped and casefolded. A missing, `null` or empty `drinks` means no drinks.
     - **Gallons:** a missing, `null` or empty `gallons` means none. One number with several drinks applies to each drink. Otherwise the numbers pair with the drinks by position, and the multiset of (drink, gallons) pairs must be equal. A count that is neither 1 nor the number of drinks is a mismatch.
     - **Guests:** a missing or `null` `guests` means none.
   - **`scale_recipe`:**
     - `recipe` is equal after stripping and casefolding.
     - `gallons` is a single number. A missing or `null` value, or an empty list, means none. A one-item list counts as its number, and any longer list is a mismatch.
     - `guests`: a missing or `null` value means none.
   - **Numbers** are equal by value (`6 == 6.0`; a numeric string counts as its number; a boolean is never a number). Keys not listed here are ignored.
3. **Search queries:** the case's route decides the rule.
   - **TOOL case:** no `search_documents` call.
   - **DOCS and BOTH cases:**
     - At least one `search_documents` call.
     - **keep:** for each *keep* group, at least one of its terms appears as a substring of the casefolded `query` texts of all searches joined together. Terms are lower case; a term like `stor` matches "store", "stored" and "storage".
     - **drop:** no *drop* term appears in any single query as a whole word or phrase, ignoring case. A number matches only as a whole number, so `6` does not match "16".

`LOC` below stands for the keep group `where | locat | kept | stor | find | plac`.

**Run and thresholds:** the eval runs all 30 cases **once** (the model runs at temperature 0; revision 1's three runs were identical). A path passes when it scores at least **9 of 10** (T1 to T10, D1 to D10, M1 to M10). No threshold, but reported: the route accuracy per path, and the planner call time per case and on average.

## 5. Edge cases
**Planner (unit, scripted fake model, no Ollama):**
- EC-1: `SEARCH_TOOL.name == "search_documents"`; its argument schema's properties are exactly `{"query"}`, of string type, and `query` is required; `SEARCH_TOOL.invoke({"query": "x"}) == ""`. `PLANNER_TOOLS` is `(SEARCH_TOOL, PLANNER_BEV_TOOL, RECIPE_TOOL)` by identity. `PLAN_ROUTES == ("TOOL", "DOCS", "BOTH")`.
- EC-1b: `PLANNER_BEV_TOOL`:
  - `PLANNER_BEV_TOOL is not BEV_TOOL` and `PLANNER_BEV_TOOL.name == BEV_TOOL.name == "calculate_bev_item"`.
  - Its schema's properties are exactly `{"item", "drinks", "gallons", "guests"}`, `item` is required, and the `item` enum is exactly `["gallons", "cambros", "cups", "everything"]`.
  - Its description and argument descriptions contain neither "whether to bring" nor "what to bring" (ignoring case), and do not contain the word `supplies` as an item value in an example call.
  - `BEV_TOOL`'s `item` enum still contains `"supplies"`: the real tool is unchanged.
- EC-2: `PLANNER_PROMPT` contains `search_documents`, `calculate_bev_item` and `scale_recipe`. It also contains each of the six example questions of §3.2 verbatim, plus the example queries `what to bring for coffee` and `where is the orange juice concentrate`. The TOOL examples appear before the DOCS examples, which appear before the BOTH examples.
- EC-3: "Where is the coffee?" with a fake whose reply is `search_documents {"query": "where is the coffee"}`:
  - `bind_tools` is called once, with a list equal to `list(PLANNER_TOOLS)`, and `invoke` is called once.
  - The first message is `SystemMessage(PLANNER_PROMPT)`; the last is a `HumanMessage` containing "Where is the coffee?".
  - Result: `Plan("DOCS", (PlannedCall("search_documents", {"query": "where is the coffee"}),), False)`.
- EC-4: history `[{"role": "user", "content": "How many cambros for coffee and decaf?"}, {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"}]`, question "5 gallons each." → both history contents and "5 gallons each." appear in the messages sent. A `summary` item's content appears too. `history=None` and `history=[]` both work.
- EC-5: reply with two calls, `calculate_bev_item {"item": "cambros", "drinks": ["peach tea"], "gallons": [7]}` then `scale_recipe {"recipe": "lemonade", "gallons": 4}` → `route="TOOL"`, both calls in that order, args equal to those sent.
- EC-6: reply `search_documents {"query": "where are the cambros kept"}` then `calculate_bev_item {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}` → `route="BOTH"`, two calls in that order. The tool call first, then the search, also gives BOTH.
- EC-7: reply with no tool calls (text only: "The coffee is under the machine.") for "  Where is the coffee?  " → `Plan("DOCS", (PlannedCall("search_documents", {"query": "Where is the coffee?"}),), True)`.
- EC-8: reply with only `make_coffee {"x": 1}` → fallback as EC-7. Reply with `make_coffee {...}` then `calculate_bev_item {"item": "cups", "guests": 45}` → `route="TOOL"`, one call (the bev call), `fallback=False`.
- EC-9: `search_documents` call with args `{}`, `{"query": ""}`, `{"query": "   "}`, `{"query": 5}`, `{"query": "", "k": 3}` or `None` (not a dict) → that call's args become `{"query": <question, stripped>}`, and `fallback` is False. A valid query with extra keys, `{"query": "coffee", "k": 3}` → `{"query": "coffee"}`. A `calculate_bev_item` call whose args is `None` → `{}`. (`args=None` can't be put in an `AIMessage`, so these replies are plain objects with a `tool_calls` attribute, §3.1.)
- EC-10: tool args the tools would reject are kept unchanged: `calculate_bev_item {"item": "supplies", "drinks": ["coffee"], "guests": 0, "gallons": []}` → `PlannedCall` args equal to exactly that dict.
- EC-11: two identical `search_documents` calls → both kept, `route="DOCS"`.
- EC-12: question `""`, `"   "` or `"\n\t"` → `ValueError`, and neither `bind_tools` nor `invoke` was called.
- EC-13: a fake whose `invoke` raises `RuntimeError("boom")` → `plan_question` raises that `RuntimeError`.

**Scorer (unit, hand-made plans, no model):** the scoring of §4.3 is a pure function, tested on its own:
- EC-14: for M1: a plan with `search_documents {"query": "Where are the cambros kept?"}` and `calculate_bev_item {"item": "cambros", "drinks": ["Iced Tea "], "gallons": [6.0]}` passes. The same calls in the other order pass.
- EC-15: wrong route (M1's calls without the search) fails on route and on search queries. A DOCS case plan with an extra tool call fails on tool calls. A TOOL case plan with an extra search fails on search queries.
- EC-16: tool-call mismatches fail:
  - wrong `item`;
  - a missing drink;
  - an extra drink;
  - gallons swapped between two drinks (T1 with `[3, 7]` for `["peach tea", "hot water"]`);
  - invented `guests` (T1 with an extra `"guests": 60`);
  - a missing call (T8 with only the recipe call);
  - an extra call;
  - a `scale_recipe` call with `"gallons": [4, 4]` (T8);
  - the M3 tool part sent to the wrong tool: `calculate_bev_item {"item": "gallons", "drinks": ["lemonade"], "gallons": [3]}` instead of `scale_recipe`.
- EC-17: equivalences that pass:
  - `"gallons": [5]` for two drinks equals `[5, 5]`;
  - `"gallons": []` or `null` equals no gallons;
  - `"guests": null` equals no guests;
  - `"gallons": ["6"]` equals `[6]`;
  - a `scale_recipe` `"gallons": 4`, `4.0` or `[4]` all equal 4, and `"gallons": []` equals no gallons (T6);
  - unknown extra keys are ignored;
  - drink names differing only in case and outer spaces match.
- EC-18: search checks:
  - A missing *keep* group fails: the M1 query "cambro storage" passes `LOC` through `stor`, while the query "iced tea" fails.
  - A *drop* term present fails: the M1 query "where are the cambros for 6 gallons" fails. The *drop* term `6` does not match "16".
  - M5: the query "what do I need to bring" fails, because the `coffee` group is missing; that's the lost-meaning case. "what to bring for coffee" passes.
  - D3: "5 gallon cambros placement" passes (`plac`). D10: "What if there are no syrups?" passes (`no syrup`).

## 6. Acceptance criteria
- **AC-1 (constants, planner tools and prompt):** EC-1, EC-1b, EC-2.
- **AC-2 (model use):** EC-3, EC-4, and the stripped question in EC-7.
- **AC-3 (route from calls):** EC-3, EC-5, EC-6.
- **AC-4 (fallback and cleaning):** EC-7 to EC-11.
- **AC-5 (errors):** EC-12, EC-13.
- **AC-6 (scorer):** EC-14 to EC-18.
- **AC-7 (eval, TOOL):** at least 9 of T1 to T10 pass (§4.3, one run).
- **AC-8 (eval, DOCS):** at least 9 of D1 to D10 pass.
- **AC-9 (eval, BOTH):** at least 9 of M1 to M10 pass.
- **AC-10 (eval report):** the eval prints one line per case: id, pass or fail, the failed checks as `failed=<names>` (`route`, `tools`, `search`, or `-`), the route, the call time, and every call's name and args. It ends with the pass count and route accuracy per path and the average call time.
- **AC-11 (regression):** no existing file outside `tests/planner/` and `src/blc/planner/` is changed. Every other unit test passes unchanged. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's uncommitted `DIDNT_CATCH` change).

### Eval cases
History is none unless listed. Abbreviations:
- `bev(item; drinks with gallons; guests)` is a `calculate_bev_item` call;
- `rec(recipe; gallons; guests)` is a `scale_recipe` call;
- "–" means left out.

The search checks apply to D and M cases.

**Cases T: TOOL (no search allowed)**
| id | question | expected tool calls |
|---|---|---|
| T1 | How many cambros do I need for 7 gallons of peach tea and 3 gallons of hot water? | bev(cambros; peach tea 7, hot water 3; –) |
| T2 | How many gallons of coffee should I make for 160 guests? | bev(gallons; coffee; 160) |
| T3 | How many cups for 45 guests? | bev(cups; no drinks; 45) |
| T4 | What goes on the pull sheet for 6 gallons of orange juice? | bev(everything; orange juice 6; –) |
| T5 | How many cups for iced tea and lemonade for 90 guests? | bev(cups; iced tea, lemonade; 90) |
| T6 | How do I make lemonade? | rec(lemonade; –; –) |
| T7 | How do I make lemonade for 60 guests? | rec(lemonade; –; 60) |
| T8 | How do I make 4 gallons of lemonade and how many cambros do I need for it? | rec(lemonade; 4; –), bev(cambros; lemonade 4; –) |
| T9 | history: user "How many cambros do I need for brewed hot cider?" / assistant "How many gallons of each drink, or how many guests?"; question "For 75 guests." | bev(cambros; brewed hot cider; 75) |
| T10 | history: user "How many cambros for coffee and decaf?" / assistant "How many gallons of each drink, or how many guests?"; question "5 gallons each." | bev(cambros; coffee 5, decaf 5; –) |

**Cases D: DOCS (no tool call allowed)**
| id | question | keep groups |
|---|---|---|
| D1 | What supplies do I need for coffee and hot water? | `coffee`; `hot water`; `suppl` or `bring` or `need` |
| D2 | Should I bring lemons for the iced tea? | `lemon`; `iced tea` |
| D3 | Where do the 5 gallon cambros go? | `cambro`; `5`; LOC or `go` (LOC includes `plac`) |
| D4 | Is lemonade served in a cambro? | `lemonade`; `cambro`; `serv` |
| D5 | What flavors of syrup do we have? | `syrup`; `flavor` |
| D6 | history: user "How many cambros for coffee, iced water, and hot water?" / assistant "How many gallons of each drink, or how many guests?"; question "Never mind that. What do I need to bring for them?" | `coffee`; `iced water`; `hot water`; `bring` or `need` or `suppl` |
| D7 | What's in the coffee, decaf, tea, iced water & juice package? | `package` |
| D8 | How do I pull stock of concentrates? | `concentrate`; `pull` or `stock` |
| D9 | When do we bring hot cups? | `hot cup`; `when` or `bring` or `rule` |
| D10 | history: user "Where are the syrups?" / assistant "Above the lemons in the beverage cooler, near the sink by the coffee machine (data/supplies/syrups.md)."; question "What if there are none there?" | `syrup`; `backup` or `none` or `else` or `other` or `empty` or `out of` or `no syrup` or `not found` or `not there` |

D cases have no *drop* terms.

**Cases M: BOTH (one tool part, one documents part)**
| id | question | expected tool calls | keep groups | drop |
|---|---|---|---|---|
| M1 | Where are the cambros kept and how many do I need for 6 gallons of iced tea? | bev(cambros; iced tea 6; –) | `cambro`; LOC | `6` |
| M2 | How many cups for coffee for 80 guests, and where are the hot cups stored? | bev(cups; coffee; 80) | `hot cup`; LOC | `80` |
| M3 | Where is the lemon concentrate, and how much do I need for 3 gallons of lemonade? | rec(lemonade; 3; –) | `concentrate`; LOC | `3` |
| M4 | How many cambros for 4 gallons of decaf, and where is the oatmilk? | bev(cambros; decaf 4; –) | `oatmilk` or `oat milk`; LOC | `4` |
| M5 | How many cambros to bring for 3 gallons of coffee and what stuffs do I need to bring | bev(cambros; coffee 3; –) | `coffee`; `bring` or `stuff` or `need` or `suppl` | `3` |
| M6 | What flavors of concentrate do we have, and how do I make 5 gallons of lemonade? | rec(lemonade; 5; –) | `concentrate`; `flavor` | `5` |
| M7 | Is iced tea served in a cambro, and how many gallons of iced tea do I make for 120 guests? | bev(gallons; iced tea; 120) | `iced tea`; `cambro` | `120` |
| M8 | How many cups for peach tea for 40 guests, and do we bring lemons for it? | bev(cups; peach tea; 40) | `lemon`; `peach tea` | `40` |
| M9 | Where do the 5 gallon cambros go, and how many cambros do I need for 12 gallons of orange juice? | bev(cambros; orange juice 12; –) | `cambro`; `5`; LOC or `go` | `12` |
| M10 | history: user "How do I make 2 gallons of lemonade?" / assistant "Use 14 oz of lemon concentrate and fill with water to 2 gallons."; question "Where is the concentrate kept, and how much do I need for 6 gallons instead?" | rec(lemonade; 6; –) | `concentrate`; LOC | `6` |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-6 tests need no Ollama and no network, and read nothing under `data/` or `.chroma/`. | unit (review by test-evaluator) |
| NFR-3 | The eval (AC-7 to AC-10) is marked `eval` and skips, not fails, when Ollama is not running. It warms the model up with one call first. It needs no Chroma store and reads nothing under `data/`. | unit (marker review); run output |
| NFR-4 | `PLANNER_PROMPT`, `SEARCH_TOOL`'s description and `PLANNER_BEV_TOOL`'s descriptions contain no eval question (T1 to M10) word for word. The prompt's examples are only those of §3.2. No example in any of them shares a drink-and-amount pair with an eval case. | unit (questions not in the texts); manual (examples) |
| NFR-5 | The package follows `CLAUDE.md`'s code structure: split by purpose, no catch-all modules, no imports from `scripts/`, about 250 lines per file. | manual (code-evaluator) |
| NFR-6 | The planner makes exactly one model call per question. The average call time is reported (no threshold). | unit (EC-3); eval report |
| NFR-7 | The eval's scorer (§4.3) is a pure function of a case and a `Plan`, so it is unit-tested (EC-14 to EC-18) without a model. | unit |

Tests go in `tests/planner/` (no `__init__.py`):
- `conftest.py`: the scripted fake model, the 30 cases and the scorer;
- `test_plan.py`: AC-1 to AC-5;
- `test_scorer.py`: AC-6;
- `test_planner_eval.py`: AC-7 to AC-10.

## Revision history
**Revision 1 (2026-11-14).** The first run passed DOCS 9/10 but missed TOOL (8/10) and BOTH (8/10). All unit behaviour passed except one test bug. The path rule is now **"worked out → TOOL, written down → DOCS"**: what to bring and whether to bring a supply are DOCS when no count is needed.

1. **New prompt structure (§3.2):** the prompt is now three rules (TOOL, DOCS, BOTH), each with two fixed examples. The BOTH examples show a search query that keeps its meaning ("what to bring" becomes "what to bring for coffee").
   - Developer: rewrite `PLANNER_PROMPT` to §3.2.
2. **§4.1 table:** the "whether to bring a named supply → TOOL" and "what to bring in general → TOOL" rows are gone. Both are now DOCS when no count is needed. `everything` is used only for the pull sheet with an amount.
3. **Eval cases re-sorted, still 10 per path:**

   | Change | Cases |
   |---|---|
   | New TOOL cases | T4 (pull sheet, orange juice), T5 (cups for two drinks), T9 (guests follow-up) |
   | DOCS cases replaced | D1 → a supplies list for two drinks; D2 → the lemons question (was T4); D6 → a what-to-bring follow-up (replaces old T9) |
   | Old T5 → BOTH | becomes M5: "what stuffs to bring" is a DOCS part, and the search must keep `coffee` |
   | BOTH cases replaced | M5 → old T5 (the old M5 was two DOCS parts); M8 → a cups + lemons question (the old M8's "what to bring" part is now DOCS) |
   | Removed | "any of" alternatives in expected calls (no case needs them) |
4. **Clarifications:**
   - `SEARCH_TOOL.invoke` on other input is unspecified.
   - Replies may be any object with `tool_calls`.
   - A repaired search query is not a fallback, including non-dict search args.
   - Recipe `gallons` is a single number (a one-item list counts).
   - Booleans are not numbers.
   - Drop terms are checked per query.
5. **Eval:** runs 3 times. A path passes with ≥ 9/10 in at least 2 of 3 runs. The report shows all three runs.
6. **Tester:**
   - Update the cases and scorer tests (EC-16 to EC-18) to match.
   - Remove `test_search_tool_rejects_missing_query` (it was not in the spec).
   - Replace `test_prompt_names_missing_tool_would_fail` with the EC-2 checks.
   - Loosen `test_question_is_stripped_in_human_message`: the content contains the stripped question; don't require the whole content to have no outer whitespace.
   - Make `test_report_content` check the failed-check names, route, time and call names in each case line.

**Revision 2 (2026-11-14).** Revision 1's eval scored TOOL 9/10, DOCS 7/10 and BOTH 7/10. The three runs were identical.
- **Scorer too strict (2 cases).** The model kept the meaning, but my keep words missed it: D3 "placement", D10 "no syrups".
- **Tool description conflict (2 cases).** The shared `BEV_TOOL` description says supplies and "what to bring" are its job, which contradicts Rule 2. The model followed it: D1 → `supplies`; M5 → `supplies` with invented `guests: 30`.
- **"How much … N gallons" sent to the beverage tool (3 cases).** M3 and M10 went to item `gallons` instead of `scale_recipe`, and T4 went to `gallons` instead of `everything`.
- **Unit tests.** The only failure was the undefined case of a valid search query with extra keys.

Supply questions stay DOCS (user decision).

1. **`PLANNER_BEV_TOOL` (§3.1, EC-1b):** the planner gets its own view of `calculate_bev_item`. It has the same name and arguments, with `item` limited to gallons, cambros, cups and everything. Its descriptions match the path rule. `PLANNER_TOOLS` uses it instead of `BEV_TOOL`, which is unchanged. Spec 019 trims the real tool and deletes this view.
2. **"How much" rule (§3.2, §4.1):** one rule line under Rule 1, with no new example.
3. **Search args (§4.2, EC-9):** always exactly `{"query": ...}`. Extra keys are dropped, also for a valid query.
4. **Scorer:**
   - `LOC` gains `plac`; D10 gains `no syrup`.
   - An empty recipe `gallons` list means none.
   - EC-16 adds the M3 wrong-tool case.
5. **Eval:** one run, at least 9/10 per path. The report puts the failed checks in a `failed=` field.
6. **Developer:**
   - add `PLANNER_BEV_TOOL` and use it in `PLANNER_TOOLS`;
   - add the "how much" rule to the prompt;
   - drop extra keys from valid search calls.
7. **Tester:**
   - EC-1 and EC-1b tests;
   - update the EC-9 extra-keys test (keys dropped);
   - the EC-16, EC-17 and EC-18 additions;
   - the D3 and D10 keep words;
   - one eval run;
   - in `test_report_content`, assert the exact `failed=` field.

**Revision 3 (2026-11-14).** Revision 2's eval scored TOOL 9/10, DOCS 9/10 and BOTH 7/10, with 100% route accuracy on every path. The three BOTH misses all need meaning carried from another part:
- M3 and M10 ("how much do I need for N gallons of lemonade" → `calculate_bev_item` gallons instead of `scale_recipe`);
- M5 (search "what stuffs do I need to bring" without `coffee`).

D10 failed on a narrow keep list ("syrups are not found"). The unit tests all passed, but the test-evaluator found one missing EC-17 case.
1. **Second BOTH example in §3.2 replaced:** it is now "Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?" → search + `scale_recipe {"recipe": "orange juice", "gallons": 8}`. It shows the cross-part "how much" case. The first BOTH example (`what to bring for coffee`) is unchanged. EC-2's example queries are unchanged.
   - Developer: update the example in `PLANNER_PROMPT`. Nothing else changes.
2. **D10 keep group** gains `not found` and `not there`.
3. **Tester:**
   - Update the EC-2 example text.
   - Update D10's keep group.
   - Add the missing EC-17 case: a `scale_recipe` call with `"gallons": []` equals no gallons (T6).
   - Make the quality fixes from revision 2's test review:
     - the "how much" prompt test checks the rule text, not just "how much";
     - `test_report_content` checks each call's args, not only its name;
     - the arg-type comparison compares whole property dicts (without `description`/`title`);
     - `test_plan_is_frozen` expects `dataclasses.FrozenInstanceError`;
     - a valid search query with outer spaces is kept as sent (EC-9).

**Closing note (2026-11-14).** Revision 3's final run:

| Check | Result |
|---|---|
| TOOL | 8/10 (T2 and T9 failed) |
| DOCS | 10/10 |
| BOTH | 8/10 (M2 and M8 failed) |
| Route accuracy | 90% TOOL, 100% DOCS, 100% BOTH |
| Unit tests | 156/156; full suite 2848 passed, with only the accepted `DIDNT_CATCH` failure |

The user accepted this as correct enough and closed the spec below AC-7 and AC-9's thresholds.
- **Known weakness:** with a guest count, the model tends to drop the named drink (T2, M2, M8). Revision 3 removed the only prompt example that showed a drink together with guests.
- **T9:** made no call for a guests-only follow-up.
- **Possible future fix:** give the cups example a drink, or try `qwen2.5:14b` as the planner model.
