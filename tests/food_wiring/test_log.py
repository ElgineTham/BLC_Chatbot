"""Spec 030 section 6.6 LOG-1 to LOG-4 (AC-19): the eval log writer and report, from fake outcomes.
Unit, no model. LOG-5 (the real run) is in test_eval.py."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

import food_wiring_helpers as fwh
from blc.planner import Plan, PlannedCall

FOOD = "calculate_food_item"
SEARCH = "search_documents"
FORKS_TEXT = "Forks: 120 (70 guests + 50 extra)"


def plan(route, *calls):
    return Plan(route, tuple(PlannedCall(n, a) for n, a in calls), False)


def outcome(final, first=None, rejected=(), retried=False, tools=(), searches=(), reply="", by_model=False):
    return SimpleNamespace(
        plan=final, first_plan=first or final, rejected=tuple(rejected), retried=retried,
        tools=tuple(SimpleNamespace(name=n, args=a, status=s, text=t) for n, a, s, t in tools),
        searches=tuple(SimpleNamespace(query=q, chunks=tuple(chunks)) for q, chunks in searches),
        reply=reply, answered_by_model=by_model)


def chunk(text, source=None):
    return Document(page_content=text, metadata={} if source is None else {"source": source})


def section(case_id, out):
    """The section text of one case, built the way the eval builds it."""
    r = fwh.run_case(fwh.CASES[case_id], lambda case, on_token: out)
    assert r["error"] is None, r["error"]
    return "\n".join(r["section"])


def forks_outcome():
    p = plan("TOOL", (FOOD, {"item": "forks", "guests": 90}))
    return outcome(p, tools=[(FOOD, {"item": "forks", "guests": 90}, "ok", FORKS_TEXT)], reply=FORKS_TEXT)


# ---------------------------------------------------------------- LOG-1 TOOL turn

def test_log_1_tool_turn_has_all_six_subsections_in_order():
    """Covers: AC-19 (right), LOG-1. A TOOL turn's section has Input, Planner, Tools, Retrieved, Answer,
    Verdict, in that order, under its own heading."""
    text = section("CALL-1", forks_outcome())
    assert text.startswith("## CALL-1")
    positions = [text.index(h) for h in fwh.SUBSECTIONS]
    assert positions == sorted(positions)


def test_log_1_tool_turn_shows_name_arguments_status_and_exact_text():
    """Covers: AC-19 (right), LOG-1. The Tools sub-section shows the tool's name, arguments, status and exact
    text."""
    text = section("CALL-1", forks_outcome())
    tools = text.split("### Tools")[1].split("### Retrieved")[0]
    assert FOOD in tools
    assert "'guests': 90" in tools and "'item': 'forks'" in tools
    assert "ok" in tools
    assert FORKS_TEXT in tools


def test_log_1_tool_turn_has_retrieved_none():
    """Covers: AC-19 (right), LOG-1. A turn with no search shows Retrieved: none."""
    text = section("CALL-1", forks_outcome())
    retrieved = text.split("### Retrieved")[1].split("### Answer")[0]
    assert retrieved.strip() == "none"


def test_log_1_input_answer_and_verdict_parts():
    """Covers: AC-19 (right), LOG-1. Input has id, area, question and 'history: none'; Answer has the reply
    verbatim, answered_by_model and the times; Verdict is pass with '-' for failed checks."""
    text = section("CALL-1", forks_outcome())
    inp = text.split("### Input")[1].split("### Planner")[0]
    assert "CALL-1" in inp and "CALL" in inp
    assert fwh.CASES["CALL-1"]["question"] in inp
    assert "history: none" in inp
    ans = text.split("### Answer")[1].split("### Verdict")[0]
    assert FORKS_TEXT in ans
    assert "answered_by_model: no" in ans
    assert "time to first piece" in ans and "total time" in ans
    verdict = text.split("### Verdict")[1]
    assert "pass" in verdict and "failed checks -" in verdict


def test_log_1_planner_shows_first_and_final_plan_not_retried():
    """Covers: AC-19 (right), LOG-1. Planner shows first plan, rejected: none, retried: no, final plan."""
    text = section("CALL-1", forks_outcome())
    planner = text.split("### Planner")[1].split("### Tools")[0]
    assert "first plan" in planner and "final plan" in planner
    assert "rejected: none" in planner
    assert "retried: no" in planner
    assert planner.count(FOOD) == 2


def test_log_1_a_failing_turn_names_the_failed_checks():
    """Covers: AC-19 (wrong), LOG-1. A turn that fails shows 'fail' and the names of the failed checks."""
    p = plan("DOCS", (SEARCH, {"query": "forks"}))
    out = outcome(p, searches=[("forks", [chunk("Forks are on the rack.", "data/food.md")])], reply="x", by_model=True)
    text = section("CALL-1", out)
    verdict = text.split("### Verdict")[1]
    assert "fail" in verdict
    assert "route" in verdict and "tools" in verdict
    assert "failed checks -" not in verdict


def test_log_1_a_part_that_does_not_apply_says_none():
    """Covers: AC-19 (boundary), LOG-1. A turn with no tools shows 'none' under Tools."""
    p = plan("DOCS", (SEARCH, {"query": "napkins iced tea"}))
    out = outcome(p, searches=[("napkins iced tea", [chunk("Napkins.", "data/a.md")])], reply="r", by_model=True)
    tools = section("CALL-6", out).split("### Tools")[1].split("### Retrieved")[0]
    assert tools.strip() == "none"


# ---------------------------------------------------------------- LOG-2 follow-up with searches

def croissant_outcome():
    first = chunk("C" * 300, "data/food/croissants.md")
    second = chunk("Second chunk text.")
    p = plan("DOCS", (SEARCH, {"query": "where are the croissants kept"}))
    return outcome(p, searches=[("where are the croissants kept", [first, second])],
                   reply="Croissants are on the rack.", by_model=True)


def test_log_2_input_shows_history_turns_verbatim():
    """Covers: AC-19 (right), LOG-2. A follow-up's Input shows both history turns as 'role: content'."""
    text = section("FD-1", croissant_outcome())
    inp = text.split("### Input")[1].split("### Planner")[0]
    for h in fwh.H_FORKS:
        assert f"{h['role']}: {h['content']}" in inp
    assert fwh.CASES["FD-1"]["question"] in inp
    assert "history: none" not in inp


def test_log_2_retrieved_shows_query_sources_and_120_char_previews():
    """Covers: AC-19 (right), LOG-2 (boundary). Retrieved shows the query and each source with exactly the
    first 120 characters of its chunk."""
    text = section("FD-1", croissant_outcome())
    retrieved = text.split("### Retrieved")[1].split("### Answer")[0]
    assert "where are the croissants kept" in retrieved
    assert "data/food/croissants.md" in retrieved
    assert "C" * 120 in retrieved
    assert "C" * 121 not in retrieved


def test_log_2_chunk_without_source_is_unknown():
    """Covers: AC-19 (wrong), LOG-2. A chunk with no source is shown as 'unknown', with its preview."""
    text = section("FD-1", croissant_outcome())
    retrieved = text.split("### Retrieved")[1].split("### Answer")[0]
    assert "unknown" in retrieved
    assert "Second chunk text." in retrieved


def test_log_2_short_chunk_preview_is_whole_text():
    """Covers: AC-19 (boundary), LOG-2. A chunk shorter than 120 characters is shown whole."""
    p = plan("DOCS", (SEARCH, {"query": "croissant where"}))
    out = outcome(p, searches=[("croissant where", [chunk("Short.", "data/a.md")])], reply="r", by_model=True)
    assert "Short." in section("FD-1", out)


def test_log_2_search_with_no_chunks_says_so():
    """Covers: AC-19 (boundary), LOG-2. A search that returns nothing is shown with its query and says so."""
    p = plan("DOCS", (SEARCH, {"query": "croissant where"}))
    out = outcome(p, searches=[("croissant where", [])], reply="r")
    retrieved = section("FD-1", out).split("### Retrieved")[1].split("### Answer")[0]
    assert "croissant where" in retrieved
    assert "no chunks" in retrieved.lower()


def test_log_2_tools_say_none_and_two_searches_both_shown():
    """Covers: AC-19 (right), LOG-2. A docs turn: Tools says none; two searches show both queries."""
    p = plan("DOCS", (SEARCH, {"query": "croissant where"}), (SEARCH, {"query": "croissant kept"}))
    out = outcome(p, searches=[("croissant where", [chunk("A.", "data/a.md")]),
                               ("croissant kept", [chunk("B.", "data/b.md")])], reply="r", by_model=True)
    text = section("FD-1", out)
    assert text.split("### Tools")[1].split("### Retrieved")[0].strip() == "none"
    retrieved = text.split("### Retrieved")[1].split("### Answer")[0]
    assert "croissant where" in retrieved and "croissant kept" in retrieved
    assert "data/a.md" in retrieved and "data/b.md" in retrieved


# ---------------------------------------------------------------- LOG-3 retried turn

def retried_outcome():
    first = plan("TOOL", (FOOD, {"item": "forks", "guests": 100}))
    final = plan("TOOL", (FOOD, {"item": "forks"}))
    need = "How many guests?"
    return outcome(final, first=first,
                   rejected=[SimpleNamespace(name=FOOD, args={"item": "forks", "guests": 100},
                                             invented={"guests": (100,)})],
                   retried=True, tools=[(FOOD, {"item": "forks"}, "need_info", need)], reply=need)


def test_log_3_planner_shows_first_plan_rejected_values_retried_and_final_plan():
    """Covers: AC-19 (right), LOG-3. The Planner sub-section shows the first plan with guests 100, the
    rejected values, retried: yes, and the final plan without guests."""
    text = section("FT-6", retried_outcome())
    planner = text.split("### Planner")[1].split("### Tools")[0]
    assert "retried: yes" in planner
    assert "(100,)" in planner
    assert "'guests': 100" in planner
    first_part, final_part = planner.split("final plan")
    assert "'guests': 100" in first_part
    assert "guests" not in final_part
    assert "rejected: none" not in planner


def test_log_3_tools_show_the_arguments_that_ran():
    """Covers: AC-19 (right), LOG-3. The Tools sub-section shows the need_info call that ran, without guests."""
    text = section("FT-6", retried_outcome())
    tools = text.split("### Tools")[1].split("### Retrieved")[0]
    assert "need_info" in tools and "How many guests?" in tools
    assert "'guests'" not in tools


# ---------------------------------------------------------------- LOG-4 isolation and report

class _Exploding:
    """An outcome whose section cannot be built: reading .tools raises."""

    plan = plan("TOOL", (FOOD, {"item": "forks", "guests": 90}))
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
    outs = {"CALL-1": forks_outcome(), "CALL-2": _Exploding(), "CALL-3": forks_outcome()}
    return [fwh.run_case(fwh.CASES[cid], lambda case, on_token, o=o: o) for cid, o in outs.items()]


def test_log_4_a_case_that_raises_is_recorded_as_error_and_failed():
    """Covers: AC-19 (wrong), LOG-4. The second case's section holds the error message; its report line says
    fail and carries the message."""
    results = three_results()
    bad = results[1]
    assert bad["error"] is not None and "boom while building the section" in bad["error"]
    assert "boom while building the section" in "\n".join(bad["section"])
    assert "CALL-2" in bad["line"] and "fail" in bad["line"] and "boom" in bad["line"]


def test_log_4_the_run_goes_on_after_an_error():
    """Covers: AC-19 (right), LOG-4. The first and third sections are fully written."""
    results = three_results()
    for good in (results[0], results[2]):
        assert good["error"] is None
        text = "\n".join(good["section"])
        for h in fwh.SUBSECTIONS:
            assert h in text


def test_log_4_a_case_that_raises_while_running_is_recorded():
    """Covers: AC-19 (wrong), LOG-4. A run_turn that raises is recorded the same way."""
    def boom(case, on_token):
        raise ValueError("model gone")

    r = fwh.run_case(fwh.CASES["CALL-1"], boom)
    assert "model gone" in r["error"] and "model gone" in "\n".join(r["section"])


def test_log_4_report_counts_the_error_case_as_failed():
    """Covers: AC-19 (right), LOG-4. The per-area count is 2 of 3: the error case is not a pass."""
    report = fwh.build_report(three_results())
    assert "CALL: 2 of 3 passed" in report
    assert report.count("CALL-1: pass") == 1 and "CALL-2: fail" in report and "CALL-3: pass" in report


def test_log_4_log_file_has_sections_in_case_order_and_report(tmp_path):
    """Covers: AC-19 (right), LOG-4. write_log creates the folder, names the file
    food_wiring_<timestamp>.md, writes all three sections in order and the report."""
    results = three_results()
    report = fwh.build_report(results)
    path = fwh.write_log(results, report, tmp_path / "logs")
    assert path.parent == tmp_path / "logs"
    assert path.name.startswith("food_wiring_") and path.suffix == ".md"
    text = path.read_text(encoding="utf-8")
    assert text.index("## CALL-1") < text.index("## CALL-2") < text.index("## CALL-3")
    assert "boom while building the section" in text
    assert report in text


def test_log_4_writing_touches_only_the_log_dir(tmp_path):
    """Covers: AC-19 (boundary), LOG-4. Nothing but the log folder is created."""
    results = three_results()
    fwh.write_log(results, fwh.build_report(results), tmp_path / "logs")
    assert [p.name for p in tmp_path.iterdir()] == ["logs"]
    assert len(list((tmp_path / "logs").iterdir())) == 1


@pytest.mark.parametrize("first_piece", [True, False])
def test_log_time_to_first_piece(first_piece):
    """Covers: AC-19 (boundary), LOG-1. A turn that streamed shows a first-piece time; one that never called
    on_token shows 'none'."""
    out = forks_outcome()

    def run_turn(case, on_token):
        if first_piece:
            on_token("x")
        return out

    r = fwh.run_case(fwh.CASES["CALL-1"], run_turn)
    answer = "\n".join(r["section"]).split("### Answer")[1].split("### Verdict")[0]
    line = next(ln for ln in answer.splitlines() if "time to first piece" in ln)
    assert ("none" not in line) == first_piece
