"""CAL-1 to CAL-6 (AC-2): the judge gate. Eval; real judge (llm=None), Ollama required."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def test_calibration_case_gets_expected_verdict(cal_case, calibration_results):
    """Covers: CAL-1..CAL-6, AC-2 (right for pass cases, wrong for fail cases). Verdict equals the expected one."""
    res = calibration_results[cal_case["id"]]
    assert not isinstance(res, Exception), f"{cal_case['id']}: judge raised {res!r}"
    assert res.passed == cal_case["expected"], (
        f"{cal_case['id']}: expected passed={cal_case['expected']}, got {res.passed}. "
        f"Reason: {res.reason!r}. Answer: {cal_case['answer']!r}"
    )
