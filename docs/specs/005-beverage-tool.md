# Spec 005: Beverage calculator tool in the chatbot

- **Status:** approved (revision 3)
- **Date:** 2026-11-11 (revision 1 and revision 2: 2026-11-11)

## 1. Goal
The chatbot answers pull sheet number questions (gallons, cambros, cups, supplies) by reading the knowledge files, and a 7B model sometimes reads them wrong (spec 004: "one 1 gal cambro" for 3 gallons). This spec gives the chatbot a calculator tool, `calculate_bev_item`, that computes these answers with the existing, tested pull sheet code (specs 002/003) and the same JSON menu and rules. The model decides from each question whether to call the tool, fills in its arguments, and phrases the result. Questions that are not pull sheet calculations (locations, recipes, menu meanings) keep using retrieval (RAG) as today, and one question can use both. The chat flow is split into small steps so a later move to LangGraph is a rewiring, not a rewrite. Later sections (food, serving utensils) will each add one tool of the same shape.

The tool's arguments are **flat and simple** (§3.3) so that a 7B model (qwen2.5:7b) can fill them in reliably, and the tool accepts the common wrong shapes such a model produces (§4.0).

## 2. Out of scope
- LangGraph. Other pull sheet sections and their tools. Reading BEO files or photos in chat.
- Any change to `src/blc/pull_sheet/` behaviour or its public interface, or to `scripts/pull_sheet.py`.
- Any change to the knowledge files or to `ingest.py`. (Trimming the number tables from `data/pull_sheet/rules/beverages.md` is a planner decision after this spec's eval results.)
- Any change to `blc.judge` (that is spec 004 revision 2).
- Changing models, `TOP_K`, chunking, or the temperature used by `main()`.
- Storing tool calls in chat history (history keeps only user and assistant text, as today).
- Units other than gallons and "each" (e.g. quarts, liters).
- Parsing amounts out of free text inside an argument (e.g. a drink named "7 gallons of lemonade").

## 3. Interface contract

### 3.1 The calculator: `src/blc/tools/bev_tools/` (feature package)
Everything below is importable as `from blc.tools.bev_tools import ...`. `src/blc/tools/__init__.py` is empty; later sections add sibling packages (e.g. `src/blc/tools/food_tools/`).

```python
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from langchain_core.tools import BaseTool
from blc.pull_sheet import Catalog, PullLine

BEV_TOOL_NAME = "calculate_bev_item"
BEV_ITEMS: tuple[str, ...] = ("gallons", "cambros", "cups", "supplies", "everything")
BEV_STATUSES: tuple[str, ...] = ("ok", "need_info", "not_on_menu", "invalid")

@dataclass(frozen=True)
class DrinkRequest:
    menu: str                      # a drink or package name as the user said it
    quantity: float | None = None  # amount of this drink, if the user gave one
    unit: str | None = None        # "gallon"/"gallons"/"gal" or "each" (case-insensitive); None = the item's own unit

@dataclass(frozen=True)
class DrinkAmount:
    drink: str          # menu display name, e.g. "Coffee"
    amount: Fraction    # gallons for gallon items, pieces for each items
    unit: str           # "gallon" or "each" (blc.pull_sheet.GALLON / EACH)
    from_guests: bool   # True if the amount was worked out from `guests`

@dataclass(frozen=True)
class BevResult:
    status: str                       # one of BEV_STATUSES
    text: str                         # what the tool returns to the chat model (§4.4)
    drinks: tuple[DrinkAmount, ...]   # resolved drinks with the amounts used, in request order; () unless status is "ok"
    lines: tuple[PullLine, ...]       # pull lines answering the item (§4.3); () unless status is "ok"
    not_on_menu: tuple[str, ...]      # requested names not on the menu, stripped, in request order
    gallons_each: int | None          # item "gallons" with no drinks: gallons per drink for `guests`; else None
    cups_each: int | None             # NEW: item "cups" with no drinks: cups (guests + extras) for `guests`; else None

def calculate_bev_item(
    item: str,
    drinks: Sequence[DrinkRequest] = (),
    guests: int | None = None,
    catalog: Catalog | None = None,
) -> BevResult:
    """Pure calculation, no I/O except loading the catalog. catalog=None means
    load_catalog() (the real data/pull_sheet files). Never raises for bad user
    input: problems give status "invalid" or "need_info" (§4). RuleFileError from
    loading the catalog propagates."""

def run_bev_tool(args: Mapping[str, object], catalog: Catalog | None = None) -> BevResult:
    """Run the tool on a raw argument dict as the chat model sends it (§4.0).
    Never raises for bad arguments: they give status "invalid"."""

def make_bev_tool(catalog: Catalog | None = None) -> BaseTool:
    """NEW. A LangChain tool named BEV_TOOL_NAME with the schema in §3.3. Invoking it
    with an argument dict returns run_bev_tool(args, catalog).text. catalog=None means
    the real files, loaded when the tool runs, not when it is made."""

BEV_TOOL: BaseTool   # make_bev_tool(): the tool the chatbot uses
```

### 3.2 The chat flow: `scripts/chat.py`
Existing names keep their behaviour unless stated. `answer_turn`, `TurnResult` and `main` are unchanged (spec 001); because `answer_turn` calls `answer_from_context`, text chat and voice chat both get the tool.

```python
from blc.tools.bev_tools import BEV_TOOL

CHAT_TOOLS: tuple[BaseTool, ...] = (BEV_TOOL,)
MAX_TOOL_ROUNDS = 3
TOOL_HINT_WORDS: tuple[str, ...] = (
    "cambro", "cup", "guest", "people", "supplies",
    "napkin", "creamer", "sugar", "stir stick", "tea packet",
    "gallon", "container", "bring", "what do i put",          # NEW in revision 1
)
TOOL_LIMIT_REPLY = "Sorry, I couldn't work that out. Please try rephrasing the question."

@dataclass(frozen=True)
class ToolCallRecord:
    name: str                  # tool name the model asked for
    args: dict[str, object]    # arguments exactly as the model sent them
    result: str                # text returned to the model

@dataclass(frozen=True)
class ToolAnswer:
    reply: str                           # final answer text
    tool_calls: tuple[ToolCallRecord, ...]  # every tool call in this answer, in order
    retried: bool                        # True if the safety net (§4.6) asked the model again

def answer_with_tools(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    docs: list[Document],
    question: str,
    tools: Sequence[BaseTool] = CHAT_TOOLS,
) -> ToolAnswer:
    """One answer: the model sees the system prompt, history, retrieved docs and the
    question, and may call tools (§4.5). Prints nothing."""

def answer_from_context(llm, history, docs, question) -> str:
    """Returns answer_with_tools(llm, history, docs, question).reply."""
```

**How the chat flow talks to the model** (so tests can use a fake chat model): `answer_with_tools` calls `llm.bind_tools(list(tools))` once and calls `.invoke(messages)` on the returned object, where `messages` is a list of LangChain messages. It reads the reply's `.content` (text) and `.tool_calls` (list of dicts with `name`, `args`, `id`). Each tool result is sent back as a `ToolMessage` with the matching `tool_call_id`. `llm.invoke` itself is used only for history summaries, as today.

**The system prompt is sent once.** In every `.invoke(messages)` call, `messages[0]` is a `SystemMessage` containing `SYSTEM_PROMPT`, and the text of `SYSTEM_PROMPT` appears in no other message.

**Code structure (NFR-6):** the flow is split into step functions that take data in and return data out (e.g. build messages, call the model, run tool calls, safety check), with one small function that only decides the order. No step prints.

**`SYSTEM_PROMPT`** tells the model to: call `calculate_bev_item` for any question about how many gallons, cambros, cups or beverage supplies to bring, or which containers to use; never work these numbers out itself; use the documents for everything else (locations, recipes, menu meanings); and, when the tool asks for missing information, ask the user that question. The developer writes the wording (NFR-7).

**`CHAT_MODEL`** stays `"qwen2.5:7b"` (revision 2's switch to `"qwen2.5:14b"` was withdrawn in revision 3; this spec no longer fixes the model name, and no test checks it).

### 3.3 What the model receives (tool schema)
`langchain_core.utils.function_calling.convert_to_openai_tool(tool)["function"]`, for `BEV_TOOL` and for any `make_bev_tool(catalog)`, has `name == BEV_TOOL_NAME`, a `description` (rules below) and exactly these `parameters` (descriptions shown as `…`):

```json
{
  "type": "object",
  "properties": {
    "item":    {"type": "string", "enum": ["gallons", "cambros", "cups", "supplies", "everything"], "description": "…"},
    "drinks":  {"type": "array", "items": {"type": "string"}, "description": "…"},
    "gallons": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0}, "description": "…"},
    "guests":  {"type": "integer", "minimum": 1, "description": "…"}
  },
  "required": ["item"]
}
```
- Each property has exactly the keys shown (`type`, plus `enum`, `items` or `minimum` as shown, plus `description`). The `items` objects have exactly the keys shown.
- Nothing inside `parameters` uses `anyOf`, `oneOf`, `allOf`, `$ref`, `$defs`, `default`, `title` or the type `"null"`.
- `enum` equals `list(BEV_ITEMS)`; `required` equals `["item"]`.

**Descriptions** (wording is the developer's):
- The tool's `description` says what the tool does and that the model must use it instead of calculating, and contains **at least two example calls** written as argument dicts: one with `drinks` and `gallons` together (several drinks, amounts in the same order) and one with `guests` and no `drinks`.
- `drinks`: names every menu item and the package in Appendix A (case-insensitive), and says a package is passed as one name.
- `gallons`: says the numbers are in the same order as `drinks`, that oatmilk's number is a count of pieces, to leave it out when no amounts were given, and (NEW) to use only amounts the user said, never amounts worked out from guests.
- `guests`: says to leave it out when no guest or people count was given.
- `item` (NEW): says in the user's words what each item answers: gallons to make (`gallons`); which cambros or containers, or what to put or serve a drink in (`cambros`); how many cups (`cups`); whether to bring a particular supply (`supplies`); what to bring in general (`everything`).
- No example (in the descriptions, the `invalid` text or `SYSTEM_PROMPT`) uses the question or the drinks-and-amounts of any eval case in §6 or in spec 004 §6 (NFR-7).

## 4. Inputs and outputs

### 4.0 Raw arguments (`run_bev_tool`)
The expected shape is the §3.3 schema:
```json
{"item": "cambros", "drinks": ["iced tea", "peach tea"], "gallons": [4, 2], "guests": 60}
```
- `drinks`, `gallons` and `guests` may each be missing, `null` or (for lists) empty, which all mean "not given". Unknown extra keys are ignored. A missing or unknown `item` is **invalid**.
- `gallons[i]` is the amount of `drinks[i]` in that drink's own unit (gallons; pieces for Oatmilk). It becomes `DrinkRequest(drinks[i], quantity=gallons[i])`. A `null` or `0` at a position means no amount for that drink. A negative number is **invalid**.
- **One amount, several drinks:** if `gallons` has exactly one number and `drinks` has several names, every drink gets that amount ("5 gallons of coffee and lemonade" = 5 each).
- Otherwise a `gallons` list whose length differs from `drinks` is **invalid**, and `gallons` without `drinks` is **invalid**.
- `guests`: `null` or `0` mean not given. Otherwise it must be a whole number ≥ 1 (`70`, `70.0` and `"70"` are all 70); anything else (`-5`, `2.5`, `"seventy"`) is **invalid**.
- Numbers may arrive as numeric strings (`"7"`, `"2.5"`); a non-numeric string where a number is expected is **invalid**.

**Other shapes accepted** (common model mistakes):
- `drinks` is a single string → one drink.
- `drinks` is an object mapping names to amounts (number, numeric string or `null`), e.g. `{"coffee": 5, "lemonade": 3}` → those drinks, in key order, with those amounts.
- `drinks` is a list of objects, each with a name under `menu`, `name`, `menu_name` or `drink` (first present wins), an optional amount under `quantity`, `gallons` or `amount`, and an optional `unit` (as `DrinkRequest.unit`), e.g. `[{"name": "Coffee", "quantity": 7}]`. An object with none of those name keys is **invalid**.
- When `drinks` carries its own amounts (object forms above) and a non-empty `gallons` list is also given → **invalid**.
- Any other shape (e.g. `drinks` a number) → **invalid**.

### 4.1 Resolving drinks
- Each `DrinkRequest.menu` is matched against the menu the same way BEO descriptions are (spec 002 §4.2): item names, `also_written_as` names and package names, after normalisation. "coffee", "Coffee" and "Fresh-brewed coffee" all resolve to Coffee.
- **Short names (NEW):** a name that matches nothing above but is exactly (after the same normalisation) "tea" or "hot tea" resolves to Hot water, and "juice" resolves to Orange juice. "iced tea" and "peach tea" still resolve to their own items.
- A **package** name resolves to the drinks it stands for, in package order, with placeholders filled by their default (`JUICE` → Orange juice).
- A name that matches nothing goes to `not_on_menu` (stripped, as given) and is otherwise ignored.
- If the same menu item is requested more than once (e.g. "coffee" and "Fresh-brewed coffee"), it appears once in `drinks`, with the larger amount.

### 4.2 Amounts
For each resolved drink, in this order:
1. **Quantity given:** `unit` None means the item's own unit. A gallon unit (`gallon`, `gallons`, `gal`) is allowed only for gallon items and `each` only for each items; anything else is **invalid**. Quantity must be > 0, else **invalid**. `from_guests=False`.
2. **No quantity, `guests` given:** a gallon item gets gallons from guests by the pull sheet rule (25 guests per gallon, half rounds up, minimum 1). `from_guests=True`. An each item (Oatmilk) gets no amount.
3. **Package:** a quantity on a package is **invalid** (packages are sized by `guests`). Its drinks get their amounts from `guests` as in step 2.
4. **Otherwise** the drink has no amount.

In `calculate_bev_item`, `guests`, when given, must be an integer ≥ 1, else **invalid**. An `item` not in `BEV_ITEMS` is **invalid**.

### 4.3 What each item answers

| `item` | Needs (else `need_info`) | `lines` | Other fields |
|---|---|---|---|
| `gallons` | drinks: an amount for every gallon drink. No drinks: `guests` | `()` | `drinks` with amounts; with no drinks, `gallons_each` = gallons for `guests` |
| `cambros` | at least one drink; an amount for every gallon drink | the cambro lines | |
| `cups` | `guests`. With drinks: the cup lines (supply lines from `guest+extra` rules). **No drinks (NEW): status `ok`**, `lines` `()` | see Needs | with no drinks, `cups_each` = guests + extras for `guests` |
| `supplies` | at least one drink | all supply lines (from the rules' `supplies`); without `guests`, lines whose amount depends on guests are left out | |
| `everything` | at least one drink; an amount for every gallon drink | cambro lines, then add-on lines, then supply lines; without `guests`, guest-dependent lines are left out | |

Status precedence: `invalid` first, then `not_on_menu` (drinks were requested and **none** is on the menu), then `need_info`, else `ok`. When some drinks are on the menu and some are not, status is `ok` (or `need_info`) and `not_on_menu` lists the unknown ones.

**Agreement with the pull sheet program (key rule).** For status `ok`, `lines` equal the matching lines of `build_pull_sheet(catalog, beo)` for the equivalent BEO: each drink with a given amount becomes a line `(drink, amount, "Gallon")` (or `"Each"`), each drink sized from guests becomes `(name, guests, "")`, a package becomes `(package name, guests, "")`, and the BEO's Guest Count is `guests`. For `cambros` (which never depends on guests) any Guest Count gives the same cambro lines.

### 4.4 The tool's text
`text` is short plain English for the chat model to repeat. It must contain:
- `ok`: each drink's display name with its amount ("Coffee: 7 gal", "Oatmilk: 2 each"), adding "from N guests" when `from_guests`; each line's supply name with its quantity, or "bring" for a tick; for `gallons_each`, the gallons and the guest count; for `cups_each`, the cup count, the guest count, and that the same count applies to hot cups and to cold cups; and when guest-dependent lines were left out, a note that cup counts need the number of guests.
- `need_info`: one question ending in `?` naming what is missing: "gallons" and "guests" when an amount is missing, "guests" when cups need them, "drink" when no drink was given.
- `not_on_menu` (any status): each unknown name with the words "not on the beverage menu".
- `invalid`: starts with "invalid", says what was wrong, and shows the expected argument format with an example call. It contains `"item"`, `"drinks"`, `"gallons"` and `"guests"` (with the double quotes).
- `invalid` because of an amount on a package (NEW): also says the package is sized by guests, so the call should pass `guests` instead of `gallons`. The text contains the word "package" and the words "instead" and "guests".
- **Grammar (NEW):** an amount of exactly 1 is singular. `text` never contains "1 gallons", "1 cambros" or "1 cups" (as whole words).

Example (`item="cambros"`, Iced tea 4 gal + Peach tea 2 gal). The wording is illustrative: only the parts listed above are required, and tests must not compare the text word for word:
```
Iced tea: 4 gal. Peach tea: 2 gal.
5 gal cambro: 1 (for Iced tea). 2 gal cambro: 1 (for Peach tea).
```

### 4.5 The tool loop
- The model may answer directly, or ask for one or more tool calls. Every requested call is run, recorded in `tool_calls`, and its `result` sent back; then the model is asked again.
- A call to a name not in `tools` is recorded with result `"error: unknown tool <name>"` and sent back; nothing raises.
- After `MAX_TOOL_ROUNDS` rounds of tool calls, if the model still asks for tools, the reply is `TOOL_LIMIT_REPLY`.
- The final reply is the model's last text content, stripped.

### 4.6 The safety net
After the loop, if **no tool was called**, the **question** contains any of `TOOL_HINT_WORDS` (case-insensitive substring), and the **reply** contains a digit, the model is asked **once** more with an added instruction to call `calculate_bev_item` if the question is about pull sheet amounts, and otherwise to answer as before. That second answer (including any tool calls it makes, run as in §4.5) is final, and `retried` is True. Otherwise `retried` is False.

The added instruction is for the model only: the final reply must not repeat, quote or describe it (checked in AC-12).

## 5. Edge cases
**Calculator (unit, exact; using the Appendix A catalog):**
- EC-1: `cambros`, Lemonade 7 gal → lines `5 gal cambro: 1`, `2 gal cambro: 1`.
- EC-2: `cambros`, Lemonade 3 gal → `5 gal cambro: 1` (not 2 + 1). 2.5 gal → `5 gal cambro: 1`. 12 gal → `5 gal cambro: 2`, `2 gal cambro: 1`.
- EC-3: `cambros`, Coffee 5 gal + Lemonade 3 gal → `5 gal cambro: 2`.
- EC-4: `cambros`, Lemonade, guests 70 → Lemonade 3 gal `from_guests=True`; `5 gal cambro: 1`.
- EC-5: `gallons`, no drinks, guests 25 → `gallons_each` 1; guests 37 → 1; 38 → 2; 75 → 3; 100 → 4.
- EC-6: `cups`, Coffee + Lemonade, guests 70 → `hot-cups: 120`, `cold-cups: 120`. Coffee + Decaf, guests 70 → `hot-cups: 120` only.
- EC-7: `supplies`, Coffee, no guests → Cocktail napkins (tick), Creamer (tick), Stir sticks 1, Sugar 1; no cup lines; the text notes cups need guests.
- EC-8: `everything`, Coffee, guests 50 → `2 gal cambro: 1`, `hot-cups: 70`, Cocktail napkins (tick), Creamer (tick), `Stir sticks: 1`, `Sugar: 1`.
- EC-9: `cambros`, "Coffee, decaf, tea, iced water & juice" package, guests 70 → five drinks at 3 gal each (Orange juice included); `5 gal cambro: 5`.
- EC-10: "Fresh-brewed coffee" resolves to Coffee; "coffee" and "Fresh-brewed coffee" together give one Coffee entry with the larger amount.
- EC-11: `cambros`, Hot chocolate 4 gal → status `not_on_menu`, `not_on_menu=("Hot chocolate",)`, no lines; Hot chocolate + Coffee 7 gal → status `ok`, Coffee lines, `not_on_menu=("Hot chocolate",)`.
- EC-12: `cambros`, Coffee + Lemonade, no quantities, no guests → `need_info`, text asks for gallons or guests. `cups`, Coffee, no guests → `need_info` (guests). `cups`, no drinks, no guests → `need_info` (guests). `cambros` with no drinks → `need_info` (drink). `gallons`, no drinks, no guests → `need_info`.
- EC-13: invalid inputs to `calculate_bev_item` → status `invalid`, no raise: item "pans"; quantity 0 or −1; guests 0, −5 or 2.5; unit "quarts"; unit "each" on Coffee; unit "gallon" on Oatmilk; a quantity on a package.
- EC-14 (NEW): `cups`, no drinks → guests 20 → `cups_each` 30; 50 → 70; 70 → 120; 100 → 150; 150 → 250. Status `ok`, `lines` `()`, `gallons_each` None.
- EC-15 (NEW): short names, guests 70, `cambros`: drinks "coffee", "decaf", "tea", "iced water", "juice" → five drinks (Coffee, Decaf, Hot water, Iced water, Orange juice) at 3 gal each, `5 gal cambro: 5`, same lines as EC-9. "hot tea" → Hot water. "iced tea" → Iced tea. "peach tea" → Peach tea.
- EC-16 (NEW): grammar: `gallons`, no drinks, guests 25 → text contains "1 gallon" and not "1 gallons"; `cambros`, Lemonade 7 gal → text does not contain "1 cambros".

**Raw arguments (`run_bev_tool`, unit, Appendix A catalog):**
- EC-17: `{"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}` → same result as EC-1. `{"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, 3]}` → same as EC-3. `"gallons": ["7"]` → same as EC-1.
- EC-18: one amount for several drinks: `{"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5]}` → Coffee 5 gal and Lemonade 5 gal, `5 gal cambro: 2`.
- EC-19: not given: `{"item": "cups", "guests": 70}`, the same with `"drinks": []` or `"drinks": null`, and `{"item": "cups", "drinks": null, "gallons": null, "guests": 70}` all → `cups_each` 120. `{"item": "cambros", "drinks": ["lemonade"], "guests": 0}` → `need_info` (as with no guests). `{"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, 0]}` → `need_info` (Lemonade has no amount). `"guests": "70"` and `"guests": 70.0` → same as 70.
- EC-20: other shapes: `"drinks": "lemonade", "gallons": [7]` → same as EC-1. `"drinks": {"coffee": 5, "lemonade": 3}` → same as EC-3. `"drinks": [{"menu": "lemonade", "quantity": 7, "unit": "gallons"}]`, `[{"name": "lemonade", "quantity": 7}]`, `[{"menu_name": "Lemonade", "gallons": 7}]` and `[{"drink": "lemonade", "amount": "7"}]` → same as EC-1. `"drinks": {"lemonade": null}, "guests": 70` → same as EC-4.
- EC-21: invalid, no raise: missing `item`; `item` "pans"; `"drinks": 5`; `"drinks": [{"description": "Drinks named by the user"}]`; `"gallons": [5, 3]` with one drink; `"gallons": [5]` with no drinks; `"gallons": [-2]`; `"gallons": ["seven"]`; `"guests": -5`, `2.5` or `"seventy"`; `"drinks": {"coffee": 5}` together with `"gallons": [5]`. Each `invalid` text contains `"item"`, `"drinks"`, `"gallons"` and `"guests"`. For `{"item": "cambros", "drinks": ["Coffee, decaf, tea, iced water & juice"], "gallons": [3]}` the text also contains "package", "instead" and "guests" (§4.4).

**Tool schema (unit):**
- EC-22: `convert_to_openai_tool(BEV_TOOL)["function"]["parameters"]` and the same for `make_bev_tool(<Appendix A catalog>)` match §3.3 exactly, and contain none of the forbidden keys or `"null"` anywhere (checked recursively).
- EC-23: `make_bev_tool(<Appendix A catalog>).invoke({"item": "cambros", "drinks": ["lemonade"], "gallons": [7]})` returns `run_bev_tool(same args, <Appendix A catalog>).text`, and needs no file under `data/`.

**Chat flow (unit, fake model):**
- EC-24: the model answers without tool calls → `tool_calls=()`, reply is its text.
- EC-25: the model asks for `calculate_bev_item` → the tool runs with those args, the model gets a `ToolMessage` with the result and the matching id, and its next text is the reply.
- EC-26: two tool calls in one model reply → both run, both recorded, in order.
- EC-27: unknown tool name → recorded with `"error: unknown tool <name>"`, no raise.
- EC-28: the model keeps asking for tools → after `MAX_TOOL_ROUNDS` rounds the reply is `TOOL_LIMIT_REPLY`.
- EC-29: safety net fires: question "How many cambros for 7 gallons of coffee?", first reply "You need 2 cambros." with no tool call → model asked once more, `retried=True`, second reply final. Same for question "What do I put 7 gallons of lemonade in?" with first reply "A 5 gal and a 2 gal cambro."
- EC-30: safety net does not fire: question "How many oz of concentrate per batch of lemonade?" (no hint word) with reply "35 oz"; or a hint-word question whose reply has no digit; or any answer where a tool was called → `retried=False`, no extra call.
- EC-31: `answer_from_context(...)` returns exactly `answer_with_tools(...).reply`.
- EC-32 (NEW): in every `.invoke(messages)` call of EC-24 to EC-29, `messages[0]` is a `SystemMessage` containing `SYSTEM_PROMPT`, and no other message contains `SYSTEM_PROMPT`.

## 6. Acceptance criteria
- **AC-1 (calculator values):** `calculate_bev_item` gives the results in EC-1 to EC-12 and EC-14 to EC-15 (status, `drinks`, `lines` supply names and quantities, `not_on_menu`, `gallons_each`, `cups_each`).
- **AC-2 (agreement):** for status `ok` with `guests` given, `lines` equal the matching lines of `build_pull_sheet` for the equivalent BEO (§4.3), for at least: each EC-1 to EC-9 case with guests added where missing, EC-15, and every item in `BEV_ITEMS` except `gallons`.
- **AC-3 (bad input):** EC-13 and EC-21 give status `invalid` and never raise.
- **AC-4 (text):** `text` contains the parts listed in §4.4 for every status (checked on EC-3, EC-4, EC-7, EC-11, EC-12, EC-13, EC-14, EC-21 cases), and EC-16 holds.
- **AC-5 (raw arguments):** `run_bev_tool` gives the results in EC-17 to EC-20.
- **AC-6 (tool object and schema):** EC-22 and EC-23. `BEV_TOOL.name == BEV_TOOL_NAME`; `chat.CHAT_TOOLS` contains `BEV_TOOL`. The tool's `description` contains at least two `{` and the words `drinks`, `gallons` and `guests`; the `drinks` property's description contains every Appendix A item name and the package name (case-insensitive); the `item` property's description contains the word "container" (NEW).
- **AC-7 (tool loop):** `answer_with_tools` with a fake model behaves as in EC-24 to EC-28, EC-31 and EC-32.
- **AC-8 (safety net):** EC-29 and EC-30; `TOOL_HINT_WORDS` equals the tuple in §3.2.
- **AC-9 (unchanged behaviour):** all spec 001 tests (`tests/test_voice_io.py`, `tests/test_voice_io_answer_turn.py`) still pass, apart from `test_constants_match_contract`, which already fails because of the user's uncommitted `DIDNT_CATCH` change.
- **AC-10 (tool choice eval):** with the real model (`ChatOllama(model=CHAT_MODEL, temperature=0)`) and the real store, for every case in the table below, `answer_with_tools(llm, history, retrieve(store, question), question)`'s tool calls match the **Tool** column (rules below). **Pass threshold: all cases.**
- **AC-11 (answer eval):** for every case below, `judge_answer(question, reference, reply)` gives `passed=True`. **Pass threshold: all cases.**
- **AC-12 (no leaked instructions):** for every case below, the reply (casefolded) contains none of `calculate_bev_item`, `tool`, `instruction`, `json`, `"item"` or `argument`. Checked in the AC-11 run.
- **AC-13 (spec 004 regression):** spec 004's generation eval (`tests/beverage_knowledge/test_generation.py`, as of spec 004 revision 2) passes all 20 cases. It calls `answer_from_context`, so it now runs through the tool loop.
- **AC-14 (withdrawn in revision 3):** there is no check on `chat.CHAT_MODEL`. The two tests written for it (`test_ac14_chat_model_is_14b` and `test_ac14_chat_model_is_not_the_old_7b`) are deleted.

**Tool column rules** (each case is checked exactly as written, including `from_guests` and `guests`). `none`: no tool call. `<item>: …`: at least one call to `calculate_bev_item`, every such call has that `item`, and running `run_bev_tool` on the call's args gives the listed status (default `ok`), resolved drinks (display names), amounts, `from_guests` (where listed) and `guests` (where listed; "no guests" means not given). `none or <item>`: either no call, or calls matching `<item>` whose result status is as listed. Drinks are compared as resolved by the calculator, so "lemonade" and "Lemonade" are the same.

| id | question (prior turns, if any) | Tool | reference |
|---|---|---|---|
| T1 | Where is the coffee located? | none | Required: under the coffee machine in the beverage room. May also: the backup location beside the cambros near the washing pit. |
| T2 | How many cambros do I need to bring for 7 gallons of lemonade? | cambros: Lemonade 7 gal | Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size of cambros. |
| T3 | How many oz of lemonade concentrate do I need to make 5 gallons of lemonade? | none | Required: 35 oz of lemonade concentrate. Must not: give any other amount. |
| T4 | Where is the coffee, and how many gallons of coffee do I need for 75 people? | gallons: guests 75; drinks Coffee (3 gal from guests) or no drinks | Required: the coffee is under the coffee machine in the beverage room, and 3 gallons of coffee for 75 people. May also: the backup location. Must not: give any other gallon amount. |
| T5 | How many cambros do I need for coffee and lemonade? | none or cambros (status need_info) | Required: asks how many gallons of each drink or how many guests. Must not: give any number of cambros. |
| T6 | (user: T5 question; assistant: "How many gallons of each drink, or how many guests?") 5 gallons each. | cambros: Coffee 5 gal, Lemonade 5 gal | Required: two 5 gal cambros, one for the coffee and one for the lemonade. Must not: recommend any other count or size. |
| T7 | I need 5 gallons of coffee and lemonade. How many cambros? | cambros: Coffee 5 gal, Lemonade 5 gal | Required: two 5 gal cambros, one for each drink. Must not: recommend any other count or size. |
| T8 | How many cups do I need for coffee? | none or cups (status need_info) | Required: asks how many guests. Must not: give a number of cups. |
| T9 | 5 gallons of coffee and 3 gallons of lemonade, how many cambros? | cambros: Coffee 5 gal, Lemonade 3 gal | Required: two 5 gal cambros. Must not: recommend any other count or size. |
| T10 | Coffee and lemonade for 70 guests, how many cups? | cups: Coffee, Lemonade; guests 70 | Required: 120 hot cups and 120 cold cups. Must not: give any other cup numbers. |
| T11 | How many cambros for lemonade for 70 guests? | cambros: Lemonade 3 gal from guests; guests 70 | Required: one 5 gal cambro (3 gallons). Must not: recommend any other count or size. |
| T12 | How many cambros for 4 gallons of hot chocolate? | none or cambros (status not_on_menu) | Required: says hot chocolate is not on the beverage menu, or that it doesn't know. Must not: give any number of cambros. |
| T13 | How many cambros for 7 gallons of fresh-brewed coffee? | cambros: Coffee 7 gal | Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size. |
| T14 | We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros? | cambros: Coffee, Decaf, Hot water, Iced water, Orange juice at 3 gal each from guests; guests 70 | Required: five 5 gal cambros, one per drink. Must not: recommend any other count or size. |
| T15 | What's in the coffee, decaf, tea, iced water & juice package? | none | Required: coffee (regular), decaf, hot water (for tea), iced water and orange juice, all five named. |
| T16 | What syrup flavors do we have? | none | Required: mango, strawberry and peach. |
| T17 | What time does my shift start tomorrow? | none | Required: says it doesn't know. Must not: give a time. |
| T18 | What do I put 7 gallons of lemonade in? | cambros: Lemonade 7 gal | Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size. |
| T19 | Seven gallons of lemonade, which containers do I bring? | cambros: Lemonade 7 gal | Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size. |
| T20 | What do I need to bring for coffee for 50 guests? | everything: Coffee 2 gal from guests; guests 50 | Required: one 2 gal cambro, 70 hot cups, cocktail napkins, creamer, stir sticks and sugar. Must not: give a different cambro or cup count. |
| T21 | Do I need sugar for coffee? | supplies: Coffee; no guests | Required: yes, 1 sugar. Must not: give 2 or more sugars. |
| T22 | How many gallons do I make for 25 people? | gallons: guests 25; no drinks | Required: 1 gallon of each drink. Must not: give any other amount. |
| T23 | How many hot cups do I need for 40 guests? | cups: guests 40; no drinks, or drinks that are all hot drinks | Required: 60 hot cups. Must not: give any other number of cups. |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | The calculator only reads the menu and rules (through `load_catalog`); it prints nothing and calls no model. | manual (code review) |
| NFR-3 | AC-1 to AC-9 tests need no Ollama and no network, and read no file under `data/`: calculator, raw-argument and tool tests use the Appendix A catalog (through `catalog=` or `make_bev_tool(catalog)`). | unit (review by test-evaluator) |
| NFR-4 | Eval tests (AC-10 to AC-13) are marked `eval` and skip, not fail, when Ollama is not running or the knowledge files are not in the store. No test writes to `.chroma/` or `data/`. | unit (marker review by test-evaluator) |
| NFR-5 | The calculator's numbers come only from the pull sheet package and the JSON files; no gallon, cambro, cup or supply rule is re-implemented (AC-2 checks the result). The short names in §4.1 are the only menu knowledge outside the JSON. | manual (code review) |
| NFR-6 | The chat flow is split into step functions that take data and return data, with no printing, plus one function that only orders them (§3.2), so a move to LangGraph only rewires them. | manual (code review) |
| NFR-7 | `SYSTEM_PROMPT`, the tool's descriptions, the `invalid` text and the safety-net instruction contain no eval question or reference from §6 or spec 004 §6 word for word, and no example call uses the drinks-and-amounts of any of those cases. | manual (code review) |
| NFR-8 | A number question that uses the tool takes at most about twice as long as a plain RAG answer. | manual (timed by the planner during the eval run) |

Tests go in `tests/bev_tools/` (no `__init__.py`): `conftest.py` (the Appendix A catalog written to `tmp_path`, a fake tool-calling chat model, the eval cases, the store fixture), `test_bev_calculator.py` (AC-1, AC-2), `test_bev_inputs.py` (AC-3, AC-4), `test_bev_args.py` (AC-5), `test_bev_tool.py` (AC-6), `test_answer_loop.py` (AC-7, AC-8), `test_tool_choice_eval.py` (AC-10), `test_answer_eval.py` (AC-11, AC-12). AC-9 and AC-13 are checked by running the existing test files.

## Revision history
- **Revision 1 (2026-11-11)**, after the first eval run (tool choice 6/22, answers 5/22, spec 004 regression 12/20). The calculator was right, but qwen2.5:7b could not fill in the nested `drinks` argument (lists of objects with optional, nullable fields) and sent dicts, invented keys, or copied the schema's own description text in as a value.
  - **Flat schema (§3.3):** `drinks` is a list of names, amounts move to a parallel `gallons` list, `unit` is dropped from the schema, and nothing is nullable. The exact schema is part of the contract and tested (EC-22).
  - **Lenient raw arguments (§4.0):** `run_bev_tool` takes the new shape and the common wrong shapes; one amount for several drinks; `null`/`0` mean not given. Old EC-14 is replaced by EC-17 to EC-21.
  - **`make_bev_tool(catalog)`** so tool tests use the Appendix A catalog instead of `data/` (NFR-3).
  - **Cups without a drink** answer with the new `cups_each` (EC-14, T23) instead of asking which drink.
  - **Short names** "tea", "hot tea" and "juice" (§4.1, EC-15).
  - **Tool text:** `invalid` shows the expected format with an example; amounts of 1 are singular (EC-16).
  - **Chat flow:** the system prompt is sent once (EC-32); `TOOL_HINT_WORDS` adds "gallon", "container", "bring" and "what do i put"; the safety-net instruction must not leak into replies (AC-12). The old EC-21 example now contains a hint word, so EC-30 uses a different question.
  - **Evals:** T1 and T4 references allow the backup location; T23 added; the Tool column is checked exactly, including `from_guests` and `guests` (T11, T21). Edge cases and ACs are renumbered.
  - **Code to change:** `src/blc/tools/bev_tools/` (schema, raw arguments, short names, `cups_each`, text, `make_bev_tool`) and `scripts/chat.py` (system prompt once, hint words, safety-net instruction). `calculate_bev_item`'s results for existing cases do not change.
  - **Tests to change:** all files in `tests/bev_tools/` to match the renumbered ECs and ACs, plus the new `test_bev_args.py`.
- **Revision 2 (2026-11-11)**, after the AC-10 run on revision 1 (tool choice 15/23: arguments well-formed, but chosen badly: guests turned into gallons by the model, invented amounts, wrong `item` for "containers" and "what to bring", a recipe question sent to the tool, tool name in replies). The user chose a bigger chat model now and a question router next (spec 006). This revision only:
  - **`CHAT_MODEL` becomes `qwen2.5:14b`** (§3.2, new AC-14). The judge (spec 004) also uses 14B.
  - **Descriptions (§3.3):** `item` explains each item in the user's words; `gallons` says to use only amounts the user said, never amounts worked out from guests. AC-6 checks that the `item` description mentions containers.
  - **Tool text (§4.4):** an amount on a package gives an `invalid` text that says to pass `guests` instead (checked in EC-21). The §4.4 example's wording is illustrative; tests must not compare it word for word.
  - **No change** to the eval table, the Tool column rules or the thresholds. AC-10 is re-run on 14B as a baseline for spec 006.
  - **Code to change:** `scripts/chat.py` (`CHAT_MODEL` only) and `src/blc/tools/bev_tools/` (the `item` and `gallons` descriptions, the package `invalid` text). Nothing else.
  - **Tests to change**, in `tests/bev_tools/`: AC-14; the EC-21 package text check and the AC-6 `item` check; `test_text_matches_spec_example` must not compare the example word for word; the EC-29 safety-net test must show that a message added after the first reply (not `SYSTEM_PROMPT`) mentions `calculate_bev_item`; `test_oatmilk_gets_no_amount_from_guests` must assert the status and the exact `drinks` and `lines`; `test_text_supplies_ticks_and_cup_note` must not forbid the word "hot-cups" in a note.

- **Revision 3 (2026-11-11)**, housekeeping. The user decided to stay on `qwen2.5:7b`, so revision 2's switch to 14B is withdrawn: `CHAT_MODEL` stays `"qwen2.5:7b"` and AC-14 is withdrawn. This revision only:
  - **Tests to change**, in `tests/bev_tools/`: delete `test_ac14_chat_model_is_14b` and `test_ac14_chat_model_is_not_the_old_7b` (and nothing else; no other assertion is weakened).
  - **No change** to code, the calculator, the tool schema, the eval table or any other AC.
  - **Superseded elsewhere (for the reader, no test change here):** the chat flow and tool loop (§3.2, §4.5, AC-7) are replaced by spec 006; the safety net (§4.6, AC-8) was removed by spec 006; the tool step's arguments are checked by spec 009.

## Appendix A: catalog used by unit tests
Unit tests write these two files to `tmp_path` (`menu/beverages.json`, `rules/beverages.json`) and use `load_catalog(tmp_path)`. They are the current real files.

`menu/beverages.json`:
```json
{
  "items": {
    "Coffee": {"unit": "gallon", "also_written_as": ["Fresh-brewed coffee"], "tags": ["HOT", "COFFEE"]},
    "Decaf": {"unit": "gallon", "also_written_as": ["Fresh-brewed decaffeinated coffee"], "tags": ["HOT", "COFFEE"]},
    "Hot water": {"unit": "gallon", "also_written_as": ["Hot water with an assortment of black, green, and herbal tea bags"], "tags": ["HOT", "HOT-WATER"]},
    "Brewed hot cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
    "Ginger Honeycrisp apple cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
    "Iced water": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
    "Iced tea": {"unit": "gallon", "also_written_as": ["Iced tea with lemon wedges"], "tags": ["COLD", "ICED-TEA"]},
    "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
    "Lemonade": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
    "Peach tea": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
    "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []}
  },
  "packages": {
    "Coffee, decaf, tea, iced water & juice": {
      "includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
      "placeholders": {"JUICE": "Orange juice"}
    }
  }
}
```

`rules/beverages.json`:
```json
{
  "cambros": [
    {"supply": "5 gal cambro", "gallons": 5},
    {"supply": "2 gal cambro", "gallons": 2},
    {"supply": "1 gal cambro", "gallons": 1}
  ],
  "supplies": [
    {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
    {"supply": "cold-cups", "qty": 1, "per": "guest+extra", "when_tagged": "COLD"},
    {"supply": "Cocktail napkins", "tick": true},
    {"supply": "Creamer", "tick": true, "when_tagged": "COFFEE"},
    {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
    {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
    {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    {"supply": "Lemon tongs", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    {"supply": "Lemons", "tick": true, "when_tagged": "HOT-WATER"},
    {"supply": "Tea packets", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    {"supply": "Lemons", "tick": true, "when_tagged": "ICED-TEA"}
  ],
  "extras": [
    {"guests_up_to": 20, "extra": 10},
    {"guests_up_to": 50, "extra": 20},
    {"guests_up_to": 100, "extra": 50},
    {"guests_up_to": null, "extra": 100}
  ]
}
```
