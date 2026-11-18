"""AC-2: judge calibration with the real model (all of C1 to C35 must match)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def test_calibration_case(calibration_case, calibration_results):
    """Covers: AC-2 (right/wrong/boundary per case), EC-2/EC-3/EC-4 via C-cases. The real judge returns the expected verdict for this C case (threshold: all cases)."""
    cid = calibration_case["id"]
    result = calibration_results[cid]
    if isinstance(result, Exception):
        pytest.fail(f"{cid}: judge raised {type(result).__name__}: {result}")
    expected = calibration_case["expected"]
    assert result.passed == expected, (
        f"{cid} (for {calibration_case['for']}): expected "
        f"{'PASS' if expected else 'FAIL'}, got "
        f"{'PASS' if result.passed else 'FAIL'}. "
        f"Answer: {calibration_case['answer']!r}. Reason: {result.reason!r}"
    )


def test_all_35_calibration_cases_present(calibration_results):
    """Covers: AC-2 (boundary). Calibration covers every case C1 to C35 exactly once."""
    assert sorted(calibration_results, key=lambda s: int(s[1:])) == [
        f"C{i}" for i in range(1, 36)
    ]
