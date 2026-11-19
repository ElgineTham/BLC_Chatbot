"""Spec 043 section 6.7 LOG-1 (AC-13): the eval log writer on fake outcomes. Unit; writes only to tmp_path."""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

import serv_wiring_helpers as swh
from blc.planner import Plan, PlannedCall

SERV, SEARCH = swh.SERV, swh.SEARCH


def _plan(*calls, route="TOOL"):
    return Plan(route, tuple(PlannedCall(n, a) for n, a in calls), False)


def _tool(name, args, status, text):
    return SimpleNamespace(name=name, args=args, status=status, text=text)


def _outcome(plan, first_plan=None, rejected=(), retried=False, tools=(), searches=(), reply="", model=False):
    return SimpleNamespace(plan=plan, first_plan=first_plan or plan, rejected=tuple(rejected), retried=retried,
                           tools=tuple(tools), searches=tuple(searches), reply=reply, answered_by_model=model)


GOOD = {"items": [{"food": "butter croissants", "qty": 3}]}
BAD = {"items": [{"food": "bagels", "qty": 48}]}
FIXED = {"items": [{"food": "bagels"}]}


@pytest.fixture
def results():
    """One TOOL turn (CALL-1), one retried turn (ARGS-1), one DOCS follow-up (FOLLOW-4), one raising case
    (ARGS-2), then one more TOOL turn (ARGS-3) that must still be written."""
    tool_turn = _outcome(_plan((SERV, GOOD)), tools=[_tool(SERV, GOOD, "ok", "Small tongs: 4\nCounted for: x 3")],
                         reply="Small tongs: 4\nCounted for: x 3")
    retried = _outcome(
        _plan((SERV, FIXED)), first_plan=_plan((SERV, BAD)),
        rejected=[SimpleNamespace(name=SERV, args=BAD, invented={"qty": (48,)})], retried=True,
        tools=[_tool(SERV, FIXED, "need_info", "How many bagels?")], reply="How many bagels?")
    chunk = SimpleNamespace(page_content="Muffins are on the rack.\nSecond line.", metadata={"source": "data/f.md"})
    docs = _outcome(_plan((SEARCH, {"query": "where are the muffins kept"}), route="DOCS"),
                    searches=[SimpleNamespace(query="where are the muffins kept", chunks=[chunk])],
                    reply="On the rack.", model=True)
    cases = swh.CASES

    def run_turn(case, on_token):
        if case["id"] == "ARGS-2":
            raise RuntimeError("model unavailable")
        return {"CALL-1": tool_turn, "ARGS-1": retried, "FOLLOW-4": docs, "ARGS-3": tool_turn}[case["id"]]

    chosen = [cases["CALL-1"], cases["ARGS-1"], cases["ARGS-2"], cases["ARGS-3"], cases["FOLLOW-4"]]
    # Score with a fake tool runner so no rules file is read.
    return [swh.run_case(c, run_turn, run_tool=lambda args: SimpleNamespace(status="need_info", utensils=None))
            for c in chosen]


def _section(text, cid):
    parts = re.split(r"(?m)^## (?=(?:CALL|ARGS|FOLLOW)-\d)", text)[1:]
    for p in parts:
        if p.splitlines()[0].strip() == cid:
            return p
    raise AssertionError(f"no section {cid}")


@pytest.fixture
def log_text(results, tmp_path):
    path = swh.write_log(results, swh.build_report(results), tmp_path / "logs")
    return path, path.read_text(encoding="utf-8")


def test_log_file_name_and_location(log_text, tmp_path):
    """Covers: AC-13 (right), LOG-1. The log is logs/serv_wiring_<YYYY-MM-DD_HHMMSS>.md under the given dir."""
    path, _ = log_text
    assert path.parent == tmp_path / "logs"
    assert re.fullmatch(r"serv_wiring_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_sections_follow_case_order(log_text):
    """Covers: AC-13 (right), LOG-1. One section per case, in the order given."""
    _, text = log_text
    ids = re.findall(r"(?m)^## ((?:CALL|ARGS|FOLLOW)-\d)", text)
    assert ids == ["CALL-1", "ARGS-1", "ARGS-2", "ARGS-3", "FOLLOW-4"]


@pytest.mark.parametrize("cid", ["CALL-1", "ARGS-1", "ARGS-3", "FOLLOW-4"])
def test_every_normal_section_has_all_six_subsections(log_text, cid):
    """Covers: AC-13 (right), LOG-1. Input, Planner, Tools, Retrieved, Answer and Verdict, in that order."""
    sec = _section(log_text[1], cid)
    positions = [sec.index(h) for h in swh.SUBSECTIONS]
    assert positions == sorted(positions)


def test_tools_section_shows_name_args_status_and_exact_text(log_text):
    """Covers: AC-13 (right), LOG-1. The Tools sub-section has the call name, arguments, status and the exact
    text."""
    sec = _section(log_text[1], "CALL-1")
    tools = sec.split("### Tools")[1].split("### Retrieved")[0]
    assert SERV in tools and str(GOOD) in tools and "ok" in tools
    assert "Small tongs: 4\nCounted for: x 3" in tools


def test_retried_turn_shows_first_plan_rejected_values_and_final_plan(log_text):
    """Covers: AC-13 (right), LOG-1. The retried turn shows the first plan (qty 48), the rejected values, that
    it retried, and the final plan (no qty)."""
    sec = _section(log_text[1], "ARGS-1")
    planner = sec.split("### Planner")[1].split("### Tools")[0]
    assert "first plan" in planner and "final plan" in planner
    assert str(BAD) in planner and str(FIXED) in planner
    assert "48" in planner and "invented" in planner
    assert "retried: yes" in planner
    assert planner.index("first plan") < planner.index("final plan")


def test_followup_shows_its_history(log_text):
    """Covers: AC-13 (right), LOG-1. The follow-up section shows each history turn verbatim."""
    sec = _section(log_text[1], "FOLLOW-4")
    for h in swh.CASES["FOLLOW-4"]["history"]:
        assert f"{h['role']}: {h['content']}" in sec


def test_retrieved_shows_query_and_source(log_text):
    """Covers: AC-13 (right), LOG-1. The DOCS follow-up lists its query and the chunk's source."""
    sec = _section(log_text[1], "FOLLOW-4")
    retrieved = sec.split("### Retrieved")[1].split("### Answer")[0]
    assert "where are the muffins kept" in retrieved and "data/f.md" in retrieved


def test_no_history_is_written_as_none(log_text):
    """Covers: AC-13 (boundary), LOG-1. A case without history says so (not a crash, not blank)."""
    sec = _section(log_text[1], "CALL-1")
    assert "history: none" in sec


def test_raising_case_is_an_error_and_the_run_goes_on(results, log_text):
    """Covers: AC-13 (wrong), LOG-1. The case that raised is recorded as an error with its message, counted as
    failed, and the case after it is still written in full."""
    by_id = {r["case"]["id"]: r for r in results}
    assert by_id["ARGS-2"]["error"] and "model unavailable" in by_id["ARGS-2"]["error"]
    assert by_id["ARGS-3"]["error"] is None
    text = log_text[1]
    sec = _section(text, "ARGS-2")
    assert "Error" in sec and "model unavailable" in sec
    for h in swh.SUBSECTIONS:
        assert h in _section(text, "ARGS-3")


def test_report_lists_every_case_and_counts_errors_as_failed(results):
    """Covers: AC-13 (boundary), LOG-1. One report line per case; the raised case is a fail; the per-area
    counts exclude it."""
    report = swh.build_report(results)
    for r in results:
        assert re.search(rf"(?m)^{re.escape(r['case']['id'])}: (pass|fail)", report)
    assert re.search(r"(?m)^ARGS-2: fail", report)
    assert "FOLLOW: " in report and "CALL: " in report and "ARGS: " in report
