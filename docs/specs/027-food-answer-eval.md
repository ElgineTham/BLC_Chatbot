# Spec 027: Food answer-quality eval (single and multi-turn)

- **Status:** approved
- **Date:** 2026-11-16

## 1. Goal
Retrieval for `food.md` is now measured (specs 025, 026), but a manual chat showed the model can have the right chunks and still answer wrongly: it said croissants need nothing with them and that they "do not come with raspberry preserves", then repeated that after the user pushed back. This spec adds an **answer-quality eval** for the food menu that runs the real chat flow, grades each reply with the LLM judge against a reference answer, and includes **multi-turn conversations** (pairing questions, vague follow-ups, user pushback). It only measures; fixes are decided afterwards.

## 2. Out of scope
- Changing the chat flow, prompts, planner, router, retrieval, models, `TOP_K`, or the judge (`src/blc/judge/`). A failing answer is reported, not fixed here.
- Re-calibrating the judge in general (spec 004 owns that). This spec only adds a small food-specific gate (§6.2).
- Editing `food.md` or the golden files from specs 025/026.
- Retrieval quality, router/tool behaviour, voice, and beverage questions.
- Running `ingest.py` from a test. The store is ingested beforehand by the planner.

## 3. Interface contract
Existing names, all **unchanged**; tests only use them.

```python
# scripts/chat.py
CHROMA_DIR: Path
CHAT_MODEL: str                 # "qwen2.5:7b"
CHAT_TEMPERATURE: int           # 0
def build_store() -> Chroma: ...   # opens the real .chroma/

# src/blc/flow  (from blc.flow import run_planned_turn, TurnOutcome)
def run_planned_turn(
    llm: BaseChatModel, store, question: str,
    history: list[dict[str, str]] | None = None,
) -> TurnOutcome: ...          # other parameters keep their defaults
# TurnOutcome.reply: str          the answer text
# TurnOutcome.history: list[dict[str, str]]   history including this turn; pass it to the next turn

# src/blc/judge  (from blc.judge import judge_answer, JUDGE_MODEL, Verdict)
def judge_answer(question: str, reference: str, answer: str, llm=None) -> Verdict
# Verdict.passed: bool, Verdict.reason: str
```

**Pipeline under test** (what the live chat does): `llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE)`; `store = build_store()`; for each case start with `history = []`; for each turn call `run_planned_turn(llm, store, turn.question, history)`, take `outcome.reply`, set `history = outcome.history`, and grade `judge_answer(turn.question, turn.reference, outcome.reply)`.

**Golden file (new data, written by the planner):** `evals/answers/food_answers.jsonl`, one JSON object per line:
`{"id": str, "turns": [{"question": str, "reference": str}, ...], "must_pass": bool, "notes": str}`.
A case with one turn is a single question; a case with several turns is a conversation. A `reference` uses the spec 004 format: it starts with `Required:` and may have `May also:` and `Must not:` parts.

**Constant (defined in the test module):** `MIN_PASS_RATE = 0.90`.

Files read: `evals/answers/food_answers.jsonl`, the real `.chroma/`. Tests write nothing.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| Golden case | JSON line | 23 cases, 30 turns | one reply per turn from the real flow, one verdict per turn |
| Calibration case | question, reference, answer, expected verdict | 6 cases in §6.2 | `judge_answer` verdict compared with expected |

## 5. Acceptance criteria
- **AC-1:** The golden file has between 20 and 40 turns in total and unique non-empty ids; every case has at least one turn; every question and reference is non-blank; every reference starts with `Required:`; `must_pass` is a bool; at least 4 cases have two or more turns; the cases with ids `croissant-extras`, `croissant-preserves` and `conv-croissant-pushback` exist and have `must_pass` true.
- **AC-2** *(eval)*: **Judge gate.** With the real judge (`llm=None`), every calibration case in §6.2 gets its expected verdict. If any does not, every graded test in AC-3 and AC-4 fails (or errors) with a message naming the failed calibration ids, instead of grading.
- **AC-3** *(eval)*: Across all turns of all cases, the fraction whose verdict is `passed=True` is at least `MIN_PASS_RATE`.
- **AC-4** *(eval)*: Every turn of every case with `must_pass` true passes individually (the bug cases).
- **AC-5** *(eval)*: Conversations carry history: turn *n* is run with the history returned by turn *n−1* of the same case, never with another case's history. Each case starts with an empty history. *(verified `manual`: the planner reads the test.)*
- **AC-6** *(eval)*: When the rate is below `MIN_PASS_RATE` or a `must_pass` turn fails, the failure message lists every failing turn with: case id, turn number, question, the reply, and the judge's reason. Results are shown per turn (ids visible in the run output), but only AC-3 and AC-4 are asserted.
- **AC-7:** Eval tests skip with a clear message when Ollama is not running, when the judge model (`JUDGE_MODEL`) or `CHAT_MODEL` is not available, or when the real store has no documents with source `data/pull_sheet/menu/food.md` ("run scripts/ingest.py first").
- **AC-8** *(manual)*: Only files under `tests/food_answers/` and `evals/answers/food_answers.jsonl` are added; nothing under `scripts/`, `src/` or `data/` changes; eval tests carry the `eval` marker; tests import only the names in §3; files stay under ~400 lines.

## 6. Test cases
### 6.1 GOLD (golden file validity, unit)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| GOLD-1 | load the file | 20–40 turns in total, unique non-empty ids | AC-1 |
| GOLD-2 | every turn | non-blank question; reference starts with `Required:` | AC-1 |
| GOLD-3 | cases with 2+ turns | at least 4 | AC-1 |
| GOLD-4 | the three bug cases | present, `must_pass` true | AC-1 |
| GOLD-5 | `must_pass` of every case | is a bool | AC-1 |

### 6.2 CAL (judge gate, eval; the expected verdict must be returned)
| ID | Question | Reference | Answer | Expected | Covers |
|---|---|---|---|---|---|
| CAL-1 | Do I need to bring anything with croissants? | same as `croissant-extras` | "Yes. Bring the raspberry preserves from the service cooler." | pass | AC-2 |
| CAL-2 | same | same | "No, you do not need to bring anything with croissants. They are on the metal rack in the service room." | fail | AC-2 |
| CAL-3 | Do butter croissants come with raspberry preserves? | same as `croissant-preserves` | "Yes, on a BEO they are served with raspberry preserves, which are in the service cooler and pulled with the croissants." | pass | AC-2 |
| CAL-4 | same | same | "No, they do not come with raspberry preserves. The preserves are served separately." | fail | AC-2 |
| CAL-5 | Where are the cupcakes? | same as `abstain-cupcakes` | "I don't know. The documents don't cover cupcakes." | pass | AC-2 |
| CAL-6 | same | same | "Cupcakes are in the service cooler." | fail | AC-2 |

### 6.3 ANS (single-turn cases, eval; the reference of each is in the golden file)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ANS-1 | `croissant-extras` | raspberry preserves, service cooler (**must pass**) | AC-3, AC-4 |
| ANS-2 | `croissant-preserves` | yes, served with preserves (**must pass**) | AC-3, AC-4 |
| ANS-3 | `bagels-extras` | cream cheese, service cooler | AC-3 |
| ANS-4 | `yogurt-sides` | yogurt, granola, berries, honey in their four places | AC-3 |
| ANS-5 | `deli-sides` | Dijon mustard and mayonnaise, service cooler | AC-3 |
| ANS-6 | `cascade-items` | the Cascade contents | AC-3 |
| ANS-7 | `olympic-vs-cascade` | Cascade adds yogurt with honey and granola | AC-3 |
| ANS-8 | `honey-where` | metal racks in the pull area | AC-3 |
| ANS-9 | `gf-pastry-where` | service cooler, near the door to the kitchen | AC-3 |
| ANS-10 | `dijon-where` | service cooler | AC-3 |
| ANS-11 | `box-meals-where` | service cooler or beverage cooler | AC-3 |
| ANS-12 | `tabbouleh-serves` | 15-20 entrée or 30-40 side portions | AC-3 |
| ANS-13 | `eggs-where` | hot box inside the kitchen | AC-3 |
| ANS-14 | `jam-where` | raspberry preserves, service cooler | AC-3 |
| ANS-15 | `near-kitchen-door` | gluten-free vegan pastry and gluten-free/vegan cookie | AC-3 |
| ANS-16 | `popcorn-where` | metal rack in the service room | AC-3 |
| ANS-17 | `water-where` | beverage cooler | AC-3 |
| ANS-18 | `abstain-cupcakes` | says it does not know; no location given | AC-3 |
| ANS-19 | `abstain-oat-milk` | says it does not know; no location given | AC-3 |

### 6.4 CONV (conversations, eval)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| CONV-1 | `conv-croissant-pushback` (5 turns; the manual chat) | all five turns pass (**must pass**): preserves needed, "served with" confirmed, no "nothing needed" repeated | AC-3, AC-4, AC-5 |
| CONV-2 | `conv-bagels-pronoun` | "And what goes with them?" gives cream cheese, service cooler | AC-3, AC-5 |
| CONV-3 | `conv-box-meals-pushback` | user's wrong "only service cooler" is corrected | AC-3, AC-5 |
| CONV-4 | `conv-yogurt-honey` | "And the honey that goes with it?" gives the pull-area racks | AC-3, AC-5 |

### 6.5 RATE (aggregate and reporting, eval)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| RATE-1 | all 30 turns | pass rate ≥ `MIN_PASS_RATE` | AC-3 |
| RATE-2 | the three `must_pass` cases | every turn passes | AC-4 |
| RATE-3 | any failure | message lists case id, turn, question, reply, judge reason | AC-6 |
| RATE-4 | judge gate fails | graded tests fail naming the CAL ids | AC-2 |
| RATE-5 | Ollama down / model missing / food.md not in store | tests skip with a message | AC-7 |
