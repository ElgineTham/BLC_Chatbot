# Spec 022: Keep the named drink: fill in dropped drinks in code

- **Status:** approved
- **Date:** 2026-11-14

## 1. Goal
When the user gives a guest count, the planner often leaves the drink out of the `calculate_bev_item` call. For "How many cups to bring for decaf, 40 guests" it sent `{"item": "cups", "guests": 40}`. The tool then answered for all drinks ("The same count applies to hot cups and to cold cups") instead of "Hot cups: 60". Spec 021's golden eval showed the same in G2, G3 and B6.

A rule in the tool description fixed only one of these cases and made a follow-up turn worse. A scratch test of a **code fix** fixed the user's conversation, G2, G3 and B6, and changed nothing in the other cases. This spec builds that fix as a named, tested step of the flow:
- **When:** after the planner, the invented-number check and any retry or drop (spec 021), the plan has **exactly one** `calculate_bev_item` call, and that call has **no drinks**.
- **What:** code adds the menu drinks the user named, taken from the question or, if the question names none, from the **most recent user message** in the history that names one.
- **Recorded:** the turn's outcome and the golden eval log show when drinks were filled in.

## 2. Out of scope
- **Plans with two or more `calculate_bev_item` calls.** They are never changed, even when one call has no drinks (e.g. spec 020's X4).
- **Calls that already have drinks.** Their drinks are never changed, added to or checked.
- **Short names** such as "tea", "hot tea" and "juice", which the beverage tool accepts on its own. Only the menu's item names, their `also_written_as` aliases and package names are recognised. Misspellings and plurals are not.
- **Assistant replies and summaries** in the history. Only user messages are searched for drink names.
- **`scale_recipe` calls.** Their `recipe` is not filled in.
- **The planner, its prompt, `PLANNER_BEV_TOOL`, the tools, `FLOW_ANSWER_PROMPT`, the old flow and voice.** They are unchanged. Answer wording (e.g. the reply leaving out "hot") is a later spec.
- **Refactoring the existing private uses** of `Catalog._names` in `blc.tools.bev_tools`.

## 3. Interface contract

### 3.1 `blc.pull_sheet` (spec 002/003's package)
```python
def menu_names(catalog: Catalog) -> dict[str, str]:
    """Every menu item name, every item alias (also_written_as) and every package name,
    normalised (case-folded, runs of whitespace as one space, stripped), mapped to the display
    name of its item or package. A new public function; Catalog and load_catalog are unchanged.
    Pure; never raises for a catalog built by load_catalog."""
```

### 3.2 `blc.flow` (spec 019/021's package)
```python
def drinks_named(text: str, names: Mapping[str, str]) -> tuple[str, ...]:
    """The display names of the menu drinks named in text, in order of first appearance,
    without repeats. names is a menu_names() result. Pure; never raises."""

@dataclass(frozen=True)
class FilledDrinks:
    call_index: int            # index of the filled call in the plan's calls
    drinks: tuple[str, ...]    # the display names added
    source: str                # FROM_QUESTION or FROM_HISTORY

FROM_QUESTION = "question"
FROM_HISTORY = "history"

def fill_missing_drinks(
    plan: Plan,
    question: str,
    history: list[dict[str, str]] | None,
    names: Mapping[str, str],
) -> tuple[Plan, FilledDrinks | None]:
    """The plan with the one drink-less calculate_bev_item call given the named drinks (§4.2),
    and what was filled. When nothing is filled: the plan unchanged (equal to the input) and None.
    Never changes the input plan. Pure; never raises."""
```

**Changes to existing names:**
```python
# TurnOutcome gains one field, after its existing ones:
#   filled: FilledDrinks | None     # None when nothing was filled in
# TurnOutcome.plan and TurnOutcome.tools show the filled drinks. first_plan and rejected
# are unchanged (they are the planner's own output).

def run_planned_turn(
    llm, store, question, history=None, on_token=None, planner_llm=None, tool_runners=None,
    drink_catalog: Catalog | None = None,       # NEW, last, keyword or positional
) -> TurnOutcome: ...

def build_flow_graph(
    llm, store, planner_llm=None, tool_runners=None,
    drink_catalog: Catalog | None = None,       # NEW, last
): ...
# drink_catalog=None turns the fill off: filled is None and the plan runs as before.
# With a catalog, the fill uses menu_names(drink_catalog).
```
All other arguments, defaults and behaviours of spec 019 and 021 stay as they are.

### 3.3 `scripts/chat.py`
- `main()` calls `load_catalog()` **once**, before the chat loop, through the module-level name `chat.load_catalog` (imported from `blc.pull_sheet`, so tests can replace it).
- Every `run_planned_turn` call in `main()` passes that catalog as `drink_catalog`.
- If `load_catalog()` raises (`RuleFileError` or `OSError`), `main()` still runs, passing `drink_catalog=None`.

### 3.4 Tests carried over from spec 021
In `tests/no_invented/test_retry.py`, EC-14's check that the second planner call contains `6` can't fail, because the question ("For 60 guests…") already contains a 6. It becomes a check on the **text added by the retry**: the content of the second planner call's messages that is not in the first call's messages contains `6` as a whole number (not inside "60"), plus `gallons`, `calculate_bev_item` and `NO_INVENTED_RULE`.

## 4. Inputs and outputs

### 4.1 `drinks_named`
- **Case:** matching ignores case. "DECAF" names Decaf.
- **Whitespace:** a run of spaces, tabs or newlines in the text matches one space in a name.
- **Whole words:** a name matches only when it is not preceded or followed by a letter. "decaffeinated" does not name Decaf, and "coffeemaker" does not name Coffee. Punctuation, digits and spaces around a name are fine ("decaf?", "(decaf)", "decaf,").
- **Longest name wins:** where names overlap, the longest one at that place is used, and the shorter names inside it are not matched separately. "iced tea with lemon wedges" names Iced tea once. The package name "Coffee, decaf, tea, iced water & juice" names only the package.
- **Display names:** each match gives its display name. An alias gives its item: "fresh-brewed coffee" gives "Coffee".
- **Order and repeats:** the order of first appearance in the text, each display name once.

### 4.2 `fill_missing_drinks`
1. **Which plans:** the plan's calls contain **exactly one** `calculate_bev_item` call, and that call has **no drinks**: no `drinks` key, or `drinks` is `None`, `[]` or a string that is empty after stripping. Other calls (`search_documents`, `scale_recipe`) don't count and are never changed. Any other plan → unchanged, `None`.
2. **Where the drinks come from:**
   - `drinks_named(question, names)`, if that is not empty → source `FROM_QUESTION`;
   - else the most recent history item with `role == "user"` whose `content` names at least one drink → its `drinks_named(...)`, source `FROM_HISTORY`. Items with other roles are skipped;
   - else nothing is filled → unchanged, `None`.
3. **The change:** that call's args gain `"drinks": [<display names>]`, a list in the order of §4.1. Every other argument of the call is kept as it is. The call's name and position, the other calls, the route and the fallback are unchanged.

### 4.3 In the flow
- The fill runs on the plan that is about to run: after spec 021's check, retry and drop, and before any tool runs. It makes no model call, so the turn's planner and answer call counts are as in spec 021.
- `TurnOutcome.plan` is the filled plan, `TurnOutcome.tools` holds the filled args, and `TurnOutcome.filled` records the fill.
- The numbers check of spec 021 is unaffected: drinks are not numbers.

### 4.4 Golden eval (spec 021 §4.4, extended)
- **Same 30 cases, scorer and thresholds** (at least 9 of 10 per path). Every `run_planned_turn` call passes `drink_catalog=load_catalog()`, loaded once per eval run.
- **Report:** each case line also shows whether drinks were filled. The totals add how many cases were filled.
- **Log:** each case's **Plan** sub-section gains a line after the final plan: `filled drinks: <drinks> from <source> (call <index>)`, or `filled drinks: none`.
- **Conversation C1 (report only, no threshold):** the user's three turns, run in order, each with the previous turn's `outcome.history`, and the fill on:
  1. "How many cups to bring for decaf, 40 guests";
  2. "How many cups to bring for 2 gallons of decaf";
  3. "50".

  For each turn, the eval reports and logs: the run calls, whether **every** `calculate_bev_item` call that ran names Decaf (stripped, ignoring case), the filled drinks, and the reply. It also re-runs the real tool on each run call, as part 3 does, and reports:
  - turn 1: a cups call whose result lines are exactly {hot-cups: 60};
  - turn 3: a cups call whose result lines are exactly {hot-cups: 70}.

  The log gets a C1 section after the 30 cases, with one sub-section per turn. The printed report ends with one C1 line per turn.

The required outcomes were checked with the real tool: Decaf cups for 40 guests → hot-cups 60; for 50 guests → hot-cups 70; cups for 2 gallons of Decaf with no guests → `need_info` "How many guests?".

## 5. Edge cases
Unit tests use a catalog built from spec 005 Appendix A's test menu (items Coffee with alias "Fresh-brewed coffee", Decaf with alias "Fresh-brewed decaffeinated coffee", Hot water, Iced water, Iced tea with alias "Iced tea with lemon wedges", Orange juice, Lemonade, Peach tea, Oatmilk, Brewed hot cider, Ginger Honeycrisp apple cider, and the package "Coffee, decaf, tea, iced water & juice"). `N` is `menu_names` of that catalog.

**`menu_names` (unit):**
- EC-1: `N["decaf"] == "Decaf"`, `N["fresh-brewed coffee"] == "Coffee"`, `N["iced tea with lemon wedges"] == "Iced tea"`, `N["coffee, decaf, tea, iced water & juice"] == "Coffee, decaf, tea, iced water & juice"`.
- EC-2: every key is case-folded and stripped. "tea", "hot tea" and "juice" are not keys. Every value is an item or package display name.

**`drinks_named` (unit, with `N`):**
- EC-3: "How many cups to bring for decaf, 40 guests" → `("Decaf",)`.
- EC-4: "Cups needed for orange juice and decaf, 140 guests?" → `("Orange juice", "Decaf")`.
- EC-5: "DECAF for 40" → `("Decaf",)`; "Iced\n  tea for 30" → `("Iced tea",)`.
- EC-6: "decaffeinated please" → `()`; "the coffeemaker is broken" → `()`; "(decaf)" → `("Decaf",)`; "decaf?" → `("Decaf",)`.
- EC-7: "iced tea with lemon wedges for 30" → `("Iced tea",)`; "fresh-brewed coffee and coffee" → `("Coffee",)`.
- EC-8: "the Coffee, decaf, tea, iced water & juice package for 120" → `("Coffee, decaf, tea, iced water & juice",)`.
- EC-9: "How many hot cups for 40 guests?" → `()`; "tea for 30" → `()`; "" → `()`.
- EC-10: "peach tea then lemonade then peach tea" → `("Peach tea", "Lemonade")`.

**`fill_missing_drinks` (unit, with `N`):**
- EC-11: plan TOOL `[bev {"item": "cups", "guests": 40}]`, question "How many cups to bring for decaf, 40 guests" → call args `{"item": "cups", "guests": 40, "drinks": ["Decaf"]}`; `FilledDrinks(0, ("Decaf",), "question")`. The route and fallback are unchanged, and the input plan is unchanged.
- EC-12: the same with `drinks: []`, `drinks: None` and `drinks: "  "` → filled the same way.
- EC-13: the call has `drinks: ["coffee"]` and the question names Decaf → unchanged, `None`.
- EC-14: two bev calls, one without drinks (question "How many cups and gallons of decaf do I need for 40 guests?") → unchanged, `None`.
- EC-15: no bev call (search only, or `scale_recipe` only) → unchanged, `None`.
- EC-16: plan BOTH `[search {"query": "lemons for hot water"}, bev {"item": "cups", "guests": 35}]`, question "Do we bring lemons for hot water, and how many cups for hot water for 35 guests?" → the bev call (index 1) gets `["Hot water"]`; the search call is unchanged; `call_index == 1`.
- EC-17: question "50", history `[user "How many cups to bring for decaf, 40 guests", assistant "Hot cups: 60 for 40 guests.", user "How many cups to bring for 2 gallons of decaf", assistant "How many guests?"]` → `["Decaf"]`, source `"history"`.
- EC-18: question "50", history `[user "cups for coffee", assistant "How many guests?", user "actually decaf", assistant "How many guests?"]` → `["Decaf"]` (the most recent user message wins).
- EC-19: question "50", history `[user "How many guests do we have?", assistant "Coffee for 40 guests."]` → unchanged, `None` (assistant text is not searched). A `summary` item naming a drink is not searched either.
- EC-20: question names Iced tea, history's user message names Decaf → `["Iced tea"]`, source `"question"`.
- EC-21: question and history name no drink (e.g. "How many cups for 45 guests?") → unchanged, `None`. History `None` behaves as `[]`.

**Flow (unit; scripted fake planner and answer models, fake store, fake runners, the test catalog):**
- EC-22: `run_planned_turn(..., drink_catalog=catalog)` with the question "How many cups to bring for decaf, 40 guests" and the planned call `bev {"item": "cups", "guests": 40}` → the bev runner gets `{"item": "cups", "guests": 40, "drinks": ["Decaf"]}`; `outcome.filled == FilledDrinks(0, ("Decaf",), "question")`; `outcome.plan`'s call has the drinks; `outcome.first_plan`'s call does not; `outcome.tools[0].args` has the drinks.
- EC-23: the same turn without `drink_catalog` (or with `None`) → the runner gets the call without drinks, and `outcome.filled is None`.
- EC-24: a turn that needs no fill → `outcome.filled is None`, and the run is as in spec 021.
- EC-25 (after the retry): the first plan has `bev {"item": "cups", "guests": 40, "gallons": [6]}` for "How many cups to bring for decaf, 40 guests"; the second plan has `bev {"item": "cups", "guests": 40}` → the runner gets `{"item": "cups", "guests": 40, "drinks": ["Decaf"]}`; `retried=True`; one rejected call; the fill is recorded.
- EC-26: with the fill on, the turn makes the same number of planner and answer calls as without it.

**`chat.main` (unit, as spec 020's `chat.main` tests):**
- EC-27: with `chat.load_catalog` replaced by a fake that counts calls and returns a sentinel, two turns → `load_catalog` called once, and both `run_planned_turn` calls get `drink_catalog` equal to the sentinel.
- EC-28: with `chat.load_catalog` raising `OSError` (and, separately, `RuleFileError`) → `main()` still answers turns, passing `drink_catalog=None`.

## 6. Acceptance criteria
- **AC-1 (`menu_names`):** EC-1 and EC-2.
- **AC-2 (`drinks_named`):** EC-3 to EC-10.
- **AC-3 (`fill_missing_drinks`):** EC-11 to EC-21.
- **AC-4 (flow):** EC-22 to EC-26.
- **AC-5 (`chat.main`):** EC-27 and EC-28.
- **AC-6 (golden eval):** at least 9 of 10 pass on each path (G, L, B), with the fill on (§4.4).
- **AC-7 (report and log):** the report and log of spec 021 §4.4 are produced with 30 case sections. Each Plan sub-section has the `filled drinks:` line, and the report counts filled cases. The C1 section is present with three turn sub-sections and the facts of §4.4. C1 has no threshold.
- **AC-8 (carry-over):** §3.4.
- **AC-9 (regression):** every other existing unit test passes unchanged, including `tests/planned_flow/`, `tests/no_invented/` and `tests/test_voice_io_answer_turn.py`. The exception is the `chat.main` fixture in `tests/test_voice_io_answer_turn.py`, which may replace `chat.load_catalog` so that no test reads `data/`; its assertions stay. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's `DIDNT_CATCH` change).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | Changed code is limited to: `blc.pull_sheet` (the new `menu_names`, exported from the package), `blc.flow` (`drinks_named`, `fill_missing_drinks`, `FilledDrinks`, the two constants, the `filled` field and the `drink_catalog` parameter) and `scripts/chat.py` `main()` (§3.3). The fill code does not read `Catalog`'s private fields outside `blc.pull_sheet`. No new dependencies. | manual (code-evaluator) |
| NFR-2 | `drinks_named` and `fill_missing_drinks` do no I/O and make no model call. | manual; unit (EC-26) |
| NFR-3 | The catalog is loaded at most once per chat session; the flow never loads it itself. | unit (EC-27); manual |
| NFR-4 | Unit tests need no Ollama, Chroma or network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-5 | The eval stays marked `eval`. It skips, not fails, without Ollama, the store or the catalog, and writes only under `logs/`. | unit (marker); run output |
| NFR-6 | New files stay near the size guidelines (about 250 lines for code, about 400 for tests). The golden eval's additions go in new helper files rather than growing `tests/no_invented/conftest.py`. | manual |

Tests go in:
- `tests/drink_fill/`, with no `__init__.py`:
  - `conftest.py`: the test catalog (built in a temp dir from spec 005 Appendix A's data), plan helpers and flow fakes;
  - `test_menu_names.py`: AC-1;
  - `test_drinks_named.py`: AC-2;
  - `test_fill.py`: AC-3;
  - `test_flow_fill.py`: AC-4;
- `tests/test_voice_io_answer_turn.py`: AC-5 and its fixture change (AC-9);
- `tests/no_invented/`: AC-6 and AC-7 (the eval and its log writer; new helpers in new files) and AC-8.
