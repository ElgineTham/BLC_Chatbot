"""Spec 043 evals: CALL-1 to 4 (AC-10), ARGS-1 to 4 (AC-11), FOLLOW-1 to 4 (AC-12) and LOG-2 (AC-13), all from
ONE run of the real planned flow (real Claude model, real Gemini embeddings, real .chroma/, real rules file).

Marked eval; skips (does not fail) when ANTHROPIC_API_KEY or GOOGLE_API_KEY is unset, .chroma/ is missing, or
the real rules file is missing. The run writes only logs/serv_wiring_<timestamp>.md. A case that raises is
recorded and counted as failed, and the run goes on.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import serv_wiring_helpers as swh

pytestmark = pytest.mark.eval

ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = ROOT / "logs"
WATCHED = ("data", "evals", "backend/scripts", "backend/src", "docs", "backend/tests", "frontend")


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
    """Run the 12 cases once through run_planned_turn, write the log and print the report."""
    from blc.flow import run_planned_turn

    before = _snapshot()

    def run_turn(case, on_token):
        history = [dict(h) for h in case["history"]] if case["history"] else None
        return run_planned_turn(eval_llm, eval_store, case["question"], history, on_token=on_token)

    results = [swh.run_case(swh.CASES[cid], run_turn) for cid in swh.CASE_IDS]
    placeholder = swh.build_report(results)
    path = swh.write_log(results, placeholder, LOG_DIR)
    report = swh.build_report(results, log_path=path)
    path.write_text(path.read_text(encoding="utf-8").replace(placeholder, report), encoding="utf-8")
    print("\n" + report)
    return {"results": {r["case"]["id"]: r for r in results}, "report": report, "path": path,
            "before": before, "after": _snapshot()}


def _passed(r):
    return r["error"] is None and not r["failed"]


def _area(eval_run, area):
    rs = {cid: r for cid, r in eval_run["results"].items() if r["case"]["area"] == area}
    assert len(rs) == swh.AREA_SIZES[area]
    bad = {cid: (r["error"] or sorted(r["failed"])) for cid, r in rs.items() if not _passed(r)}
    return len(rs) - len(bad), bad


def test_call_area_meets_threshold(eval_run):
    """Covers: AC-10 (right), CALL-1 to CALL-4. At least 3 of the 4 CALL cases pass."""
    passed, bad = _area(eval_run, "CALL")
    assert passed >= swh.THRESHOLD, f"CALL {passed}/4; failed: {bad}"


def test_args_area_meets_threshold(eval_run):
    """Covers: AC-11 (right), ARGS-1 to ARGS-4. At least 3 of the 4 ARGS cases pass (judged by totals)."""
    passed, bad = _area(eval_run, "ARGS")
    assert passed >= swh.THRESHOLD, f"ARGS {passed}/4; failed: {bad}"


def test_follow_area_meets_threshold(eval_run):
    """Covers: AC-12 (right), FOLLOW-1 to FOLLOW-4. At least 3 of the 4 FOLLOW cases pass."""
    passed, bad = _area(eval_run, "FOLLOW")
    assert passed >= swh.THRESHOLD, f"FOLLOW {passed}/4; failed: {bad}"


# ---------------------------------------------------------------- LOG-2 / AC-13

def _sections(text):
    """[(case id, section text)] for the case headings, in file order."""
    parts = re.split(r"(?m)^## (?=(?:CALL|ARGS|FOLLOW)-\d)", text)[1:]
    return [(p.splitlines()[0].strip(), p) for p in parts]


def test_log_2_file_exists_in_logs_with_timestamped_name(eval_run):
    """Covers: AC-13 (right), LOG-2. logs/serv_wiring_<YYYY-MM-DD_HHMMSS>.md exists."""
    path = eval_run["path"]
    assert path.exists() and path.parent == LOG_DIR
    assert re.fullmatch(r"serv_wiring_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_2_has_12_sections_in_case_order(eval_run):
    """Covers: AC-13 (right), LOG-2. 12 case sections in the order CALL, ARGS, FOLLOW."""
    text = eval_run["path"].read_text(encoding="utf-8")
    assert [cid for cid, _ in _sections(text)] == swh.CASE_IDS
    assert len(swh.CASE_IDS) == 12


def test_log_2_every_section_has_all_six_subsections(eval_run):
    """Covers: AC-13 (right), LOG-2. Each section has Input, Planner, Tools, Retrieved, Answer and Verdict
    (or is recorded as an error)."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        if eval_run["results"][cid]["error"] is not None:
            assert "Error" in sec, cid
            continue
        for h in swh.SUBSECTIONS:
            assert h in sec, (cid, h)


def test_log_2_follow_up_sections_show_their_history(eval_run):
    """Covers: AC-13 (right), LOG-2. Every FOLLOW section shows each history turn verbatim."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        case = swh.CASES[cid]
        for h in case["history"] or []:
            assert f"{h['role']}: {h['content']}" in sec, (cid, h["role"])


def test_log_2_planner_shows_first_and_final_plan(eval_run):
    """Covers: AC-13 (right), LOG-2. Every non-error section's Planner shows the first plan, the final plan
    and whether it retried."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        if eval_run["results"][cid]["error"] is not None:
            continue
        planner = sec.split("### Planner")[1].split("### Tools")[0]
        assert "first plan" in planner and "final plan" in planner and "retried:" in planner, cid


def test_log_2_report_names_the_log_and_every_case(eval_run):
    """Covers: AC-13 (right), LOG-2. The printed report has one line per case, the per-area counts and the log
    file name."""
    report = eval_run["report"]
    for cid in swh.CASE_IDS:
        assert re.search(rf"(?m)^{re.escape(cid)}: (pass|fail)", report), cid
    for area in swh.AREAS:
        assert f"{area}: " in report and "of 4 passed" in report
    assert eval_run["path"].name in report


def test_log_2_nothing_written_outside_logs(eval_run):
    """Covers: AC-13 (boundary), LOG-2. No file under data/, evals/, backend/scripts, backend/src, docs/,
    backend/tests or frontend/ was created, removed or changed by the run."""
    assert eval_run["before"] == eval_run["after"]
