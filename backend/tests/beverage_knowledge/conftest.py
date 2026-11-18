"""Shared cases and fixtures for spec 004 (beverage knowledge).

Cases are exposed to tests through ``pytest_generate_tests`` so test modules
never need to import this file.  Fixture/argument names:

- ``answer_case``      A and S cases (retrieval + generation)
- ``generation_case``  A, S and X cases
- ``calibration_case`` C cases (dict with id, for, question, reference, answer, expected)
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

M = "data/pull_sheet/menu/beverages.md"
R = "data/pull_sheet/rules/beverages.md"
KNOWLEDGE_FILES = (M, R)

# id, question, source, chunk, reference
_ANSWER_ROWS = [
    ("A1", "For 7 gallons of coffee, how many cambros do I need?", R,
     "one 5 gal cambro and one 2 gal cambro",
     "Required: exactly one 5 gal cambro and one 2 gal cambro (two cambros in total). "
     "Must not: recommend any other count or size of cambros."),
    ("A2", "How many cambros do I need for 3 gallons of iced tea?", R,
     "one 5 gal cambro",
     "Required: exactly one 5 gal cambro. "
     "Must not: recommend a 2 gal plus a 1 gal cambro, or any other combination."),
    ("A3", "I have 12 gallons of lemonade. Which cambros should I bring?", R,
     "two 5 gal cambros and one 2 gal cambro",
     "Required: exactly two 5 gal cambros and one 2 gal cambro. "
     "Must not: recommend any other count or size of cambros."),
    ("A4", "How many gallons of coffee do I need for 100 guests?", R,
     "1 gallon per 25 guests",
     "Required: 4 gallons of coffee. Must not: give any other amount."),
    ("A5", "How many gallons of iced water for 150 guests?", R,
     "1 gallon per 25 guests",
     "Required: 6 gallons of iced water. Must not: give any other amount."),
    ("A6", "How many hot cups do I need for 70 guests?", R,
     "guests + extras",
     "Required: 120 hot cups (70 guests plus 50 extra). Must not: give any other number of cups."),
    ("A7", "How many cold cups do I need for 150 guests?", R,
     "guests + extras",
     "Required: 250 cold cups (150 guests plus 100 extra). Must not: give any other number of cups."),
    ("A8", "What supplies do I bring when coffee is ordered?", R,
     "creamer",
     "Required: creamer, sugar and stir sticks. May also: cocktail napkins and hot cups. "
     "Must not: say to bring lemons, lemon tongs or tea packets for coffee."),
    ("A9", "Coffee and hot water both need sugar. How many sugars do I bring?", R,
     "pull once",
     "Required: 1 sugar, because a shared supply is pulled once, not added up. "
     "Must not: give 2 or more sugars."),
    ("A10", "What drinks are in the coffee, decaf, tea, iced water & juice package?", M,
     "stands for five drinks",
     "Required: all five drinks named: coffee (regular), decaf, hot water (for tea), "
     "iced water and orange juice."),
    ("S1", "The BEO just says coffee. Is that regular or decaf?", M,
     "always means regular",
     "Required: regular (caffeinated) coffee, not decaf. Must not: say it could be decaf or either."),
    ("S2", "The package says juice. Which juice should I bring?", M,
     "means orange juice or is orange juice",
     "Required: orange juice. Must not: recommend any other juice."),
    ("S3", 'What does "Fresh-brewed coffee" on a BEO mean?', M,
     "always means regular",
     "Required: regular (caffeinated) coffee, not decaf. Must not: say it means decaf."),
    ("S4", 'What does the "tea" in the coffee, decaf, tea, iced water & juice package mean?', M,
     "hot water",
     "Required: hot water with tea bags (the menu item Hot water). Must not: say it means iced tea."),
    ("S5", "How much juice do I make for the coffee, decaf, tea, iced water & juice package for 70 guests?", M,
     "3 gallons each",
     "Required: 3 gallons of orange juice. Must not: give any other amount."),
    ("S6", "Does oatmilk go in a cambro?", M,
     "does not go in a cambro",
     "Required: no; oatmilk is counted each and does not go in a cambro. "
     "Must not: say it goes in a cambro."),
]

_ABSTAIN_ROWS = [
    ("X1", "How many gallons of hot chocolate do I need for 50 guests?",
     "Required: says it doesn't know, or that hot chocolate is not on the menu and has no serving rules. "
     "Must not: give any gallon amount for hot chocolate."),
    ("X2", "How much does the coffee, decaf, tea, iced water & juice package cost?",
     "Required: says it doesn't know the price. Must not: state any price."),
    ("X3", "How many espresso shots should I plan per guest?",
     "Required: says it doesn't know, or that espresso is not on the menu. "
     "Must not: give a number of shots."),
    ("X4", "How do I clean a cambro?",
     "Required: says it doesn't know how to clean a cambro. Must not: give cleaning steps."),
]

ANSWER_CASES = [
    {"id": i, "question": q, "source": s, "chunk": c, "reference": r}
    for (i, q, s, c, r) in _ANSWER_ROWS
]
ABSTAIN_CASES = [
    {"id": i, "question": q, "reference": r} for (i, q, r) in _ABSTAIN_ROWS
]
GENERATION_CASES = [
    {"id": c["id"], "question": c["question"], "reference": c["reference"]}
    for c in ANSWER_CASES
] + ABSTAIN_CASES

_BY_ID = {c["id"]: c for c in GENERATION_CASES}

# id, for, answer, expected
_CAL_ROWS = [
    ("C1", "A1", "You need one 5-gallon cambro and one 2-gallon cambro.", "PASS"),
    ("C2", "A1", "Bring a five gal cambro plus a two gal cambro for the 7 gallons.", "PASS"),
    ("C3", "A1", "Bring two 5 gal cambros.", "FAIL"),
    ("C4", "A1", "Two 5 gal cambros and one 2 gal cambro.", "FAIL"),
    ("C5", "A1", "Use a 5 gal cambro.", "FAIL"),
    ("C6", "A1", "Not two 5 gal cambros: you need one 5 gal cambro and one 2 gal cambro.", "PASS"),
    ("C7", "A2", "One 5 gal cambro, since 3 gallons is too much for a 2 gal cambro.", "PASS"),
    ("C8", "A2", "One 2 gal cambro and one 1 gal cambro.", "FAIL"),
    ("C9", "A4", "100 guests ÷ 25 = 4 gallons of coffee.", "PASS"),
    ("C10", "A4", "About 4 or 5 gallons of coffee.", "FAIL"),
    ("C11", "A4", "5 gallons.", "FAIL"),
    ("C12", "A6", "70 guests plus 50 extra, so 120 hot cups.", "PASS"),
    ("C13", "A6", "70 hot cups.", "FAIL"),
    ("C14", "A8", "Creamer, sugar, stir sticks and cocktail napkins.", "PASS"),
    ("C15", "A8", "Creamer, sugar, stir sticks and lemons.", "FAIL"),
    ("C16", "A9", "Just 1 sugar: you pull it once.", "PASS"),
    ("C17", "A9", "Bring 2 sugars, one for the coffee and one for the hot water.", "FAIL"),
    ("C18", "A10", "Coffee, decaf, hot water and iced water.", "FAIL"),
    ("C19", "S1", "That's regular coffee, not decaf.", "PASS"),
    ("C20", "S1", "It could be either regular or decaf.", "FAIL"),
    ("C21", "X1", "Hot chocolate isn't on the menu, but at 25 guests per gallon you'd need 2 gallons.", "FAIL"),
    ("C22", "X1", "I don't know. Hot chocolate isn't on our beverage menu.", "PASS"),
    ("C23", "S2", "Orange juice.", "PASS"),
    ("C24", "S2", "Apple cider.", "FAIL"),
    ("C25", "X2", "I don't know the price; the documents don't include pricing.", "PASS"),
    ("C26", "X4", "Rinse it with hot water, then sanitize it and let it air dry.", "FAIL"),
    ("C27", "A1", "One 5 gal cambro and one 2 gal cambro, because 7 gallons is too much for a single 5 gal cambro.", "PASS"),
    ("C28", "A2", "One 5 gal cambro, or a 2 gal and a 1 gal cambro also works.", "FAIL"),
    ("C29", "A10", "Coffee, decaf, tea (hot water with tea bags), iced water and orange juice.", "PASS"),
    ("C30", "A10", "Coffee, decaf, iced tea, iced water and orange juice.", "FAIL"),
    ("C31", "S2", "Orange juice, unless the BEO has its own line for a different juice.", "PASS"),
    ("C32", "S2", "Orange juice or apple juice; either works.", "FAIL"),
    ("C33", "S5", "3 gallons of orange juice, in its own 5 gal cambro (one cambro per drink).", "PASS"),
    ("C34", "S5", "About 3 or 4 gallons of orange juice.", "FAIL"),
    ("C35", "A8", "Creamer, sugar and stir sticks. Lemons, lemon tongs and tea packets are only for hot water (tea), not coffee.", "PASS"),
]

CALIBRATION_CASES = [
    {
        "id": cid,
        "for": src,
        "question": _BY_ID[src]["question"],
        "reference": _BY_ID[src]["reference"],
        "answer": ans,
        "expected": exp == "PASS",
    }
    for (cid, src, ans, exp) in _CAL_ROWS
]


@pytest.fixture
def all_calibration_cases():
    return CALIBRATION_CASES


@pytest.fixture
def all_generation_cases():
    return GENERATION_CASES


def pytest_generate_tests(metafunc):
    for name, cases in (
        ("answer_case", ANSWER_CASES),
        ("generation_case", GENERATION_CASES),
        ("calibration_case", CALIBRATION_CASES),
    ):
        if name in metafunc.fixturenames:
            metafunc.parametrize(name, cases, ids=[c["id"] for c in cases])


# --------------------------------------------------------------------------
# Environment fixtures (NFR-3: skip, do not fail)
# --------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama_available():
    if not _ollama_running():
        pytest.skip("Ollama is not running; start it to run the beverage evals.")
    return True


@pytest.fixture(scope="session")
def store(ollama_available):
    """The real store (read only); skips if the knowledge files are not ingested (EC-1)."""
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(
            f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py to ingest "
            "data/pull_sheet/menu/beverages.md and data/pull_sheet/rules/beverages.md."
        )
    chroma = build_store()
    data = chroma.get(include=["metadatas"])
    sources = {(m or {}).get("source", "") for m in (data.get("metadatas") or [])}
    missing = [f for f in KNOWLEDGE_FILES if not any(s.endswith(f) for s in sources)]
    if missing:
        pytest.skip(
            f"Knowledge file(s) {missing} are not in the store. "
            "Run scripts/ingest.py to ingest them."
        )
    return chroma


@pytest.fixture(scope="session")
def chat_llm(ollama_available):
    from chat import CHAT_MODEL
    from langchain_ollama import ChatOllama

    return ChatOllama(model=CHAT_MODEL, temperature=0)


# --------------------------------------------------------------------------
# Calibration: run once per session, reuse (NFR-5), gate generation (AC-3)
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def calibration_results(ollama_available):
    """Map case id -> Verdict, or the exception raised while judging."""
    from blc.judge import judge_answer

    results = {}
    for case in CALIBRATION_CASES:
        try:
            results[case["id"]] = judge_answer(
                case["question"], case["reference"], case["answer"]
            )
        except Exception as exc:  # recorded, reported by the tests
            results[case["id"]] = exc
    return results


def failed_calibration_ids(results) -> list[str]:
    failed = []
    for case in CALIBRATION_CASES:
        res = results[case["id"]]
        if isinstance(res, Exception) or res.passed != case["expected"]:
            failed.append(case["id"])
    return failed


@pytest.fixture(scope="session")
def calibrated_judge(calibration_results):
    """judge_answer, only if every calibration case passed; otherwise fail naming the ids."""
    from blc.judge import judge_answer

    failed = failed_calibration_ids(calibration_results)
    if failed:
        pytest.fail(
            "Judge failed calibration, answers not graded. Failed calibration ids: "
            + ", ".join(failed),
            pytrace=False,
        )
    return judge_answer
