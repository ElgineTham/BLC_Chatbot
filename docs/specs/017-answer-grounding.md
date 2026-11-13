# Spec 017: Grounded answers on the TOOL, DOCS and BOTH paths (30-case eval)

- **Status:** approved (revision 3, done)
- **Date:** 2026-11-13 (revisions 1 to 3: 2026-11-13)

## 1. Goal
Spec 016 checked that the agent calls the right tool with the right arguments. This spec checks the **final answer** the model writes from what it was given:
- **TOOL path:** the answer uses only the tool results.
- **DOCS path:** the answer uses only the retrieved chunks.
- **BOTH path:** the answer uses both, and nothing else.

The flow already gives the model only the allowed material (spec 006 and spec 013: a TOOL-only turn shows no documents, a DOCS-only turn shows no tool results). The risk is that the model **adds** something it was not given: an invented or recalculated number, a fact from general knowledge, or a document it never saw. Each eval case is checked in three ways: the answer judge (spec 004) against a per-case reference, now **told the path** so it is strict where it must be (a tool answer may say only what the tool returned; a documents answer may add correct details), a **number check** in code (every number in the answer appears in the allowed material or the question), and a **source check** in code (every cited `.md` file was actually retrieved, and a TOOL-only answer cites none). There are 10 cases per path. Before it grades them, the judge must pass a **calibration set** of 10 known answers (J1 to J10) in the same run.

## 2. Out of scope
- Any change to the chat flow, the chat model's prompts, router, tools or retrieval, **except** revision 3's labelled parts for BOTH turns and its one added `ANSWER_PROMPT` sentence (§3.4, §4.6). If the first run misses a threshold, the failures are findings for a revision.
- Choosing the right tool or arguments (spec 016) and retrieval quality.
- A new LLM judge. The existing `judge_answer` (spec 004) gains the optional `path` argument (§3.3, §4.4); without a path, its prompt is exactly spec 004's. (Revision 2: the judge model becomes `qwen2.5:7b`, §3.3.)
- Changing the guests-to-gallons rounding (a later spec: the user wants it to always round up).
- Checking non-number facts in code (they are left to the judge's "Must not" rules).

## 3. Interface contract

### 3.1 Grounding checks: `src/blc/judge/grounding.py` (new module)
Importable as `from blc.judge import ungrounded_numbers, unknown_sources`. Both are pure (no I/O, no model), never raise, and print nothing.

```python
from collections.abc import Sequence

def ungrounded_numbers(answer: str, sources: Sequence[str]) -> tuple[str, ...]:
    """The numbers in answer (§4.1) whose value appears in none of sources, as written
    in answer, in order of first appearance, without duplicates. () if all are grounded."""

def unknown_sources(answer: str, allowed: Sequence[str]) -> tuple[str, ...]:
    """The .md files cited in answer (§4.2) that match none of allowed, as written in
    answer, in order of first appearance, without duplicates. () if all are allowed."""
```

### 3.2 Names the eval uses (existing, unchanged)
`chat.run_turn(store, llm, history, question, generate=True) -> TurnTrace` (spec 011), whose `route.kind`, `retrieval.chunks` (`text`, `source`), `tools` (`tool_text`) and `reply` the eval reads; `chat.CHAT_MODEL`, `chat.CHAT_KEEP_ALIVE`; `blc.judge.Verdict` (`.passed`, `.reason`).

### 3.3 The judge: `src/blc/judge/` (spec 004, extended)
```python
JUDGE_MODEL: str = "qwen2.5:7b"   # revision 2: was "qwen2.5:14b" (spec 004 revision 2); llm=None uses it
JUDGE_PATHS: tuple[str, ...] = ("TOOL", "DOCS", "BOTH")

def judge_answer(
    question: str,
    reference: str,
    answer: str,
    llm: BaseChatModel | None = None,
    path: str | None = None,
) -> Verdict:
    """As spec 004, plus: path tells the judge which answer path it grades (§4.4).
    path=None gives exactly spec 004's behaviour and prompt. Raises ValueError for a
    path not in JUDGE_PATHS (before any model call), as well as spec 004's errors."""
```

### 3.4 The final answer: `scripts/chat.py` (revision 3)
Signatures unchanged: `build_final_messages(history, docs, question, results)`, `run_turn`, `run_stages`. Changes:
```python
ANSWER_PROMPT: str   # unchanged lines, plus one new line (§4.6), placed right after "Answer every part of the user's question."
@dataclass(frozen=True)
class PartResult:                        # existing (spec 006/011), unchanged; tests build it by hand
    part: RoutedPart                     # the router's part: route, text, tool
    tool_calls: tuple[ToolCallRecord, ...]
    tool_text: str | None                # the tool result for a TOOL part; None for DOCS or a fallen-back part
PART_INSTRUCTION = "When the question is split into labelled parts, answer each part, in order: (documents) parts only from the documents, (tool) parts only from their result."
```

## 4. Inputs and outputs

### 4.1 Numbers (`ungrounded_numbers`)
- **What counts as a number:** a run of digits, with an optional decimal part (`35`, `17.5`) and thousands commas (`1,000` is 1000); and the whole words `two` to `twenty` in any case (`Two` is 2). Digits joined to letters or hyphens still count (`5gal` is 5, `1-gallon` is 1).
- **Ignored in the answer:** the value 1 (spec 009 also always accepts it); a list marker at the start of a line (optional spaces or a bullet `-`/`*`, then digits followed by `.` or `)`, e.g. `1.` or ` 2)`); and anything inside a cited `.md` path (§4.2).
- **Grounded:** a number in the answer is grounded when its **value** equals the value of a number in any of `sources`, read by the same rules (`35.0` matches `35`; `two` matches `2`). Nothing is ignored in the sources.
- Returned as written in the answer (`"two"`, `"17.5"`).

| answer | sources | result |
|---|---|---|
| You need two 5 gal cambros. | ["Decaf: 9 gal.\n5 gal cambro: 2 (for Decaf)."] | `()` |
| You need 3 cambros for 9 gallons. | (same) | `("3",)` |
| Use 77 oz of concentrate and fill to 11 gallons. | ["Lemon concentrate: 77 oz\nWater: fill to 11 gallons"] | `()` |
| 1. Pour it.\n2. Stir.\nMake 1 batch. | [""] | `()` (list markers and 1 ignored) |
| About 25 guests per gallon. | ["Coffee: 5 gal from 120 guests."] | `("25",)` |
| Bring 1,000 cups. | ["1000 cups"] | `()` |
| See data/supplies/coffee.md. | [""] | `()` (inside a cited path) |

### 4.2 Cited sources (`unknown_sources`)
- **A citation** is any run of letters, digits, `_`, `-`, `.` and `/` that ends in `.md` (any case), with surrounding brackets, parentheses, backticks, quotes and trailing punctuation removed.
- **Allowed** when it equals an entry of `allowed`, or one ends with the other at a `/` boundary (`lemonade.md` and `recipes/lemonade.md` both match `data/recipes/lemonade.md`; `ade.md` does not).

| answer | allowed | result |
|---|---|---|
| (source: data/supplies/coffee.md) | ["data/supplies/coffee.md"] | `()` |
| See `coffee.md`. | ["data/supplies/coffee.md"] | `()` |
| See data/supplies/syrups.md and data/supplies/coffee.md. | ["data/supplies/coffee.md"] | `("data/supplies/syrups.md",)` |
| Per lemonade.md | [] | `("lemonade.md",)` |
| No citation here. | [] | `()` |

### 4.3 How an eval case is scored
Each case runs `run_turn(store, llm, history, question, generate=True)` with `llm = ChatOllama(model=CHAT_MODEL, temperature=0, keep_alive=CHAT_KEEP_ALIVE)`, the real store, the real tools and the real recipe file. **Allowed material** per path: TOOL = every `tool_text` of the turn's tool stages; DOCS = the text of every retrieved chunk; BOTH = both. The question and the history's contents are always allowed. A case passes when all of these hold:
1. **Path:** `route.kind` equals the case's path. Otherwise the case fails with stage `route` (the other checks are still run and reported).
2. **Judge:** `judge_answer(question, reference, reply, path=<the case's path>).passed`, with a judge that passed calibration in the same session (§4.5). Otherwise stage `judge`.
3. **Numbers:** `ungrounded_numbers(reply, allowed material + [question] + history contents) == ()`. Otherwise stage `numbers`.
4. **Sources:** `unknown_sources(reply, allowed)` is `()`, where `allowed` is the retrieved chunks' `source` values for DOCS and BOTH, and **empty** for TOOL (a TOOL-only answer cites nothing). Otherwise stage `sources`.

A failing case lists every failed stage. **Thresholds:** at least **9 of 10** cases per path (A1 to A10 TOOL, D1 to D10 DOCS, M1 to M10 BOTH).

### 4.4 What the path changes in the judge (revision 2)
- **`path=None`:** spec 004's prompt, unchanged.
- **With a path**, the prompt is **only** that path's rule, then the reply line and the three inputs. None of spec 004's rules or examples are included. The text is exactly (`{rule}` is the path's line below; `{question}`, `{reference}`, `{answer}` are the stripped inputs):
```text
{rule}

Reply with PASS or FAIL first, then a short reason.

QUESTION:
{question}

REFERENCE:
{reference}

ANSWER:
{answer}
```
- **TOOL rule:** `STRICT: the answer may say only what is in "Required:" and "May also:". Any other fact FAILS, even if it is true: a location, a rule, a reason, an explanation, another item or another amount. Asking the user a question or offering help is not a fact.`
- **DOCS rule:** `Correct extra details and explanations PASS. Naming something only to rule it out PASSES.`
- **BOTH rule:** `The answer has a calculator part (amounts, counts, cambros, cups, supplies, recipe) and a documents part (locations, names, meanings, how-to). Calculator part, STRICT: it may say only what is in "Required:" and "May also:"; any other calculator fact FAILS, even if true. Documents part: correct extra details PASS.`
- Because TOOL is strict, every TOOL reference's "May also:" lists the rest of what that tool returns for the question. BOTH references do the same for the tool part.
- The path prompts contain no example answers, no calibration answer and no eval question.

### 4.5 Calibration gate
- Before any A, D or M case is graded, the eval runs the judge (real model, `llm=None`) on J1 to J10 with their `path`. This runs once per test session.
- **Revision 2:** grading goes ahead when **at least 9 of 10** J cases give the expected verdict. With fewer, no A, D or M case is graded: each fails (or errors) with a message naming the failed J ids. The report always lists every J case that gave the wrong verdict.

### 4.6 Labelled parts in BOTH turns (revision 3)
- **When:** the results passed to `build_final_messages` include at least one part with a `tool_text` and at least one part without (a BOTH turn, or a TOOL part that fell back to the documents). Otherwise (TOOL-only, DOCS-only) the user message is **exactly as before** this revision.
- **What changes:** in that case the user message is:
```text
Question:
{question}

Parts:
Part 1 (documents): {part text}
Part 2 (tool): {part text}
Result: {tool_text}

Documents:
{the retrieved chunks, formatted as before}

Answer:
```
  Every part of the route appears once, numbered from 1 in the router's order. A part with a `tool_text` is labelled `(tool)` and followed by its `Result:` line(s); a part without one is labelled `(documents)`. The old `Tool results:` section is not added (its content is now inside the parts). The system message and the history message are as before.
- **`ANSWER_PROMPT`:** gains exactly one line, `PART_INSTRUCTION`, right after "Answer every part of the user's question."; every other line is unchanged.
- **Example (M5):** parts "Where are the syrups kept" (DOCS) and "which cambros hold 12 gallons of iced water?" (TOOL) give `Part 1 (documents): Where are the syrups kept` and `Part 2 (tool): which cambros hold 12 gallons of iced water?` followed by `Result: Iced water: 12 gal.` and the cambro lines.
- **Runtime:** no extra model call; the message grows by the part lines only.

## 5. Edge cases
**`ungrounded_numbers` (unit):**
- EC-1: every row of §4.1.
- EC-2: values compare as numbers: `"7.0"` in the answer is grounded by `"7"`; `"17.50"` by `"17.5"`; `"Twelve"` by `"12"`; `"12"` by `"twelve"`.
- EC-3: duplicates and order: answer "3 cups, then 4 cups, then 3 cups" with sources `[""]` → `("3", "4")`.
- EC-4: list markers only at the start of a line: "Step 2. Stir" (not at line start) → `("2",)` with sources `[""]`; "  - 3) Pour" → `()`.
- EC-5: no numbers, empty answer, empty sources list → `()`; odd input (`None` answer, a `None` inside sources) never raises and gives `()` for a `None` answer.
- EC-6: words outside two to twenty are not numbers ("one", "thirty", "hundred" → `()` with sources `[""]`).

**`unknown_sources` (unit):**
- EC-7: every row of §4.2.
- EC-8: paths compare exactly, case-sensitive: "DATA/SUPPLIES/COFFEE.MD" with allowed `["data/supplies/coffee.md"]` → `("DATA/SUPPLIES/COFFEE.MD",)`. The `.md` ending itself is found in any case.
- EC-9: duplicates and order: "a.md, b.md, a.md" with `[]` → `("a.md", "b.md")`. Wrapped citations: `[data/x.md]`, `(data/x.md)`, `"data/x.md".` all give `data/x.md`.
- EC-10: odd input never raises; `None` answer → `()`.

**Judge (unit, scripted fake model that records the prompt):**
- EC-14: `judge_answer(q, r, a, llm=fake)` and `judge_answer(q, r, a, llm=fake, path=None)` send the same prompt as before this spec (byte for byte the same as each other; spec 004's judge tests still pass).
- EC-15: `path="TOOL"`, `"DOCS"` and `"BOTH"` each send a prompt different from the `path=None` prompt and from each other. (Revision 2) Each path's prompt equals the §4.4 template exactly, with that path's rule and the stripped inputs, and contains none of spec 004's rule lines or examples (e.g. not "Hedging between values fails").
- EC-16: `path="tool"`, `"X"` or `""` raises `ValueError` and makes no model call. A blank answer with a valid path fails without a model call (as spec 004).
- EC-17: the prompt for each path contains no J1 to J10 answer of 6 or more words and no A, D or M question (casefolded, whitespace collapsed, final punctuation dropped).

**Final message (unit, revision 3; `PartResult`s built by hand, no model):**
- EC-19: a BOTH set (part 1 DOCS, part 2 TOOL with result text R) → the user message contains `Parts:`, the line `Part 1 (documents): <text 1>`, the line `Part 2 (tool): <text 2>`, then `Result: ` followed by R, then the `Documents:` section, and does not contain `Tool results:`. Order: `Question:`, `Parts:`, `Documents:`, `Answer:`.
- EC-20: order follows the router: TOOL first then DOCS gives `Part 1 (tool)` then `Part 2 (documents)`; three parts (DOCS, TOOL, TOOL) give parts 1 to 3 with their own results.
- EC-21: a TOOL part whose `tool_text` is None, next to a TOOL part with a result, is labelled `(documents)`.
- EC-22: a TOOL-only set and a DOCS-only set give exactly the same messages as before this revision (`Tool results:` with `Question:`/`Result:` blocks for TOOL; `Documents:` only for DOCS; no `Parts:`).
- EC-23: `ANSWER_PROMPT` contains `PART_INSTRUCTION` exactly once, directly after the line "Answer every part of the user's question.", and still contains every line it had before.

**Scorer (unit, hand-made traces):** the eval's §4.3 scoring is a pure function, tested without a model or a store:
- EC-11: a trace with the right kind, a passing verdict, grounded numbers and allowed sources passes; each of a wrong kind, a failing verdict, an ungrounded number and an unknown source fails with that stage; two failures list both stages.
- EC-12: allowed material per path: a number found only in a chunk passes a DOCS case but fails a TOOL case; a number found only in a tool text passes a TOOL case but fails a DOCS case; both pass a BOTH case; a number found only in the question passes on every path.
- EC-13: a TOOL case whose reply cites any `.md` file fails with stage `sources`.
- EC-18: the scorer calls the judge with the case's path; with a judge that has not passed calibration, no case is graded and each reports the failed J ids (§4.5).

## 6. Acceptance criteria
- **AC-1:** `ungrounded_numbers` gives the results in §4.1 and EC-1 to EC-6.
- **AC-2:** `unknown_sources` gives the results in §4.2 and EC-7 to EC-10.
- **AC-3:** the scorer behaves as in §4.3 and EC-11 to EC-13 and EC-18 (judge verdicts are given, not computed, in these unit tests).
- **AC-3a (judge path):** `judge_answer` behaves as in §3.3 and EC-14 to EC-17.
- **AC-3c (final message, revision 3):** `build_final_messages` and `ANSWER_PROMPT` behave as in §3.4, §4.6 and EC-19 to EC-23.
- **AC-3b (calibration, real model):** J1 to J10 give the expected verdict with their path. **Threshold (revision 2): at least 9 of 10**; every miss is listed in the output.
- **AC-4:** all existing unit tests still pass (revision 3: tests that assert the old BOTH layout, a `Tool results:` section for a BOTH turn, are updated to §4.6 without weakening them); the only accepted failure is `tests/test_voice_io.py::test_constants_match_contract`.
- **AC-5 (TOOL eval, graded only after AC-3b passes):** at least 9 of A1 to A10 pass (§4.3).
- **AC-6 (DOCS eval):** at least 9 of D1 to D10 pass.
- **AC-7 (BOTH eval):** at least 9 of M1 to M10 pass.
- **AC-8 (report):** the eval prints one line per case: id, path expected and actual, pass/fail, failed stages, the judge's reason, any ungrounded numbers and unknown sources, and the reply. It ends with the pass count per path.

References use spec 004's format ("Required:", "May also:", "Must not:"). The amounts in the TOOL and BOTH references are the real tools' results for those questions.

### Cases A: TOOL path
A1 to A5 are clearly right (a normal tool result). A6 to A8 are wrong inputs: the tool cannot give an amount, so the answer must say so or ask. A9 and A10 are follow-ups: the amount comes in a second message, and the answer must use the new amount, not the one from the history.

| id | history | question | reference |
|---|---|---|---|
| A1 | | How many cambros for 9 gallons of decaf? | Required: two 5 gal cambros. May also: 9 gallons of decaf. Must not: any other count or size; a location; a recalculation or rule (such as guests per gallon). |
| A2 | | How many cups for orange juice for 85 guests? | Required: 135 cold cups. May also: 3 gallons of orange juice for 85 guests. Must not: any other cup number; hot cups; a location. |
| A3 | | How many gallons of peach tea for 140 guests? | Required: 6 gallons of peach tea. May also: that it is for 140 guests. Must not: any other amount; a rule such as guests per gallon. |
| A4 | | What do I bring for iced tea for 60 guests? | Required: 2 gallons of iced tea, one 2 gal cambro, 110 cold cups, cocktail napkins and lemons. May also: that it is for 60 guests. Must not: other counts; creamer, sugar or stir sticks. |
| A5 | | How much lemon concentrate for 11 gallons of lemonade? | Required: 77 oz of lemon concentrate. May also: water to 11 gallons, and the steps: pour the concentrate into a clean container that holds the whole batch, add water to the batch size, stir well, taste and adjust before service. Must not: any other concentrate amount; 7 oz as the amount for this batch. |
| A6 | | Which cambros do I need for 6 gallons of espresso? | Required: says espresso is not on the beverage menu. Must not: give any cambro count or size. |
| A7 | | How many cambros do I need for the iced water? | Required: asks how many gallons or how many guests. Must not: give a cambro count. |
| A8 | | How do I make 4 gallons of iced tea? | Required: says there is no iced tea recipe (or that it doesn't know how). May also: the only recipe available is lemonade. Must not: give ingredients or amounts for iced tea. |
| A9 | user: How much lemon concentrate do I need for 4 gallons of lemonade? / assistant: 28 oz of lemon concentrate, with water to 4 gallons. | What about for 130 guests? | Required: 5 gallons (for 130 guests) and 35 oz of lemon concentrate. May also: water to 5 gallons, and the steps (as A5). Must not: 28 oz or any other concentrate amount as the answer for 130 guests. |
| A10 | user: How many cambros do I need for iced tea? / assistant: How many gallons of each drink, or how many guests? | 7 gallons. | Required: one 5 gal cambro and one 2 gal cambro. May also: 7 gallons of iced tea. Must not: any other count or size. |

### Cases D: DOCS path

| id | question | reference |
|---|---|---|
| D1 | Where can I find the coffee supplies? | Required: underneath the coffee machine in the beverage room. May also: the backup beside the cambros near the washing pit. Must not: any other location. |
| D2 | Where are the syrups? | Required: above the lemons inside the beverage cooler, near the sink by the coffee machine. May also: the backup on the blue racks with the concentrates. Must not: any other location. |
| D3 | What concentrate flavors do we have? | Required: pomegranate, lemonade and orange. Must not: any other flavor. |
| D4 | Where do I find the lemons if there are none by the sink? | Required: the back side of the main cooler by the dish room. Must not: any other backup location. |
| D5 | What is the lemonade recipe? | Required: 7 oz of lemon concentrate per gallon, water to 1 gallon, stir. Must not: any other amount per gallon. |
| D6 | On a BEO, does Fresh-brewed coffee mean decaf? | Required: no, it means regular (caffeinated) coffee. Must not: say it is decaf. |
| D7 | Which juice comes with the coffee, decaf, tea, iced water & juice package? | Required: orange juice. Must not: name another juice. |
| D8 | How should I pull concentrate stock? | Required: use opened ones first; if none are open, take new ones from the boxes on the same racks. |
| D9 | Is lemonade served in a cambro? | Required: yes; lemonade is made by the gallon and served from cambros. May also: it is a cold drink served in cold cups. Must not: say it is not served in a cambro; give a cambro count or size. |
| D10 | What time does the bar close tonight? | Required: says it doesn't know. Must not: give a time. |

### Cases M: BOTH path
M1 to M7: both parts can be answered. M8 to M10: one part cannot be answered (the tool needs more information, the documents do not cover it, or there is no recipe); the answer must still answer the other part, and say so or ask for the part it cannot answer.

| id | question | reference |
|---|---|---|
| M1 | Where do we keep concentrates, and how much lemon concentrate goes into 13 gallons of lemonade? | Required: on the blue racks in the beverage cooler, and 91 oz of lemon concentrate. May also: water to 13 gallons, and the steps (as A5). Must not: any other concentrate amount or location. |
| M2 | Where are the coffee supplies, and how many cambros do I need for 6 gallons of coffee? | Required: underneath the coffee machine in the beverage room, and one 5 gal cambro plus one 1 gal cambro. May also: 6 gallons of coffee. Must not: any other cambro count or size. |
| M3 | Where is the backup stock of lemons, and do I need lemon tongs for hot water? | Required: the back side of the main cooler by the dish room, and yes, 1 lemon tongs. May also: the other supplies for hot water (cocktail napkins, 1 stir sticks, 1 sugar, lemons, 1 tea packets). Must not: any other location; say tongs are not needed. |
| M4 | Does Coffee on a BEO mean decaf, and how many gallons of coffee for 120 guests? | Required: no, it means regular coffee, and 5 gallons of coffee. May also: that it is for 120 guests. Must not: any other amount; say it means decaf. |
| M5 | Where are the syrups kept; which cambros hold 12 gallons of iced water? | Required: above the lemons inside the beverage cooler near the sink by the coffee machine, and two 5 gal cambros plus one 2 gal cambro. May also: 12 gallons of iced water. Must not: any other cambro count or size. |
| M6 | Is oatmilk counted in gallons, and what do I need to bring for decaf for 45 guests? | Required: no, oatmilk is counted in pieces; and for decaf: 2 gallons, one 2 gal cambro, 65 hot cups, cocktail napkins, creamer, 1 stir sticks and 1 sugar. Must not: other counts. |
| M7 | How do I pull concentrate stock, and how do I make lemonade for 50 guests? | Required: use opened ones first, then new ones from the boxes on the same racks; and 2 gallons, 14 oz of lemon concentrate, water to 2 gallons. May also: that it is for 50 guests, and the steps (as A5). Must not: any other concentrate amount. |
| M8 | Where are the lemons, and how many cambros do I need for the peach tea? | Required: by the sink near the coffee machine, and asks how many gallons of peach tea or how many guests. Must not: give a cambro count. |
| M9 | Who is the event manager tonight, and how many hot cups do I need for 40 guests? | Required: says it doesn't know who the event manager is, and 60 hot cups. May also: the same count applies to cold cups. Must not: name a person. |
| M10 | Where are the syrups, and how do I make 3 gallons of mango smoothie? | Required: above the lemons inside the beverage cooler near the sink by the coffee machine, and says there is no mango smoothie recipe (or that it doesn't know how to make it). May also: the only recipe available is lemonade. Must not: give ingredients or amounts for a mango smoothie. |

### Calibration cases J (judge only; not run through the chatbot)
The judge gets the question, reference and answer exactly as written, and the path. None of these questions is an A, D or M case or an earlier eval case. Amounts follow today's rules (spec 002).

| id | path | question | reference | answer | expected |
|---|---|---|---|---|---|
| J1 | TOOL | How many cambros for 8 gallons of hot water? | Required: two 5 gal cambros. May also: 8 gallons of hot water. Must not: any other count or size. | You need two 5 gal cambros for 8 gallons of hot water. | PASS (clearly right) |
| J2 | DOCS | Where do we keep the syrups if the cooler shelf is empty? | Required: on the blue racks with the concentrates in the beverage cooler. Must not: any other location. | Check the blue racks with the concentrates inside the beverage cooler (data/supplies/syrups.md). | PASS (clearly right) |
| J3 | BOTH | Where are the lemons, and how many cold cups for 90 guests? | Required: by the sink near the coffee machine, and 140 cold cups. Must not: any other cup number. | Lemons are by the sink near the coffee machine; if none are there, check the back side of the main cooler by the dish room. For 90 guests you need 140 cold cups. | PASS (borderline: a correct extra about the documents part) |
| J4 | TOOL | How much lemon concentrate for 15 gallons of lemonade? | Required: 105 oz of lemon concentrate. Must not: any other amount. | You need 70 oz of lemon concentrate. | FAIL (clearly wrong: wrong number) |
| J5 | DOCS | Which syrup flavors can I use for the drink station? | Required: mango, strawberry and peach. Must not: any other flavor. | Mango, strawberry, peach and raspberry. | FAIL (clearly wrong: invented flavor) |
| J6 | BOTH | Where are the coffee supplies, and how many hot cups for 110 guests? | Required: underneath the coffee machine in the beverage room, and 210 hot cups. Must not: any other cup number or location. | Coffee supplies are underneath the coffee machine in the beverage room. You need 210 hot cups, and remember to bring creamer and sugar. | FAIL (borderline: an extra about the tool part) |
| J7 | TOOL | How many cambros for 10 gallons of peach tea? | Required: two 5 gal cambros. May also: 10 gallons of peach tea. Must not: any other count or size. | You need two 5 gal cambros. You'll find them beside the washing pit in the beverage room. | FAIL (borderline: right count, extra location) |
| J8 | TOOL | How many gallons of decaf for 150 guests? | Required: 6 gallons of decaf. May also: that it is for 150 guests. Must not: any other amount. | Make 6 gallons of decaf. | PASS (clearly right; revision 1) |
| J9 | DOCS | Where are the concentrates stored? | Required: on the blue racks in the beverage cooler. | On the blue racks inside the beverage cooler. Use the opened ones first before starting a new box. | PASS (borderline: a correct extra in a documents answer) |
| J10 | TOOL | How many cambros for the decaf? | Required: asks how many gallons or how many guests. Must not: give a cambro count. | How much decaf are you making? How many gallons, or roughly how many people? | PASS (borderline: "people" means guests; a question to the user is not an extra) |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 to AC-4 tests need no Ollama and no network, and read nothing under `data/`. | unit (review by test-evaluator) |
| NFR-3 | The eval (AC-3b, AC-5 to AC-8) is marked `eval`, skips (not fails) when Ollama is missing, the store is empty or `data/recipes/recipes.json` is missing, and warms both models up first. No test writes to `data/` or `.chroma/`. | unit (marker review); run output |
| NFR-4 | No source change outside `src/blc/judge/` and (revision 3) `build_final_messages` and `ANSWER_PROMPT` in `scripts/chat.py` (new `grounding.py`; the `path` argument, `JUDGE_PATHS` and the path rules in the judge prompt; the new names in `blc.judge`'s exports). | manual (code review) |
| NFR-6 | The judge prompt states the path rules in general terms, has at most 4 example answers in total, and contains no calibration answer or eval question (§4.4). If a J case still fails with general rules, the developer reports it instead of adding a rule or example aimed at it. | unit (EC-17) and manual (code review) |
| NFR-5 | The grounding checks are deterministic: the same input always gives the same output. | unit |

Tests go in `tests/answer_grounding/` (no `__init__.py`): `conftest.py` (the A, D and M cases, the scorer, the eval fixtures), `test_numbers.py` (AC-1), `test_sources.py` (AC-2), `test_scorer.py` (AC-3), `test_judge_path.py` (AC-3a), `test_judge_calibration.py` (AC-3b), `test_grounding_eval.py` (AC-5 to AC-8).

## Revision history
- **Revision 1 (2026-11-13)**, after the first run. Unit tests passed; the judge passed J1 to J7, J9 and J10 but gave PASS on J8 (expected FAIL), so the gate stopped the A, D and M grading. The user decided that J8's answer ("Make 6 gallons of decaf, since we make 1 gallon per 25 guests.") was not a fair test, and changed it.
  - **J8:** the answer is now "Make 6 gallons of decaf." and the expected verdict is **PASS**. J7 still checks that a TOOL answer with an extra fact (a location) fails.
  - **Spec 004's calibration (C1 to C35) is no longer required by this spec.** C31 and C35 fail on the unchanged `path=None` prompt, so they are a spec 004 matter, not caused by this spec.
  - **No code change.**
  - **Tests to change:** the J8 row in `tests/answer_grounding/conftest.py` (answer and expected verdict), and anything that counts the J cases by verdict. No other test changes.
- **Revision 2 (2026-11-13)**, after the first graded run with the `qwen2.5:14b` judge (calibration 10/10; TOOL passed; DOCS 8/10 and BOTH 6/10, with three failures the planner traced to the judge wrongly failing correct answers, two to the router, one to the chat model) and the user's experiments with prompts on `qwen2.5:7b` (best: 9/10, missing J3, with the path-rule-only prompt). **The user chose the 7B judge with the path-rule-only prompt.**
  - **Code to change (`src/blc/judge/`):** `JUDGE_MODEL = "qwen2.5:7b"`; with a path, the prompt is exactly the §4.4 template (no spec 004 rules or examples). Without a path, spec 004's prompt is unchanged.
  - **Gate and AC-3b:** at least 9 of 10 J cases (was all 10). Known miss with this judge: J3 (a correct documents extra in a BOTH answer is failed).
  - **Tests to change:** the gate and AC-3b threshold (9 of 10, misses listed); the EC-15 test gains the exact-template check; spec 004's model-name test (`tests/beverage_knowledge/test_judge.py`, AC-8 of spec 004) now expects `"qwen2.5:7b"`. No other assertion is weakened.
- **Revision 3 (2026-11-13)**, after the revision 2 run (7B judge; calibration 9/10, J3 missed; TOOL 8, DOCS 8, BOTH 6). Tracing M5 showed the router, retrieval and tool were all right, but the final message named only the tool part, so the model answered the tool part and dropped the documents part (also M8). The user chose two changes only:
  - **Code to change (`scripts/chat.py`):** for turns that mix tool and documents parts, the final user message lists every part with its label, `(documents)` or `(tool)` plus its result (§4.6); `ANSWER_PROMPT` gains `PART_INSTRUCTION` (§3.4). TOOL-only and DOCS-only messages are unchanged. Router, retrieval, tools and the judge are unchanged.
  - **Tests to change:** new EC-19 to EC-23 tests (AC-3c); existing tests that assert the old BOTH layout are updated to §4.6, nothing else weakened. The eval and its thresholds are unchanged; it is re-run.
- **Closed (2026-11-13)** by the user after the revision 3 run, as a baseline. Results (7B judge): calibration 9/10 (J3 missed); TOOL 7/10, DOCS 8/10, BOTH 4/10, all below threshold. Planner triage of the 16 misses: judge wrongly failed correct answers (A10, D4, M2, M5, M9); router (D9, M6); chatbot (A2 invented a unit conversion; A4 and M4 cited sources that were not retrieved or echoed part labels; M8 added example amounts after asking for gallons). Revision 3 itself worked: BOTH answers now cover every part. After closing, the user edited `ANSWER_PROMPT` in `scripts/chat.py` directly; that edit is not part of this spec and has not been run through the eval.
