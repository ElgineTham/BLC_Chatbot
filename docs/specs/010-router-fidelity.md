# Spec 010: Router fidelity (keep the user's wording)

- **Status:** approved
- **Date:** 2026-11-11

## 1. Goal
A diagnostic of the router on `qwen2.5:7b` (after spec 007) showed it changes the meaning of questions before the tool step sees them:
- "I need 5 gallons of coffee and lemonade. How many cambros?" was split into **two** parts, one per drink;
- "We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros?" became "How many cambros do I need for 70 guests?" (**the package name was dropped**);
- "Brewed hot cider for 100 people, what goes on the pull sheet?" became "How many **gallons** of brewed hot cider for 100 people?" (**a different question**).

The cause is the prompt rule "rewrite every part as a complete, self-contained question": the model applies it to questions that were already clear. This spec makes the **code** decide whether a rewrite is acceptable, with checks that do not depend on the model's judgment:
1. With no chat history, every part must be copied from the question (it may only cut the question between separate questions).
2. With chat history, a part may be rewritten (a follow-up like "5 each" needs the history), but the rewrite must keep every number, menu drink name and pull sheet item the user wrote.
3. A reply that fails the check is sent back to the model once with the reason. If it fails again, the decision falls back to **the whole original question as one part** (option 1 of the design discussion).

`route_question` (spec 006/007) is not changed. The check lives in a new function that wraps it, and `answer_with_tools` calls the new function.

## 2. Out of scope
- `route_question`, `ROUTER_SCHEMA`, the item set and the item guard (spec 007), including their tests.
- The tool step, the argument check (spec 009), retrieval and the final call.
- Stopping the model from splitting a follow-up per drink (e.g. "5 each" into two TOOL parts): the checks below cannot see it (every number, drink and item is still there). It is handled by the prompt and measured by the eval (F4); a code rule is a later spec if the eval shows it is needed.
- Keeping the TOOL/DOCS split of a mixed question when the fallback happens (the fallback is one part).
- `CHAT_MODEL` stays `qwen2.5:7b`.

## 3. Interface contract

### 3.1 The drinks set: `src/blc/router/drinks.py` (new)
Importable as `from blc.router import MENU_DRINKS, menu_drinks_in`.

```python
MENU_DRINKS: tuple[str, ...] = (
    "coffee", "decaf", "hot water", "brewed hot cider", "ginger honeycrisp apple cider",
    "cider", "iced water", "iced tea", "orange juice", "lemonade", "peach tea", "oatmilk",
    "tea", "juice", "package",
)   # lower case words and phrases that name a menu drink or the package

def menu_drinks_in(text: str) -> tuple[str, ...]:
    """The entries of MENU_DRINKS that appear in text, each at most once, in MENU_DRINKS
    order. Matching ignores case and works on whole words or phrases ("lemonade" is not
    found in "lemonades"; "tea" is found in "iced tea"). () for no match or blank text.
    Never raises. Prints nothing."""
```

### 3.2 The fidelity check and the router wrapper: `src/blc/router/`
Importable as `from blc.router import FIDELITY_PREFIX, check_fidelity, route_faithfully`.

```python
FIDELITY_PREFIX: str = "invalid (rewrite): "

def check_fidelity(
    question: str,
    history: list[dict[str, str]],
    parts: tuple[RoutedPart, ...],
) -> str | None:
    """None if the parts are faithful to the question (§4.1). Otherwise one line, starting
    with FIDELITY_PREFIX, that says what to change. Never raises. No I/O. Prints nothing."""

def route_faithfully(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
) -> RouteDecision:
    """route_question plus the fidelity check and one retry (§4.2). Makes one or two
    llm.invoke calls, each with the keyword argument format=ROUTER_SCHEMA and no other
    keyword argument, and calls no other method of llm. Raises ValueError if question is
    blank (before any model call). Never raises for an unreadable or unfaithful reply.
    Prints nothing."""
```
`RouteDecision` gets one new field **with a default**, so existing code that builds it keeps working:
```python
@dataclass(frozen=True)
class RouteDecision:
    parts: tuple[RoutedPart, ...]
    kind: str
    fallback: bool
    unfaithful: bool = False   # NEW: True if the parts failed the check twice and this is the whole-question fallback (§4.2)
```

### 3.3 The chat flow: `scripts/chat.py`
`answer_with_tools` keeps its signature. It gets its `RouteDecision` from `route_faithfully(llm, history, question)` instead of `route_question`. So the router now takes **one or two** `llm.invoke` calls (spec 006 §3.2 said exactly one); everything after it is unchanged. A DOCS-only answer therefore makes 2 or 3 `llm.invoke` calls and no `bind_tools` call.

## 4. Inputs and outputs

### 4.1 `check_fidelity`
Let `Q` be the question and `texts` the parts' texts. Comparing text means: ignoring case, runs of spaces, and any punctuation at the start or end of a part.

- **Rule V (verbatim):** every part's text occurs inside `Q`.
- **Rule P (preserved)**, used only when `history` is not empty: all three hold:
  - every number written in `Q` (digits, decimals, `1,000`, or spelled out from "zero" to "one hundred", as in spec 009 §4.1) appears, **by value**, in the parts' texts taken together;
  - every entry of `menu_drinks_in(Q)` appears in the parts' texts taken together (as whole words or phrases);
  - every item of `pull_sheet_items_in(Q)` is among the items of `pull_sheet_items_in(" ".join(texts))`. The parts may add items (a follow-up rewrite gets "cambros" from the history) but may not drop one.
- The parts are **faithful** if rule V holds, or if `history` is not empty and rule P holds. Otherwise the result is a reason.
- The reason is one line (no newline). It starts with `FIDELITY_PREFIX`. When rule V fails and there is no history it contains the text of the first part that is not in `Q`. When rule P fails it contains each lost number, drink name and item word as written in `Q`. It also tells the model to copy the user's own words.

| Question | History | Parts | Result |
|---|---|---|---|
| I need 9 gallons of decaf and hot water, how many containers? | none | (TOOL, the whole question) | `None` |
| I need 9 gallons of decaf and hot water, how many containers? | none | (TOOL, How many containers for 9 gallons of decaf?), (TOOL, How many containers for 9 gallons of hot water?) | reason (not inside the question) |
| The decaf, tea, iced water package is ordered for 110 guests, how many cups? | none | (TOOL, How many cups for 110 guests?) | reason (not inside the question) |
| Where is the creamer kept, and do I bring sugar for hot water for 35 guests? | none | (DOCS, Where is the creamer kept?), (TOOL, do I bring sugar for hot water for 35 guests?) | `None` |
| Peach tea for 80 people, what should I pack? | none | (TOOL, How many gallons of peach tea for 80 people?) | reason (not inside the question) |
| Peach tea for 80 people, what should I pack? | one earlier turn | (TOOL, How many gallons of peach tea for 80 people?) | reason (names `pack`; the item is dropped) |
| 6 each. | assistant had asked "How many gallons of each?" about orange juice and iced tea | (TOOL, How many cambros for 6 gallons of orange juice and 6 gallons of iced tea?) | `None` (no drink or item is lost; "6" is kept) |
| 6 each. | same | (TOOL, How many cambros for 4 gallons of orange juice?) | reason (names `6`) |
| Seven gallons of decaf, which containers? | one earlier turn | (TOOL, Which containers hold 7 gallons of decaf?) | `None` (7 equals "Seven"; gallons and containers are kept) |

### 4.2 `route_faithfully`
1. Make the first call exactly as `route_question` does and read it (including the spec 007 guard). If the reply was unreadable (`decision.fallback` is `True`), return that decision as it is, with **no** retry.
2. If `check_fidelity(question, history, decision.parts)` is `None`, return the decision as it is.
3. Otherwise make **one more call**. Its messages are the first call's messages, then the model's first reply (as an assistant message), then one human message that contains the reason. Read it as in step 1.
4. If that reply is readable and `check_fidelity` returns `None` for it, return that decision (`unfaithful=False`).
5. Otherwise return the **whole-question fallback**: one part whose text is the stripped question, with `unfaithful=True` and `fallback=False`. The part's route is `TOOL` if every part of the latest readable decision was `TOOL`, else `DOCS`. If that route is `TOOL` but `pull_sheet_items_in(question) == ()`, it is `DOCS`. `kind` follows the one part.

| Situation | invoke calls | Result |
|---|---|---|
| First reply faithful | 1 | the first decision |
| First reply unfaithful, second faithful | 2 | the second decision, `unfaithful=False`; the second call's last message contains the reason |
| Both unfaithful, all parts TOOL | 2 | (TOOL, whole question), `unfaithful=True` |
| Both unfaithful, parts mixed or DOCS | 2 | (DOCS, whole question), `unfaithful=True` |
| First unfaithful, second unreadable | 2 | whole-question fallback, route from the first decision's parts |
| First reply unreadable | 1 | DOCS fallback of spec 006 (`fallback=True`, `unfaithful=False`) |

## 5. Edge cases
**`menu_drinks_in` (unit):**
- EC-1: every entry of `MENU_DRINKS` is found alone, ignoring case; "lemonades" does not give `lemonade`; "iced tea" gives `iced tea` and `tea`; the package text "coffee, decaf, tea, iced water & juice package" gives `coffee`, `decaf`, `tea`, `iced water`, `juice`, `package`; blank or no match gives `()`.

**`check_fidelity` (unit, no model):**
- EC-2: every row of §4.1.
- EC-3: rule V ignores case, extra spaces and punctuation at the ends of a part (a part `how many cups for 45 guests` is inside "Where is the tea? How many cups for 45 guests?"); punctuation inside the question must match (the package text with its commas and `&` is inside only if it is copied exactly).
- EC-4: with no history, a part that is a rewrite fails even if it keeps every number and drink.
- EC-5: with history, a rewrite that keeps every number, drink and item passes; losing one number, one drink or one item fails; adding a drink or an item that is only in the history passes.
- EC-6: numbers compare by value: "Seven" and `7`, `1,000` and `1000` match; `5` is not matched by `50`.
- EC-7: unusual input never raises (blank question, empty `parts`, odd history items, a very long question).
- EC-8: the reason has no newline and starts with `FIDELITY_PREFIX`.

**`route_faithfully` (unit, scripted fake model that records its calls):**
- EC-9: every row of the §4.2 table.
- EC-10: both calls carry `format == ROUTER_SCHEMA` and no other keyword; no `bind`, `bind_tools` or `with_structured_output` call; the second call's messages are the first call's messages, the first reply as an assistant message, then one human message with the reason.
- EC-11: blank question → `ValueError`, no model call.
- EC-12: the guard of spec 007 still applies to each reply (a TOOL part with no item becomes DOCS before the check), and to the whole-question fallback (§4.2 step 5).
- EC-13: a faithful decision from `route_faithfully` equals the decision `route_question` gives for the same reply.

**Flow (unit, scripted fake model, as spec 006 §5):**
- EC-14: `answer_with_tools` with a router that is unfaithful twice: the tool step and the final call receive the **whole question** (the TOOL part's text is the question), `route.unfaithful` is `True`, and the model is invoked for the router twice, then the final call once.
- EC-15: `answer_with_tools` with a faithful first reply makes the same calls as before this spec (one router call).

## 6. Acceptance criteria
- **AC-1 (drinks set):** `MENU_DRINKS` has exactly the entries of §3.1, and `menu_drinks_in` behaves as EC-1.
- **AC-2 (check):** `check_fidelity` gives the results in §4.1 and EC-2 to EC-8.
- **AC-3 (wrapper):** `route_faithfully` behaves as §4.2 and EC-9 to EC-13.
- **AC-4 (flow):** EC-14 and EC-15; spec 006's flow tests (`tests/router/test_answer_flow.py`) still pass after the tester of this spec makes **every scripted router reply faithful to the question the test passes** (no assertion weakened, nothing else changed). Spec 007's router tests (`test_router_items.py`, `test_router_reading.py`, `test_router_parsing.py`) are **not** changed and still pass.
- **AC-5 (router eval, real model):** with `ChatOllama(model=CHAT_MODEL, temperature=0)`, `route_faithfully` gives the listed result for every case below. The spec 007 eval (R1 to R14, A1 to D6, E1 to E3) is also run through `route_faithfully` (the tester changes the eval test to call it) with spec 007's thresholds. **Pass threshold:** every F case, and spec 007's thresholds.
- **AC-6 (whole flow, report only):** the planner runs spec 005's T1 to T26 through the chat flow once and reports the count and, for each failure, the router's parts. Not a gate.

**Router eval cases F** (real model; "one part" means exactly one part)

| id | history | question | expected |
|---|---|---|---|
| F1 | none | I need 5 gallons of coffee and lemonade. How many cambros? | one TOOL part whose text contains "coffee", "lemonade", "5" and "cambros" |
| F2 | none | We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros? | one TOOL part whose text contains "package", "70" and "cambros" |
| F3 | none | Brewed hot cider for 100 people, what goes on the pull sheet? | one TOOL part whose text contains "pull sheet" and "100" and not "gallons" |
| F4 | user: "How many cambros do I need for coffee and lemonade?"; assistant: "How many gallons of each drink, or how many guests?" | 5 gallons each. | one TOOL part whose text contains "coffee", "lemonade" and "5" |
| F5 | none | Where is the creamer kept, and do I bring sugar for the decaf for 60 guests? | DOCS then TOOL; each part's text is inside the question (rule V) |
| F6 | user: "Where is the coffee?"; assistant: "Under the coffee machine in the beverage room." | How many hot cups do I need for 130 guests? | one TOOL part whose text contains "130" and "cups" |
| F7 | user: "How many cups for the coffee, decaf, tea, iced water & juice package?"; assistant: "How many guests?" | 85 guests. | one TOOL part whose text contains "package", "85" and "cups" |

F1 to F3 and F5 have no history, so their parts must be copied from the question (rule V), or the whole-question fallback is used. The eval also reports, for each case, whether `unfaithful` was set (it is information, not a failure).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-4 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The AC-5 eval is marked `eval` and skips, not fails, when Ollama is missing. | unit (marker review) |
| NFR-4 | `ROUTER_PROMPT` contains no question from §6, spec 007 §6, spec 005 §6 or spec 004 §6, and no example uses their drinks together with their amounts. | manual (code review) |
| NFR-5 | The check is separate from the call: `check_fidelity` and `menu_drinks_in` take data and return data (no I/O, no model); `route_faithfully` only orders the calls. | manual (code review) |
| NFR-6 | A faithful first reply costs the same as before (one router call); an unfaithful one costs one more. | manual (review; the planner counts retries on the eval run) |
| NFR-7 | `MENU_DRINKS` still covers the menu in `data/pull_sheet/menu/beverages.md`. | manual (planner review whenever the menu changes) |
| NFR-8 | Files stay about 250 lines each, split by job (drinks set, fidelity check, wrapper). | manual (code review) |

Tests go in `tests/router/`: `test_router_drinks.py` (AC-1), `test_router_fidelity.py` (AC-2), `test_router_faithful.py` (AC-3), `test_answer_flow.py` (AC-4, edited), `test_router_eval.py` and `conftest.py` (AC-5, edited).

## Appendix A: Router prompt changes (for the developer; wording is not tested)
Keep `ROUTER_PROMPT` (spec 007 Appendix A) with these changes. The old rule "Rewrite every part as a complete question that makes sense alone" is **replaced**:
- **Copy, do not reword.** Write each part with the user's own words, exactly as in the question. Do not paraphrase, shorten or change a word. Cut the question only between separate questions. Keep every number, drink name, package name and phrase such as "pull sheet" exactly as written.
- **One part per question, not one per drink.** "Coffee and lemonade" stays in one part.
- **Rewrite only a follow-up.** If the latest message cannot be understood without the chat history (for example it only gives an amount, or says "each" or "the same"), write the complete question using the history, and keep every number and drink from the user's message.
- Add these examples (they follow NFR-4); keep the old ones that still fit:

```text
Question: I need 9 gallons of decaf and hot water, how many containers?
{"parts": [{"route": "TOOL", "text": "I need 9 gallons of decaf and hot water, how many containers?"}]}

Question: The coffee, decaf, tea, iced water & juice package is ordered for 110 guests, how many cups should I bring?
{"parts": [{"route": "TOOL", "text": "The coffee, decaf, tea, iced water & juice package is ordered for 110 guests, how many cups should I bring?"}]}

Question: Peach tea for 80 people, what should I pack?
{"parts": [{"route": "TOOL", "text": "Peach tea for 80 people, what should I pack?"}]}

History: the assistant asked "How many gallons of each?" about orange juice and iced tea. Question: 6 each.
{"parts": [{"route": "TOOL", "text": "How many cambros for 6 gallons of orange juice and 6 gallons of iced tea?"}]}
```
(Remove or reword any older example that rewrites a clear question. The old mocha/chai follow-up example stays valid.)

## Closure note (2026-11-12)
The user closed this spec for now. State at closing, from the implementation-evaluator's run on `qwen2.5:7b` and a blind comparison run on a larger model:
- **Met:** AC-1 to AC-4 (1056 unit tests pass, including the spec 006/007 regression).
- **Not met (AC-5, real-model router eval):** F3 routed DOCS instead of TOOL; C1 (spec 007) was not split; E2 gave DOCS, DOCS. The fidelity check itself behaved as specified (`unfaithful` was never set), so these come from the revised router prompt on the 7B model. Spec 007's prompt had passed C1 and the E group.
- **E1 and E3 (spec 007 group E):** the user judged them poor test cases ("How do I make lemonade for 90 guests?" asks only for a recipe). A larger model also answered DOCS only. They are not to be treated as router defects.
- **Not run:** AC-6 (whole-flow T1 to T26 count), the real-model fallback path (never triggered in the eval), and retry counting (NFR-6).
- **Open follow-ups, if the work resumes:** relax E1 and E3 to accept either route; restore the splitting behaviour of spec 007's prompt while keeping `check_fidelity` as the safeguard; accept parts that pass rule V or rule P without history (so rewrites that keep the context are allowed); record router call counts in the eval.
