"""Shared setup for spec 020, section 4.2 (mixed-question eval). Written from the spec only.

Exposed as fixtures (so no test imports from conftest):
- mixed_cases        the 6 cases: X1 to X5 plus spec 018's T5 (id, question, history, expected)
- score_case         score_case(plan, expected) -> list of failed check names ([] = pass)
- ollama_available / real_store / real_llm   (eval only) skip when Ollama or the store is missing
"""
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

BEV = "calculate_bev_item"
REC = "scale_recipe"

# expected: the set of items (one calculate_bev_item call per item), the one drink and the guest count.
_CASES = [
    ("X1", "How many gallons and how many cups for iced tea for 90 guests?",
     {"items": {"gallons", "cups"}, "drink": "iced tea", "guests": 90}),
    ("X2", "How many cambros and how many cups for coffee for 120 guests?",
     {"items": {"cambros", "cups"}, "drink": "coffee", "guests": 120}),
    ("X3", "For 60 guests of peach tea, how many gallons, cambros and cups?",
     {"items": {"gallons", "cambros", "cups"}, "drink": "peach tea", "guests": 60}),
    ("X4", "How many cups and gallons of decaf do I need for 40 guests?",
     {"items": {"cups", "gallons"}, "drink": "decaf", "guests": 40}),
    ("X5", "What do I need in gallons and cups for lemonade for 30 guests?",
     {"items": {"gallons", "cups"}, "drink": "lemonade", "guests": 30}),
]
# T5 of spec 018 is in the log only (no expectation, not scored).
T5 = ("T5", "How many cups for iced tea and lemonade for 90 guests?", None)


@pytest.fixture(scope="session")
def mixed_cases():
    """The 5 scored cases as {"id", "question", "history", "expected"}."""
    return [{"id": i, "question": q, "history": None, "expected": e} for i, q, e in _CASES]


@pytest.fixture(scope="session")
def t5_case():
    """Spec 018's T5, written to the log but not scored."""
    i, q, e = T5
    return {"id": i, "question": q, "history": None, "expected": e}


def _drink_names(args):
    drinks = args.get("drinks")
    if isinstance(drinks, str):
        return [drinks]
    if isinstance(drinks, (list, tuple)) and all(isinstance(d, str) for d in drinks):
        return list(drinks)
    return None


def _guests(args):
    g = args.get("guests")
    if isinstance(g, bool):
        return None
    try:
        return int(float(g))
    except (TypeError, ValueError):
        return None


@pytest.fixture(scope="session")
def score_case():
    """Spec 4.2 'How a case passes'. Returns the names of the failed checks:
    "items" (the set of item values differs from the expected set), "drink" (a call does not name exactly
    the expected drink, stripped, ignoring case), "guests" (a call's guests differs), "recipe" (a
    scale_recipe call is present). search_documents calls are ignored."""

    def _score(plan, expected):
        failed = []
        calls = [c for c in plan.calls if c.name == BEV]
        if any(c.name == REC for c in plan.calls):
            failed.append("recipe")
        if {c.args.get("item") for c in calls} != set(expected["items"]):
            failed.append("items")
        want = expected["drink"].strip().casefold()
        def _names(call):
            names = _drink_names(call.args)
            return None if names is None else [n.strip().casefold() for n in names]

        if any(_names(c) != [want] for c in calls):
            failed.append("drink")
        if any(_guests(c.args) != expected["guests"] for c in calls):
            failed.append("guests")
        return failed

    return _score


# --------------------------------------------------------------------------
# Eval environment (NFR-3: skip, do not fail)
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
        pytest.skip("Ollama is not running; start it to run the mixed-question eval.")
    return True


@pytest.fixture(scope="session")
def real_store(ollama_available):
    """The real Chroma store; skips when it is missing or empty."""
    import chat

    if not Path(chat.CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py.")
    store = chat.build_store()
    if not store.get(limit=1).get("ids"):
        pytest.skip("Chroma store is empty. Run scripts/ingest.py.")
    return store


@pytest.fixture(scope="session")
def real_llm(ollama_available):
    """The real chat model, warmed up with one call."""
    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL, CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")
    return llm
