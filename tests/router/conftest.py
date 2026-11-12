"""Shared setup for spec 006 (question router). Written from the spec only.

Unit tests: no Ollama, no Chroma, no network, nothing read under data/.
Helpers are exposed as fixtures so test files never import this module.

Fixtures:
- catalog / bev_tool   the spec 005 Appendix A catalog (written to tmp_path) and make_bev_tool(catalog)
- Scripted             class: scripted fake chat model (plain invoke list + bound invoke list)
- ai, tc               build scripted AIMessages and tool-call dicts
- text_of              join the content of a message list into one string
- router_case          (eval only) parametrized over R1 to R14
- chat_llm             (eval only) real ChatOllama; skips when Ollama is not running
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

PKG = "Coffee, decaf, tea, iced water & juice"


# --------------------------------------------------------------------------
# Appendix A catalog (copy of spec 005 Appendix A, as in tests/bev_tools/conftest.py)
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


# --------------------------------------------------------------------------
# Scripted fake chat model (spec 006 section 3.2, "How the flow talks to the model")
# --------------------------------------------------------------------------

def tc(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def ai(content="", calls=()):
    return AIMessage(content=content, tool_calls=list(calls))


def text_of(messages):
    return "\n".join(str(getattr(m, "content", "")) for m in messages)


class _Bound:
    def __init__(self, owner):
        self.owner = owner

    def invoke(self, messages, *args, **kwargs):
        o = self.owner
        o.bound_invocations.append(list(messages))
        if not o.bound_script:
            raise AssertionError("tool step asked the model more times than scripted")
        if o.repeat_last and len(o.bound_script) == 1:
            return o.bound_script[0]
        return o.bound_script.pop(0)


class Scripted:
    """llm.invoke(messages) pops `plain` replies (router first, final last); strings become AIMessages.
    llm.bind_tools(tools) returns an object whose invoke pops `bound` replies (tool steps).
    With repeat_last=True the last bound reply is returned forever (for the round limit).
    Records: plain_invocations, bound_invocations (message-list snapshots), bind_calls (tool lists)."""

    def __init__(self, plain, bound=(), repeat_last=False):
        self.plain_script = list(plain)
        self.bound_script = list(bound)
        self.repeat_last = repeat_last
        self.plain_invocations = []
        self.bound_invocations = []
        self.bind_calls = []

    def invoke(self, messages, *args, **kwargs):
        self.plain_invocations.append(list(messages))
        if not self.plain_script:
            raise AssertionError("llm.invoke was called more times than scripted")
        reply = self.plain_script.pop(0)
        return AIMessage(content=reply) if isinstance(reply, str) else reply

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(list(tools))
        return _Bound(self)


class RouterFake:
    """Spec 010: scripted router model. Has only invoke (no bind, bind_tools or with_structured_output).
    Each invoke pops the next reply (str becomes an AIMessage) and records messages, args and kwargs."""

    def __init__(self, *replies):
        self.script = list(replies)
        self.messages = []
        self.args = []
        self.kwargs = []

    def invoke(self, messages, *args, **kwargs):
        self.messages.append(list(messages))
        self.args.append(args)
        self.kwargs.append(kwargs)
        if not self.script:
            raise AssertionError("llm.invoke was called more times than scripted")
        reply = self.script.pop(0)
        return AIMessage(content=reply) if isinstance(reply, str) else reply


def jparts(*parts):
    """JSON router reply from (route, text) pairs."""
    return json.dumps({"parts": [{"route": r, "text": t} for r, t in parts]})


@pytest.fixture(name="RouterFake")
def _router_fake_fixture():
    return RouterFake


@pytest.fixture(name="jparts")
def _jparts_fixture():
    return jparts


@pytest.fixture(name="Scripted")
def _scripted_fixture():
    return Scripted


@pytest.fixture(name="ai")
def _ai_fixture():
    return ai


@pytest.fixture(name="tc")
def _tc_fixture():
    return tc


@pytest.fixture(name="text_of")
def _text_of_fixture():
    return text_of


@pytest.fixture
def make_tool():
    """make_tool(name, result="tool-result") -> (tool, calls); calls records each argument dict."""
    from langchain_core.tools import StructuredTool

    def _make(name, result="tool-result"):
        calls = []

        def _fn(x: str = "") -> str:
            calls.append({"x": x})
            return result

        _fn.__name__ = name
        return StructuredTool.from_function(func=_fn, name=name, description="fake tool for tests"), calls

    return _make


# --------------------------------------------------------------------------
# Router eval cases (spec 006 section 6). routes: list of acceptable route tuples.
# --------------------------------------------------------------------------

ROUTER_CASES = [
    {"id": "R1", "question": "How many cambros do I need to bring for 7 gallons of lemonade?", "history": [], "routes": [("TOOL",)]},
    {"id": "R2", "question": "How many oz of lemonade concentrate do I need to make 5 gallons of lemonade?", "history": [], "routes": [("DOCS",)]},
    {"id": "R3", "question": "Where is the coffee, and how many gallons of coffee do I need for 75 people?", "history": [], "routes": [("DOCS", "TOOL")]},
    {"id": "R4", "question": "What's in the coffee, decaf, tea, iced water & juice package?", "history": [], "routes": [("DOCS",)]},
    {"id": "R5", "question": "What do I put 7 gallons of lemonade in?", "history": [], "routes": [("TOOL",)]},
    {"id": "R6", "question": "Do I need sugar for coffee?", "history": [], "routes": [("TOOL",)]},
    {"id": "R7", "question": "What do I need to bring for coffee for 50 guests?", "history": [], "routes": [("TOOL",)]},
    {"id": "R8", "question": "The BEO just says coffee. Is that regular or decaf?", "history": [], "routes": [("DOCS",)]},
    {"id": "R9", "question": "How many gallons of hot chocolate do I need for 50 guests?", "history": [], "routes": [("DOCS",), ("TOOL",)]},
    {"id": "R10", "question": "Which jugs do I fill with 9 gallons of iced water?", "history": [], "routes": [("TOOL",)]},
    {"id": "R11", "question": "How do I clean a cambro?", "history": [], "routes": [("DOCS",)]},
    {"id": "R12", "question": "5 gallons each.",
     "history": [
         {"role": "user", "content": "How many cambros for coffee and lemonade?"},
         {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
     ],
     "routes": [("TOOL",)], "text_must_contain": ("coffee", "lemonade", "5")},
    {"id": "R13", "question": "Where are the lemons, and do I need lemons for iced tea?", "history": [], "routes": [("DOCS", "TOOL")]},
    {"id": "R14", "question": "What syrup flavors do we have?", "history": [], "routes": [("DOCS",)]},
]

# Spec 007 section 6 eval cases, groups A to D (every case must pass).
_SPEC7_CASES = [
    ("A1", "Where do we keep the stir sticks?", ("DOCS",)),
    ("A2", "What is the difference between Decaf and Coffee on a BEO?", ("DOCS",)),
    ("A3", "How long does brewed hot cider stay good?", ("DOCS",)),
    ("B1", "How many hot cups do I need for 120 guests?", ("TOOL",)),
    ("B2", "Do I bring tea packets for hot water?", ("TOOL",)),
    ("B3", "How many gallons of orange juice for 60 people?", ("TOOL",)),
    ("B4", "Which cambros do I use for 12 gallons of Ginger Honeycrisp apple cider?", ("TOOL",)),
    ("C1", "What is Oatmilk counted in, and how many cups do I need for 80 guests?", ("DOCS", "TOOL")),
    ("C2", "Where are the lemon tongs kept, and do I bring lemons for hot water for 40 guests?", ("DOCS", "TOOL")),
    ("C3", "How do I clean the coffee urn, and which cambros hold 4 gallons of decaf?", ("DOCS", "TOOL")),
    ("C4", "How many napkins should I bring, and what is in the orange juice package?", ("TOOL", "DOCS")),
    ("D1", "How to make 3 gallons of lemonade?", ("DOCS",)),
    ("D2", "How do I make 6 gallons of iced tea?", ("DOCS",)),
    ("D3", "How much sugar goes in a batch of lemonade?", ("DOCS",)),
    ("D4", "How many lemons do I squeeze for a gallon of lemonade?", ("DOCS",)),
    ("D5", "What are the steps to brew 5 gallons of coffee?", ("DOCS",)),
    ("D6", "How many cambros for 3 gallons of lemonade?", ("TOOL",)),
]
ROUTER_CASES.extend({"id": i, "question": q, "history": [], "routes": [r]} for i, q, r in _SPEC7_CASES)

# Group E: recipe plus guests. Threshold: at least 2 of 3 must give DOCS, TOOL.
GROUP_E_CASES = [
    {"id": "E1", "question": "How do I make lemonade for 90 guests?", "history": [], "routes": [("DOCS", "TOOL")]},
    {"id": "E2", "question": "What is the recipe for iced tea for 120 people, and how much do I need?", "history": [], "routes": [("DOCS", "TOOL")]},
    {"id": "E3", "question": "How do I make peach tea for 60 guests?", "history": [], "routes": [("DOCS", "TOOL")]},
]


@pytest.fixture
def group_e_cases():
    return GROUP_E_CASES


def pytest_generate_tests(metafunc):
    if "router_case" in metafunc.fixturenames:
        metafunc.parametrize("router_case", ROUTER_CASES, ids=[c["id"] for c in ROUTER_CASES])


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
        pytest.skip("Ollama is not running; start it to run the router evals.")
    return True


@pytest.fixture(scope="session")
def chat_llm(ollama_available):
    from chat import CHAT_MODEL
    from langchain_ollama import ChatOllama

    return ChatOllama(model=CHAT_MODEL, temperature=0)
