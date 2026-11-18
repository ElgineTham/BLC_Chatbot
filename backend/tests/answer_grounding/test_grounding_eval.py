"""Spec 017 AC-5 to AC-8: the grounded-answer eval with the real model, store and tools (A1-A10, D1-D10, M1-M10).

Marked eval; skips (does not fail) when Ollama is not running, the store is empty or missing, or
data/recipes/recipes.json is missing (NFR-3). Both models are warmed up once by the `grounding_env` fixture.
Each case runs `run_turn(store, llm, history, question, generate=True)` once; the tests share the results.
The judge must pass calibration (J1-J10) first: otherwise no case is graded and each fails naming the J ids (section 4.5).
Read only: nothing is written to data/ or .chroma/. The scorer is the unit-tested one from conftest.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval

THRESHOLD = 9
GROUPS = (("TOOL", "A"), ("DOCS", "D"), ("BOTH", "M"))


def _real_judge(question, reference, answer, path=None):
    from blc.judge import Verdict, judge_answer

    try:
        return judge_answer(question, reference, answer, path=path)
    except Exception as exc:  # a judge error is a failed judge stage, not a crashed run
        return Verdict(passed=False, reason=f"judge raised {exc!r}")


def _run_all(env, score_case, cases, failed_calibration):
    """Run every case once; cache {path: rows} on env. A row is (case, trace or None, Score, error)."""
    if env.results is not None:
        return env.results
    from types import SimpleNamespace

    results = {"TOOL": [], "DOCS": [], "BOTH": []}
    for case in cases:
        trace, error = None, ""
        if failed_calibration:
            score = score_case(None, case, _real_judge, failed_calibration=tuple(failed_calibration))
        else:
            try:
                trace = env.chat.run_turn(env.store, env.llm, list(case["history"]), case["question"], generate=True)
                score = score_case(trace, case, _real_judge)
            except Exception as exc:  # a crash is a failed case
                error = f"run_turn raised {exc!r}"
                score = SimpleNamespace(passed=False, stages=("route",), detail=error, ungrounded=(), unknown=())
        results[case["path"]].append((case, trace, score))
    env.results = results
    return results


def _line(case, trace, score):
    actual = trace.route.kind if trace is not None and trace.route is not None else "-"
    reply = (trace.reply if trace is not None else None) or ""
    return (
        f"{case['id']}: expected={case['path']} actual={actual} {'PASS' if score.passed else 'FAIL'} "
        f"stages={list(score.stages)} judge={score.detail!r} ungrounded={list(score.ungrounded)} "
        f"unknown={list(score.unknown)} reply={reply!r}"
    )


def _check(rows, tag, failed_calibration):
    if failed_calibration:
        pytest.fail("Judge failed calibration, answers not graded. Failed J ids: " + ", ".join(failed_calibration), pytrace=False)
    for case, trace, score in rows:
        print(_line(case, trace, score))
    passed = sum(1 for _, _, s in rows if s.passed)
    print(f"{tag}: passed {passed} of {len(rows)}")
    assert len(rows) == 10
    assert passed >= THRESHOLD, (
        f"only {passed} of 10 passed: "
        + str([(c["id"], s.stages, s.ungrounded, s.unknown) for c, _, s in rows if not s.passed])
    )


@pytest.fixture
def results(grounding_env, score_case, cases, calibration_failures):
    return _run_all(grounding_env, score_case, cases, calibration_failures)


def test_tool_path_grounding(results, calibration_failures):
    """Covers: AC-5 (right/wrong per case A1-A10), AC-8. At least 9 of 10 TOOL cases pass (graded only after AC-3b passes); one line is printed per case."""
    _check(results["TOOL"], "TOOL", calibration_failures)


def test_docs_path_grounding(results, calibration_failures):
    """Covers: AC-6 (right/wrong per case D1-D10), AC-8. At least 9 of 10 DOCS cases pass; one line is printed per case."""
    _check(results["DOCS"], "DOCS", calibration_failures)


def test_both_path_grounding(results, calibration_failures):
    """Covers: AC-7 (right/wrong per case M1-M10), AC-8. At least 9 of 10 BOTH cases pass; one line is printed per case."""
    _check(results["BOTH"], "BOTH", calibration_failures)


def test_report_summary(results, calibration_failures):
    """Covers: AC-8. The report ends with the pass count per path; every failed stage is one of route, judge, numbers, sources."""
    if calibration_failures:
        pytest.fail("Judge failed calibration, answers not graded. Failed J ids: " + ", ".join(calibration_failures), pytrace=False)
    parts = []
    for path, letter in GROUPS:
        rows = results[path]
        assert all(c["id"].startswith(letter) for c, _, _ in rows)
        parts.append(f"{path}: passed {sum(1 for _, _, s in rows if s.passed)} of {len(rows)}")
        for case, _, score in rows:
            assert set(score.stages) <= {"route", "judge", "numbers", "sources"}, f"{case['id']}: {score.stages}"
    print("SUMMARY " + " | ".join(parts))
    assert len(parts) == 3
