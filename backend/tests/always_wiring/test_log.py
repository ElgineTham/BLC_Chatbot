"""Spec 045 section 6.6 LOG-1 (AC-18) and the scorer of section 4.6: the eval log writer, report and scorer, from
fake outcomes. Unit, no model. LOG-2 (the real run) is in test_eval.py."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import always_wiring_helpers as awh
from blc.planner import Plan, PlannedCall

ALWAYS = "calculate_always_items"
FOOD = "calculate_food_item"
SEARCH = "search_documents"
OK_TEXT = "Bus tubs: check\nTowels: check\nBlack linens: 9\nPurple napkins: 8"


def plan(route, *calls):
    return Plan(route, tuple(PlannedCall(n, a) for n, a in calls), False)


def outcome(final, first=None, rejected=(), retried=False, tools=(), reply="", by_model=False):
    return SimpleNamespace(
        plan=final, first_plan=first or final, rejected=tuple(rejected), retried=retried,
        tools=tuple(SimpleNamespace(name=n, args=a, status=s, text=t) for n, a, s, t in tools),
        searches=(), reply=reply, answered_by_model=by_model)


def section(case_id, out):
    r = awh.run_case(awh.CASES[case_id], lambda case, on_token: out)
    assert r["error"] is None, r["error"]
    return "\n".join(r["section"])


def ok_outcome():
    args = {"about": "tables", "tables": 4}
    return outcome(plan("TOOL", (ALWAYS, args)), tools=[(ALWAYS, args, "ok", OK_TEXT)], reply=OK_TEXT)


# ---------------------------------------------------------------- LOG-1 ok turn

def test_log_1_ok_turn_has_six_subsections_in_order():
    """Covers: AC-18 (right), LOG-1. An ok turn's section has the six sub-sections in order under its own
    heading."""
    text = section("EVAL-1", ok_outcome())
    assert text.startswith("## EVAL-1")
    positions = [text.index(h) for h in awh.SUBSECTIONS]
    assert positions == sorted(positions)


def test_log_1_ok_turn_shows_tool_name_args_status_text():
    """Covers: AC-18 (right), LOG-1. Tools shows the tool name, arguments, status and exact text."""
    text = section("EVAL-1", ok_outcome())
    tools = text.split("### Tools")[1].split("### Retrieved")[0]
    assert ALWAYS in tools and "'tables': 4" in tools and "ok" in tools and "Black linens: 9" in tools
    assert "history: none" in text.split("### Input")[1].split("### Planner")[0]


def test_log_1_passing_verdict():
    """Covers: AC-18 (right), LOG-1. A correct turn is a pass."""
    verdict = section("EVAL-1", ok_outcome()).split("### Verdict")[1]
    assert "pass" in verdict and "failed checks -" in verdict


# ---------------------------------------------------------------- LOG-1 retried turn

def retried_outcome():
    first = plan("TOOL", (ALWAYS, {"about": "tables", "tables": 1}))
    final = plan("TOOL", (ALWAYS, {"about": "tables"}))
    need = "Bus tubs: check\nTowels: check\nHow many tables are there?"
    return outcome(final, first=first,
                   rejected=[SimpleNamespace(name=ALWAYS, args={"about": "tables", "tables": 1},
                                             invented={"tables": (1,)})],
                   retried=True, tools=[(ALWAYS, {"about": "tables"}, "need_info", need)], reply=need)


def test_log_1_retried_turn_shows_first_rejected_and_final_plan():
    """Covers: AC-18 (right), LOG-1. The Planner sub-section shows the first plan with tables 1, the rejected
    values, retried: yes and the final plan without tables."""
    text = section("EVAL-5", retried_outcome())
    planner = text.split("### Planner")[1].split("### Tools")[0]
    assert "retried: yes" in planner
    assert "(1,)" in planner
    first_part, final_part = planner.split("final plan")
    assert "'tables': 1" in first_part
    assert "tables" not in final_part.replace("'about': 'tables'", "")
    assert "rejected: none" not in planner


# ---------------------------------------------------------------- LOG-1 follow-up with history

def test_log_1_follow_up_shows_history():
    """Covers: AC-18 (right), LOG-1. A follow-up's Input shows both history turns as 'role: content'."""
    args = {"about": "both", "tables": 6, "drip_trays": 2}
    out = outcome(plan("TOOL", (ALWAYS, args)), tools=[(ALWAYS, args, "ok", OK_TEXT)], reply=OK_TEXT)
    inp = section("EVAL-8", out).split("### Input")[1].split("### Planner")[0]
    for h in awh.H_ASK:
        assert f"{h['role']}: {h['content']}" in inp
    assert awh.CASES["EVAL-8"]["question"] in inp
    assert "history: none" not in inp


# ---------------------------------------------------------------- LOG-1 a case that raises

class _Exploding:
    plan = plan("TOOL", (ALWAYS, {"about": "tables", "tables": 4}))
    first_plan = plan
    rejected = ()
    retried = False
    searches = ()
    reply = "x"
    answered_by_model = False

    @property
    def tools(self):
        raise RuntimeError("boom while building the section")


def three_results():
    args3 = {"about": "both", "tables": 5, "drip_trays": 2}
    out3 = outcome(plan("TOOL", (ALWAYS, args3)), tools=[(ALWAYS, args3, "ok", OK_TEXT)], reply=OK_TEXT)
    outs = {"EVAL-1": ok_outcome(), "EVAL-2": _Exploding(), "EVAL-3": out3}
    return [awh.run_case(awh.CASES[cid], lambda case, on_token, o=o: o) for cid, o in outs.items()]


def test_log_1_raising_case_recorded_as_error():
    """Covers: AC-18 (wrong), LOG-1. A case that raises is recorded as an error with its message."""
    bad = three_results()[1]
    assert bad["error"] is not None and "boom while building the section" in bad["error"]
    assert "boom while building the section" in "\n".join(bad["section"])
    assert "EVAL-2" in bad["line"] and "fail" in bad["line"]


def test_log_1_run_goes_on_after_an_error():
    """Covers: AC-18 (right), LOG-1. The cases after the error are still fully written."""
    results = three_results()
    for good in (results[0], results[2]):
        assert good["error"] is None
        text = "\n".join(good["section"])
        for h in awh.SUBSECTIONS:
            assert h in text


def test_log_1_run_turn_that_raises_is_recorded():
    """Covers: AC-18 (wrong), LOG-1. A run_turn that raises is recorded the same way."""
    def boom(case, on_token):
        raise ValueError("model gone")

    r = awh.run_case(awh.CASES["EVAL-1"], boom)
    assert "model gone" in r["error"] and "model gone" in "\n".join(r["section"])


def test_log_1_file_sections_in_case_order(tmp_path):
    """Covers: AC-18 (right), LOG-1. write_log names the file always_wiring_<timestamp>.md, creates the folder
    and writes the sections in order."""
    results = three_results()
    path = awh.write_log(results, awh.build_report(results), tmp_path / "logs")
    assert path.parent == tmp_path / "logs"
    assert path.name.startswith("always_wiring_") and path.suffix == ".md"
    text = path.read_text(encoding="utf-8")
    assert text.index("## EVAL-1") < text.index("## EVAL-2") < text.index("## EVAL-3")
    assert [p.name for p in tmp_path.iterdir()] == ["logs"]


# ---------------------------------------------------------------- scorer (section 4.6)

def _score(case_id, p):
    return awh.score_case(awh.CASES[case_id], p)


def test_scorer_passes_a_correct_scope_plan():
    """Covers: AC-15 (right). EVAL-1 with about tables, tables 4 passes all three checks."""
    p = plan("TOOL", (ALWAYS, {"about": "tables", "tables": 4}))
    assert _score("EVAL-1", p) == set()


def test_scorer_about_value_not_compared_only_result():
    """Covers: AC-15 (boundary). Only the result is compared: about 'tables' with an out-of-scope drip_trays
    gives the same result and passes; about 'both' with tables 4 gives need_info and fails."""
    p = plan("TOOL", (ALWAYS, {"about": "tables", "tables": 4, "drip_trays": 9}))
    assert _score("EVAL-1", p) == set()
    wrong = plan("TOOL", (ALWAYS, {"about": "both", "tables": 4}))
    assert _score("EVAL-1", wrong) == {"result"}


def test_scorer_wrong_number_fails_result():
    """Covers: AC-15 (wrong). tables 5 for EVAL-1 fails the result check only."""
    p = plan("TOOL", (ALWAYS, {"about": "tables", "tables": 5}))
    assert _score("EVAL-1", p) == {"result"}


def test_scorer_wrong_tool_set_fails_tools():
    """Covers: AC-15 (wrong). A food call for EVAL-4 passes; an always call for EVAL-4 fails tools."""
    assert _score("EVAL-4", plan("TOOL", (FOOD, {"item": "forks", "guests": 60}))) == set()
    bad = plan("TOOL", (ALWAYS, {"about": "both"}))
    assert "tools" in _score("EVAL-4", bad)


def test_scorer_wrong_route_fails_route():
    """Covers: AC-15 (wrong). A DOCS plan fails route and tools."""
    p = plan("DOCS", (SEARCH, {"query": "always items"}))
    assert {"route", "tools", "result"} <= _score("EVAL-1", p)


def test_scorer_search_calls_are_not_tool_names():
    """Covers: AC-15 (boundary). A search next to the always call changes the route, not the tool-name check."""
    p = plan("BOTH", (SEARCH, {"query": "x"}), (ALWAYS, {"about": "tables", "tables": 4}))
    assert _score("EVAL-1", p) == {"route"}


def test_scorer_need_info_cases():
    """Covers: AC-16 (right/wrong). EVAL-5 passes with about tables and no tables; a guessed tables 1 fails;
    EVAL-7 needs the linen counts and the drip trays question."""
    assert _score("EVAL-5", plan("TOOL", (ALWAYS, {"about": "tables"}))) == set()
    assert _score("EVAL-5", plan("TOOL", (ALWAYS, {"about": "tables", "tables": 1}))) == {"result"}
    assert _score("EVAL-7", plan("TOOL", (ALWAYS, {"about": "both", "tables": 4}))) == set()
    assert _score("EVAL-7", plan("TOOL", (ALWAYS, {"about": "tables"}))) == {"result"}
    assert _score("EVAL-6", plan("TOOL", (ALWAYS, {"about": "both"}))) == set()


def test_scorer_missing_always_call_fails_result():
    """Covers: AC-15 (wrong). No always call at all fails the result check."""
    assert "result" in _score("EVAL-2", plan("TOOL", (FOOD, {"item": "forks", "guests": 60})))


def test_report_counts_error_case_as_failed():
    """Covers: AC-18 (right). The report counts the raising case as not passed: SCOPE 2 of 3 in this run."""
    report = awh.build_report(three_results())
    assert "SCOPE: 2 of 3 passed" in report
    assert "EVAL-2: fail" in report


@pytest.mark.parametrize("area,size,threshold", [("SCOPE", 4, 3), ("ASK", 3, 2), ("MIX", 3, 2)])
def test_area_sizes_and_thresholds(area, size, threshold):
    """Covers: AC-15/16/17 (boundary). The case copy matches the section 4.6 sizes and thresholds."""
    assert sum(1 for c in awh.CASES.values() if c["area"] == area) == size == awh.AREA_SIZES[area]
    assert awh.THRESHOLDS[area] == threshold
