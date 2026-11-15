"""Spec 021, AC-4 to AC-7 and NFR-4 (golden eval): 30 cases, one run_planned_turn each, scored on three parts.

Marked eval. Skips (does not fail) when Ollama is not running or the Chroma store is missing or empty.
Uses real models, the real store and real tools (one warm-up call first). The scorer runs no model.
Writes only logs/golden_calls_<YYYY-MM-DD_HHMMSS>.md and prints the report of section 4.4.
The log writer and report (isolated per case, revision 2) live in conftest as the golden_log fixture, where
tests/no_invented/test_golden_log.py unit-tests them without a model.
"""
import re
from pathlib import Path

import pytest

from blc.flow import run_planned_turn
from blc.tools.bev_tools import run_bev_tool
from blc.tools.recipe_tools import run_recipe_tool

pytestmark = pytest.mark.eval

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
SUBSECTIONS = ("### Question", "### Plan", "### Part 1, gold call", "### Part 2, invented numbers",
               "### Part 3, required outcome", "### Answer", "### Verdict")
BEV = "calculate_bev_item"


def tool_result(name, args):
    """The real tool, re-run on the run args: deterministic, no model."""
    return run_bev_tool(dict(args)) if name == BEV else run_recipe_tool(dict(args))


@pytest.fixture(scope="module")
def eval_run(real_llm, real_store, golden_cases, scorer, golden_log):
    def run_turn(case, on_token):
        return run_planned_turn(real_llm, real_store, case["question"], case["history"], on_token=on_token)

    results = [golden_log.run_case(scorer, c, run_turn, tool_result) for c in golden_cases]
    report = golden_log.report(results)
    path = golden_log.write_log(results, report, LOG_DIR)
    print(f"\n{report}\nGolden calls log: {path}")
    return {"results": results, "report": report, "path": path, "text": path.read_text(encoding="utf-8")}


def _passed(eval_run, path):
    return sum(1 for r in eval_run["results"] if r["case"]["path"] == path and r["score"] and r["score"]["passed"])


def test_tool_path_threshold(eval_run):
    """Covers: AC-4 (right). At least 9 of G1 to G10 pass all three parts, the route and no search."""
    assert _passed(eval_run, "TOOL") >= 9, eval_run["report"]


def test_docs_path_threshold(eval_run):
    """Covers: AC-5 (right). At least 9 of L1 to L10 pass."""
    assert _passed(eval_run, "DOCS") >= 9, eval_run["report"]


def test_both_path_threshold(eval_run):
    """Covers: AC-6 (right). At least 9 of B1 to B10 pass."""
    assert _passed(eval_run, "BOTH") >= 9, eval_run["report"]


def test_log_written_under_logs_with_a_timestamped_name(eval_run):
    """Covers: AC-7 (right), NFR-4. The log is logs/golden_calls_<YYYY-MM-DD_HHMMSS>.md."""
    path = eval_run["path"]
    assert path.exists() and path.parent == LOG_DIR
    assert re.fullmatch(r"golden_calls_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_has_30_sections_each_with_every_subsection(eval_run, golden_cases):
    """Covers: AC-7 (right). One section per case in order; each holds all seven sub-sections (or an Error line)."""
    text = eval_run["text"]
    assert re.findall(r"^## ([GLB]\d+)$", text, flags=re.M) == [c["id"] for c in golden_cases]
    parts = re.split(r"^## [GLB]\d+$", text, flags=re.M)[1:]
    assert len(parts) == 30
    for case, part in zip(golden_cases, parts):
        assert case["question"] in part
        if "- Error:" in part:
            continue
        for sub in SUBSECTIONS:
            assert sub in part, (case["id"], sub)


def test_part3_log_shows_required_actual_and_a_result_per_fact(eval_run, golden_cases):
    """Covers: AC-7 (right), revision 1. In every case section that ran a tool, the Part 3 sub-section holds
    'required', 'actual' and a per-fact pass or fail; searches show their query and source paths."""
    sections = re.split(r"^## [GLB]\d+$", eval_run["text"], flags=re.M)[1:]
    checked = 0
    for case, sec, res in zip(golden_cases, sections, eval_run["results"]):
        if res["error"] or res["outcome"] is None:
            continue
        part3 = sec.split("### Part 3, required outcome")[1].split("### Answer")[0]
        if res["outcome"].tools:
            checked += 1
            assert "required" in part3 and "actual" in part3, case["id"]
            fact_lines = [l for l in part3.splitlines() if l.startswith("  - ") and "required" in l]
            assert fact_lines, case["id"]
            assert all(l.endswith(": pass") or l.endswith(": fail") for l in fact_lines), case["id"]
            assert any(l.startswith("  - status:") for l in fact_lines), case["id"]
        for sr in res["outcome"].searches:
            assert repr(sr.query) in part3, case["id"]
    assert checked > 0


def test_report_has_a_line_per_case_and_the_totals(eval_run, golden_cases):
    """Covers: AC-7 (right). One line per case (id, pass/fail, route, three parts, retried) and the totals."""
    rep = eval_run["report"]
    for c in golden_cases:
        assert re.search(rf"^{c['id']}: (pass|fail)", rep, flags=re.M), c["id"]
    for path in ("TOOL", "DOCS", "BOTH"):
        assert re.search(rf"^{path}: \d+ of 10", rep, flags=re.M)
    assert "invented a number" in rep and "retried" in rep and "dropped" in rep


def test_every_case_ran_or_recorded_its_error(eval_run, golden_cases):
    """Covers: AC-7 (boundary). All 30 cases ended with an outcome or a recorded error."""
    results = eval_run["results"]
    assert [r["case"]["id"] for r in results] == [c["id"] for c in golden_cases]
    assert all((r["outcome"] is None) != (r["error"] is None) for r in results)
