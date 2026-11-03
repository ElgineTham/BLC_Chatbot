"""Generation eval against evals/retrieval/golden.jsonl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from langchain_ollama import ChatOllama

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GOLDEN_PATH = ROOT / "evals" / "retrieval" / "golden.jsonl"

sys.path.insert(0, str(SCRIPTS))

from chat import (  # noqa: E402
    CHAT_MODEL,
    CHROMA_DIR,
    answer_from_context,
    build_store,
    retrieve,
    unknown_retrieval_reply,
)

# Substrings that signal an abstain / "I don't know" reply.
ABSTAIN_MARKERS = (
    "don't know",
    "do not know",
    "dont know",
    "rephras",
    "no recipe",
)


def load_golden_cases() -> list[dict]:
    cases: list[dict] = []
    with GOLDEN_PATH.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            case = json.loads(text)
            case["_line"] = line_no
            cases.append(case)
    return cases


GOLDEN_CASES = load_golden_cases()


def normalize(text: str) -> str:
    return text.casefold()


def missing_substrings(answer: str, required: list[str]) -> list[str]:
    lowered = normalize(answer)
    return [item for item in required if normalize(item) not in lowered]


def forbidden_hits(answer: str, forbidden: list[str]) -> list[str]:
    lowered = normalize(answer)
    return [item for item in forbidden if normalize(item) in lowered]


def has_abstain_signal(answer: str) -> bool:
    lowered = normalize(answer)
    return any(marker in lowered for marker in ABSTAIN_MARKERS)


def generate_answer(store, llm: ChatOllama, question: str) -> str:
    """Single-turn generation: retrieve, then answer with empty history."""
    docs = retrieve(store, question)
    if not docs:
        return unknown_retrieval_reply()
    return answer_from_context(llm, history=[], docs=docs, question=question)


@pytest.fixture(scope="module")
def store():
    if not CHROMA_DIR.exists():
        pytest.skip(
            f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py first."
        )
    return build_store()


@pytest.fixture(scope="module")
def llm():
    return ChatOllama(model=CHAT_MODEL, temperature=0)


@pytest.mark.parametrize(
    "case",
    GOLDEN_CASES,
    ids=[c["id"] for c in GOLDEN_CASES],
)
def test_generation_against_golden(store, llm: ChatOllama, case: dict) -> None:
    """Answer must hit required phrases, avoid forbidden ones, and abstain when labeled."""
    answer = generate_answer(store, llm, case["question"])
    case_id = case["id"]

    assert answer.strip(), f"{case_id}: empty generation"

    missing = missing_substrings(answer, case.get("must_include") or [])
    assert not missing, (
        f"{case_id}: missing required phrase(s) {missing}. Answer: {answer!r}"
    )

    hits = forbidden_hits(answer, case.get("must_not_include") or [])
    assert not hits, (
        f"{case_id}: forbidden phrase(s) present {hits}. Answer: {answer!r}"
    )

    if case.get("expect_abstain"):
        assert has_abstain_signal(answer), (
            f"{case_id}: expected abstain signal "
            f"(one of {ABSTAIN_MARKERS}). Answer: {answer!r}"
        )
