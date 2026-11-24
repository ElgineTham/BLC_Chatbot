# Spec 046: Planner prompt restructure

- **Status:** done
- **Closed** (2026-11-23): every AC is met. The whole unit suite passed (3482 passed, 0 failed). The NOTEXT evals, spec 045's always evals (ASK, SCOPE, MIX) and the five other planner eval suites (36/36) passed in a single run. AC-3, AC-4 and AC-8 were checked by the planner.
- **Date:** 2026-11-23

## 1. Goal
Spec 045 left the ASK evals failing, and the cause was the planner prompt. Its framing ("decide … not by the topic", TOOL = "a number from an amount", DOCS = "what something is") sent questions with no number to search. Haiku also sometimes **replied with text** (asking the user for a missing number itself) instead of calling a tool. `plan_question` turned that text into a fallback search, so the user got "I don't know". The same bug hit serving utensils ("Which tongs for the tabbouleh?").

This spec replaces `PLANNER_PROMPT` with a restructured text (Appendix A) that:
- tells the planner never to write text or ask the user anything itself;
- defines TOOL as "a tool produces the answer, with or without numbers";
- gives each tool its own short bullet.

It was tried against the real planner model before this spec was written. EVAL-5 and EVAL-6 of spec 045 then pass, and EVAL-7 still fails.

## 2. Out of scope
- Any code change: `plan_question`, `tool_choice`, the flow, the tools, a keyword backstop.
- The tools' descriptions (`blc.planner.*_view`, `SEARCH_TOOL`, `RECIPE_TOOL`), the answer prompt, retrieval, models, ingest and `data/`.
- Spec 045's EVAL-7 ("Always items for 4 tables?" is read as `tables`). It stays a known limit.
- Fixing eval failures. They are reported, and the planner and user decide.

## 3. Interface contract
No new public names. Unchanged: `PLANNER_PROMPT` (still a `str` in `blc.planner`), `plan_question`, `PLANNER_TOOLS`, `Plan`, `run_planned_turn`.

```python
# blc.planner
PLANNER_PROMPT: str   # now exactly the text of Appendix A (§4.1)
```

**Existing tests:** none should need to change. Appendix A keeps every example question of spec 018 word for word and in TOOL → DOCS → BOTH order. It keeps the "how much … ingredient → scale_recipe", "how many gallons" and "pull sheet … everything" rules, and it contains no eval question of any spec word for word. If an existing assertion still fails because it checks wording that Appendix A drops, the implementation-evaluator reports it as a spec question. It is not edited.

**Eval setup** (eval rows only): as in spec 043 §3. `build_chat_model(temperature=CHAT_TEMPERATURE)` and `build_domain_store()` come from `chat.py`, and `run_planned_turn(llm, store, question)` runs with the default runners. The rows skip when `ANTHROPIC_API_KEY` or `GOOGLE_API_KEY` is unset or `.chroma/` is missing. Nothing is written outside `logs/`, and no log file is required.

## 4. Inputs and outputs

### 4.1 The prompt text
`PLANNER_PROMPT` is the text inside the Appendix A fence:
- lines are joined with `\n`;
- there are no leading or trailing blank lines and no trailing newline;
- each blank line inside the fence is one empty line;
- long lines stay single lines, with no backslash wrapping in the string's value.

### 4.2 What the restructure must keep and drop (testable parts)
| Must contain | Must not contain |
|---|---|
| `Never ask the user anything yourself` | `not by the topic` |
| `with or without numbers` | `How many black linens do I need?` (spec 045 revision 5 example) |
| all six tool names: `search_documents`, `calculate_bev_item`, `scale_recipe`, `calculate_food_item`, `calculate_serving_utensils`, `calculate_always_items` | the word `Rule 1` / `Rule 2` / `Rule 3` |
| the 11 example questions of Appendix A, word for word, in Appendix A order | |

### 4.3 How a NOTEXT eval case is scored
A case passes when the final plan (`outcome.plan`) meets all of these:
- `fallback` is False;
- the route is `TOOL`;
- the tool names (not `search_documents`) are exactly `[calculate_serving_utensils]`;
- the serving call's `items` has one entry whose `food` contains the case's keyword (casefolded);
- that entry has no `qty`.

**Threshold:** at least 2 of 3.

## 5. Acceptance criteria
- **AC-1:** `PLANNER_PROMPT` contains everything in the left column of §4.2 and nothing in the right column. The 11 example questions appear in Appendix A order.
- **AC-2:** `plan_question` still sends `PLANNER_PROMPT` as its system message, unchanged.
- **AC-3** *(manual)*: `PLANNER_PROMPT` equals the Appendix A text exactly as §4.1 sets out (checked by the planner, character for character).
- **AC-4:** Nothing regresses in the unit layer. The whole unit suite (`-m "not integration and not eval"`) passes, with no existing test edited.
- **AC-5** *(eval)*: **No text replies.** The NOTEXT cases (§6.2) meet §4.3's threshold.
- **AC-6** *(eval)*: **Always ASK.** Spec 045's ASK area (EVAL-5 to EVAL-7) meets its threshold of 2 of 3, and its SCOPE and MIX areas still meet theirs.
- **AC-7** *(eval)*: **No eval regressions.** Every other eval suite whose cases go through the planner is run, and each meets its own spec's thresholds:
  - `planner/test_planner_eval.py`
  - `planned_flow/test_flow_eval.py`
  - `mixed_questions/test_mixed_eval.py`
  - `food_wiring/test_eval.py`
  - `serv_wiring/test_eval.py`

  A suite that fails is reported with its failing case IDs. The planner then compares it against a run on the spec 045 prompt before calling it a regression.
- **AC-8** *(manual)*: Only `backend/src/blc/planner/prompt.py` and the new tests change.

## 6. Test cases

### 6.1 PROMPT (unit)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PROMPT-1 | `PLANNER_PROMPT` | contains each "must contain" item of §4.2 | AC-1 |
| PROMPT-2 | `PLANNER_PROMPT` | contains none of the "must not contain" items of §4.2 (the `Rule n` check is case-sensitive) | AC-1 |
| PROMPT-3 | the 11 example questions of Appendix A | each appears verbatim; their positions increase in Appendix A order | AC-1 |
| PROMPT-4 | `plan_question` with a fake model | the first message is a `SystemMessage` whose content equals `PLANNER_PROMPT` | AC-2 |
| PROMPT-5 | `PLANNER_PROMPT` | is a `str`; the whole text does not start or end with whitespace (so no trailing `\n`) | AC-1 |

### 6.2 NOTEXT (eval, scored by §4.3)
| ID | Question | Keyword | Covers |
|---|---|---|---|
| NOTEXT-1 *(eval)* | "Which tongs for the tabbouleh?" | `tabbouleh` | AC-5 |
| NOTEXT-2 *(eval)* | "What serving utensils do I need for the scones?" | `scone` | AC-5 |
| NOTEXT-3 *(eval)* | "Which serving spoons for the roasted breakfast potatoes?" | `potato` | AC-5 |

### 6.3 Existing suites (run by the implementation-evaluator, no new tests)
| ID | Suite | Expected | Covers |
|---|---|---|---|
| SUITE-1 | whole unit suite | passes, no test edited | AC-4 |
| SUITE-2 *(eval)* | `always_wiring/test_eval.py` | ASK at least 2 of 3; SCOPE and MIX meet their thresholds | AC-6 |
| SUITE-3 *(eval)* | the five suites of AC-7 | each meets its own thresholds | AC-7 |

### 6.4 Checks without a test row
AC-3 and AC-8 are checked by the planner.

## Appendix A: the prompt text
```text
You are the planner for the Bay Laurel Catering assistant. You never answer and never write text. You read the question and the recent chat history, then reply only with tool calls; the calls are the plan. Never ask the user anything yourself: when a number is missing, call the tool without it and the tool asks.

How to decide, for each part of the question:
- TOOL when one of the tools below produces the answer: a count, an amount, a list of items to pull, or a recipe. This holds with or without numbers; leave a missing number out.
- DOCS (search_documents) only when no tool covers it and the answer is written down: where something is kept or goes, what a menu item or package contains, how to do something, and written rules or yes/no facts.
- BOTH when the question has a TOOL part and a DOCS part: one call per part.

The tools:
- calculate_bev_item: gallons, cambros or cups for drinks, or item "everything" for the full beverage pull sheet with an amount.
- scale_recipe: how to make a drink, or ingredient amounts for a batch, with or without an amount. "How much ... for N gallons of a drink" is scale_recipe, even when the ingredient is named only in another part or in the history; calculate_bev_item item "gallons" answers only "how many gallons to make".
- calculate_food_item: spoons, forks, knives, small or large plates for a guest count; whether cocktail or dinner napkins are needed for a meal (breakfast, reception, lunch, dinner).
- calculate_serving_utensils: which or how many serving utensils (tongs, serving spoons, spreaders, honey bears, ladles) foods need, every food line in one call. On a package BEO send the item lines with "unit": "each"; a plain count before a food is "unit": "each"; "dozen" only when written. A question about which or how many serving utensils with no amount of food (e.g. a food named alone) still calls it with qty left out; never search_documents.
- calculate_always_items: the Always box: bus tubs, towels, black linens, purple napkins and black napkins. Any question about these, about "the always items", or the Always box goes here, with or without numbers, never to search_documents. Asking what the always items are is this tool too (it lists them), not a search. Choose about, first match wins: if the words "always items", "Always box" or "pull sheet" appear anywhere in the question, about is "both", and a table count or drip tray count alone never changes that to "tables" or "drip_trays"; else black linens or purple napkins or only tables -> "tables"; else black napkins or only drip trays -> "drip_trays"; else "both".
- Napkins asked about with a drink and no meal type are a written rule: search_documents.

Examples:
"How many cups do I need for 70 guests?" -> calculate_bev_item {"item": "cups", "guests": 70}
"How much lemon concentrate for 8 gallons of lemonade?" -> scale_recipe {"recipe": "lemonade", "gallons": 8}
"How many knives for 35 guests?" -> calculate_food_item {"item": "knives", "guests": 35}
"Are cocktail napkins needed at dinner?" -> calculate_food_item {"item": "cocktail napkins", "meal": "dinner"}
"Which tongs for 7 dozen bagels?" -> calculate_serving_utensils {"items": [{"food": "bagels", "qty": 7, "unit": "dozen"}]}
"How many black napkins should I pull?" -> calculate_always_items {"about": "drip_trays"}
"What goes in the Always box for 7 drip trays?" -> calculate_always_items {"about": "both", "drip_trays": 7}
"Where are the lemons kept?" -> search_documents {"query": "where are the lemons kept"}
"Should I bring creamer for decaf?" -> search_documents {"query": "should I bring creamer for decaf"}
"How many cambros for 4 gallons of coffee and what to bring?" -> calculate_bev_item {"item": "cambros", "drinks": ["coffee"], "gallons": [4]} and search_documents {"query": "what to bring for coffee"}
"Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?" -> search_documents {"query": "where is the orange juice concentrate"} and scale_recipe {"recipe": "orange juice", "gallons": 8}

Argument rules:
- One call per part asked. Do not drop a part and do not add what was not asked. Two tool parts give two tool calls.
- A search query must stand on its own: it carries the drink or thing the part is about, even when the user only wrote it in another part, but not the tool part's amounts.
- Take drinks, recipes and amounts from the whole question and the history. If a part says "it" or "each", use the drink or drinks named earlier.
- Use only numbers the user wrote. A guest count goes in guests and is never turned into gallons or tables. Leave out any number not given.
- If the user changes an amount ("instead"), use the new amount.
- For a follow-up such as "what about spoons?", carry the guest count or meal over from the earlier turns. A question about where food is kept or what comes with it is search_documents only, and never reuses an old guest count.
```
