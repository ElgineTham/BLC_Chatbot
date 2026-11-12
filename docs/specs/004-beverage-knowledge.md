# Spec 004: Beverage knowledge in the chatbot

- **Status:** approved (revision 2)
- **Date:** 2026-11-10 (revision 1: 2026-11-11; revision 2: 2026-11-11)

## 1. Goal
Staff should be able to ask the chatbot about the beverage menu and the pull sheet rules (what a package includes, what "coffee" or "juice" on a BEO means, how many gallons, cambros and cups to bring) and get correct, short answers. Two hand-written knowledge files, `data/pull_sheet/menu/beverages.md` and `data/pull_sheet/rules/beverages.md`, already exist and have already been ingested into the real store (`.chroma/`) by the planner with the existing `ingest.py`. This spec:
1. adds an **LLM judge** that grades an answer against a reference answer, and which must first pass a **calibration** set of known good, bad and boundary answers before it is trusted;
2. adds evals that check the right chunks are retrieved and, using the calibrated judge, that the chatbot's answers are correct (numbers, synonyms) and that it says it doesn't know when the documents don't cover a question.

## 2. Out of scope
- Any change to `scripts/ingest.py` or `scripts/chat.py` (including `SYSTEM_PROMPT`, `TOP_K`, the models and chunking). Ingesting is done by hand with the existing `ingest.py`; the evals read the real store.
- Keeping the example BEOs in `data/pull_sheet/examples/` out of a full `ingest.py` run (handled outside this spec).
- Writing or changing the two knowledge files. The planner and user own them. If an eval fails because of their wording, that is triaged as a data issue, not a code or test bug.
- Generating the markdown from the JSON files automatically, or checking that the two stay in sync.
- Letting the chatbot run the pull sheet program, or any change to `src/blc/pull_sheet/` or `scripts/pull_sheet.py`.
- Changing `evals/retrieval/golden.jsonl`, `tests/test_retrieval_eval.py` or `tests/test_generation_eval.py`, or using the judge for them.
- Multi-turn conversations: every eval question is asked with an empty history.
- A CLI for the judge, or using the judge in the chatbot itself. The judge is test equipment.

## 3. Interface contract
Existing names the evals use, all **unchanged**:

```python
# scripts/chat.py
CHROMA_DIR: Path                    # ROOT / ".chroma"
CHAT_MODEL: str                     # "qwen2.5:7b"
TOP_K: int                          # 3

def build_store() -> Chroma: ...                                             # opens .chroma/
def retrieve(store: Chroma, question: str) -> list[Document]: ...
def answer_from_context(llm, history, docs, question) -> str: ...
def unknown_retrieval_reply() -> str: ...
```

Each retrieved `Document` has `metadata["source"]`: the file's path from the project root, e.g. `data/pull_sheet/rules/beverages.md`.

New:

```python
# src/blc/judge/  (new feature package; everything below is importable as `from blc.judge import ...`)
from dataclasses import dataclass
from langchain_core.language_models import BaseChatModel

JUDGE_MODEL: str = "qwen2.5:14b"   # revision 2: was "qwen2.5:7b"; the chatbot itself stays on CHAT_MODEL

class JudgeError(Exception):
    """The judge model's reply could not be read as a verdict."""

@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str      # short explanation for humans; may be ""; tests do not compare its text

def judge_answer(
    question: str,
    reference: str,
    answer: str,
    llm: BaseChatModel | None = None,
) -> Verdict:
    """Grade `answer` to `question` against `reference` (the correct answer, with any
    must / must-not rules). llm=None means ChatOllama(model=JUDGE_MODEL, temperature=0).
    Raises ValueError if question or reference is empty or only whitespace.
    An empty or whitespace-only answer gives Verdict(False, ...) without calling the model.
    Raises JudgeError if the model's reply cannot be read as a verdict (§4)."""
```

**Store under test:** the real store, `build_store()`.

**Answer pipeline under test** (no new code; the evals build it from the names above): `docs = retrieve(store, question)`; if `docs` is empty the answer is `unknown_retrieval_reply()`, otherwise `answer_from_context(ChatOllama(model=CHAT_MODEL, temperature=0), [], docs, question)`.

Files: the evals only read `.chroma/`; no test or judge code writes files.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `judge_answer(question, reference, answer, llm)` | strings; chat model | question and reference non-blank | `Verdict` |
| Eval question | one string, empty history | the cases in §6 | retrieved chunks (top `TOP_K`) and a generated answer |

**Reference format.** Every reference has a `Required:` part (what a correct answer must say). It may also have a `May also:` part (extra things that are fine to mention) and a `Must not:` part (things a correct answer must not recommend, give or state as the answer). Example: `Required: exactly one 5 gal cambro. Must not: recommend a 2 gal plus a 1 gal cambro, or any other combination.`

**What the judge decides.** `passed` is `True` only if the answer states everything in `Required:` and does nothing listed in `Must not:`:
- Same meaning in different words passes: "gal", "gallon", "gallons", "5-gallon" and "five gallon" are the same; "a", "one" and "1" are the same.
- What counts is what the answer **recommends or gives as its answer**. Explanations, reasons and working are extra information: they pass if they are correct and don't change the answer's recommendation.
- Mentioning another option only to explain or rule it out passes, whatever its form. Example (reference "Required: 50 cold cups. Must not: give any other number of cups."): "50 cold cups, not 30, because you add 20 extras" passes.
- Offering a `Must not:` item as an acceptable alternative fails. Same reference: "50 cold cups, though 30 would also be fine" fails.
- **Correct details from the documents pass (NEW in revision 2)**, even when they name another item, an alias or a condition, as long as the answer's own recommendation for the question asked still meets the reference. Examples: for "Required: lemons.", "lemons, plus lemon tongs if hot water is ordered" passes; for "Required: peach tea.", "peach tea (a cold drink, served in cold cups)" passes.
- Any wrong number, wrong count of an item or missing `Required:` fact fails.
- Hedging between values ("4 or 5 gallons") fails.
- Saying "I don't know" or "it's not on the menu" and then giving what `Must not:` forbids anyway fails.

**What the judge's prompt may contain (NEW in revision 2).** The prompt the judge sends may use the examples in this section, or other examples the developer writes, but must not contain any calibration answer from §6 or any eval question from §6 (word for word or lightly reworded). The calibration cases test the judge; they are not training examples.
- **General rules, not case patches.** The prompt states the rules of this section in general terms. It has **at most 4 example answers** in total, and no example may copy the shape of a calibration case with the nouns or numbers swapped (e.g. "one large tray, since 30 portions is too much for a 20 portion tray" copies C7).
- **Size limit.** For `judge_answer("Q?", "Required: x.", "y.")`, the text the model receives is at most **3,000 characters**.
- **Tuning.** The developer may run the calibration cases to check the judge. If a case still fails with a general prompt, the developer reports it (case id and the judge's reason) instead of adding a rule or example aimed at that case. A failing calibration case is a finding for the planner, not something to patch around.

**How the judge's reply is read** (so unit tests can use a fake chat model). The judge takes the text content of the model's reply. Its first word, ignoring case and surrounding `*`, `#`, `:`, `.`, `-` and whitespace, must be `PASS` or `FAIL`; anything after it is the `reason`.

| Model reply | Result |
|---|---|
| `PASS` | `passed=True` |
| `pass\nMatches the reference.` | `passed=True` |
| `**PASS**` | `passed=True` |
| `FAIL: says two 5 gal cambros` | `passed=False` |
| `**FAIL** - wrong count` | `passed=False` |
| `I think it passes` | `JudgeError` |
| `` (empty) | `JudgeError` |
| `PASSED` | `JudgeError` |

**Eval case format.**
- Retrieval (answer cases A and S): `source` is the file that must be retrieved, and `chunk` is a phrase (compared with `str.casefold`, plain substring) that at least one retrieved chunk **from that source** must contain. Where `chunk` lists phrases joined by " or ", any one of them is enough.
- Generation (all cases A, S and X): the chatbot's answer is graded by `judge_answer(question, reference, answer)` with the case's `reference`, and must get `passed=True`.
- Calibration (cases C): `judge_answer(question, reference, answer)` must return the expected verdict. A C case's question and reference are those of the case it names, copied exactly.

## 5. Edge cases
- EC-1: The real store does not contain the two knowledge files (e.g. not ingested yet): the retrieval and generation evals skip with a message saying to ingest them, rather than fail.
- EC-2: Synonyms: "coffee" means regular coffee, not decaf; "juice" in the package means orange juice (cases S1 to S5).
- EC-3: Cambro boundaries: 3 gallons → one 5 gal cambro (not 2 + 1); 7 → 5 + 2; 12 → 5 + 5 + 2 (cases A1 to A3). "Two 5 gal cambros" contains "5 gal" but is wrong for 7 gallons (C3).
- EC-4: A question about a drink not on the menu (hot chocolate) must not be answered with the 25-guests-per-gallon rule, even alongside "it isn't on the menu" (C21).
- EC-5: `judge_answer` with an empty answer returns `passed=False` and never calls the model; with a blank question or reference it raises `ValueError`.
- EC-6: Judge reply parsing follows the table in §4, including `PASSED` → `JudgeError`.

## 6. Acceptance criteria
- **AC-1 (judge mechanics):** with a fake chat model, `judge_answer` follows §4's reply table, raises `ValueError` for a blank question or reference, returns `passed=False` for a blank answer without calling the model (EC-5, EC-6), and passes the question, reference and answer to the model (each appears in the text the model receives).
- **AC-2 (judge calibration):** with the real model (`llm=None`), the judge returns the expected verdict for **every** case C1 to C35. **Pass threshold: all cases.**
- **AC-3 (calibration gate):** the generation eval (AC-5) only grades answers with a judge that has passed calibration in the same test session. If any calibration case fails, every AC-5 case fails (or errors) with a message naming the failed calibration ids, instead of being graded.
- **AC-4 (retrieval eval):** using the real store (`build_store()`), every answer case (A and S) passes: `retrieve` returns at most `TOP_K` chunks, and at least one has `source` equal to the case's source and contains the case's `chunk` phrase. **Pass threshold: all cases.**
- **AC-5 (generation eval):** with the real store and the answer pipeline of §3, the calibrated judge gives `passed=True` for every case A1 to A10, S1 to S6 and X1 to X4. **Pass threshold: all cases.**
- **AC-6 (no calibration answers in the prompt, NEW):** with a fake chat model, call `judge_answer("Q?", "Required: x.", "y.")` and take the text the model receives. Casefolded and with runs of whitespace collapsed to one space, it contains no calibration answer from C1 to C35 that has 6 or more words, and no question from cases A1 to A10, S1 to S6 or X1 to X4 (each compared the same way, without its final punctuation).
- **AC-7 (prompt size, NEW):** with a fake chat model, the text the model receives for `judge_answer("Q?", "Required: x.", "y.")` is at most 3,000 characters (all messages joined).
- **AC-8 (judge model, NEW):** `JUDGE_MODEL == "qwen2.5:14b"`.

Sources: **M** = `data/pull_sheet/menu/beverages.md`, **R** = `data/pull_sheet/rules/beverages.md`.

**Answer cases: numbers and rules**

| id | question | source | chunk | reference |
|---|---|---|---|---|
| A1 | For 7 gallons of coffee, how many cambros do I need? | R | one 5 gal cambro and one 2 gal cambro | Required: exactly one 5 gal cambro and one 2 gal cambro (two cambros in total). Must not: recommend any other count or size of cambros. |
| A2 | How many cambros do I need for 3 gallons of iced tea? | R | one 5 gal cambro | Required: exactly one 5 gal cambro. Must not: recommend a 2 gal plus a 1 gal cambro, or any other combination. |
| A3 | I have 12 gallons of lemonade. Which cambros should I bring? | R | two 5 gal cambros and one 2 gal cambro | Required: exactly two 5 gal cambros and one 2 gal cambro. Must not: recommend any other count or size of cambros. |
| A4 | How many gallons of coffee do I need for 100 guests? | R | 1 gallon per 25 guests | Required: 4 gallons of coffee. Must not: give any other amount. |
| A5 | How many gallons of iced water for 150 guests? | R | 1 gallon per 25 guests | Required: 6 gallons of iced water. Must not: give any other amount. |
| A6 | How many hot cups do I need for 70 guests? | R | guests + extras | Required: 120 hot cups (70 guests plus 50 extra). Must not: give any other number of cups. |
| A7 | How many cold cups do I need for 150 guests? | R | guests + extras | Required: 250 cold cups (150 guests plus 100 extra). Must not: give any other number of cups. |
| A8 | What supplies do I bring when coffee is ordered? | R | creamer | Required: creamer, sugar and stir sticks. May also: cocktail napkins and hot cups. Must not: say to bring lemons, lemon tongs or tea packets for coffee. |
| A9 | Coffee and hot water both need sugar. How many sugars do I bring? | R | pull once | Required: 1 sugar, because a shared supply is pulled once, not added up. Must not: give 2 or more sugars. |
| A10 | What drinks are in the coffee, decaf, tea, iced water & juice package? | M | stands for five drinks | Required: all five drinks named: coffee (regular), decaf, hot water (for tea), iced water and orange juice. |

**Answer cases: synonyms**

| id | question | source | chunk | reference |
|---|---|---|---|---|
| S1 | The BEO just says coffee. Is that regular or decaf? | M | always means regular | Required: regular (caffeinated) coffee, not decaf. Must not: say it could be decaf or either. |
| S2 | The package says juice. Which juice should I bring? | M | means orange juice or is orange juice | Required: orange juice. Must not: recommend any other juice. |
| S3 | What does "Fresh-brewed coffee" on a BEO mean? | M | always means regular | Required: regular (caffeinated) coffee, not decaf. Must not: say it means decaf. |
| S4 | What does the "tea" in the coffee, decaf, tea, iced water & juice package mean? | M | hot water | Required: hot water with tea bags (the menu item Hot water). Must not: say it means iced tea. |
| S5 | How much juice do I make for the coffee, decaf, tea, iced water & juice package for 70 guests? | M | 3 gallons each | Required: 3 gallons of orange juice. Must not: give any other amount. |
| S6 | Does oatmilk go in a cambro? | M | does not go in a cambro | Required: no; oatmilk is counted each and does not go in a cambro. Must not: say it goes in a cambro. |

**Abstain cases** (generation only; no retrieval check)

| id | question | reference |
|---|---|---|
| X1 | How many gallons of hot chocolate do I need for 50 guests? | Required: says it doesn't know, or that hot chocolate is not on the menu and has no serving rules. Must not: give any gallon amount for hot chocolate. |
| X2 | How much does the coffee, decaf, tea, iced water & juice package cost? | Required: says it doesn't know the price. Must not: state any price. |
| X3 | How many espresso shots should I plan per guest? | Required: says it doesn't know, or that espresso is not on the menu. Must not: give a number of shots. |
| X4 | How do I clean a cambro? | Required: says it doesn't know how to clean a cambro. Must not: give cleaning steps. |

**Calibration cases** (question and reference copied exactly from the named case)

| id | for | answer | expected | type |
|---|---|---|---|---|
| C1 | A1 | You need one 5-gallon cambro and one 2-gallon cambro. | PASS | good |
| C2 | A1 | Bring a five gal cambro plus a two gal cambro for the 7 gallons. | PASS | boundary (wording) |
| C3 | A1 | Bring two 5 gal cambros. | FAIL | bad |
| C4 | A1 | Two 5 gal cambros and one 2 gal cambro. | FAIL | bad (extra cambro) |
| C5 | A1 | Use a 5 gal cambro. | FAIL | bad (missing cambro) |
| C6 | A1 | Not two 5 gal cambros: you need one 5 gal cambro and one 2 gal cambro. | PASS | boundary (rejected option) |
| C7 | A2 | One 5 gal cambro, since 3 gallons is too much for a 2 gal cambro. | PASS | boundary (mentions other size) |
| C8 | A2 | One 2 gal cambro and one 1 gal cambro. | FAIL | bad |
| C9 | A4 | 100 guests ÷ 25 = 4 gallons of coffee. | PASS | boundary (other numbers present) |
| C10 | A4 | About 4 or 5 gallons of coffee. | FAIL | boundary (hedge) |
| C11 | A4 | 5 gallons. | FAIL | bad |
| C12 | A6 | 70 guests plus 50 extra, so 120 hot cups. | PASS | good |
| C13 | A6 | 70 hot cups. | FAIL | bad |
| C14 | A8 | Creamer, sugar, stir sticks and cocktail napkins. | PASS | boundary (extra correct item) |
| C15 | A8 | Creamer, sugar, stir sticks and lemons. | FAIL | bad (must-not item) |
| C16 | A9 | Just 1 sugar: you pull it once. | PASS | good |
| C17 | A9 | Bring 2 sugars, one for the coffee and one for the hot water. | FAIL | bad |
| C18 | A10 | Coffee, decaf, hot water and iced water. | FAIL | bad (missing item) |
| C19 | S1 | That's regular coffee, not decaf. | PASS | good |
| C20 | S1 | It could be either regular or decaf. | FAIL | bad |
| C21 | X1 | Hot chocolate isn't on the menu, but at 25 guests per gallon you'd need 2 gallons. | FAIL | boundary (abstains, then answers) |
| C22 | X1 | I don't know. Hot chocolate isn't on our beverage menu. | PASS | good |
| C23 | S2 | Orange juice. | PASS | good |
| C24 | S2 | Apple cider. | FAIL | bad |
| C25 | X2 | I don't know the price; the documents don't include pricing. | PASS | good |
| C26 | X4 | Rinse it with hot water, then sanitize it and let it air dry. | FAIL | bad |
| C27 | A1 | One 5 gal cambro and one 2 gal cambro, because 7 gallons is too much for a single 5 gal cambro. | PASS | boundary (reason mentions another option) |
| C28 | A2 | One 5 gal cambro, or a 2 gal and a 1 gal cambro also works. | FAIL | boundary (must-not offered as an alternative) |
| C29 | A10 | Coffee, decaf, tea (hot water with tea bags), iced water and orange juice. | PASS | boundary (alias named alongside the item) |
| C30 | A10 | Coffee, decaf, iced tea, iced water and orange juice. | FAIL | bad (wrong item) |
| C31 | S2 | Orange juice, unless the BEO has its own line for a different juice. | PASS | boundary (condition from the documents) |
| C32 | S2 | Orange juice or apple juice; either works. | FAIL | bad (must-not offered as an alternative) |
| C33 | S5 | 3 gallons of orange juice, in its own 5 gal cambro (one cambro per drink). | PASS | boundary (extra correct detail) |
| C34 | S5 | About 3 or 4 gallons of orange juice. | FAIL | boundary (hedge) |
| C35 | A8 | Creamer, sugar and stir sticks. Lemons, lemon tongs and tea packets are only for hot water (tea), not coffee. | PASS | boundary (must-not items named only to rule them out) |

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No new dependencies. | manual (review `pyproject.toml`) |
| NFR-2 | AC-1 and AC-6 tests need no Ollama and no network. | unit |
| NFR-3 | Tests that need Ollama (AC-2 to AC-5) are marked `eval` and skip, not fail, when Ollama is not running; the retrieval and generation evals also skip when the knowledge files are not in the store (EC-1). No test writes to `.chroma/`. | unit (marker review by test-evaluator) |
| NFR-4 | Chat and judge run at temperature 0; each eval question uses an empty history. | manual (code and test review) |
| NFR-5 | The judge is calibrated once per test session and its results are reused, not rerun per generation case. | manual (test review) |
| NFR-6 | The existing evals (`tests/test_retrieval_eval.py`, `tests/test_generation_eval.py`) do no worse now that the knowledge files are in the store. | eval (run by the planner with the user) |
| NFR-7 | The two knowledge files match the JSON menu and rules. | manual (user review) |
| NFR-8 | The judge prompt's examples are not calibration answers or eval questions, and none copies the shape of a calibration case; at most 4 example answers (§4). AC-6 checks the word-for-word case. | unit (AC-6) and manual (code review for reworded or same-shape copies) |
| NFR-9 | No agent downloads or deletes Ollama models; the planner and user manage them (`qwen2.5:14b` is installed). | manual |

Tests go in `tests/beverage_knowledge/` (no `__init__.py`): `conftest.py` (cases, the store fixture, the calibrated-judge fixture), `test_judge.py` (AC-1, AC-6, AC-7, AC-8), `test_judge_calibration.py` (AC-2), `test_retrieval.py` (AC-4), `test_generation.py` (AC-3, AC-5).

## Revision history
- **Revision 1 (2026-11-11)**, after the first test run (calibration case C7 got FAIL instead of PASS, so the gate blocked all generation cases):
  - Every reference in §6 is rewritten in the labelled format `Required:` / `May also:` / `Must not:` (§4 "Reference format"). The facts are unchanged; only the wording and labels change.
  - §4 "What the judge decides" now says the judge grades what the answer **recommends or gives as its answer**; explanations and reasons that mention another option pass, and offering a `Must not:` item as an alternative fails.
  - New calibration cases C27 (PASS) and C28 (FAIL); AC-2 now covers C1 to C28.
  - Code: update the judge so it follows the revised §4 and gets the expected verdict on all 28 calibration cases with the real model, keeping C3, C4, C5, C10, C21 and C28 as FAIL.
  - Tests: update the case data in place (the new reference texts, C27 and C28, and anything that counts 26 calibration cases). No other test changes.
- **Revision 2 (2026-11-11)**, after spec 005's eval run and a code review:
  - The judge prompt contained calibration answers C6, C7, C27 and C28 word for word, because §4 used them as its examples. A judge that has seen its test answers is not really calibrated. §4 now uses examples that are not calibration cases, and says the prompt must not contain calibration answers or eval questions. New AC-6 checks this with a fake model; new NFR-8.
  - Spec 005's answer eval showed the judge failing correct answers that added correct details from the documents: "tea" named alongside "hot water", "one per drink", and "unless the BEO has its own line for a different juice". §4 gets the rule "correct details from the documents pass", and new calibration cases C29 to C35 (four PASS boundaries, three FAILs that must stay FAIL). AC-2 now covers C1 to C35.
  - Code: rewrite the judge prompt to follow the revised §4 without any calibration answer or eval question, and get the expected verdict on all 35 calibration cases with the real model.
  - Tests: add C29 to C35 to the case data, update anything that counts 28 calibration cases, and add the AC-6 test to `test_judge.py`. No other test changes.
  - **Amendment (2026-11-11, same revision):** the first attempt at the new prompt passed AC-6 but grew to about 5 KB of examples that were calibration cases with the nouns swapped (C6, C7, C29, C31, C33, C35): the 7B judge was being coached case by case. Changes: `JUDGE_MODEL` becomes `qwen2.5:14b` (the judge is test equipment, so speed does not matter; the chatbot stays on 7B); the prompt is limited to general rules, at most 4 example answers, none copying a calibration case's shape, and 3,000 characters (new AC-7); new AC-8 for the model name; a calibration case that still fails is reported, not patched; new NFR-9 (no model downloads by agents).
  - Code: rewrite `src/blc/judge/prompt.py` from scratch under these limits (the current file is the rejected attempt) and set `JUDGE_MODEL`.
  - Tests: add the AC-7 and AC-8 tests to `test_judge.py`. No other test changes.
