# Spec 020: Beverage tool replies follow `item` (cups say only cups, in plain words)

- **Status:** approved (done: closed by the user; one test fix carried to spec 021)
- **Date:** 2026-11-14

## 1. Goal
For a cups question with named drinks, `calculate_bev_item` today replies with every drink's gallons followed by a raw pull sheet line, e.g. "Iced tea: 4 gal from 90 guests. Lemonade: 4 gal from 90 guests. `cold-cups: 140.`". The 7B answer model then invents numbers to connect the two, such as "one gallon is about 16 servings" (spec 019, case T5).

A scratch test showed that a cups-only plain sentence ("Cold cups: 140 for 90 guests (90 guests plus 50 extras).") is passed on cleanly. This spec makes **the tool's reply text follow `item`**:
- **cups:** a cups reply says only the cups, in plain words with their reason;
- **warnings and notes:** these always stay;
- **other items:** their text is unchanged.

It also adds an eval of **mixed questions**, where one question asks for two items (e.g. gallons and cups). Since a cups reply no longer carries gallons, the planner must make one call per item, and the eval measures that.

Finally, it finishes spec 019 revision 1's tester items.

## 2. Out of scope
- **The calculation:** every number, status and `lines` value stays exactly as today. Only `BevResult.text` changes, and only for `item: "cups"`.
- **The text of the other items:** `gallons`, `cambros`, `supplies` and `everything` keep their current text. That includes `everything`'s raw "hot-cups: 120" lines, which the pull sheet uses.
- **Other parts of the system:** the pull sheet program and its output, the planner prompt, `PLANNER_BEV_TOOL`, the flow, and `FLOW_ANSWER_PROMPT`.
- **A context line** (e.g. gallons per drink) in cups replies. It's only to be added if the mixed-question eval shows the planner often misses the second call.

## 3. Interface contract
No new public names. The changed behaviour is `BevResult.text` from `calculate_bev_item` and `run_bev_tool` in `blc.tools.bev_tools` (spec 005), for status `ok` and `item == "cups"` only. `BEV_TOOL` returns that same text. Every other field of `BevResult`, and every other status and item, is unchanged.

Spec 005 §4.4's first bullet (`ok` text) no longer applies to `item: "cups"`; §4.1 below replaces it for cups.

## 4. Inputs and outputs

### 4.1 The `ok` text for `item: "cups"`
| Case | Text (wording illustrative; the required parts are listed below) |
|---|---|
| Drinks named, cup lines found | one sentence per cup line, in `lines` order: "Hot cups: 120 for 70 guests (70 guests plus 50 extras)." |
| No drinks (spec 005's `cups_each`) | "For 45 guests: 65 cups (45 guests plus 20 extras). The same count applies to hot cups and to cold cups." |
| Drinks named, but none needs cups (e.g. Oatmilk) | one sentence saying no cups are needed for those drinks, naming them: "Oatmilk needs no cups." |

**Required in every cup-line sentence:**
- the cup kind in **plain words**: the supply name with `-` replaced by a space and the first letter upper case, so "hot-cups" becomes "Hot cups";
- the **count**;
- **"for N guests"**;
- the **reason** "N guests plus M extras", where M = count − N.

**Required in the no-drinks sentence:**
- the count;
- "N guests" and "M extras";
- that the same count applies to hot and to cold cups.

**Never in a cups `ok` text:**
- any drink amount: no "gal", "gallon", "each" amounts, and no "from N guests" drink sentence;
- the raw supply names "hot-cups" or "cold-cups";
- the line "Drinks: …".

**Always kept, after the cups sentences:**
- the not-on-menu sentence for each unknown drink ("hot chocolate is not on the beverage menu."), as today;
- the guest note, when spec 005 adds it.

Spec 005's grammar rule holds: "1 guest", never "1 guests". M is never 1 under the current rules, but the singular rule applies if it is.

### 4.2 Mixed-question eval (planner, then the flow)
The eval runs these 5 questions through spec 018's `plan_question` and spec 019's `run_planned_turn`, with the real models and data:

| id | question | expected `calculate_bev_item` calls (one per item, any order) |
|---|---|---|
| X1 | How many gallons and how many cups for iced tea for 90 guests? | gallons (iced tea; 90 guests) + cups (iced tea; 90 guests) |
| X2 | How many cambros and how many cups for coffee for 120 guests? | cambros (coffee; 120 guests) + cups (coffee; 120 guests) |
| X3 | For 60 guests of peach tea, how many gallons, cambros and cups? | gallons + cambros + cups (peach tea; 60 guests each) |
| X4 | How many cups and gallons of decaf do I need for 40 guests? | cups + gallons (decaf; 40 guests each) |
| X5 | What do I need in gallons and cups for lemonade for 30 guests? | gallons + cups (lemonade; 30 guests each) |

**How a case passes:**
- The set of `item` values over the plan's `calculate_bev_item` calls equals the expected set.
- Every one of those calls names exactly the expected drink (stripped, ignoring case), and `guests` equals the expected number.
- Other `calculate_bev_item` calls, and any `scale_recipe` calls, fail the case. `search_documents` calls are ignored.

**Report only, no threshold:** the eval prints one line per case, and the count passed out of 5. It also writes `logs/mixed_answers_<YYYY-MM-DD_HHMMSS>.md` in spec 019 §4.5's format, covering X1 to X5 plus spec 018's T5, for the user to read. The eval test passes when the log is complete.

## 5. Edge cases
Unit tests use spec 005 Appendix A's test catalog (`tests/bev_tools/conftest.py`), whose rules give 70 guests → 120 cups (+50) and 45 guests → 65 cups (+20).
- **EC-1:** cups, Coffee, 70 guests →
  - status `ok`; `lines` == `[("hot-cups", 120)]`, unchanged;
  - text contains "Hot cups", "120", "for 70 guests" and "50 extras";
  - text contains none of "gal", "hot-cups" or "Coffee: ".
- **EC-2:** cups, Coffee and Iced tea, 70 guests → two sentences, "Hot cups" then "Cold cups", each with 120, "70 guests" and "50 extras"; no "gal".
- **EC-3:** cups, Iced tea and Lemonade, 90 guests → one "Cold cups" sentence with 140, "for 90 guests" and "50 extras"; no "gal".
- **EC-4:** cups, no drinks, 45 guests → text contains "65", "45 guests" and "20 extras", and says the count applies to hot cups and to cold cups. `cups_each` == 65, unchanged.
- **EC-5:** cups, Coffee and "hot chocolate", 70 guests → the Hot cups sentence, then "hot chocolate is not on the beverage menu"; `not_on_menu` == `("hot chocolate",)`; no "gal".
- **EC-6:** cups, the package "Coffee, decaf, tea, iced water & juice", 120 guests → Hot cups and Cold cups sentences, each with 220, "for 120 guests" and "100 extras"; no "gal".
- **EC-7:** cups, Oatmilk, 30 guests → status `ok`, `lines` == `()`, and the text contains "Oatmilk" and "no cups".
- **EC-8:** cups, no drinks, 1 guest → "For 1 guest" (not "1 guests"), "11", "10 extras".
- **EC-9 (unchanged):** cups with drinks but no guests → `need_info`, with the same question as today. Cups with only unknown drinks → `not_on_menu`, with the same text. Cups with bad arguments → `invalid`, with the same text.
- **EC-10 (unchanged):** for sample inputs of `gallons`, `cambros`, `supplies` and `everything`, the text equals what it was before this spec. Spec 005's existing text tests for those items pass unchanged, including `"hot-cups: 120" in text` for `everything`.
- **EC-11:** `BEV_TOOL.invoke({"item": "cups", "drinks": ["iced tea", "lemonade"], "guests": 90})` (a real tool built on the test catalog) returns the same text as `run_bev_tool` for those args.

## 6. Acceptance criteria
- **AC-1 (cups text):** EC-1 to EC-8 and EC-11.
- **AC-2 (nothing else changes):** EC-9 and EC-10. Every `BevResult` field except `text`, for every item, equals its value before this spec.
- **AC-3 (mixed-question eval):** §4.2 runs, prints the per-case lines and the count out of 5, and writes the log with 6 sections (X1 to X5 and T5). No threshold.
- **AC-4 (spec 019 carry-over):**
  - In `tests/test_voice_io_answer_turn.py`, the 16 `chat.main` tests are updated as spec 019 revision 1 states. They check the same behaviours against `run_planned_turn` instead of `answer_turn`: the stripped question, empty input ignored, non-exit inputs answered, exit words, turn order, and history carried as `outcome.history`.
  - `tests/planned_flow/test_contract.py` gains a test that `FLOW_ANSWER_PROMPT` contains "simple", "straightforward" and "grounded", ignoring case.
- **AC-5 (existing tests updated, nothing weakened):** an existing test that asserts the **old cups text** for drinks named (drink gallon sentences, "Drinks: …" or raw "hot-cups"/"cold-cups" in a **cups** reply) is updated to §4.1. Its other assertions stay. Tests of `lines`, of other items and of the pull sheet are not touched.
- **AC-6 (regression):** after AC-4 and AC-5, the full unit suite passes. The only accepted failure is `tests/test_voice_io.py::test_constants_match_contract` (the user's `DIDNT_CATCH` change).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | Only the reply writing changes, in `src/blc/tools/bev_tools/` (e.g. `reply_text.py` and the call that builds the text). No calculation, catalog, pull sheet, planner or flow code changes. | manual (code-evaluator) |
| NFR-2 | AC-1, AC-2, AC-4 and AC-5 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The mixed-question eval is marked `eval`. It skips, not fails, when Ollama or the Chroma store is missing, and it writes only under `logs/`. | unit (marker review); run output |
| NFR-4 | No new dependencies. | manual |

Tests go in:
- `tests/bev_tools/test_cups_text.py`: AC-1 and AC-2's new checks;
- `tests/mixed_questions/test_mixed_eval.py`, with its `conftest.py`: AC-3;
- the AC-4 files: `tests/test_voice_io_answer_turn.py` and `tests/planned_flow/test_contract.py`;
- any `tests/bev_tools/` file AC-5 touches.

## Closing note (2026-11-14)
**Results:**
- **Unit tests:** 2992 passed. The 4 failures are 3 cases of a test bug in `test_cup_line_sentence_counts_at_extras_band_edges` plus the accepted `DIDNT_CATCH` failure. The test asserts `"1 guests" not in text`, which also matches inside "21 guests", "51 guests" and "101 guests". The code's text is correct. The fix is carried to spec 021.
- **Mixed-question eval:** 1 of 5 cases had the right planned calls (report only). The log is `logs/mixed_answers_2026-11-14_125539.md`.

**Findings:**
- **T5 is fixed:** "140 cups … including an extra 50 cups", with no invented servings.
- **The planner invents gallons on cambros calls:** X2 `[10]`, X3 `[12]`, and the user's "For 60 guests of peach tea" `[6]`. The cause is the bare example call in `PLANNER_BEV_TOOL`'s description, which has peach tea with gallons. Spec 021 adds a no-invented-numbers rule and an argument check.
- **The answer model dropped a part (X1)** and added an "equivalent to" link (X4).
- **The cambros raw-line text ("5 gal cambro: 1 …") was misread** as "1 cambro". A plain cambros reply is a possible later spec.
