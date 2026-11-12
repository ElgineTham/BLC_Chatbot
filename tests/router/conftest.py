"""Shared setup for the router and chat-flow tests (specs 006, 013, 014). Written from the spec only.

Unit tests: no Ollama, no Chroma, no network, nothing read under data/.
Helpers are exposed as fixtures so test files never import this module.

Fixtures:
- catalog / bev_tool   the spec 005 Appendix A catalog (written to tmp_path) and make_bev_tool(catalog)
- Scripted             class: scripted fake chat model (plain invoke list + bound invoke list)
- RouterFake           class: scripted router model with only `invoke`
- FakeStore            fake store with similarity_search(query, k=...)
- run_turn_with        run_turn on a fake store with the given tools patched into chat.CHAT_TOOLS
- ai, tc               build scripted AIMessages and tool-call dicts
- text_of              join the content of a message list into one string
- make_tool            recording fake tool
- fast_llm             (eval only) real ChatOllama with keep_alive; skips when Ollama is not running
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
    """llm.invoke(messages) pops `plain` replies (router first when needed, final last); strings become AIMessages.
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


class FakeStore:
    """similarity_search(query, k=...) -> the fixed docs. Records (query, k)."""

    def __init__(self, docs=()):
        self.docs = list(docs)
        self.calls = []

    def similarity_search(self, query, k=4, *args, **kwargs):
        self.calls.append((query, k))
        return list(self.docs)


@pytest.fixture(name="RouterFake")
def _router_fake_fixture():
    return RouterFake


@pytest.fixture(name="Scripted")
def _scripted_fixture():
    return Scripted


@pytest.fixture(name="FakeStore")
def _fake_store_fixture():
    return FakeStore


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
def run_turn_with(monkeypatch, FakeStore):
    """run_turn_with(llm, question, tools, docs, history=None, generate=True) -> TurnTrace.
    Patches chat.CHAT_TOOLS to `tools` and passes a FakeStore(docs) to the real chat.run_turn."""
    import chat

    def _run(llm, question, tools, docs, history=None, generate=True):
        monkeypatch.setattr(chat, "CHAT_TOOLS", list(tools), raising=False)
        return chat.run_turn(FakeStore(docs), llm, [] if history is None else history, question, generate=generate)

    return _run


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
def fast_llm(ollama_available):
    """Spec 013 AC-6 (eval only): the real chat model with keep_alive=CHAT_KEEP_ALIVE, warmed up by one call."""
    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=CHAT_MODEL, temperature=0, keep_alive=CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")  # warm-up: loads the model so timings are fair
    return llm
