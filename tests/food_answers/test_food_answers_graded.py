"""ANS-1..19, CONV-1..4, RATE-1..3 (AC-3, AC-4, AC-5, AC-6): graded answers from the real flow.

Eval; needs Ollama, qwen2.5:7b, the judge model and an ingested food.md (skips otherwise, AC-7).
Only the pass rate (AC-3) and the must_pass turns (AC-4) are asserted; per-case tests exist so
each case id shows in the run output (AC-6). If the judge gate fails, the `graded` fixture fails
naming the failed calibration ids (AC-2, RATE-4).
"""

from __future__ import annotations

import pytest

from food_answer_helpers import MIN_PASS_RATE, describe, load_golden

pytestmark = pytest.mark.eval


def test_overall_pass_rate(graded):
    """Covers: RATE-1, AC-3 (boundary), AC-6. Fraction of passing turns is at least MIN_PASS_RATE."""
    rows = [r for turns in graded.values() for r in turns]
    assert rows, "no turns were graded"
    failing = [r for r in rows if not r.passed]
    rate = (len(rows) - len(failing)) / len(rows)
    assert rate >= MIN_PASS_RATE, (
        f"pass rate {rate:.2%} ({len(rows) - len(failing)}/{len(rows)}) is below "
        f"{MIN_PASS_RATE:.0%}. Failing turns:\n{describe(failing)}"
    )


def test_must_pass_turns_all_pass(graded):
    """Covers: RATE-2, ANS-1, ANS-2, CONV-1, AC-4 (right/wrong), AC-6. Every turn of every must_pass case passes."""
    must = [r for turns in graded.values() for r in turns if r.must_pass]
    assert must, "no must_pass turns were graded"
    failing = [r for r in must if not r.passed]
    assert not failing, f"{len(failing)} must_pass turn(s) failed:\n{describe(failing)}"


def test_case_reported(case_id, graded):
    """Covers: ANS-1..ANS-19, CONV-1..CONV-4, AC-3, AC-4, AC-6. One result per case, shown by id in the run.

    Only must_pass cases are asserted here (AC-4); other cases count toward the rate in
    test_overall_pass_rate and their verdicts are printed.
    """
    rows = graded[case_id]
    assert rows, f"{case_id}: no turns graded"
    for r in rows:
        print(f"{r.case_id} turn {r.turn}: {'PASS' if r.passed else 'FAIL'} - {r.reason}")
    if rows[0].must_pass:
        failing = [r for r in rows if not r.passed]
        assert not failing, f"{case_id} is must_pass but failed:\n{describe(failing)}"


def test_graded_turns_match_golden_file(graded):
    """Covers: AC-5 (right), AC-3. Each case was graded with exactly its own turns, in order."""
    for case in load_golden():
        got = [(r.turn, r.question) for r in graded[case["id"]]]
        want = [(n, t["question"]) for n, t in enumerate(case["turns"], start=1)]
        assert got == want, f"{case['id']}: graded turns differ from the golden file"


def test_replies_are_non_empty(graded):
    """Covers: ANS-1..ANS-19, CONV-1..CONV-4 (boundary). The real flow returned a non-blank reply for each turn."""
    blank = [(r.case_id, r.turn) for turns in graded.values() for r in turns if not r.reply.strip()]
    assert not blank, f"blank replies at (case, turn): {blank}"
