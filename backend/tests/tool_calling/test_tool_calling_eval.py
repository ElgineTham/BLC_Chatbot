"""Spec 016 AC-6 to AC-8: the tool-calling eval with the real model and the real store (B1 to B20, R1 to R20).

Marked eval; skips (does not fail) when Ollama is not running, the store is empty or missing, or
data/recipes/recipes.json is missing (NFR-3). The model is warmed up once by the `tool_env` fixture. Each case
runs `run_turn(store, llm, history, question, generate=False)` once, and the three tests share the results.
Read only: nothing is written to data/ or .chroma/. The scorer is the unit-tested one from conftest.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.eval

THRESHOLD = 18


def _run_all(env, score_case, b_cases, r_cases):
    """Run every case once; cache {"B": rows, "R": rows} on env. A row is (case, trace or None, Score)."""
    if env.results is not None:
        return env.results
    from blc.tools.bev_tools import run_bev_tool
    from blc.tools.recipe_tools import run_recipe_tool

    results = {}
    for tag, cases in (("B", b_cases), ("R", r_cases)):
        rows = []
        for case in cases:
            try:
                trace = env.chat.run_turn(env.store, env.llm, list(case["history"]), case["question"], generate=False)
                score = score_case(trace, case, run_bev_tool, run_recipe_tool)
            except Exception as exc:  # a crash is a failed case, not a crashed run
                trace = None
                score = SimpleNamespace(passed=False, stage="router", detail=f"run_turn raised {exc!r}", first_call=False)
            rows.append((case, trace, score))
        results[tag] = rows
    env.results = results
    return results


def _line(case, trace, score):
    status = "PASS" if score.passed else "FAIL"
    stage = score.stage or "-"
    if trace is None or trace.route is None:
        return f"{case['id']}: {status} stage={stage} parts=[] calls=[] {score.detail}"
    parts = [(p.route, p.tool) for p in trace.route.parts]
    calls = [(c.name, c.args, "refused" if c.refused else "ran") for s in trace.tools for c in s.calls]
    return f"{case['id']}: {status} stage={stage} parts={parts} calls={calls}" + (f" [{score.detail}]" if score.detail else "")


def _counts(rows):
    passed = sum(1 for _, _, s in rows if s.passed)
    first = sum(1 for _, _, s in rows if s.passed and s.first_call)
    return passed, first


def _report(tag, rows):
    for case, trace, score in rows:
        print(_line(case, trace, score))
    passed, first = _counts(rows)
    print(f"{tag}: passed {passed} of {len(rows)}; passed on the first call {first} of {len(rows)}")


def _failures(rows):
    return [(c["id"], s.stage, s.detail) for c, _, s in rows if not s.passed]


@pytest.fixture
def results(tool_env, score_case, b_cases, r_cases):
    return _run_all(tool_env, score_case, b_cases, r_cases)


def test_beverage_tool_calling(results):
    """Covers: AC-6 (right/wrong per case B1-B20), AC-8, NFR-3. At least 18 of the 20 calculate_bev_item cases pass (right tool at the router, a call made, right arguments); one line is printed per case."""
    rows = results["B"]
    _report("calculate_bev_item", rows)
    assert len(rows) == 20
    passed, _ = _counts(rows)
    assert passed >= THRESHOLD, f"only {passed} of 20 passed: {_failures(rows)}"


def test_recipe_tool_calling(results):
    """Covers: AC-7 (right/wrong per case R1-R20), AC-8, NFR-3. At least 18 of the 20 scale_recipe cases pass; one line is printed per case."""
    rows = results["R"]
    _report("scale_recipe", rows)
    assert len(rows) == 20
    passed, _ = _counts(rows)
    assert passed >= THRESHOLD, f"only {passed} of 20 passed: {_failures(rows)}"


def test_eval_report_summary(results):
    """Covers: AC-8. The report ends with the pass counts per tool and the first-call pass counts; failures are listed with the stage that caused them (router, no call or arguments)."""
    summary = []
    for tag, name in (("B", "calculate_bev_item"), ("R", "scale_recipe")):
        passed, first = _counts(results[tag])
        summary.append(f"{name}: passed {passed} of 20, first call {first} of 20")
        for cid, stage, detail in _failures(results[tag]):
            assert stage in ("router", "no call", "arguments"), f"{cid}: unknown stage {stage!r}"
    print("SUMMARY " + " | ".join(summary))
    assert len(summary) == 2
