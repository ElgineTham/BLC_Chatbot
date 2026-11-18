"""Shared fakes and fixtures for spec 030 (food tool wiring).

Unit tests: scripted fake models, fake store, tool runners built from run_food_tool with the spec 029
Appendix A rules written to tmp_path. No Ollama, no Chroma, no network, nothing read under data/.
Plain data and pure functions (cases, scorer, log writer) live in food_wiring_helpers.py.

Fixtures (so tests do not import fakes from conftest):
- mk, doc, make_llm, make_store, make_runner, text_of   fakes and builders
- rules, food_runner                                    Appendix A rules and a real-rules food runner
- point_rules_file_at                                   patch FOOD_RULES_FILE everywhere it is bound
- run                                                   run one planned turn with scripted plans
- ollama_available / eval_llm / eval_store              (eval only) skip when Ollama or .chroma is missing
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from blc.tools.food_tools import load_food_rules, run_food_tool  # noqa: E402

FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

APPENDIX_A = {
    "extras": [
        {"guests_up_to": 20, "extra": 10},
        {"guests_up_to": 50, "extra": 20},
        {"guests_up_to": 100, "extra": 50},
        {"guests_up_to": None, "extra": 100},
    ],
    "napkins": {
        "breakfast": {"cocktail": True, "dinner": False},
        "reception": {"cocktail": True, "dinner": False},
        "lunch": {"cocktail": False, "dinner": True},
        "dinner": {"cocktail": False, "dinner": True},
    },
}


# --------------------------------------------------------------------------
# Scripted fake model: the planner (bind_tools + invoke) and the answerer (stream)
# --------------------------------------------------------------------------

class FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        n = len(self.parent.invoke_calls)
        if n > len(self.parent.plan_replies):
            raise AssertionError(f"planner called {n} times; only {len(self.parent.plan_replies)} scripted")
        return self.parent.plan_replies[n - 1]


class FakeLLM:
    """plan_replies: one reply per planner call, in order (a call past the script raises).
    probe: list that on_token appends to; its length is recorded when stream starts."""

    def __init__(self, plan_replies=(), pieces=("Answer.",)):
        self.plan_replies = list(plan_replies)
        self.pieces = list(pieces)
        self.bind_calls = []
        self.invoke_calls = []
        self.stream_calls = []
        self.probe = None
        self.tokens_at_stream = []

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        if self.probe is not None:
            self.tokens_at_stream.append(len(self.probe))
        return (AIMessageChunk(content=p) for p in self.pieces)


class FakeStore:
    """Satisfies DocumentStore. results maps a query to the chunks it returns (default: none)."""

    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        return list(self.results.get(query, []))


class FakeRunner:
    def __init__(self, status="ok", text=""):
        self.status = status
        self.text = text
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        return ToolOutput(self.status, self.text)


class FoodRunner:
    """A ToolRunner for calculate_food_item built from run_food_tool(args, rules); records its calls."""

    def __init__(self, rules):
        self.rules = rules
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        result = run_food_tool(args, self.rules)
        return ToolOutput(result.status, result.text)


def ai(*calls, content=""):
    return AIMessage(content=content,
                     tool_calls=[{"name": n, "args": a, "id": f"call_{i}"} for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture(scope="session")
def mk():
    return SimpleNamespace(ai=ai)


@pytest.fixture(scope="session")
def doc():
    return lambda text, source: Document(page_content=text, metadata={"source": source})


@pytest.fixture(scope="session")
def make_llm():
    return FakeLLM


@pytest.fixture(scope="session")
def make_store():
    return FakeStore


@pytest.fixture(scope="session")
def make_runner():
    return FakeRunner


@pytest.fixture(scope="session")
def text_of():
    return lambda messages: "\n".join(str(m.content) for m in messages)


# --------------------------------------------------------------------------
# Rules and the real-rules food runner
# --------------------------------------------------------------------------

@pytest.fixture
def rules_path(tmp_path):
    """Appendix A written to tmp_path/food.json."""
    p = tmp_path / "food.json"
    p.write_text(json.dumps(copy.deepcopy(APPENDIX_A)), encoding="utf-8")
    return p


@pytest.fixture
def rules(rules_path):
    return load_food_rules(rules_path)


@pytest.fixture
def food_runner(rules):
    return FoodRunner(rules)


@pytest.fixture
def point_rules_file_at(monkeypatch):
    """point_rules_file_at(path): patch FOOD_RULES_FILE in blc.tools.food_tools* and blc.flow* modules."""
    def _point(path):
        for name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            if (name.startswith("blc.tools.food_tools") or name.startswith("blc.flow")) \
                    and hasattr(mod, "FOOD_RULES_FILE"):
                monkeypatch.setattr(mod, "FOOD_RULES_FILE", path)
        return path
    return _point


# --------------------------------------------------------------------------
# Run one planned turn with scripted plans
# --------------------------------------------------------------------------

@pytest.fixture
def run(food_runner):
    """run(question, plans, history=None, docs=None, runners=None, pieces=...) -> namespace.

    plans: a list with one entry per scripted planner reply; each entry is a list of (name, args).
    runners: None gives the real-rules food runner plus ok fakes for the other two tools."""

    def _run(question, plans, history=None, docs=None, runners=None, pieces=("Answer.",)):
        from blc.flow import run_planned_turn

        llm = FakeLLM([ai(*p) for p in plans], pieces)
        store = FakeStore(docs)
        if runners is None:
            runners = {BEV: FakeRunner("ok", "BEV TEXT"), REC: FakeRunner("ok", "RECIPE TEXT"), FOOD: food_runner}
        tokens = []
        llm.probe = tokens
        outcome = run_planned_turn(llm, store, question, history, tool_runners=runners, on_token=tokens.append)
        return SimpleNamespace(outcome=outcome, llm=llm, store=store, runners=runners, tokens=tokens)

    return _run


# --------------------------------------------------------------------------
# Eval environment: skip, do not fail
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
        pytest.skip("Ollama is not running; start it to run the food wiring eval.")
    return True


@pytest.fixture(scope="session")
def eval_store(ollama_available):
    """build_domain_store() (spec 027); skips when .chroma/ is missing."""
    from chat import CHROMA_DIR, build_domain_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run scripts/ingest.py first.")
    return build_domain_store()


@pytest.fixture(scope="session")
def eval_llm(ollama_available):
    """The real chat model, warmed up once."""
    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL, CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")
    return llm
