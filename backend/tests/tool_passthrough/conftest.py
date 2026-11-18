"""Shared fakes and helpers for the spec 023 tests (tool results go to the user word for word).

Unit tests: no Ollama, no Chroma, no network, nothing read under data/.
Everything is exposed as fixtures or module constants of fixtures, so test files do not import from conftest.

- run            run one turn with scripted fakes; returns a namespace (outcome, llm, store, tokens, events)
- doc            build a Document with a source path
- make_runner    fake tool runner that records its calls
- make_llm       fake model class (planner + answerer)
"""
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
H = "Hot cups: 60 for 40 guests (40 guests plus 20 extras)."


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
    """plan_replies: one reply per planner call. stream records the call in events."""

    def __init__(self, plan_replies=(), pieces=("Answer.",)):
        self.plan_replies = list(plan_replies)
        self.pieces = list(pieces)
        self.bind_calls = []
        self.invoke_calls = []
        self.stream_calls = []
        self.events = None

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        if self.events is not None:
            self.events.append(("stream", None))
        return self._gen()

    def _gen(self):
        for piece in self.pieces:
            yield AIMessageChunk(content=piece)


class FakeStore:
    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        return list(self.results.get(query, []))


class FakeRunner:
    def __init__(self, status="ok", text="", raises=None):
        self.status = status
        self.text = text
        self.raises = raises
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        if self.raises is not None:
            raise self.raises
        return ToolOutput(self.status, self.text)


class SeqRunner:
    """Fake ToolRunner that returns (status, text) pairs in order, one per call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        status, text = self.results[len(self.calls) - 1]
        return ToolOutput(status, text)


@pytest.fixture(scope="session")
def make_seq_runner():
    return SeqRunner


def _plan(*calls):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"call_{i}"}
                                             for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture(scope="session")
def doc():
    def _doc(text, source):
        return Document(page_content=text, metadata={"source": source})
    return _doc


@pytest.fixture(scope="session")
def make_runner():
    return FakeRunner


@pytest.fixture(scope="session")
def make_llm():
    return FakeLLM


@pytest.fixture(scope="session")
def text_of():
    def _text(messages):
        return "\n".join(str(m.content) for m in messages)
    return _text


_DEFAULT = object()


@pytest.fixture
def run():
    """Run one turn.

    plans: list of call lists, one per planner call, each a list of (name, args). A bare list of
    (name, args) pairs is taken as a single plan.
    runners: dict of tool name to FakeRunner.
    docs: dict of query to chunks.
    on_token: recording by default; None for no callback.
    """

    def _run(question, plans=(), *, pieces=("Answer.",), docs=None, runners=None, history=None,
             on_token=_DEFAULT):
        from blc.flow import run_planned_turn

        plans = list(plans)
        if plans and isinstance(plans[0], tuple):
            plans = [plans]
        if not plans:
            plans = [[]]
        llm = FakeLLM([_plan(*p) for p in plans], pieces)
        store = FakeStore(docs)
        if runners is None:
            runners = {BEV: FakeRunner("ok", H), REC: FakeRunner("ok", "B")}
        events = []
        llm.events = events
        tokens = []

        def record(piece):
            tokens.append(piece)
            events.append(("token", piece))

        kwargs = {}
        if on_token is _DEFAULT:
            kwargs["on_token"] = record
        elif on_token is not None:
            kwargs["on_token"] = on_token
        outcome = run_planned_turn(llm, store, question, history, tool_runners=runners, **kwargs)
        return SimpleNamespace(outcome=outcome, llm=llm, store=store, runners=runners,
                               tokens=tokens, events=events)

    return _run
