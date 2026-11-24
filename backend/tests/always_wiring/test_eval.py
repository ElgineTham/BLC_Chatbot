"""Spec 045 evals: SCOPE (AC-15), ASK (AC-16), MIX (AC-17) and LOG-2 (AC-18), all from ONE run of the real planned
flow (real Claude model, real Gemini embeddings, real .chroma/).

Marked eval; skips (does not fail) when ANTHROPIC_API_KEY or GOOGLE_API_KEY is unset or .chroma/ is missing.
The run writes only logs/always_wiring_<timestamp>.md. A case that raises is recorded and counted as failed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import always_wiring_helpers as awh

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
    """Run the 10 cases once through run_planned_turn, write the log and print the report."""
    from blc.flow import run_planned_turn

    before = _snapshot()

    def run_turn(case, on_token):
        history = [dict(h) for h in case["history"]] if case["history"] else None
        return run_planned_turn(eval_llm, eval_store, case["question"], history, on_token=on_token)

    results = [awh.run_case(awh.CASES[cid], run_turn) for cid in awh.CASE_IDS]
    placeholder = awh.build_report(results)
    path = awh.write_log(results, placeholder, LOG_DIR)
    report = awh.build_report(results, log_path=path)
    path.write_text(path.read_text(encoding="utf-8").replace(placeholder, report), encoding="utf-8")
    print("\n" + report)
    return {"results": {r["case"]["id"]: r for r in results}, "report": report, "path": path,
            "before": before, "after": _snapshot()}


def _passed(r):
    return r["error"] is None and not r["failed"]


def _area(eval_run, area):
    rs = {cid: r for cid, r in eval_run["results"].items() if r["case"]["area"] == area}
    assert len(rs) == awh.AREA_SIZES[area]
    bad = {cid: (r["error"] or sorted(r["failed"])) for cid, r in rs.items() if not _passed(r)}
    return len(rs) - len(bad), bad


def test_scope_area_meets_threshold(eval_run):
    """Covers: AC-15 (right), EVAL-1 to EVAL-4. At least 3 of the 4 SCOPE cases pass."""
    passed, bad = _area(eval_run, "SCOPE")
    assert passed >= awh.THRESHOLDS["SCOPE"], f"SCOPE {passed}/4; failed: {bad}"


def test_ask_area_meets_threshold(eval_run):
    """Covers: AC-16 (right), EVAL-5 to EVAL-7. At least 2 of the 3 ASK cases pass."""
    passed, bad = _area(eval_run, "ASK")
    assert passed >= awh.THRESHOLDS["ASK"], f"ASK {passed}/3; failed: {bad}"


def test_mix_area_meets_threshold(eval_run):
    """Covers: AC-17 (right), EVAL-8 to EVAL-10. At least 2 of the 3 MIX cases pass."""
    passed, bad = _area(eval_run, "MIX")
    assert passed >= awh.THRESHOLDS["MIX"], f"MIX {passed}/3; failed: {bad}"


# ---------------------------------------------------------------- LOG-2 / AC-18

def _sections(text):
    """[(case id, section text)] for the case headings, in file order."""
    parts = re.split(r"(?m)^## (?=EVAL-\d)", text)[1:]
    return [(p.splitlines()[0].strip(), p) for p in parts]


def test_log_2_file_exists_in_logs_with_timestamped_name(eval_run):
    """Covers: AC-18 (right), LOG-2. logs/always_wiring_<YYYY-MM-DD_HHMMSS>.md exists."""
    path = eval_run["path"]
    assert path.exists() and path.parent == LOG_DIR
    assert re.fullmatch(r"always_wiring_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_2_has_10_sections_in_case_order(eval_run):
    """Covers: AC-18 (right), LOG-2. 10 case sections in case order."""
    text = eval_run["path"].read_text(encoding="utf-8")
    assert [cid for cid, _ in _sections(text)] == awh.CASE_IDS
    assert len(awh.CASE_IDS) == 10


def test_log_2_every_section_has_all_six_subsections(eval_run):
    """Covers: AC-18 (right), LOG-2. Each section has the six sub-sections (or is recorded as an error)."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        if eval_run["results"][cid]["error"] is not None:
            assert "Error" in sec, cid
            continue
        for h in awh.SUBSECTIONS:
            assert h in sec, (cid, h)


def test_log_2_follow_up_shows_history(eval_run):
    """Covers: AC-18 (right), LOG-2. The follow-up section shows each history turn verbatim."""
    text = eval_run["path"].read_text(encoding="utf-8")
    for cid, sec in _sections(text):
        for h in awh.CASES[cid]["history"] or []:
            assert f"{h['role']}: {h['content']}" in sec, (cid, h["role"])


def test_log_2_nothing_written_outside_logs(eval_run):
    """Covers: AC-18 (boundary), LOG-2. No file under data/, evals/, backend/scripts, backend/src, docs/,
    backend/tests or frontend/ was created, removed or changed by the run."""
    assert eval_run["before"] == eval_run["after"]
