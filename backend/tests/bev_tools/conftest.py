"""Shared setup for spec 005 (beverage calculator tool), revision 2. Written from the spec only.

Unit tests: no Ollama, no Chroma, no network. The Appendix A catalog is written to tmp_path.
Helpers are exposed as fixtures so test files never import this module.

Fixtures:
- catalog            the Appendix A catalog, loaded from tmp_path
- bev_tool           make_bev_tool(catalog): the tool built on the Appendix A catalog (no data/ access)
- pair_lines         BevResult/PullSheet lines -> list of (supply, quantity)
- sheet_pairs        build_pull_sheet for an equivalent BEO -> list of (supply, quantity)
- FakeChatModel      class: scripted tool-calling chat model (bind_tools / invoke)
- ai, tc             helpers to build scripted AIMessages and tool-call dicts
- make_tool          builds a recording fake tool with a given name
- eval_case          (eval only) parametrized over the 26 cases (T1-T23 of spec 005, T24-T26 of spec 006)
- store, chat_llm    (eval only) real store and real chat model; skip when unavailable
"""

from __future__ import annotations

import json
import sys
import urllib.request
from fractions import Fraction
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

PKG = "Coffee, decaf, tea, iced water & juice"
ANY = "*"  # "do not check this value" in eval expectations


# --------------------------------------------------------------------------
# Appendix A catalog
# --------------------------------------------------------------------------

def _menu():
    return {
        "items": {
            "Coffee": {"unit": "gallon", "also_written_as": ["Fresh-brewed coffee"], "tags": ["HOT", "COFFEE"]},
            "Decaf": {"unit": "gallon", "also_written_as": ["Fresh-brewed decaffeinated coffee"], "tags": ["HOT", "COFFEE"]},
            "Hot water": {
                "unit": "gallon",
                "also_written_as": ["Hot water with an assortment of black, green, and herbal tea bags"],
                "tags": ["HOT", "HOT-WATER"],
            },
            "Brewed hot cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Ginger Honeycrisp apple cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Iced water": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Iced tea": {"unit": "gallon", "also_written_as": ["Iced tea with lemon wedges"], "tags": ["COLD", "ICED-TEA"]},
            "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
            "Lemonade": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Peach tea": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []},
        },
        "packages": {
            PKG: {
                "includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
                "placeholders": {"JUICE": "Orange juice"},
            }
        },
    }


def _rules():
    return {
        "cambros": [
            {"supply": "5 gal cambro", "gallons": 5},
            {"supply": "2 gal cambro", "gallons": 2},
            {"supply": "1 gal cambro", "gallons": 1},
        ],
        "supplies": [
            {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
            {"supply": "cold-cups", "qty": 1, "per": "guest+extra", "when_tagged": "COLD"},
            {"supply": "Cocktail napkins", "tick": True},
            {"supply": "Creamer", "tick": True, "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemon tongs", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "HOT-WATER"},
            {"supply": "Tea packets", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "ICED-TEA"},
        ],
        "extras": [
            {"guests_up_to": 20, "extra": 10},
            {"guests_up_to": 50, "extra": 20},
            {"guests_up_to": 100, "extra": 50},
            {"guests_up_to": None, "extra": 100},
        ],
    }


@pytest.fixture
def catalog(tmp_path):
    from blc.pull_sheet import load_catalog

    for rel, data in (("menu/beverages.json", _menu()), ("rules/beverages.json", _rules())):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalog(tmp_path)


@pytest.fixture
def bev_tool(catalog):
    from blc.tools.bev_tools import make_bev_tool

    return make_bev_tool(catalog)


@pytest.fixture(name="PKG")
def _pkg_fixture():
    return PKG


@pytest.fixture
def pair_lines():
    def _pairs(lines):
        return [(l.supply, l.quantity) for l in lines]

    return _pairs


@pytest.fixture
def sheet_pairs(catalog):
    """sheet_pairs(guests, [(name, qty, uom), ...]) -> [(supply, quantity)] from build_pull_sheet."""
    from blc.pull_sheet import Beo, BeoLine, build_pull_sheet

    def _run(guests, entries):
        beo = Beo(guests, tuple(BeoLine(n, Fraction(str(q)), u) for n, q, u in entries))
        return [(l.supply, l.quantity) for l in build_pull_sheet(catalog, beo).lines]

    return _run


# --------------------------------------------------------------------------
# Fake tool-calling chat model (spec section 3.2, "How the chat flow talks to the model")
# --------------------------------------------------------------------------

def tc(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def ai(content="", calls=()):
    return AIMessage(content=content, tool_calls=list(calls))


class _Bound:
    def __init__(self, owner):
        self.owner = owner

    def invoke(self, messages, *args, **kwargs):
        self.owner.invocations.append(list(messages))
        if not self.owner.script:
            raise AssertionError("fake model was asked more times than scripted")
        if self.owner.repeat_last and len(self.owner.script) == 1:
            return self.owner.script[0]
        return self.owner.script.pop(0)


class FakeChatModel:
    """bind_tools(...) returns an object whose invoke(messages) pops scripted AIMessages.
    With repeat_last=True the last scripted reply is returned forever (for the round limit).
    `invocations` holds a snapshot of the message list of every model call."""

    def __init__(self, script, repeat_last=False):
        self.script = list(script)
        self.repeat_last = repeat_last
        self.invocations = []
        self.bound_tools = []
        self.plain_invokes = []

    def bind_tools(self, tools, *args, **kwargs):
        self.bound_tools.append(list(tools))
        return _Bound(self)

    def invoke(self, messages, *args, **kwargs):
        self.plain_invokes.append(messages)
        return AIMessage(content="SUMMARY")


@pytest.fixture(name="FakeChatModel")
def _fake_model_fixture():
    return FakeChatModel


@pytest.fixture(name="ai")
def _ai_fixture():
    return ai


@pytest.fixture(name="tc")
def _tc_fixture():
    return tc


@pytest.fixture
def make_tool():
    """make_tool(name, result="ok") -> (tool, calls) where calls records each argument dict."""

    def _make(name, result="tool-result"):
        calls = []

        def _fn(x: str = "") -> str:
            calls.append({"x": x})
            return result

        _fn.__name__ = name
        t = StructuredTool.from_function(func=_fn, name=name, description="fake tool for tests")
        return t, calls

    return _make


# --------------------------------------------------------------------------
# Eval cases (spec section 6, Tool column). Expectation keys:
#   kind: "none" | "item" | "none_or_item"
#   item: the calculate_bev_item item
#   status: required status (default "ok"; used by none_or_item)
#   drinks: [(display name, amount or ANY, from_guests True/False/ANY)]   (resolved drinks, any order)
#   drinks_any_of: list of alternative drinks lists
#   drinks_hot_only: True -> no drinks, or only hot drinks
#   guests: int (must be given and equal) | None ("no guests") | ANY
# --------------------------------------------------------------------------

HOT_DRINKS = {"Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider"}

EVAL_CASES = [
    {"id": "T1", "question": "Where is the coffee located?", "history": [],
     "kind": "none",
     "reference": "Required: under the coffee machine in the beverage room. May also: the backup location beside the cambros near the washing pit."},
    {"id": "T2", "question": "How many cambros do I need to bring for 7 gallons of lemonade?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Lemonade", 7, False)], "guests": None,
     "reference": "Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size of cambros."},
    {"id": "T3", "question": "How many oz of lemonade concentrate do I need to make 5 gallons of lemonade?", "history": [],
     # Spec 016 AC-4: a scale_recipe call (ok, Lemonade, 5 gallons), no calculate_bev_item call.
     "kind": "recipe", "recipe": "Lemonade", "gallons": 5,
     "reference": "Required: 35 oz of lemonade concentrate. Must not: give any other amount."},
    {"id": "T4", "question": "Where is the coffee, and how many gallons of coffee do I need for 75 people?", "history": [],
     "kind": "item", "item": "gallons", "drinks_any_of": [[], [("Coffee", 3, True)]], "guests": 75,
     "reference": "Required: the coffee is under the coffee machine in the beverage room, and 3 gallons of coffee for 75 people. May also: the backup location. Must not: give any other gallon amount."},
    {"id": "T5", "question": "How many cambros do I need for coffee and lemonade?", "history": [],
     "kind": "none_or_item", "item": "cambros", "status": "need_info",
     "reference": "Required: asks how many gallons of each drink or how many guests. Must not: give any number of cambros."},
    {"id": "T6", "question": "5 gallons each.",
     "history": [
         {"role": "user", "content": "How many cambros do I need for coffee and lemonade?"},
         {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
     ],
     "kind": "item", "item": "cambros", "drinks": [("Coffee", 5, False), ("Lemonade", 5, False)], "guests": ANY,
     "reference": "Required: two 5 gal cambros, one for the coffee and one for the lemonade. Must not: recommend any other count or size."},
    {"id": "T7", "question": "I need 5 gallons of coffee and lemonade. How many cambros?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Coffee", 5, False), ("Lemonade", 5, False)], "guests": ANY,
     "reference": "Required: two 5 gal cambros, one for each drink. Must not: recommend any other count or size."},
    {"id": "T8", "question": "How many cups do I need for coffee?", "history": [],
     "kind": "none_or_item", "item": "cups", "status": "need_info",
     "reference": "Required: asks how many guests. Must not: give a number of cups."},
    {"id": "T9", "question": "5 gallons of coffee and 3 gallons of lemonade, how many cambros?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Coffee", 5, False), ("Lemonade", 3, False)], "guests": ANY,
     "reference": "Required: two 5 gal cambros. Must not: recommend any other count or size."},
    {"id": "T10", "question": "Coffee and lemonade for 70 guests, how many cups?", "history": [],
     "kind": "item", "item": "cups", "drinks": [("Coffee", ANY, ANY), ("Lemonade", ANY, ANY)], "guests": 70,
     "reference": "Required: 120 hot cups and 120 cold cups. Must not: give any other cup numbers."},
    {"id": "T11", "question": "How many cambros for lemonade for 70 guests?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Lemonade", 3, True)], "guests": 70,
     "reference": "Required: one 5 gal cambro (3 gallons). Must not: recommend any other count or size."},
    {"id": "T12", "question": "How many cambros for 4 gallons of hot chocolate?", "history": [],
     "kind": "none_or_item", "item": "cambros", "status": "not_on_menu",
     "reference": "Required: says hot chocolate is not on the beverage menu, or that it doesn't know. Must not: give any number of cambros."},
    {"id": "T13", "question": "How many cambros for 7 gallons of fresh-brewed coffee?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Coffee", 7, False)], "guests": ANY,
     "reference": "Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size."},
    {"id": "T14", "question": "We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros?", "history": [],
     "kind": "item", "item": "cambros",
     "drinks": [("Coffee", 3, True), ("Decaf", 3, True), ("Hot water", 3, True),
                ("Iced water", 3, True), ("Orange juice", 3, True)],
     "guests": 70,
     "reference": "Required: five 5 gal cambros, one per drink. Must not: recommend any other count or size."},
    {"id": "T15", "question": "What's in the coffee, decaf, tea, iced water & juice package?", "history": [],
     "kind": "none",
     "reference": "Required: coffee (regular), decaf, hot water (for tea), iced water and orange juice, all five named."},
    {"id": "T16", "question": "What syrup flavors do we have?", "history": [],
     "kind": "none",
     "reference": "Required: mango, strawberry and peach."},
    {"id": "T17", "question": "What time does my shift start tomorrow?", "history": [],
     "kind": "none",
     "reference": "Required: says it doesn't know. Must not: give a time."},
    {"id": "T18", "question": "What do I put 7 gallons of lemonade in?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Lemonade", 7, False)], "guests": ANY,
     "reference": "Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size."},
    {"id": "T19", "question": "Seven gallons of lemonade, which containers do I bring?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Lemonade", 7, False)], "guests": ANY,
     "reference": "Required: one 5 gal cambro and one 2 gal cambro. Must not: recommend any other count or size."},
    {"id": "T20", "question": "What do I need to bring for coffee for 50 guests?", "history": [],
     "kind": "item", "item": "everything", "drinks": [("Coffee", 2, True)], "guests": 50,
     "reference": "Required: one 2 gal cambro, 70 hot cups, cocktail napkins, creamer, stir sticks and sugar. Must not: give a different cambro or cup count."},
    {"id": "T21", "question": "Do I need sugar for coffee?", "history": [],
     "kind": "item", "item": "supplies", "drinks": [("Coffee", ANY, ANY)], "guests": None,
     "reference": "Required: yes, 1 sugar. Must not: give 2 or more sugars."},
    {"id": "T22", "question": "How many gallons do I make for 25 people?", "history": [],
     "kind": "item", "item": "gallons", "drinks": [], "guests": 25,
     "reference": "Required: 1 gallon of each drink. Must not: give any other amount."},
    {"id": "T23", "question": "How many hot cups do I need for 40 guests?", "history": [],
     "kind": "item", "item": "cups", "drinks_hot_only": True, "guests": 40,
     "reference": "Required: 60 hot cups. Must not: give any other number of cups."},
    # Added by spec 006 (T24 to T26)
    {"id": "T24", "question": "How many napkins should I grab for the iced tea station?", "history": [],
     "kind": "item", "item": "supplies", "drinks": [("Iced tea", ANY, ANY)], "guests": None,
     "reference": "Required: bring cocktail napkins (the rules give no count). Must not: give a number of napkins."},
    {"id": "T25", "question": "Which jugs do I fill with 9 gallons of iced water?", "history": [],
     "kind": "item", "item": "cambros", "drinks": [("Iced water", 9, False)], "guests": None,
     "reference": "Required: two 5 gal cambros. Must not: recommend any other count or size."},
    {"id": "T26", "question": "Brewed hot cider for 100 people, what goes on the pull sheet?", "history": [],
     "kind": "item", "item": "everything", "drinks": [("Brewed hot cider", 4, True)], "guests": 100,
     "reference": "Required: one 5 gal cambro, 150 hot cups and cocktail napkins. Must not: give a different cambro or cup count."},
]


def pytest_generate_tests(metafunc):
    if "eval_case" in metafunc.fixturenames:
        metafunc.parametrize("eval_case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])


# --------------------------------------------------------------------------
# Eval environment (NFR-4: skip, do not fail)
# --------------------------------------------------------------------------

KNOWLEDGE_FILES = (
    "data/pull_sheet/menu/beverages.md",
    "data/pull_sheet/rules/beverages.md",
)


def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama_available():
    if not _ollama_running():
        pytest.skip("Ollama is not running; start it to run the beverage tool evals.")
    return True


@pytest.fixture(scope="session")
def store(ollama_available):
    """The real store (read only); skips if the knowledge files are not ingested."""
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py.")
    chroma = build_store()
    data = chroma.get(include=["metadatas"])
    sources = {(m or {}).get("source", "") for m in (data.get("metadatas") or [])}
    missing = [f for f in KNOWLEDGE_FILES if not any(s.endswith(f) for s in sources)]
    if missing:
        pytest.skip(f"Knowledge file(s) {missing} are not in the store. Run scripts/ingest.py.")
    return chroma


@pytest.fixture(scope="session")
def chat_llm(ollama_available):
    from chat import CHAT_MODEL
    from langchain_ollama import ChatOllama

    return ChatOllama(model=CHAT_MODEL, temperature=0)
