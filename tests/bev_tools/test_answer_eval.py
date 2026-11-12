"""AC-11 (answer eval) and AC-12 (no leaked instructions): cases T1 to T23.

Marked eval; skips (does not fail) when Ollama is not running or the knowledge files are not in
the store (NFR-4). Read only: nothing is written to .chroma/ or data/.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval

LEAK_WORDS = ("calculate_bev_item", "tool", "instruction", "json", '"item"', "argument")


def test_answer_case(store, chat_llm, eval_case):
    """Covers: AC-11 (right/wrong per case), AC-12 (wrong), NFR-4 (skip). judge_answer passes the reply and the reply leaks no tool or instruction wording."""
    from blc.judge import judge_answer
    from chat import run_turn

    question = eval_case["question"]
    out = run_turn(store, chat_llm, eval_case["history"], question)  # spec 014: the real flow
    calls = [c for stage in out.tools for c in stage.calls]
    retried = any(stage.retried for stage in out.tools)
    verdict = judge_answer(question, eval_case["reference"], out.reply)
    context = (
        f"{eval_case['id']}: Reply: {out.reply!r}. "
        f"Tool calls: {[(c.name, c.args) for c in calls]}. Retried: {retried}"
    )
    assert verdict.passed, f"judge FAIL. Reason: {verdict.reason!r}. {context}"

    folded = out.reply.casefold()
    leaked = [w for w in LEAK_WORDS if w in folded]
    assert not leaked, f"reply leaks {leaked}. {context}"
