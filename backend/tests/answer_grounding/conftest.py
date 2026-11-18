"""Shared setup for spec 017 (grounded answers on the TOOL, DOCS and BOTH paths). Written from the spec only.

Unit tests (AC-1 to AC-4): no Ollama, no Chroma, no network, nothing read under data/ (NFR-2).
Helpers are exposed as fixtures so test files never import this module.

Fixtures:
- cases / case_by_id     the A1-A10, D1-D10, M1-M10 eval cases (section 6) as dicts: id, path, history, question, reference
- j_cases / j_case       the calibration cases J1-J10 (id, path, question, reference, answer, expected); `j_case` is parametrized
- make_trace             build a hand-made TurnTrace for the scorer tests
- FakeJudge              a recording stand-in for judge_answer (verdicts are given, not computed)
- score_case, Score      the scorer of section 4.3: a pure function on a TurnTrace, a case and a judge (NFR-6 style)
- grounding_env          (eval only) the real store, chat model and judge model, warmed up; skips when unavailable (NFR-3)
- calibration_failures   (eval only) session-wide: the J ids that gave the wrong verdict (empty list = calibrated)
"""

from __future__ import annotations

import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

TOOL, DOCS, BOTH = "TOOL", "DOCS", "BOTH"


# --------------------------------------------------------------------------
# Eval cases (section 6)
# --------------------------------------------------------------------------

H_A9 = [
    {"role": "user", "content": "How much lemon concentrate do I need for 4 gallons of lemonade?"},
    {"role": "assistant", "content": "28 oz of lemon concentrate, with water to 4 gallons."},
]
H_A10 = [
    {"role": "user", "content": "How many cambros do I need for iced tea?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]

_A5_STEPS = ("the steps: pour the concentrate into a clean container that holds the whole batch, add water to the "
             "batch size, stir well, taste and adjust before service")

_ROWS = [
    ("A1", TOOL, [], "How many cambros for 9 gallons of decaf?",
     "Required: two 5 gal cambros. May also: 9 gallons of decaf. Must not: any other count or size; a location; a recalculation or rule (such as guests per gallon)."),
    ("A2", TOOL, [], "How many cups for orange juice for 85 guests?",
     "Required: 135 cold cups. May also: 3 gallons of orange juice for 85 guests. Must not: any other cup number; hot cups; a location."),
    ("A3", TOOL, [], "How many gallons of peach tea for 140 guests?",
     "Required: 6 gallons of peach tea. May also: that it is for 140 guests. Must not: any other amount; a rule such as guests per gallon."),
    ("A4", TOOL, [], "What do I bring for iced tea for 60 guests?",
     "Required: 2 gallons of iced tea, one 2 gal cambro, 110 cold cups, cocktail napkins and lemons. May also: that it is for 60 guests. Must not: other counts; creamer, sugar or stir sticks."),
    ("A5", TOOL, [], "How much lemon concentrate for 11 gallons of lemonade?",
     f"Required: 77 oz of lemon concentrate. May also: water to 11 gallons, and {_A5_STEPS}. Must not: any other concentrate amount; 7 oz as the amount for this batch."),
    ("A6", TOOL, [], "Which cambros do I need for 6 gallons of espresso?",
     "Required: says espresso is not on the beverage menu. Must not: give any cambro count or size."),
    ("A7", TOOL, [], "How many cambros do I need for the iced water?",
     "Required: asks how many gallons or how many guests. Must not: give a cambro count."),
    ("A8", TOOL, [], "How do I make 4 gallons of iced tea?",
     "Required: says there is no iced tea recipe (or that it doesn't know how). May also: the only recipe available is lemonade. Must not: give ingredients or amounts for iced tea."),
    ("A9", TOOL, H_A9, "What about for 130 guests?",
     f"Required: 5 gallons (for 130 guests) and 35 oz of lemon concentrate. May also: water to 5 gallons, and {_A5_STEPS}. Must not: 28 oz or any other concentrate amount as the answer for 130 guests."),
    ("A10", TOOL, H_A10, "7 gallons.",
     "Required: one 5 gal cambro and one 2 gal cambro. May also: 7 gallons of iced tea. Must not: any other count or size."),
    ("D1", DOCS, [], "Where can I find the coffee supplies?",
     "Required: underneath the coffee machine in the beverage room. May also: the backup beside the cambros near the washing pit. Must not: any other location."),
    ("D2", DOCS, [], "Where are the syrups?",
     "Required: above the lemons inside the beverage cooler, near the sink by the coffee machine. May also: the backup on the blue racks with the concentrates. Must not: any other location."),
    ("D3", DOCS, [], "What concentrate flavors do we have?",
     "Required: pomegranate, lemonade and orange. Must not: any other flavor."),
    ("D4", DOCS, [], "Where do I find the lemons if there are none by the sink?",
     "Required: the back side of the main cooler by the dish room. Must not: any other backup location."),
    ("D5", DOCS, [], "What is the lemonade recipe?",
     "Required: 7 oz of lemon concentrate per gallon, water to 1 gallon, stir. Must not: any other amount per gallon."),
    ("D6", DOCS, [], "On a BEO, does Fresh-brewed coffee mean decaf?",
     "Required: no, it means regular (caffeinated) coffee. Must not: say it is decaf."),
    ("D7", DOCS, [], "Which juice comes with the coffee, decaf, tea, iced water & juice package?",
     "Required: orange juice. Must not: name another juice."),
    ("D8", DOCS, [], "How should I pull concentrate stock?",
     "Required: use opened ones first; if none are open, take new ones from the boxes on the same racks."),
    ("D9", DOCS, [], "Is lemonade served in a cambro?",
     "Required: yes; lemonade is made by the gallon and served from cambros. May also: it is a cold drink served in cold cups. Must not: say it is not served in a cambro; give a cambro count or size."),
    ("D10", DOCS, [], "What time does the bar close tonight?",
     "Required: says it doesn't know. Must not: give a time."),
    ("M1", BOTH, [], "Where do we keep concentrates, and how much lemon concentrate goes into 13 gallons of lemonade?",
     f"Required: on the blue racks in the beverage cooler, and 91 oz of lemon concentrate. May also: water to 13 gallons, and {_A5_STEPS}. Must not: any other concentrate amount or location."),
    ("M2", BOTH, [], "Where are the coffee supplies, and how many cambros do I need for 6 gallons of coffee?",
     "Required: underneath the coffee machine in the beverage room, and one 5 gal cambro plus one 1 gal cambro. May also: 6 gallons of coffee. Must not: any other cambro count or size."),
    ("M3", BOTH, [], "Where is the backup stock of lemons, and do I need lemon tongs for hot water?",
     "Required: the back side of the main cooler by the dish room, and yes, 1 lemon tongs. May also: the other supplies for hot water (cocktail napkins, 1 stir sticks, 1 sugar, lemons, 1 tea packets). Must not: any other location; say tongs are not needed."),
    ("M4", BOTH, [], "Does Coffee on a BEO mean decaf, and how many gallons of coffee for 120 guests?",
     "Required: no, it means regular coffee, and 5 gallons of coffee. May also: that it is for 120 guests. Must not: any other amount; say it means decaf."),
    ("M5", BOTH, [], "Where are the syrups kept; which cambros hold 12 gallons of iced water?",
     "Required: above the lemons inside the beverage cooler near the sink by the coffee machine, and two 5 gal cambros plus one 2 gal cambro. May also: 12 gallons of iced water. Must not: any other cambro count or size."),
    ("M6", BOTH, [], "Is oatmilk counted in gallons, and what do I need to bring for decaf for 45 guests?",
     "Required: no, oatmilk is counted in pieces; and for decaf: 2 gallons, one 2 gal cambro, 65 hot cups, cocktail napkins, creamer, 1 stir sticks and 1 sugar. Must not: other counts."),
    ("M7", BOTH, [], "How do I pull concentrate stock, and how do I make lemonade for 50 guests?",
     f"Required: use opened ones first, then new ones from the boxes on the same racks; and 2 gallons, 14 oz of lemon concentrate, water to 2 gallons. May also: that it is for 50 guests, and {_A5_STEPS}. Must not: any other concentrate amount."),
    ("M8", BOTH, [], "Where are the lemons, and how many cambros do I need for the peach tea?",
     "Required: by the sink near the coffee machine, and asks how many gallons of peach tea or how many guests. Must not: give a cambro count."),
    ("M9", BOTH, [], "Who is the event manager tonight, and how many hot cups do I need for 40 guests?",
     "Required: says it doesn't know who the event manager is, and 60 hot cups. May also: the same count applies to cold cups. Must not: name a person."),
    ("M10", BOTH, [], "Where are the syrups, and how do I make 3 gallons of mango smoothie?",
     "Required: above the lemons inside the beverage cooler near the sink by the coffee machine, and says there is no mango smoothie recipe (or that it doesn't know how to make it). May also: the only recipe available is lemonade. Must not: give ingredients or amounts for a mango smoothie."),
]

CASES = [{"id": i, "path": p, "history": list(h), "question": q, "reference": r} for (i, p, h, q, r) in _ROWS]

# id, path, question, reference, answer, expected verdict (True = PASS)
_J_ROWS = [
    ("J1", TOOL, "How many cambros for 8 gallons of hot water?",
     "Required: two 5 gal cambros. May also: 8 gallons of hot water. Must not: any other count or size.",
     "You need two 5 gal cambros for 8 gallons of hot water.", True),
    ("J2", DOCS, "Where do we keep the syrups if the cooler shelf is empty?",
     "Required: on the blue racks with the concentrates in the beverage cooler. Must not: any other location.",
     "Check the blue racks with the concentrates inside the beverage cooler (data/supplies/syrups.md).", True),
    ("J3", BOTH, "Where are the lemons, and how many cold cups for 90 guests?",
     "Required: by the sink near the coffee machine, and 140 cold cups. Must not: any other cup number.",
     "Lemons are by the sink near the coffee machine; if none are there, check the back side of the main cooler by the dish room. For 90 guests you need 140 cold cups.", True),
    ("J4", TOOL, "How much lemon concentrate for 15 gallons of lemonade?",
     "Required: 105 oz of lemon concentrate. Must not: any other amount.",
     "You need 70 oz of lemon concentrate.", False),
    ("J5", DOCS, "Which syrup flavors can I use for the drink station?",
     "Required: mango, strawberry and peach. Must not: any other flavor.",
     "Mango, strawberry, peach and raspberry.", False),
    ("J6", BOTH, "Where are the coffee supplies, and how many hot cups for 110 guests?",
     "Required: underneath the coffee machine in the beverage room, and 210 hot cups. Must not: any other cup number or location.",
     "Coffee supplies are underneath the coffee machine in the beverage room. You need 210 hot cups, and remember to bring creamer and sugar.", False),
    ("J7", TOOL, "How many cambros for 10 gallons of peach tea?",
     "Required: two 5 gal cambros. May also: 10 gallons of peach tea. Must not: any other count or size.",
     "You need two 5 gal cambros. You'll find them beside the washing pit in the beverage room.", False),
    ("J8", TOOL, "How many gallons of decaf for 150 guests?",
     "Required: 6 gallons of decaf. May also: that it is for 150 guests. Must not: any other amount.",
     "Make 6 gallons of decaf.", True),
    ("J9", DOCS, "Where are the concentrates stored?",
     "Required: on the blue racks in the beverage cooler.",
     "On the blue racks inside the beverage cooler. Use the opened ones first before starting a new box.", True),
    ("J10", TOOL, "How many cambros for the decaf?",
     "Required: asks how many gallons or how many guests. Must not: give a cambro count.",
     "How much decaf are you making? How many gallons, or roughly how many people?", True),
]

J_CASES = [
    {"id": i, "path": p, "question": q, "reference": r, "answer": a, "expected": e}
    for (i, p, q, r, a, e) in _J_ROWS
]


@pytest.fixture
def cases():
    return list(CASES)


@pytest.fixture
def case_by_id():
    return {c["id"]: c for c in CASES}


@pytest.fixture
def j_cases():
    return list(J_CASES)


def pytest_generate_tests(metafunc):
    if "j_case" in metafunc.fixturenames:
        metafunc.parametrize("j_case", J_CASES, ids=[c["id"] for c in J_CASES])


# --------------------------------------------------------------------------
# Hand-made traces and a fake judge (unit tests of the scorer)
# --------------------------------------------------------------------------

@pytest.fixture
def make_trace():
    """make_trace(kind, reply, chunks=(), tool_texts=(), question="q", history=()) -> TurnTrace.
    chunks: iterable of (source, text). tool_texts: strings, one tool stage each. `kind` is the route kind."""
    from blc.router import RouteDecision, RoutedPart
    from blc.trace import RetrievalStage, RetrievedChunk, ToolCallLog, ToolStage, TurnTrace

    def _make(kind, reply, chunks=(), tool_texts=(), question="q", history=()):
        retrieval = RetrievalStage(
            question, 4,
            tuple(RetrievedChunk(rank=i + 1, source=s, text=t) for i, (s, t) in enumerate(chunks)),
        )
        stages = tuple(
            ToolStage(question, (ToolCallLog("calculate_bev_item", {}, text, False),), text, False)
            for text in tool_texts
        )
        parts = (RoutedPart(kind if kind != BOTH else "TOOL", question, "calculate_bev_item" if kind != DOCS else None),)
        return TurnTrace(question, tuple(history), retrieval, RouteDecision(parts, kind, False), stages, reply)

    return _make


class FakeJudge:
    """Stands in for judge_answer: returns a given verdict and records every call."""

    def __init__(self, passed=True, reason="because"):
        from blc.judge import Verdict

        self.verdict = Verdict(passed=passed, reason=reason)
        self.calls = []

    def __call__(self, question, reference, answer, path=None):
        self.calls.append({"question": question, "reference": reference, "answer": answer, "path": path})
        return self.verdict


@pytest.fixture(name="FakeJudge")
def _fake_judge_fixture():
    return FakeJudge


# --------------------------------------------------------------------------
# The scorer (section 4.3): a pure function
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Score:
    passed: bool
    stages: tuple[str, ...]       # failed stages in order: route, judge, numbers, sources; ("calibration",) if not graded
    detail: str                   # the judge's reason, or the failed J ids
    ungrounded: tuple[str, ...]
    unknown: tuple[str, ...]


def score_case(trace, case, judge, failed_calibration=()):
    """Section 4.3 / EC-18. `judge(question, reference, answer, path=...)` returns a Verdict.
    If failed_calibration is not empty, nothing is graded and the judge is not called."""
    from blc.judge import ungrounded_numbers, unknown_sources

    if failed_calibration:
        return Score(False, ("calibration",), "judge failed calibration: " + ", ".join(failed_calibration), (), ())
    path = case["path"]
    stages = []
    kind = trace.route.kind if trace.route is not None else None
    if kind != path:
        stages.append("route")
    reply = trace.reply or ""
    verdict = judge(case["question"], case["reference"], reply, path=path)
    if not verdict.passed:
        stages.append("judge")
    chunks = tuple(trace.retrieval.chunks) if trace.retrieval is not None else ()
    material = []
    if path in (TOOL, BOTH):
        material += [s.tool_text for s in trace.tools if s.tool_text]
    if path in (DOCS, BOTH):
        material += [c.text for c in chunks]
    history = [m.get("content", "") for m in list(case["history"]) + list(trace.history)]
    ungrounded = ungrounded_numbers(reply, material + [case["question"]] + history)
    if ungrounded:
        stages.append("numbers")
    allowed = [c.source for c in chunks] if path in (DOCS, BOTH) else []
    unknown = unknown_sources(reply, allowed)
    if unknown:
        stages.append("sources")
    return Score(not stages, tuple(stages), verdict.reason, ungrounded, unknown)


@pytest.fixture(name="score_case")
def _score_case_fixture():
    return score_case


# --------------------------------------------------------------------------
# Eval environment (NFR-3: skip, do not fail; warm both models up)
# --------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def grounding_env():
    """The real store, chat model and judge model, built once. Skips when Ollama is not running, the store is
    empty or missing, or data/recipes/recipes.json is missing. Reads only; nothing is written to data/ or .chroma/."""
    if not _ollama_running():
        pytest.skip("Ollama is not running; start it to run the grounding eval.")
    import chat
    from blc.judge import JUDGE_MODEL
    from blc.tools.recipe_tools import RECIPES_FILE
    from langchain_ollama import ChatOllama

    if not Path(RECIPES_FILE).exists():
        pytest.skip(f"{RECIPES_FILE} is missing; the recipe tool has no recipes.")
    if not Path(chat.CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py.")
    store = chat.build_store()
    if not (store.get(include=["metadatas"]).get("ids") or []):
        pytest.skip("The Chroma store is empty. Run scripts/ingest.py.")
    llm = ChatOllama(model=chat.CHAT_MODEL, temperature=0, keep_alive=chat.CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")  # warm-up: loads the chat model
    ChatOllama(model=JUDGE_MODEL, temperature=0).invoke("Reply with one word: ready")  # warm-up: loads the judge model
    return SimpleNamespace(store=store, llm=llm, chat=chat, results=None)


@pytest.fixture(scope="session")
def j_results(grounding_env):
    """{J id: Verdict or the exception raised}, run once per session with the real judge (llm=None) and each case's path."""
    from blc.judge import judge_answer

    out = {}
    for c in J_CASES:
        try:
            out[c["id"]] = judge_answer(c["question"], c["reference"], c["answer"], path=c["path"])
        except Exception as exc:  # recorded, reported by the tests
            out[c["id"]] = exc
    return out


CALIBRATION_MIN_CORRECT = 9  # revision 2: at least 9 of 10 J cases must give the expected verdict


@pytest.fixture(scope="session")
def j_misses(j_results):
    """Every J id whose verdict was wrong (or that raised), always listed in the report."""
    missed = []
    for c in J_CASES:
        r = j_results[c["id"]]
        if isinstance(r, Exception) or r.passed != c["expected"]:
            missed.append(c["id"])
    return missed


@pytest.fixture(scope="session")
def calibration_failures(j_misses):
    """The gate (section 4.5, revision 2): [] when at least 9 of 10 J cases are right (grading goes ahead);
    otherwise the failed J ids (no A, D or M case is graded)."""
    if len(J_CASES) - len(j_misses) >= CALIBRATION_MIN_CORRECT:
        return []
    return list(j_misses)
