"""Shared fakes and fixtures for spec 046 (planner prompt restructure).

Unit tests: a scripted fake chat model, no network. Eval fixtures skip (do not fail) when keys or .chroma/ are
missing.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage


class FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        return self.parent.reply


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.invoke_calls = []

    def bind_tools(self, tools, *args, **kwargs):
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")


@pytest.fixture
def make_llm():
    def _make(name="search_documents", args=None):
        args = {"query": "where is the coffee"} if args is None else args
        reply = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call_1"}])
        return FakeLLM(reply)
    return _make


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
