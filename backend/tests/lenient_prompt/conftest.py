"""Shared fakes for the spec 038 tests (lenient answer prompt). Unit: no Ollama, no Chroma, no network."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

SEARCH = "search_documents"
GOLDEN_PATH = Path(__file__).resolve().parents[3] / "evals" / "answers" / "food_answers.jsonl"


class FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        return self.parent.plan_reply


class FakeLLM:
    def __init__(self, plan_reply, pieces):
        self.plan_reply = plan_reply
        self.pieces = list(pieces)
        self.invoke_calls = []
        self.stream_calls = []

    def bind_tools(self, tools, *args, **kwargs):
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        return iter([AIMessageChunk(content=p) for p in self.pieces])


class FakeStore:
    def __init__(self, results):
        self.results = dict(results)

    def similarity_search(self, query, k):
        return list(self.results.get(query, []))


@pytest.fixture
def run_search_turn():
    """Run one planned turn: a single search 'x'. docs maps the query to Documents."""

    def _run(question="Do we need creamer for hot tea?", docs=None, pieces=("No.",)):
        from blc.flow import run_planned_turn

        plan = AIMessage(content="", tool_calls=[{"name": SEARCH, "args": {"query": "x"}, "id": "call_1"}])
        llm = FakeLLM(plan, pieces)
        if docs is None:
            docs = {"x": [Document(page_content="Creamer is for coffee.", metadata={"source": "data/a.md"})]}
        store = FakeStore(docs)
        outcome = run_planned_turn(llm, store, question, None, tool_runners={})
        return SimpleNamespace(outcome=outcome, llm=llm)

    return _run


@pytest.fixture(scope="module")
def golden():
    cases = []
    with GOLDEN_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(json.loads(line))
    return cases
