"""AC-3 and AC-5: generation eval graded by the calibrated judge."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def _answer(store, llm, question: str) -> str:
    """Answer pipeline of spec section 3, empty history."""
    from chat import answer_from_context, retrieve, unknown_retrieval_reply

    docs = retrieve(store, question)
    if not docs:
        return unknown_retrieval_reply()
    return answer_from_context(llm, [], docs, question)


def test_generation_case(store, chat_llm, calibrated_judge, generation_case):
    """Covers: AC-5 (right/wrong per case), AC-3 (gate), EC-1 (skip), EC-2, EC-3, EC-4. The calibrated judge passes the chatbot's answer for every A, S and X case; if calibration failed, this case fails naming the failed calibration ids."""
    cid = generation_case["id"]
    answer = _answer(store, chat_llm, generation_case["question"])
    verdict = calibrated_judge(
        generation_case["question"], generation_case["reference"], answer
    )
    assert verdict.passed, (
        f"{cid}: judge FAIL. Reason: {verdict.reason!r}. Answer: {answer!r}"
    )
