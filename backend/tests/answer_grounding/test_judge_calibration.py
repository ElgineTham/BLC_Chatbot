"""Spec 017 AC-3b: judge calibration with the real model (J1 to J10 with their path; revision 2: at least 9 of 10
must match, every miss is listed).

Marked eval; skips (does not fail) when Ollama, the store or data/recipes/recipes.json is missing (NFR-3).
Spec 004's own C1 to C35 (path=None) are not required by this spec (revision 1).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def _describe(j_case, result):
    return (
        f"{j_case['id']} ({j_case['path']}): expected {'PASS' if j_case['expected'] else 'FAIL'}, "
        f"got {'PASS' if result.passed else 'FAIL'}. Answer: {j_case['answer']!r}. Reason: {result.reason!r}"
    )


def test_j_case_report(j_cases, j_results, j_misses, capsys):
    """Covers: AC-3b (right/wrong). Every J case that gave the wrong verdict is listed in the output (id, path, verdict, reason)."""
    lines = []
    for c in j_cases:
        r = j_results[c["id"]]
        if c["id"] in j_misses:
            lines.append("MISS " + (f"{c['id']}: judge raised {r!r}" if isinstance(r, Exception) else _describe(c, r)))
    with capsys.disabled():
        print("\nJudge calibration misses: " + (str(len(lines)) if lines else "none"))
        for line in lines:
            print("  " + line)
    assert len(lines) == len(j_misses)


def test_calibration_at_least_nine_of_ten(j_misses):
    """Covers: AC-3b (right/wrong/boundary). At least 9 of J1 to J10 give the expected verdict with their path; the failure message lists every miss."""
    assert len(j_misses) <= 1, "Judge calibration below 9 of 10. Missed: " + ", ".join(j_misses)


def test_all_ten_j_cases_present(j_results):
    """Covers: AC-3b (boundary). Calibration covers J1 to J10 exactly once."""
    assert sorted(j_results, key=lambda s: int(s[1:])) == [f"J{i}" for i in range(1, 11)]


def test_calibration_gate_names_failed_ids(calibration_failures, j_misses):
    """Covers: AC-3b, section 4.5 (right/wrong). Grading goes ahead with at most one miss; with two or more
    the gate stops the A, D and M cases and names the failed J ids."""
    if len(j_misses) <= 1:
        assert calibration_failures == []
    else:
        assert calibration_failures == j_misses
        pytest.fail("Judge failed calibration, answers not graded. Failed: " + ", ".join(calibration_failures))
