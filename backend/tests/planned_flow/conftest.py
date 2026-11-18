"""Shared fakes and helpers for the planned-flow tests (spec 019).

Unit tests: no Ollama, no Chroma, no network, nothing read under data/.
Tests never use DEFAULT_TOOL_RUNNERS to run a turn (that would read data/); they pass fakes.

Exposed as fixtures (so no test imports from conftest):
- mk            reply builders for the planner (mk.ai, mk.raw)
- doc           build a Document with a source path
- make_runner   fake tool runner that records its calls
- text_of       join the text of a list of messages
- run           run one turn with scripted fakes; returns a namespace with the outcome and the fakes
- eval_cases    spec 018's 30 cases (id, question, history)
- ollama_available / real_store / real_llm   (eval only) skip when Ollama or the store is missing
"""
import urllib.request
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


# --------------------------------------------------------------------------
# Scripted fake model: plays the planner (bind_tools + invoke) and the answerer (stream)
# --------------------------------------------------------------------------

class FakeBound:
    """What bind_tools returns: it can invoke, and it deliberately cannot stream."""

    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        if self.parent.plan_raises is not None:
            raise self.parent.plan_raises
        return self.parent.plan_reply


class FakeLLM:
    def __init__(self, plan_reply=None, pieces=(), plan_raises=None, stream_raises=None):
        self.plan_reply = plan_reply
        self.pieces = list(pieces)
        self.plan_raises = plan_raises
        self.stream_raises = stream_raises
        self.bind_calls = []
        self.invoke_calls = []      # messages sent to the bound model (the planner call)
        self.stream_calls = []      # messages sent to stream (the answer call)
        self.probe = None           # list that on_token appends to
        self.tokens_seen_before_piece = []

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):  # the unbound model must never be invoked
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        if self.stream_raises is not None:
            raise self.stream_raises
        return self._gen()

    def _gen(self):
        for i, piece in enumerate(self.pieces):
            if self.probe is not None:
                self.tokens_seen_before_piece.append(len(self.probe))
            yield AIMessageChunk(content=piece)


class FakeStore:
    """Satisfies DocumentStore. results maps a query to the chunks it returns (default: none)."""

    def __init__(self, results=None, raises=None):
        self.results = dict(results or {})
        self.raises = raises
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        if self.raises is not None:
            raise self.raises
        return list(self.results.get(query, []))


class FakeRunner:
    """Fake ToolRunner: records the args it was called with."""

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


def _tc(name, args, idx):
    return {"name": name, "args": args, "id": f"call_{idx}"}


def ai(*calls, content=""):
    """AIMessage with the given (name, args) tool calls."""
    return AIMessage(content=content, tool_calls=[_tc(n, a, i) for i, (n, a) in enumerate(calls, 1)])


def raw(*calls, content=""):
    return SimpleNamespace(content=content, tool_calls=[_tc(n, a, i) for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture(scope="session")
def mk():
    return SimpleNamespace(ai=ai, raw=raw)


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
def make_store():
    return FakeStore


@pytest.fixture(scope="session")
def text_of():
    def _text(messages):
        return "\n".join(str(m.content) for m in messages)
    return _text


_DEFAULT = object()


@pytest.fixture
def run():
    """Run one turn with scripted fakes.

    calls: (name, args) pairs the planner returns. plan_reply overrides the whole reply.
    runners: None gives an ok fake for each tool; or pass a dict of runners.
    on_token: by default a recording list is used; pass None to call without a callback.
    """

    def _run(question, calls=(), *, pieces=("Answer.",), docs=None, runners=None, history=None,
             on_token=_DEFAULT, separate_planner=False, plan_reply=None, store_raises=None):
        from blc.flow import run_planned_turn

        reply = plan_reply if plan_reply is not None else ai(*calls)
        if separate_planner:
            planner = FakeLLM(plan_reply=reply)
            llm = FakeLLM(pieces=pieces)
        else:
            planner = None
            llm = FakeLLM(reply, pieces)
        store = FakeStore(docs, raises=store_raises)
        if runners is None:
            runners = {BEV: FakeRunner("ok", "BEV TEXT"), REC: FakeRunner("ok", "RECIPE TEXT")}
        tokens = []
        llm.probe = tokens
        kwargs = {}
        if on_token is _DEFAULT:
            kwargs["on_token"] = tokens.append
        elif on_token is not None:
            kwargs["on_token"] = on_token
        if separate_planner:
            kwargs["planner_llm"] = planner
        outcome = run_planned_turn(llm, store, question, history, tool_runners=runners, **kwargs)
        return SimpleNamespace(outcome=outcome, llm=llm, planner=planner, store=store,
                               runners=runners, tokens=tokens)

    return _run


# --------------------------------------------------------------------------
# The 30 eval cases of spec 018 (id, question, history)
# --------------------------------------------------------------------------

_ASK = "How many gallons of each drink, or how many guests?"
_H_CIDER = [{"role": "user", "content": "How many cambros do I need for brewed hot cider?"},
            {"role": "assistant", "content": _ASK}]
_H_EACH = [{"role": "user", "content": "How many cambros for coffee and decaf?"},
           {"role": "assistant", "content": _ASK}]
_H_THREE = [{"role": "user", "content": "How many cambros for coffee, iced water, and hot water?"},
            {"role": "assistant", "content": _ASK}]
_H_SYRUP = [{"role": "user", "content": "Where are the syrups?"},
            {"role": "assistant", "content": "Above the lemons in the beverage cooler, near the sink by the coffee machine (data/supplies/syrups.md)."}]
_H_LEMON = [{"role": "user", "content": "How do I make 2 gallons of lemonade?"},
            {"role": "assistant", "content": "Use 14 oz of lemon concentrate and fill with water to 2 gallons."}]

_CASES = [
    ("T1", "How many cambros do I need for 7 gallons of peach tea and 3 gallons of hot water?", None),
    ("T2", "How many gallons of coffee should I make for 160 guests?", None),
    ("T3", "How many cups for 45 guests?", None),
    ("T4", "What goes on the pull sheet for 6 gallons of orange juice?", None),
    ("T5", "How many cups for iced tea and lemonade for 90 guests?", None),
    ("T6", "How do I make lemonade?", None),
    ("T7", "How do I make lemonade for 60 guests?", None),
    ("T8", "How do I make 4 gallons of lemonade and how many cambros do I need for it?", None),
    ("T9", "For 75 guests.", _H_CIDER),
    ("T10", "5 gallons each.", _H_EACH),
    ("D1", "What supplies do I need for coffee and hot water?", None),
    ("D2", "Should I bring lemons for the iced tea?", None),
    ("D3", "Where do the 5 gallon cambros go?", None),
    ("D4", "Is lemonade served in a cambro?", None),
    ("D5", "What flavors of syrup do we have?", None),
    ("D6", "Never mind that. What do I need to bring for them?", _H_THREE),
    ("D7", "What's in the coffee, decaf, tea, iced water & juice package?", None),
    ("D8", "How do I pull stock of concentrates?", None),
    ("D9", "When do we bring hot cups?", None),
    ("D10", "What if there are none there?", _H_SYRUP),
    ("M1", "Where are the cambros kept and how many do I need for 6 gallons of iced tea?", None),
    ("M2", "How many cups for coffee for 80 guests, and where are the hot cups stored?", None),
    ("M3", "Where is the lemon concentrate, and how much do I need for 3 gallons of lemonade?", None),
    ("M4", "How many cambros for 4 gallons of decaf, and where is the oatmilk?", None),
    ("M5", "How many cambros to bring for 3 gallons of coffee and what stuffs do I need to bring", None),
    ("M6", "What flavors of concentrate do we have, and how do I make 5 gallons of lemonade?", None),
    ("M7", "Is iced tea served in a cambro, and how many gallons of iced tea do I make for 120 guests?", None),
    ("M8", "How many cups for peach tea for 40 guests, and do we bring lemons for it?", None),
    ("M9", "Where do the 5 gallon cambros go, and how many cambros do I need for 12 gallons of orange juice?", None),
    ("M10", "Where is the concentrate kept, and how much do I need for 6 gallons instead?", _H_LEMON),
]


@pytest.fixture(scope="session")
def eval_cases():
    """The 30 cases as a list of {"id", "question", "history"}."""
    return [{"id": i, "question": q, "history": h} for i, q, h in _CASES]


# --------------------------------------------------------------------------
# Eval environment (NFR-3: skip, do not fail)
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ollama_available():
    """Name kept for the dependent fixtures. Spec 037: the chat model and embeddings run on Gemini, so this
    skips when GOOGLE_API_KEY is unset (Ollama is no longer needed here)."""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set; set it to run the planned-flow eval.")
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is not set; the chat model runs on Claude (spec 039).")
    return True


@pytest.fixture(scope="session")
def real_store(ollama_available):
    """The real Chroma store; skips when it is missing or empty."""
    from pathlib import Path

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
    from chat import CHAT_TEMPERATURE, build_chat_model

    llm = build_chat_model(temperature=CHAT_TEMPERATURE)
    llm.invoke("Reply with one word: ready")
    return llm
