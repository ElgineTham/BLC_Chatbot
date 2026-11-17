"""Spec 030 evals: CALL-1 to 6 (AC-9), ARGS-1 to 6 (AC-10), ANSWER-7 (AC-13), FT-1 to 6 (AC-11),
FD-1 to 6 (AC-12) and LOG-5 (AC-18), all from ONE run of the real planned flow on qwen2.5:7b.

Marked eval; skips (does not fail) when Ollama is not running or .chroma/ is missing. The run writes only
logs/food_wiring_<timestamp>.md. A case that raises is recorded and counted as failed, and the run goes on.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import food_wiring_helpers as fwh

pytestmark = pytest.mark.eval

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
WATCHED = ("data", "evals", "scripts", "src", "docs", "tests")


def _snapshot():
    """Names and mtimes of every file outside logs/ that the eval must not write (ignoring caches)."""
    snap = {}
    for top in WATCHED:
        for dirpath, dirnames, filenames in os.walk(ROOT / top):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for f in filenames:
                p = Path(dirpath) / f
                snap[str(p)] = p.stat().st_mtime_ns
    return snap


@pytest.fixture(scope="module")
def eval_run(eval_llm, eval_store):
    """Run the 25 cases once through run_planned_turn, write the log and print the report."""
    from blc.flow import run_planned_turn

    before = _snapshot()

    def run_turn(case, on_token):
        history = [dict(h) for h in case["history"]] if case["history"] else None
        return run_planned_turn(eval_llm, eval_store, case["question"], history, on_token=on_token)

    results = [fwh.run_case(case, run_turn) for case in (fwh.CASES[cid] for cid in fwh.CASE_IDS)]
    placeholder = fwh.build_report(results)
    path = fwh.write_log(results, placeholder, LOG_DIR)
    report = fwh.build_report(results, log_path=path)
    path.write_text(path.read_text(encoding="utf-8").replace(placeholder, report), encoding="utf-8")
    print("\n" + report)
    return {"results": {r["case"]["id"]: r for r in results}, "report": report, "path": path,
            "before": before, "after": _snapshot()}


def _passed(r):
    return r["error"] is None and not r["failed"]


def _area(eval_run, area, size):
    rs = {cid: r for cid, r in eval_run["results"].items() if r["case"]["area"] == area}
    assert len(rs) == size
    bad = {cid: (r["error"] or sorted(r["failed"])) for cid, r in rs.items() if not _passed(r)}
    return size - len(bad), bad


def test_call_area_meets_threshold(eval_run):
    """Covers: AC-9 (right), CALL-1 to CALL-6. At least 5 of the 6 CALL cases pass."""
    passed, bad = _area(eval_run, "CALL", 6)
    assert passed >= fwh.THRESHOLD, f"CALL {passed}/6; failed: {bad}"


def test_args_area_meets_threshold(eval_run):
    """Covers: AC-10 (right), ARGS-1 to ARGS-6. At least 5 of the 6 ARGS cases pass."""
    passed, bad = _area(eval_run, "ARGS", 6)
    assert passed >= fwh.THRESHOLD, f"ARGS {passed}/6; failed: {bad}"


def test_follow_tool_area_meets_threshold(eval_run):
    """Covers: AC-11 (right), FT-1 to FT-6. At least 5 of the 6 FT cases pass."""
    passed, bad = _area(eval_run, "FT", 6)
    assert passed >= fwh.THRESHOLD, f"FT {passed}/6; failed: {bad}"


def test_follow_docs_area_meets_threshold(eval_run):
    """Covers: AC-12 (right), FD-1 to FD-6. At least 5 of the 6 FD cases pass."""
    passed, bad = _area(eval_run, "FD", 6)
    assert passed >= fwh.THRESHOLD, f"FD {passed}/6; failed: {bad}"


def test_answer_7_reply_is_the_tools_text(eval_run):
    """Covers: AC-13 (right), ANSWER-7. 'How many forks do I need for 70 guests?' on the real flow: route
    TOOL, the reply equals run_food_tool's text for the arguments the model sent, the answer model was not
    called."""
    from blc.tools.food_tools import run_food_tool

    r = eval_run["results"]["ANSWER-7"]
    assert r["error"] is None, r["error"]
    o = r["outcome"]
    assert o.plan.route == "TOOL"
    assert len(o.tools) == 1, [t.name for t in o.tools]
    assert o.tools[0].name == "calculate_food_item"
    assert o.reply == run_food_tool(o.tools[0].args).text
    assert o.answered_by_model is False


# ---------------------------------------------------------------- LOG-5 / AC-18

def _sections(text):
    """{case id: section text} for the 25 case headings, in file order."""
    parts = re.split(r"(?m)^## (?=(?:CALL|ARGS|ANSWER|FT|FD)-\d)", text)[1:]
    return [(p.splitlines()[0].strip(), p) for p in parts]


def test_log_5_file_exists_in_logs_with_timestamped_name(eval_run):
    """Covers: AC-18 (right), LOG-5. logs/food_wiring_<YYYY-MM-DD_HHMMSS>.md exists."""
    path = eval_run["path"]
    assert path.exists() and path.parent == LOG_DIR
    assert re.fullmatch(r"food_wiring_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_5_has_25_sections_in_case_order(eval_run):
    """Covers: AC-18 (right), LOG-5. 25 case sections, in the order CALL, ARGS, ANSWER, FT, FD."""
    text = eval_run["path"].read_text(encoding="utf-8")
    assert [cid for cid, _ in _sections(text)] == fwh.CASE_IDS
    assert len(fwh.CASE_IDS) == 25


def test_log_5_every_section_has_all_six_subsections(eval_run):
    """Covers: AC-18 (right), LOG-5. Each section has Input, Planner, Tools, Retrieved, Answer, Verdict (or is
    recorded as an error)."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        if eval_run["results"][cid]["error"] is not None:
            assert "Error" in sec, cid
            continue
        for h in fwh.SUBSECTIONS:
            assert h in sec, (cid, h)


def test_log_5_follow_up_sections_show_their_history(eval_run):
    """Covers: AC-18 (right), LOG-5. Every FT and FD section shows each of its history turns verbatim."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        case = fwh.CASES[cid]
        if case["area"] not in ("FT", "FD"):
            continue
        for h in case["history"]:
            assert f"{h['role']}: {h['content']}" in sec, (cid, h["role"])


def test_log_5_planner_shows_first_and_final_plan(eval_run):
    """Covers: AC-18 (right), LOG-5. Every non-error section's Planner shows the first and the final plan."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        if eval_run["results"][cid]["error"] is not None:
            continue
        planner = sec.split("### Planner")[1].split("### Tools")[0]
        assert "first plan" in planner and "final plan" in planner and "retried:" in planner, cid


def test_log_5_report_names_the_log_and_every_case(eval_run):
    """Covers: AC-18 (right), LOG-5. The printed report has one line per case, the per-area counts and the log
    file name."""
    report = eval_run["report"]
    for cid in fwh.CASE_IDS:
        assert re.search(rf"(?m)^{re.escape(cid)}: (pass|fail)", report), cid
    for area in ("CALL", "ARGS", "FT", "FD"):
        assert f"{area}: " in report and "of 6 passed" in report
    assert eval_run["path"].name in report


def test_log_5_nothing_written_outside_logs(eval_run):
    """Covers: AC-18 (boundary), LOG-5. No file under data/, evals/, scripts/, src/, docs/ or tests/ was
    created, removed or changed by the run."""
    assert eval_run["before"] == eval_run["after"]
