# Spec 021: No invented numbers: a tool-description rule and an argument check

- **Status:** approved (revision 2, done: accepted by the user below the TOOL and BOTH thresholds)
- **Date:** 2026-11-14 (revisions 1 and 2: 2026-11-14)

## 1. Goal
The planner sometimes puts amounts into a tool call that the user never gave. For "For 60 guests of peach tea, how many cambros and cups", it sent `gallons: [6]`, and the tool correctly sized cambros for 6 gallons instead of 60 guests. Spec 020's log showed the same with `[10]` and `[12]`. This spec stops invented numbers in two layers:
1. **Rule in the tool description:** the planner's `calculate_bev_item` description gains the sentence **"Don't invent arguments or numbers that aren't there!"** A scratch test showed this line in the tool description cut invented numbers from 3 of 10 questions to 1. The same line in the planner prompt had no effect.
2. **Argument check in the flow:** before a planned `calculate_bev_item` or `scale_recipe` call runs, code checks every `guests` and `gallons` value against the numbers in the question and the chat history, including the assistant's replies.
   - If a value is not there, the planner is asked **once more**, told what it invented.
   - If the new plan still invents a value, that argument is **dropped**, so the tool works from what the user did give (e.g. guests), or asks.

A new **golden eval** of 30 new cases (10 TOOL, 10 DOCS, 10 BOTH) scores each case on three parts read from one run: the **gold call** (the expected arguments), the **invented-number check**, and the **required outcome** (the tool's real result, such as gallons, cambros and cups, or the document that must be retrieved). Each part is logged separately.

## 2. Out of scope
- **Checking words:** drinks, recipe names and `item` are not checked. They legitimately come from history and pronouns.
- **Numbers that appear elsewhere in the question:** the check can't catch a number used in the wrong argument when it appears somewhere else in the text, e.g. "the 5 gal cambros … for 80 guests" sent as `gallons: [5]`. The golden cases do not measure this. Fractions written as words ("half a gallon") are a known limit too, because they are not recognised as numbers.
- **The old flow:** `check_arguments`, `run_turn`, the router and `scripts/trace_flow.py` are not touched. Neither are the real `BEV_TOOL` and `RECIPE_TOOL`, the planner prompt `PLANNER_PROMPT`, `FLOW_ANSWER_PROMPT`, and the tools' calculations and texts.
- **The other example calls** in `PLANNER_BEV_TOOL`'s description: they stay, apart from the rule added in §3.1.
- **Answer quality.** Answers are logged, not scored. Drinks are now scored (part 1), so the planner's known habit of dropping the drink when only guests are given will show up as part 1 failures.

## 3. Interface contract

### 3.1 `blc.planner` (changes to spec 018's package)
```python
NO_INVENTED_RULE = "Don't invent arguments or numbers that aren't there!"
# PLANNER_BEV_TOOL.description contains NO_INVENTED_RULE verbatim. Its name, schema and other
# description text are unchanged. PLANNER_PROMPT is unchanged.

def plan_question(
    llm: BaseChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
    feedback: str | None = None,          # NEW, keyword or positional
) -> Plan:
    """As spec 018. With feedback=None the messages sent are exactly as before.
    With feedback, the messages sent also contain feedback verbatim, after the question
    (layout is the developer's); still exactly one bind_tools and one invoke."""
```

### 3.2 `blc.flow` (changes to spec 019's package)
```python
CHECKED_ARGUMENTS: tuple[str, ...] = ("guests", "gallons")

def invented_numbers(
    name: str,
    args: Mapping[str, object],
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, tuple[object, ...]]:
    """For a calculate_bev_item or scale_recipe call: each CHECKED_ARGUMENTS argument that has
    at least one invented value, mapped to its invented values in order. {} when nothing is
    invented, and always {} for any other tool name. Pure; never raises."""

@dataclass(frozen=True)
class RejectedCall:
    name: str
    args: dict[str, object]                     # as planned
    invented: dict[str, tuple[object, ...]]     # as invented_numbers returned it

# TurnOutcome (spec 019) gains three fields, after its existing ones:
#   first_plan: Plan                        # the planner's first plan
#   rejected: tuple[RejectedCall, ...]      # calls of the first plan with invented numbers, in plan order
#   retried: bool                           # True when the planner was asked a second time
# TurnOutcome.plan is the plan that was run (the second plan when retried, else the first).
# TurnOutcome.tools holds the args that were actually run (after any drop, §4.3).
```
`run_planned_turn` and `build_flow_graph` keep their signatures. The graph keeps the nodes `plan`, `run` and `reply`, and may add more.

### 3.3 Tests carried over from spec 020
In `tests/bev_tools/test_cups_text.py::test_cup_line_sentence_counts_at_extras_band_edges`, the check `"1 guests" not in r.text` becomes a whole-word check. It must not match inside "21 guests", "51 guests" or "101 guests". It is applied only where the guest count is exactly 1, or written as a check for "1 guests" not preceded by a digit.

## 4. Inputs and outputs

### 4.1 Which numbers count as given
The **allowed text** is the stripped question plus the `content` of every history item (`user`, `assistant` and `summary`). The **allowed numbers** are every number in that text:
- **digits,** matched as whole numbers, so "60" gives 60, never 6;
- **decimals and thousands separators:** "2.5" and "1,200";
- **number words from zero to one hundred,** including hyphenated and spaced compounds: "twenty-five", "forty five", "one hundred".

The number **1** is always allowed, because a user writes "a gallon" or "one cambro" without a digit.

### 4.2 What is checked
| Call | Checked values |
|---|---|
| `calculate_bev_item` | `guests`, and each value in a `gallons` list (or a single `gallons` value) |
| `scale_recipe` | `guests` and `gallons` |
| `search_documents` | nothing |

- **Invented:** a value that is a number (int, float or numeric string; never a bool) and is not among the allowed numbers.
- **Not checked here:** a value that isn't a number (`"lots"`, `null`, `[]`). The tool reports it.

### 4.3 Check, retry, drop
1. **Check the first plan.** Every tool call in it goes through `invented_numbers`. The calls with something invented are recorded in `rejected`.
2. **Nothing invented:** run the first plan. `retried=False`.
3. **Something invented:** ask the planner **once more**, with `feedback`. The feedback text contains `NO_INVENTED_RULE`, plus each rejected call's tool name, each invented argument's name and its invented values. Then:
   - check the second plan the same way;
   - run its calls, with every argument that still has an invented value **removed from that call** (the whole `gallons` list, or `guests`);
   - set `retried=True`.
4. **No third planner call.** A turn makes at most two planner calls and at most one answer call.

The second plan replaces the first entirely, so its route decides the turn. The spec 019 rules then apply unchanged: the reply rules, the pass-through, `NO_DOCS_REPLY` and streaming.

### 4.4 The golden eval
Each of the 30 golden cases runs **one** `run_planned_turn` (real models, real store, real tools; one warm-up call first). It is scored on **three parts**, all read from that run's `TurnOutcome`. The scorer runs no model.

**Part 1, gold call.** The tool calls that ran (`outcome.tools`, after any drop) must match the case's gold calls as a multiset: same count, no extra calls. Two calls match when:
- the names are equal;
- for `calculate_bev_item`:
  - `item` is equal;
  - `drinks` are equal as a set of names, stripped and casefolded (missing, `null` or `[]` means none);
  - `guests` are equal (missing or `null` means none);
  - `gallons` are equal, as lists of numbers compared by value (missing, `null` or `[]` means none);
- for `scale_recipe`:
  - `recipe` is equal, stripped and casefolded;
  - `guests` are equal;
  - `gallons` are equal as one number (a one-item list counts as its number).

Numbers are compared by value: `6 == 6.0`, numeric strings count, and bools never do. A case may list **alternative gold calls** ("any of"). Any one alternative matching passes. DOCS cases have **no** gold calls, so any tool result fails part 1.

**Part 2, invented-number check.** No `guests` or `gallons` value in `outcome.tools` is outside the allowed numbers of §4.1 for that case's question and history. The scorer also records what the **first plan** invented (`outcome.rejected`) and whether the turn retried. Those two are reported, not scored.

**Part 3, required outcome.**
- **Tool cases:** the scorer re-runs the real tool on each call's run args (`run_bev_tool(args)` or `run_recipe_tool(args)`, which is deterministic and makes no model call). The structured result must hold the required facts:
  - **`calculate_bev_item`:**
    - `status == "ok"`;
    - each required drink is in `result.drinks` with the required gallons;
    - **lines:** for item `cambros` or `cups`, `result.lines` as (supply, quantity) pairs equal exactly the required lines. For `everything`, each required line is in `result.lines`. For `gallons`, `result.lines` is empty.
  - **`scale_recipe`:** `status == "ok"`, `result.gallons` equals the required gallons, and the "Lemon concentrate" ingredient's amount equals the required ounces.
- **Docs cases:** at least one `search_documents` call ran, and the **required document** is among the `metadata["source"]` of the chunks retrieved by any search. "Any of" lists several accepted documents.
- **BOTH cases:** both of the above.

**A case passes** when its route is right (`outcome.plan.route` equals the case's path), the tool cases have no search (TOOL path only), and parts 1, 2 and 3 all pass.

**Thresholds:** at least **9 of 10** pass on each path (G1 to G10, L1 to L10, B1 to B10).

**Report:** the eval prints one line per case, with:
- id;
- pass or fail;
- route;
- part 1 / part 2 / part 3, each shown as pass or fail;
- retried yes or no.

It ends with:
- the per-path pass counts;
- the per-part pass counts for each path;
- how many first plans invented a number;
- how many cases retried;
- how many still dropped a value after the retry.

**Log, one section per part.** The eval writes `logs/golden_calls_<YYYY-MM-DD_HHMMSS>.md`. Each case's section has these sub-sections:
- **Question:** id, path, question, history.
- **Plan:**
  - first plan: route and calls;
  - rejected calls with their invented values;
  - retried yes or no;
  - final plan: route and calls.
- **Part 1, gold call:** the gold call(s) or alternatives, the run calls, pass or fail, and for a failure which field differed (name, item, drinks, guests, gallons, recipe, or an extra or missing call).
- **Part 2, invented numbers:**
  - the allowed numbers found in the question and history;
  - each run `guests` and `gallons` value with allowed or invented;
  - pass or fail;
  - what the first plan invented.
- **Part 3, required outcome:**
  - for each tool call, the required facts and the actual result (status, drinks with gallons, lines, recipe gallons and concentrate oz), with pass or fail per fact;
  - for each search, its query and the retrieved source paths;
  - the required document, with pass or fail.
- **Answer:** the reply, verbatim; time to first piece; total time.
- **Verdict:** pass or fail, with the failed parts.

The file ends with the report's totals. If a case raises, its section records the error and the run continues.

## 5. Edge cases
**`invented_numbers` (unit, pure):**
- EC-1: `calculate_bev_item {"item": "cambros", "drinks": ["peach tea"], "guests": 60, "gallons": [6]}`, question "For 60 guests of peach tea, how many cambros and cups" → `{"gallons": (6,)}`.
- EC-2: the same call without `gallons` → `{}`.
- EC-3: `gallons: [7, 3]` with the question "7 gallons of peach tea and 3 gallons of hot water" → `{}`. `gallons: [7, 4]` → `{"gallons": (4,)}`.
- EC-4: number words.
  - Question "cambros for twenty-five guests of hot water", `guests: 25` → `{}`.
  - "forty five guests", `guests: 45` → `{}`.
  - "one hundred guests", `guests: 100` → `{}`.
- EC-5: decimals and commas.
  - "2.5 gallons of lemonade", `gallons: 2.5` → `{}`, and `gallons: 25` → `{"gallons": (25,)}`.
  - "1,200 guests", `guests: 1200` → `{}`.
- EC-6: the value 1 is always allowed: question "a gallon of decaf", `gallons: [1]` → `{}`.
- EC-7: history counts, the assistant's replies included.
  - History `[user "How many gallons of coffee for 100 guests?", assistant "Coffee: 4 gallons for 100 guests."]` with question "How many cambros for that?": `gallons: [4]` → `{}`, and `guests: 100` → `{}`.
  - `gallons: [5]` → `{"gallons": (5,)}`.
  - A `summary` item's numbers count too.
- EC-8: numeric strings are checked: `guests: "60"` against "60 guests" → `{}`, and `guests: "6"` → `{"guests": ("6",)}`.
- EC-9: these values are not checked, so → `{}`: `guests: true`, `gallons: "lots"`, `gallons: null`, `gallons: []`.
- EC-10: a `scale_recipe` call `{"recipe": "lemonade", "guests": 75, "gallons": 3}` with the question "How do I make lemonade for 75 guests?" → `{"gallons": (3,)}`.
- EC-11: `search_documents {"query": "where are the 9 cambros"}` → `{}` with any question. So does a tool name not in §4.2.
- EC-12: a whole-number match only: the question "60 guests" never allows 6; "16 gallons" never allows 6.

**Flow (unit; scripted fake planner and answer models, fake store, fake runners):**
- EC-13 (nothing invented): the first plan is run, there is one planner call, `retried=False`, `rejected=()` and `first_plan == plan`.
- EC-14 (retry fixes it): the first plan has `cambros {"guests": 60, "gallons": [6]}`, and the second has `cambros {"guests": 60}`.
  - Two planner calls. The second call's messages contain `NO_INVENTED_RULE`, `calculate_bev_item`, `gallons` and `6`.
  - The runner gets `{"item": "cambros", …, "guests": 60}`.
  - `retried=True`. `rejected` has one call, with `invented == {"gallons": (6,)}`.
- EC-15 (retry still invents, so drop): the second plan still has `gallons: [6]` → the runner gets the call **without** `gallons`, and its other args are unchanged. There is no third planner call, and `retried=True`.
- EC-16 (drop keeps real values): the second plan has `guests: 60, gallons: [6]` for the question "For 60 guests…" → `gallons` is dropped and `guests: 60` kept. With an invented `guests` and real `gallons`, only `guests` is dropped.
- EC-17 (the retry changes the route): the first plan is a search plus an invented tool call; the second plan is a search only. The outcome's `plan.route` is `DOCS`, and no runner is called.
- EC-18: a recipe call with invented `gallons` is handled the same way: retried, then dropped.
- EC-19: `plan_question(..., feedback=None)` sends exactly the same messages as without the argument (spec 018's tests still pass). With feedback "X", the messages contain "X", and there is still one `bind_tools` and one `invoke`.
- EC-20: `PLANNER_BEV_TOOL.description` contains `NO_INVENTED_RULE`. The schema is unchanged: same properties, required list and `item` enum. `PLANNER_PROMPT` does not contain `NO_INVENTED_RULE`. `BEV_TOOL.description` does not contain it.
- EC-21: the turn makes at most 2 planner calls and at most 1 answer call. Without a retry it makes exactly 1 planner call.

## 6. Acceptance criteria
- **AC-1 (number check):** EC-1 to EC-12.
- **AC-2 (retry and drop):** EC-13 to EC-18 and EC-21.
- **AC-3 (planner contract):** EC-19 and EC-20.
- **AC-4 (golden eval, TOOL):** at least 9 of G1 to G10 pass (§4.4).
- **AC-5 (golden eval, DOCS):** at least 9 of L1 to L10 pass.
- **AC-6 (golden eval, BOTH):** at least 9 of B1 to B10 pass.
- **AC-7 (report and log):** the report and the per-part log of §4.4 are produced, with 30 case sections, each holding every sub-section.
- **AC-7b (scorer):** the §4.4 scorer is a pure function of a case, a `TurnOutcome` and a tool-result function. It is unit-tested on hand-made outcomes with fake tool results, covering:
  - each part passing and failing;
  - "any of" alternatives;
  - a DOCS case with a tool result;
  - a dropped value counting as not invented;
  - exact line equality for cambros and cups versus subset for `everything`;
  - the required document found in a second search.
- **AC-8 (carry-over):** §3.3.
- **AC-9 (regression):** every other existing unit test passes unchanged, including spec 018's `tests/planner/` and spec 019's `tests/planned_flow/`. The exception is the 3 spec 019 tests named in revision 1, whose fixtures are updated as stated there. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's `DIDNT_CATCH` change).

### Golden cases
These are new questions, not reused from earlier specs. The required outcomes were computed with the real tools and checked against `data/pull_sheet/rules/beverages.md`:
- 1 gallon per 25 guests, rounded half up;
- cups = guests plus 10, 20, 50 or 100 extras;
- cambro sizes 5, 2 and 1 gal;
- 7 oz of lemon concentrate per gallon.

Each required document was checked to come back in the top 3 for its part's wording. History is none unless listed. Abbreviations:
- `bev(item; drinks; gallons; guests)` and `rec(recipe; gallons; guests)` are the gold calls;
- "–" means left out;
- "any of" lists alternatives.

Paths are relative to the repo root.

**Cases G: TOOL (no search allowed, no required document)**
| id | question | gold call(s) | required outcome |
|---|---|---|---|
| G1 | How many cambros for brewed hot cider for 85 guests? | bev(cambros; brewed hot cider; –; 85) | Brewed hot cider 3 gal; lines {5 gal cambro: 1} |
| G2 | Cups needed for orange juice and decaf, 140 guests? | bev(cups; orange juice, decaf; –; 140) | Orange juice 6 gal, Decaf 6 gal; lines {hot-cups: 240, cold-cups: 240} |
| G3 | How many gallons of iced water for 210 guests? | bev(gallons; iced water; –; 210) | Iced water 8 gal; no lines |
| G4 | Which cambros hold 9 gallons of iced tea? | bev(cambros; iced tea; [9]; –) | Iced tea 9 gal; lines {5 gal cambro: 2} |
| G5 | How do I make lemonade for 45 people? | rec(lemonade; –; 45) | 2 gallons; lemon concentrate 14 oz |
| G6 | How much lemon concentrate for 2.5 gallons of lemonade? | rec(lemonade; 2.5; –) | 2.5 gallons; lemon concentrate 17.5 oz |
| G7 | How many cambros for twenty-five guests of hot water? | bev(cambros; hot water; –; 25) | Hot water 1 gal; lines {1 gal cambro: 1} |
| G8 | What goes on the pull sheet for decaf for 55 guests? | bev(everything; decaf; –; 55) | Decaf 2 gal; lines include {2 gal cambro: 1, hot-cups: 105, Stir sticks: 1, Sugar: 1} |
| G9 | history: user "How many gallons of coffee for 100 guests?" / assistant "Coffee: 4 gallons for 100 guests."; question "How many cambros for that?" | any of: bev(cambros; coffee; [4]; –), bev(cambros; coffee; –; 100), bev(cambros; coffee; [4]; 100) | Coffee 4 gal; lines {5 gal cambro: 1} |
| G10 | history: user "How many cups for peach tea?" / assistant "How many guests?"; question "65 guests." | bev(cups; peach tea; –; 65) | Peach tea 3 gal; lines {cold-cups: 115} |

**Cases L: DOCS (no tool result allowed)**
| id | question | required document |
|---|---|---|
| L1 | If the coffee shelf is empty, where do I get more coffee supplies? | `data/supplies/coffee.md` |
| L2 | What flavors of concentrate are on the blue racks? | `data/supplies/concentrates.md` |
| L3 | Do we bring stir sticks for iced tea? | `data/pull_sheet/rules/beverages.md` |
| L4 | How do I pull stock of syrups? | `data/supplies/syrups.md` |
| L5 | What's the rule for cold cups when lemonade is ordered? | `data/pull_sheet/rules/beverages.md` |
| L6 | Is orange juice part of the beverage package? | `data/pull_sheet/menu/beverages.md` |
| L7 | Where are the backup lemons? | `data/supplies/lemon.md` |
| L8 | Is peach tea a hot or a cold drink? | `data/pull_sheet/menu/beverages.md` |
| L9 | Does oatmilk go in a cambro? | `data/pull_sheet/menu/beverages.md` |
| L10 | history: user "Where are the syrups kept?" / assistant "Above the lemons in the beverage cooler."; question "And the concentrates?" | `data/supplies/concentrates.md` |

**Cases B: BOTH (one tool part, one documents part)**
| id | question | gold call(s) | required outcome | required document |
|---|---|---|---|---|
| B1 | Where are the backup coffee supplies, and how many cambros of coffee for 80 guests? | bev(cambros; coffee; –; 80) | Coffee 3 gal; lines {5 gal cambro: 1} | `data/supplies/coffee.md` |
| B2 | How many cups for decaf for 150 guests, and what does decaf mean on a BEO? | bev(cups; decaf; –; 150) | Decaf 6 gal; lines {hot-cups: 250} | `data/pull_sheet/menu/beverages.md` |
| B3 | Where is the lemon concentrate kept, and how do I make lemonade for 90 guests? | rec(lemonade; –; 90) | 4 gallons; lemon concentrate 28 oz | `data/supplies/concentrates.md` |
| B4 | How many gallons of peach tea for 70 guests, and what flavors of syrup do we have? | bev(gallons; peach tea; –; 70) | Peach tea 3 gal; no lines | `data/supplies/syrups.md` |
| B5 | How many cambros for 11 gallons of orange juice, and what sizes of cambros do we have? | bev(cambros; orange juice; [11]; –) | Orange juice 11 gal; lines {5 gal cambro: 2, 1 gal cambro: 1} | `data/pull_sheet/rules/beverages.md` |
| B6 | Do we bring lemons for hot water, and how many cups for hot water for 35 guests? | bev(cups; hot water; –; 35) | Hot water 1 gal; lines {hot-cups: 55} | any of: `data/pull_sheet/rules/beverages.md`, `data/supplies/lemon.md` |
| B7 | How much concentrate for 4 gallons of lemonade, and how do I pull stock of concentrates? | rec(lemonade; 4; –) | 4 gallons; lemon concentrate 28 oz | `data/supplies/concentrates.md` |
| B8 | What goes on the pull sheet for 120 guests of iced water, and is iced water a hot or cold drink? | bev(everything; iced water; –; 120) | Iced water 5 gal; lines include {5 gal cambro: 1, cold-cups: 220} | `data/pull_sheet/menu/beverages.md` |
| B9 | history: user "How many gallons of decaf for 60 guests?" / assistant "Decaf: 2 gallons for 60 guests."; question "Which cambros for that, and what's in the beverage package?" | any of: bev(cambros; decaf; [2]; –), bev(cambros; decaf; –; 60), bev(cambros; decaf; [2]; 60) | Decaf 2 gal; lines {2 gal cambro: 1} | `data/pull_sheet/menu/beverages.md` |
| B10 | Where are the lemons, and how many gallons of coffee for forty guests? | bev(gallons; coffee; –; 40) | Coffee 2 gal; no lines | `data/supplies/lemon.md` |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | The number check reuses spec 009's number finding (`blc.tool_step.numbers`) or behaves the same on EC-4, EC-5 and EC-12. `check_arguments` itself is not changed. | unit (EC-4, EC-5, EC-12); manual |
| NFR-2 | Changed code is limited to: `blc.planner` (the `feedback` parameter, `NO_INVENTED_RULE` and the description), and `blc.flow` (the check, retry, drop and the new `TurnOutcome` fields). There are no imports from `scripts/` and no new dependencies. | manual (code-evaluator) |
| NFR-3 | Unit tests need no Ollama, Chroma or network, and read nothing under `data/`. | unit (review) |
| NFR-4 | The eval is marked `eval`. It skips, not fails, without Ollama or the store, and writes only under `logs/`. | unit (marker); run output |
| NFR-5 | No eval question (G1 to B10) appears word for word in `PLANNER_PROMPT`, `PLANNER_BEV_TOOL`'s descriptions or `FLOW_ANSWER_PROMPT`. | unit |

Tests go in:
- `tests/no_invented/`, with no `__init__.py`:
  - `conftest.py`: fakes, the 30 cases and the scorer;
  - `test_numbers.py`: AC-1;
  - `test_retry.py`: AC-2;
  - `test_planner_feedback.py`: AC-3;
  - `test_scorer.py`: AC-7b;
  - `test_golden_eval.py`: AC-4 to AC-7;
- `tests/bev_tools/test_cups_text.py`: AC-8.

## Revision history
**Revision 1 (2026-11-14).** The first run passed the 195 unit tests and the golden eval's DOCS path (10/10). No invented number reached a tool (part 2: 30/30). In G1, the planner invented `gallons: [0]`, and the retry removed it. TOOL and BOTH scored 0/10 because of a **test bug**, and three spec 019 tests failed because of a **spec conflict**. Tester only; no code changes.

1. **Scorer bug (part 3).** The scorer's number helper `num()` in `tests/no_invented/conftest.py` returns `None` for `fractions.Fraction`. The real tools return amounts as `Fraction`: `DrinkAmount.amount`, `RecipeResult.gallons` and `ScaledIngredient.amount`. So every required-outcome comparison failed. G6 is an example: the answer was correct, "17.5 oz", and part 3 still failed.
   - Tester: make `num()` accept `Fraction`, and any real number, by value (bools are still never numbers).
   - Tester: add scorer tests that use `Fraction` amounts shaped like the real results. One must pass and one must fail on a wrong value.
2. **Part 3 log content (§4.4).** For each tool call, the log shows each required fact next to the actual value from the real result, with pass or fail per fact:
   - **`calculate_bev_item`:** status; each required drink with its required and actual gallons; the required and actual lines, and whether an exact or a subset match was needed.
   - **`scale_recipe`:** status; required and actual gallons; required and actual lemon concentrate oz.
   - **Searches:** the query and the retrieved source paths.

   Tester: extend the log writer, and assert in `test_golden_eval.py` that a part 3 section contains "required", "actual" and a per-fact result.
3. **Spec conflict (AC-9 against §4.3).** Three spec 019 tests plan numeric args for the dummy question `"q"`, which contains no numbers. The new check correctly treats those numbers as invented, so it retries and then drops them. The tests are:
   - `tests/planned_flow/test_reply.py::test_answer_model_is_called_at_most_once_per_turn`;
   - `tests/planned_flow/test_run.py::test_two_tool_calls_both_run`;
   - `tests/planned_flow/test_run.py::test_runner_that_raises_gives_error_result_and_the_turn_finishes`.

   Tester: change only their question text so it contains the numbers they plan (e.g. "How do I make 4 gallons of lemonade?" for `gallons: 4`). Every assertion stays as it is. AC-9 now allows this.
4. **Re-run** the golden eval after these fixes. The thresholds are unchanged.

Known model behaviours stay visible, as intended:
- the drink is dropped when only guests are given (G2, G3, G10, B6);
- B5 skips its search;
- G10 calls `scale_recipe` for a cups question.

**Revision 2 (2026-11-14).** Revision 1's unit side passed: 3145 tests, with only the accepted `DIDNT_CATCH` failure. The golden eval ran all 30 cases, then crashed in the **test-side log writer** before writing any report or log.
- **Cause:** pull sheet lines can have `quantity = None`. These are tick items such as "Cocktail napkins: bring" and "Creamer: bring" (e.g. G8, `everything`). The part 3 log helper `_tool_facts` in `tests/no_invented/test_golden_eval.py` calls `float(None)` on them.
- **Why the whole run stopped:** that code runs outside the per-case error handling, so one case aborted the run. §4.4 requires a raising case to be recorded while the run continues.
- **The scoring is not affected:** the required lines all have numbers, and extra tick lines are allowed by the `everything` subset rule.

Tester only; no code changes.
1. **Log writer:**
   - A line quantity of `None` is shown as "bring" (as the tool's own text does), never converted to a number.
   - Drink gallons, recipe gallons and ingredient amounts get the same guard.
   - A comparison that includes a `None` quantity must not raise.
2. **Per-case isolation:** each case's log section, scoring and report line are built inside the per-case error handling. A case whose scoring or formatting raises is recorded as an error, with its message, in its section and report line. The run then continues, and the case counts as failed.
3. **Unit tests for the log writer and report**, with no model, using fake outcomes and real-shaped results:
   - a bev result with a `quantity=None` line produces a part 3 section showing "bring" without raising;
   - a case whose formatting raises is recorded as an error, and the next case is still written;
   - Fraction amounts are shown by value (e.g. 17.5).
4. **Re-run** the golden eval. The thresholds are unchanged.

## Closing note (2026-11-14)
**Results:**
- **Unit tests:** 3154 passed; the only failure is the accepted `DIDNT_CATCH` test.
- **Golden eval:** TOOL 7/10, DOCS 10/10, BOTH 8/10. Part 2 (invented numbers) 30/30. G1's invented `gallons: [0]` was caught and removed by the retry. Log: `logs/golden_calls_2026-11-14_211346.md`.

**Failures, accepted by the user:**
- G2, G3 and B6: the planner dropped the drink when only guests were given. Spec 022 fills it in code.
- G10: `scale_recipe` was called for a cups follow-up.
- B5: the search was skipped.

**Weak test, carried to spec 022:** in `tests/no_invented/test_retry.py`, EC-14's check that the second planner call contains `6` can't fail, because the question itself ("For 60 guests…") contains a 6.
