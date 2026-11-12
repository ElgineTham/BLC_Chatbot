# Spec 007: Router item set, intent rule and JSON reply

- **Status:** approved
- **Date:** 2026-11-11
- **Superseded in part (2026-11-12):** The JSON router, its reply reading and the guard in code (§3.2, §4.1, §4.2) are superseded by spec 013 and removed by spec 014. `PULL_SHEET_ITEMS` and `pull_sheet_items_in` (§3.1) are still used.

## 1. Goal
Make the router (spec 006) reliable on the 7B model `qwen2.5:7b`. Three changes, router only:
1. a closed **set of beverage pull sheet items** (`PULL_SHEET_ITEMS`) that says what the tool can be about; the router prompt lists it, and a **guard** in code turns any TOOL part that mentions no item of the set into DOCS;
2. a sharper **routing rule** in the prompt: the set says what a question is about, the *intent* says what it asks for. A question is TOOL only when it asks **how much or how many to make or bring** (or whether to bring) a set item. "How to make 3 gallons of lemonade?" mentions `gallons` but asks for a recipe, so it is DOCS. When unsure the answer is DOCS;
3. the model is asked for a **JSON reply** (Ollama schema-constrained) instead of free `TOOL:`/`DOCS:` lines; the old line format is still read as a second chance.

This spec revises spec 006 §3.1, §4.1 and §4.2 for the router only. Everything else in spec 006 stands.

## 2. Out of scope
- `scripts/chat.py`, retrieval (`answer_turn`, retrieving per DOCS part), the tool step, the final call, `src/blc/tools/` and `src/blc/pull_sheet/`. (Known follow-ups, later specs: route before retrieval; label DOCS parts in the final call; scaling a recipe by a tool result.)
- `CHAT_MODEL` stays `qwen2.5:7b`.
- A shortcut that skips the model call when no item is mentioned (a typo could send a TOOL question to DOCS).
- Reading `data/` at run time: the item set is a constant in code.

## 3. Interface contract

### 3.1 The item set: `src/blc/router/items.py` (new)
Importable as `from blc.router import PULL_SHEET_ITEMS, pull_sheet_items_in`.

```python
PULL_SHEET_ITEMS: dict[str, tuple[str, ...]] = {
    "gallons":     ("gallon", "gallons", "gal"),
    "cambros":     ("cambro", "cambros", "jug", "jugs", "container", "containers"),
    "cups":        ("cup", "cups"),
    "napkins":     ("napkin", "napkins"),
    "creamer":     ("creamer",),
    "stir sticks": ("stir stick", "stir sticks"),
    "sugar":       ("sugar",),
    "lemon tongs": ("lemon tongs", "tongs"),
    "lemons":      ("lemon", "lemons"),
    "tea packets": ("tea packet", "tea packets", "tea bag", "tea bags"),
    "everything":  ("bring", "pull sheet", "pack"),
}   # canonical item name -> the words that mean it (all lower case)

def pull_sheet_items_in(text: str) -> tuple[str, ...]:
    """Canonical names of the items whose words appear in text, each at most once, in the
    order of PULL_SHEET_ITEMS. Matching ignores case and works on whole words or phrases
    (so "lemonade" is not "lemons" and "cupboard" is not "cups"). Returns () for no match
    or blank text. Never raises. Prints nothing."""
```
The set is deliberately **generous**: a false match is harmless (the model still decides the route), a missed match would wrongly turn a TOOL part into DOCS.

### 3.2 The router: `src/blc/router/`
`RoutedPart`, `RouteDecision`, `ROUTES`, `ROUTE_KINDS` and `route_question(llm, history, question)` keep the signatures and meaning of spec 006 §3.1. Changes and new names:

```python
ROUTER_SCHEMA: dict   # JSON schema of the reply (§4.1): {"parts": [{"route": "TOOL" | "DOCS", "text": str}]}
ROUTER_PROMPT: str    # system prompt of the router; its intent is Appendix A
```
- `route_question` makes exactly one `llm.invoke(messages, ...)` call and calls **no other method** of `llm` (no `bind`, no `bind_tools`, no `with_structured_output`). The call carries the keyword argument `format=ROUTER_SCHEMA` and no other keyword arguments. Test fakes accept extra keyword arguments and record only the message list.
- The messages are as in spec 006 §3.1 (a system message `ROUTER_PROMPT`, then one human message containing the history's content and the question). No tool is bound and no documents are sent.
- Raises `ValueError` if `question` is blank, before any model call (unchanged).

## 4. Inputs and outputs

### 4.1 Reading the model's reply
Tried in this order; the first that gives at least one part wins:
1. **JSON.** The reply's `.content` is JSON: an object with a `"parts"` list. Each list item with a `"route"` that is `TOOL` or `DOCS` (any case) and a `"text"` string gives one part. Items that are not objects, lack either key, or have another route are ignored. A part with empty or blank text uses the whole question as its text (this happens before the guard of §4.2 looks at the part). An item whose `"text"` is not a string is ignored.
2. **Label lines**, exactly as spec 006 §4.1.
3. **Fallback**, exactly as spec 006 §4.1: one DOCS part with the whole question, `fallback=True`.

| Reply `.content` | Result |
|---|---|
| `{"parts":[{"route":"TOOL","text":"How many cups for 45 guests?"}]}` | (TOOL, "How many cups for 45 guests?"), kind TOOL |
| `{"parts":[{"route":"docs","text":"Where is the tea kept?"},{"route":"TOOL","text":"How many napkins should I bring?"}]}` | (DOCS, …), (TOOL, …), kind BOTH |
| `{"parts":[{"route":"DOCS","text":""}]}` | (DOCS, whole question) |
| `{"parts":[{"route":"MAYBE","text":"x"}]}` | fallback |
| `{"parts":[]}` | fallback |
| `{"parts":"oops"}` or `[1, 2]` | fallback |
| `DOCS: Where is the tea kept?` (not JSON) | (DOCS, "Where is the tea kept?") |
| `` (empty) or `not json at all` | fallback |

### 4.2 The guard
After the reply is read (from any of §4.1's formats, but not for the fallback), every TOOL part whose `text` has `pull_sheet_items_in(text) == ()` becomes a DOCS part with the same text. `kind` is then worked out again from the final parts. `fallback` is not changed by the guard. A DOCS part is never changed.

| Model says | Result |
|---|---|
| `TOOL: How many cambros for 3 gallons of mocha?` | stays TOOL (mentions cambros, gallons) |
| `TOOL: Where is the mint kept?` | becomes DOCS (no item) |
| `TOOL: How many cups for 25 guests?` + `DOCS: Where is the mint kept?` | stays BOTH |
| `TOOL: Where is the mint kept?` + `TOOL: How many cups for 25 guests?` | (DOCS, …), (TOOL, …), kind BOTH |
| `TOOL: Where is the mint kept?` alone | one DOCS part, kind DOCS, `fallback=False` |

### 4.3 The routing rule the prompt must teach
(Behaviour checked by the eval in §6; the wording is in Appendix A.)
- **TOOL:** a part that asks **how much or how many to make or bring**, or **whether to bring**, one of the `PULL_SHEET_ITEMS`, for beverages: gallons to make; which or how many cambros, jugs or containers, or what to put a drink in; how many cups; whether to bring (or how many of) napkins, creamer, sugar, stir sticks, lemons, lemon tongs, tea packets; what to bring or pack for drinks in general.
- **DOCS:** everything else. In particular, when a set word is used as an **ingredient, batch size or place**, not as an item to bring: recipes and method ("how to make 3 gallons of lemonade"), ingredient amounts ("how much sugar goes in a batch", "how many lemons do I squeeze"), where things are kept, what a menu name or package means, prices, schedules, cleaning, and drinks that are not on the menu.
- A question that asks for both gets one part per question, in the order asked. A recipe question that also gives a guest count ("how do I make X for 90 guests?") is split into a DOCS part (the recipe) then a TOOL part (how many gallons for those guests).
- Follow-ups are rewritten from the history into self-contained questions (as spec 006 §4.2).
- When unsure, DOCS.

## 5. Edge cases
**Item set (unit):**
- EC-1: every word of every item in §3.1 gives that item; matching ignores case ("CAMBROS", "Cups").
- EC-2: "lemonade" gives no `lemons`; "cupboard" gives no `cups`; "gallonage" gives no `gallons`.
- EC-3: several items in one text come back once each in `PULL_SHEET_ITEMS` order, whatever the order in the text ("Do I bring sugar for 5 gal and cups?" → `("gallons", "cups", "sugar", "everything")`).
- EC-4: `""`, whitespace and text with no item give `()`.

**Reading and guard (unit, fake model returning a fixed reply):**
- EC-5: every row of the §4.1 table.
- EC-6: every row of the §4.2 table.
- EC-7: a JSON TOOL part with no item becomes DOCS and `kind` follows; a JSON DOCS part that mentions an item stays DOCS.
- EC-8: the router makes exactly one `invoke` call, with keyword `format == ROUTER_SCHEMA` and no other keyword; no `bind`, `bind_tools` or `with_structured_output` call is made (a fake without those methods works).
- EC-9: blank question → `ValueError`, no model call (as spec 006 EC-3).
- EC-10: the fallback decision (unreadable reply) is DOCS with the whole question and is not changed by the guard.

**Prompt (unit):**
- EC-11: `ROUTER_PROMPT` is a non-empty string that contains every key of `PULL_SHEET_ITEMS`, and the words `TOOL` and `DOCS`. (Its wording is not tested.)

**Eval (real model `ChatOllama(model=CHAT_MODEL, temperature=0)`, empty history):** §6 AC-6.

## 6. Acceptance criteria
- **AC-1 (item set):** `PULL_SHEET_ITEMS` has exactly the keys and words of §3.1, and `pull_sheet_items_in` behaves as EC-1 to EC-4.
- **AC-2 (reading):** the router reads JSON, then label lines, then falls back, as §4.1 and EC-5, EC-9, EC-10.
- **AC-3 (guard):** a TOOL part with no set item becomes DOCS, `kind` follows, nothing else changes (§4.2, EC-6, EC-7).
- **AC-4 (call shape):** EC-8 and EC-11.
- **AC-5 (spec 006 regression):** spec 006's flow tests (`tests/router/test_answer_flow.py`) and its router parsing tests still pass, **except** tests whose TOOL part text mentions no set item (for example `TOOL: x`): the tester of this spec rewrites those so their TOOL text mentions an item, and adds nothing else to them. This covers **every** such use in `tests/router/`, including fake replies in tests that only check printing, history or blank questions: no test may use a TOOL reply with no set item (e.g. `TOOL: x`) unless it is testing the guard itself.
- **AC-6 (router eval):** with the real model, `route_question` gives exactly one of the listed routes, in order, for the cases below **and** spec 006's R1 to R14; `fallback` is `False`. **Pass threshold:** every case in groups A to D; at least 2 of the 3 cases in group E. Groups A to D are one test per case. Group E may stay one test, but its output (and its failure message) must list each case's id, its routes and its parts' text, so a failing case can be seen. Test docstrings cite the AC ids of this spec (the eval is AC-6).

**Eval cases** (routes in order; `DOCS, TOOL` means two parts)

| id | group | question | routes |
|---|---|---|---|
| A1 | A: clearly DOCS | Where do we keep the stir sticks? | DOCS |
| A2 | A | What is the difference between Decaf and Coffee on a BEO? | DOCS |
| A3 | A | How long does brewed hot cider stay good? | DOCS |
| B1 | B: clearly TOOL | How many hot cups do I need for 120 guests? | TOOL |
| B2 | B | Do I bring tea packets for hot water? | TOOL |
| B3 | B | How many gallons of orange juice for 60 people? | TOOL |
| B4 | B | Which cambros do I use for 12 gallons of Ginger Honeycrisp apple cider? | TOOL |
| C1 | C: clearly BOTH | What is Oatmilk counted in, and how many cups do I need for 80 guests? | DOCS, TOOL |
| C2 | C | Where are the lemon tongs kept, and do I bring lemons for hot water for 40 guests? | DOCS, TOOL |
| C3 | C | How do I clean the coffee urn, and which cambros hold 4 gallons of decaf? | DOCS, TOOL |
| C4 | C (order) | How many napkins should I bring, and what is in the orange juice package? | TOOL, DOCS |
| D1 | D: ambiguous, must be DOCS | How to make 3 gallons of lemonade? | DOCS |
| D2 | D | How do I make 6 gallons of iced tea? | DOCS |
| D3 | D | How much sugar goes in a batch of lemonade? | DOCS |
| D4 | D | How many lemons do I squeeze for a gallon of lemonade? | DOCS |
| D5 | D | What are the steps to brew 5 gallons of coffee? | DOCS |
| D6 | D (partner of D1) | How many cambros for 3 gallons of lemonade? | TOOL |
| E1 | E: recipe plus guests | How do I make lemonade for 90 guests? | DOCS, TOOL |
| E2 | E | What is the recipe for iced tea for 120 people, and how much do I need? | DOCS, TOOL |
| E3 | E | How do I make peach tea for 60 guests? | DOCS, TOOL |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-5 tests need no Ollama and no network and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The eval (AC-6) is marked `eval` and skips, not fails, when Ollama is missing. | unit (marker review) |
| NFR-4 | `ROUTER_PROMPT` contains no question from §6 or from spec 006 §6, spec 005 §6 and spec 004 §6, and no example uses their drinks and amounts. | manual (code review) |
| NFR-5 | The item list in `ROUTER_PROMPT` is built from `PULL_SHEET_ITEMS`, not typed a second time. | manual (code review) |
| NFR-6 | The router call adds at most about 1 s over spec 006's router call on the eval run. | manual (timed by the planner) |
| NFR-7 | `PULL_SHEET_ITEMS` still matches the rules in `data/pull_sheet/rules/beverages.json` (every supply there is covered by an item). | manual (planner review whenever the rules change) |
| NFR-8 | Router files stay about 250 lines each, split by job (item set, prompt, reading, routing). Calculation code does no I/O. | manual (code review) |

Tests go in `tests/router/`: `test_router_items.py` (AC-1), `test_router_parsing.py` (AC-2, AC-3, AC-4, extended and with the AC-5 rewrites), `test_router_eval.py` (AC-6, extended; the new cases go in `conftest.py`).

## Appendix A: Router system prompt (for the developer; its wording is not tested)
`ROUTER_PROMPT` should say the following. The developer may reword and shorten it, but must keep every rule and the style of the examples. Build the item list from `PULL_SHEET_ITEMS` (NFR-5); `{ITEM_LIST}` stands for one line per item: the name, then its words in brackets. The examples below are the only ones to use: they follow NFR-4 (they use drinks and amounts that are in no eval case).

```text
You route questions from Bay Laurel Catering staff. Split the question into parts and label every part TOOL or DOCS.

A calculator tool knows the beverage pull sheet. Label a part TOOL only when it asks HOW MUCH or HOW MANY of one of these items to make or bring, or whether to bring it:
{ITEM_LIST}
Menu drinks: Coffee, Decaf, Hot water, Brewed hot cider, Ginger Honeycrisp apple cider, Iced water, Iced tea, Orange juice, Lemonade, Peach tea, Oatmilk, and the package "Coffee, decaf, tea, iced water & juice".

Label everything else DOCS: recipes and how to make a drink, ingredient amounts, where things are kept, what a name or package means, prices, schedules, cleaning, and drinks that are not on the menu.

Check each part in this order:
1. Does it ask for an amount to make or bring, or whether to bring something, for one of the items above? If not, it is DOCS.
2. Is the item word used as the thing to bring, or only as an ingredient, a batch size or a place? Words like gallons, sugar and lemons show up in recipes: "how to make 8 gallons of X" asks for a method, and "how much sugar goes in X" asks for an ingredient amount. Those are DOCS. The amount in a recipe question is the batch size; it does not make the question TOOL.
3. If you are still not sure, choose DOCS.

Rules:
- If the question asks several things, write one part per question, in the order asked.
- If it asks how to make a drink and also gives a guest count, write a DOCS part for the recipe, then a TOOL part for how many gallons those guests need.
- Rewrite every part as a complete question that makes sense alone. If the latest message is a follow-up, use the chat history to fill in what it leaves out.
- Do not answer the question.

Reply only with JSON in this shape:
{"parts": [{"route": "TOOL", "text": "..."}, {"route": "DOCS", "text": "..."}]}

Examples:
Question: How do I make 8 gallons of mocha?
{"parts": [{"route": "DOCS", "text": "How do I make 8 gallons of mocha?"}]}

Question: How many cambros do I need for 8 gallons of mocha?
{"parts": [{"route": "TOOL", "text": "How many cambros do I need for 8 gallons of mocha?"}]}

Question: How much sugar goes into a batch of chai?
{"parts": [{"route": "DOCS", "text": "How much sugar goes into a batch of chai?"}]}

Question: Do I bring sugar for the chai station?
{"parts": [{"route": "TOOL", "text": "Do I bring sugar for the chai station?"}]}

Question: Where is the matcha kept, and how many cups for 25 guests?
{"parts": [{"route": "DOCS", "text": "Where is the matcha kept?"}, {"route": "TOOL", "text": "How many cups for 25 guests?"}]}

Question: How do I make cold brew for 60 guests?
{"parts": [{"route": "DOCS", "text": "How do I make cold brew?"}, {"route": "TOOL", "text": "How many gallons of cold brew for 60 guests?"}]}

History: the assistant asked "How many gallons of each?" about mocha and chai. Question: 3 each.
{"parts": [{"route": "TOOL", "text": "How many cambros for 3 gallons of mocha and 3 gallons of chai?"}]}
```
(The JSON braces in the examples must be written so that building the prompt from `PULL_SHEET_ITEMS` does not break them.)
