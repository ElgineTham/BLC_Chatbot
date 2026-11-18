"""Spec 018, AC-7 to AC-10: the planner eval on 30 questions with the real chat model, one run.

Marked eval; skips (does not fail) when Ollama is not running. Needs no Chroma store
and reads nothing under data/. The model is warmed up once by the planner_llm fixture.

A path passes when it scores at least 9 of 10.
"""
import re
import time

import pytest

from blc.planner import plan_question

pytestmark = pytest.mark.eval

THRESHOLD = 9
PATHS = {"T": "TOOL", "D": "DOCS", "M": "BOTH"}


def _case_line(cid, r):
    status = "FAIL" if r["failed"] else "PASS"
    failed = ",".join(sorted(r["failed"])) or "-"
    calls = "; ".join(f"{n}({a})" for n, a in r["calls"])
    return (f"{cid:4} {status} failed={failed} route={r['route']} "
            f"time={r['seconds']:.2f}s calls={calls}")


def _path_stats(results, prefix, route):
    ids = [i for i in results if i.startswith(prefix)]
    passed = sum(1 for i in ids if not results[i]["failed"])
    acc = sum(1 for i in ids if results[i]["route"] == route) / len(ids)
    return passed, len(ids), acc


@pytest.fixture(scope="module")
def eval_run(planner_llm, cases, score):
    """Run all 30 cases once and print the report. Returns {"results": {...}, "report": str}."""
    results = {}
    for cid, case in cases.items():
        start = time.perf_counter()
        plan = plan_question(planner_llm, case["question"], case["history"])
        seconds = time.perf_counter() - start
        results[cid] = {
            "failed": score(case, plan),
            "route": plan.route,
            "seconds": seconds,
            "calls": [(c.name, c.args) for c in plan.calls],
        }
    lines = [_case_line(cid, r) for cid, r in results.items()]
    for prefix, route in PATHS.items():
        passed, total, acc = _path_stats(results, prefix, route)
        lines.append(f"{route}: {passed}/{total} passed, route accuracy {acc:.0%}")
    avg = sum(r["seconds"] for r in results.values()) / len(results)
    lines.append(f"average call time {avg:.2f}s")
    report = "\n".join(lines)
    print("\n" + report)
    return {"results": results, "report": report}


def _check_path(eval_run, prefix):
    results = eval_run["results"]
    ids = [i for i in results if i.startswith(prefix)]
    assert len(ids) == 10
    bad = {i: sorted(results[i]["failed"]) for i in ids if results[i]["failed"]}
    return 10 - len(bad), bad


def test_tool_path(eval_run):
    """Covers: AC-7 (right). T1 to T10: at least 9 of 10 pass in one run."""
    passed, bad = _check_path(eval_run, "T")
    assert passed >= THRESHOLD, f"TOOL {passed}/10; failed: {bad}"


def test_docs_path(eval_run):
    """Covers: AC-8 (right). D1 to D10: at least 9 of 10 pass in one run."""
    passed, bad = _check_path(eval_run, "D")
    assert passed >= THRESHOLD, f"DOCS {passed}/10; failed: {bad}"


def test_both_path(eval_run):
    """Covers: AC-9 (right). M1 to M10: at least 9 of 10 pass in one run."""
    passed, bad = _check_path(eval_run, "M")
    assert passed >= THRESHOLD, f"BOTH {passed}/10; failed: {bad}"


def test_report_content(eval_run, cases):
    """Covers: AC-10 (right). Each case line has id, pass/fail, the exact failed= field, route, time and call names; the report ends with per-path counts, route accuracy and average time."""
    lines = eval_run["report"].splitlines()
    for cid in cases:
        line = next(l for l in lines if l.startswith(f"{cid} "))
        r = eval_run["results"][cid]
        assert ("FAIL" if r["failed"] else "PASS") in line.split()
        m = re.search(r"failed=(\S+)", line)
        assert m, line
        expected = ",".join(sorted(r["failed"])) or "-"
        assert m.group(1) == expected
        assert set(m.group(1).split(",")) <= {"route", "tools", "search", "-"}
        assert f"route={r['route']}" in line
        assert "time=" in line
        for name, args in r["calls"]:
            assert name in line
            assert str(args) in line
    for route in PATHS.values():
        assert any(l.startswith(f"{route}:") and "route accuracy" in l for l in lines)
    assert lines[-1].startswith("average call time")


def test_run_covers_all_cases(eval_run, cases):
    """Covers: AC-7/AC-8/AC-9 (right), AC-10, NFR-6. The single run scores all 30 cases."""
    assert set(eval_run["results"]) == set(cases)
