"""Shared fixtures for spec 047 (linen colours). Unit tests use scripted fake models; no network, no Chroma.

Fixtures: run_tool (run_always_tool wrapper), run (one planned turn with scripted planner replies),
eval_llm / eval_store (eval only; skip when keys or .chroma/ are missing).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from blc.tools.always_tools import AlwaysResult, run_always_tool  # noqa: E402


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
    def __init__(self, plan_replies=(), pieces=("Answer.",)):
        self.plan_replies = list(plan_replies)
        self.pieces = list(pieces)
        self.bind_calls = []
        self.invoke_calls = []
        self.stream_calls = []

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        return (AIMessageChunk(content=p) for p in self.pieces)


class FakeStore:
    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        return list(self.results.get(query, []))


def _ai(*calls):
    return AIMessage(content="",
                     tool_calls=[{"name": n, "args": a, "id": f"call_{i}"} for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture
def run_tool():
    """run_always_tool wrapper that also checks the return type."""

    def _run(args):
        result = run_always_tool(args)
        assert isinstance(result, AlwaysResult)
        return result

    return _run


@pytest.fixture
def run():
    """run(question, plans, history=None) -> namespace(outcome, llm). plans: one list of (name, args) per
    scripted planner reply. Uses the default tool runners."""

    def _run(question, plans, history=None):
        from blc.flow import DEFAULT_TOOL_RUNNERS, run_planned_turn

        llm = FakeLLM([_ai(*p) for p in plans])
        tokens = []
        outcome = run_planned_turn(llm, FakeStore(), question, history, tool_runners=DEFAULT_TOOL_RUNNERS,
                                   on_token=tokens.append)
        return SimpleNamespace(outcome=outcome, llm=llm)

    return _run


@pytest.fixture(scope="session")
def eval_ready():
    import os

    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is not set; the chat model runs on Claude.")
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set; embeddings run on Gemini.")
    return True


@pytest.fixture(scope="session")
def eval_store(eval_ready):
    from chat import CHROMA_DIR, build_domain_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run ingest.py first.")
    return build_domain_store()


@pytest.fixture(scope="session")
def eval_llm(eval_ready):
    from chat import CHAT_TEMPERATURE, build_chat_model

    llm = build_chat_model(temperature=CHAT_TEMPERATURE)
    llm.invoke("Reply with one word: ready")
    return llm
