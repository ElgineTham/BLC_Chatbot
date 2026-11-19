"""Shared fakes and fixtures for spec 043 (serving utensils wiring).

Unit tests: scripted fake models, fake store, a serving runner built from run_serv_tool(args, rules) with the
spec 042 Appendix A rules written to tmp_path. No Chroma, no network, nothing read under data/.
Plain data and pure functions (cases, scorer, log writer) live in serv_wiring_helpers.py.

Fixtures: mk, doc, make_llm, make_store, make_runner, text_of (fakes and builders); rules_path, rules,
serv_runner (Appendix A); point_rules_file_at (patch SERV_RULES_FILE where bound); run (one planned turn);
eval_ready / eval_llm / eval_store (eval only; skip when keys, .chroma/ or the real rules file are missing).
"""
from __future__ import annotations

import copy
import json
import sys
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

from blc.tools.serv_tools import load_serv_rules, run_serv_tool  # noqa: E402
from serv_wiring_helpers import APPENDIX_A, BEV, FOOD, REC, SERV  # noqa: E402


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


class ServRunner:
    """A ToolRunner for calculate_serving_utensils built from run_serv_tool(args, rules); records its calls."""

    def __init__(self, rules):
        self.rules = rules
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        result = run_serv_tool(args, rules=self.rules)
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
# Rules (Appendix A in tmp_path) and the serving runner
# --------------------------------------------------------------------------

@pytest.fixture
def rules_path(tmp_path):
    """Appendix A written to tmp_path/serv.json."""
    p = tmp_path / "serv.json"
    p.write_text(json.dumps(copy.deepcopy(APPENDIX_A)), encoding="utf-8")
    return p


@pytest.fixture
def rules(rules_path):
    return load_serv_rules(rules_path)


@pytest.fixture
def serv_runner(rules):
    return ServRunner(rules)


@pytest.fixture
def point_rules_file_at(monkeypatch):
    """point_rules_file_at(path): patch SERV_RULES_FILE in every blc.tools.serv_tools* and blc.flow* module
    that binds it."""
    def _point(path):
        for name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            if (name.startswith("blc.tools.serv_tools") or name.startswith("blc.flow")) \
                    and hasattr(mod, "SERV_RULES_FILE"):
                monkeypatch.setattr(mod, "SERV_RULES_FILE", path)
        return path
    return _point


# --------------------------------------------------------------------------
# Run one planned turn with scripted plans
# --------------------------------------------------------------------------

@pytest.fixture
def run(serv_runner):
    """run(question, plans, history=None, docs=None, runners=None, pieces=...) -> namespace.

    plans: one entry per scripted planner reply; each entry is a list of (name, args).
    runners: None gives the Appendix A serving runner plus ok fakes for the other three tools."""

    def _run(question, plans, history=None, docs=None, runners=None, pieces=("Answer.",)):
        from blc.flow import run_planned_turn

        llm = FakeLLM([ai(*p) for p in plans], pieces)
        store = FakeStore(docs)
        if runners is None:
            runners = {BEV: FakeRunner("ok", "BEV TEXT"), REC: FakeRunner("ok", "RECIPE TEXT"),
                       FOOD: FakeRunner("ok", "FOOD TEXT"), SERV: serv_runner}
        tokens = []
        llm.probe = tokens
        outcome = run_planned_turn(llm, store, question, history, tool_runners=runners, on_token=tokens.append)
        return SimpleNamespace(outcome=outcome, llm=llm, store=store, runners=runners, tokens=tokens)

    return _run


# --------------------------------------------------------------------------
# Eval environment: skip, do not fail
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def eval_ready():
    """Skips unless ANTHROPIC_API_KEY and GOOGLE_API_KEY are set and the real rules file exists."""
    import os

    from dotenv import load_dotenv

    from blc.tools.serv_tools import SERV_RULES_FILE

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is not set; the chat model runs on Claude.")
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set; embeddings run on Gemini.")
    if not Path(SERV_RULES_FILE).exists():
        pytest.skip(f"Real serving utensils rules not found at {SERV_RULES_FILE}.")
    return True


@pytest.fixture(scope="session")
def eval_store(eval_ready):
    """build_domain_store() from chat.py; skips when .chroma/ is missing."""
    from chat import CHROMA_DIR, build_domain_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run ingest.py first.")
    return build_domain_store()


@pytest.fixture(scope="session")
def eval_llm(eval_ready):
    """The real chat model, warmed up once."""
    from chat import CHAT_TEMPERATURE, build_chat_model

    llm = build_chat_model(temperature=CHAT_TEMPERATURE)
    llm.invoke("Reply with one word: ready")
    return llm
