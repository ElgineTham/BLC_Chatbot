"""Spec 017 AC-3: the eval's scorer (section 4.3) on hand-made traces (EC-11, EC-12, EC-13, EC-18). Unit; no model, no store.

The scorer comes from conftest.py (fixture `score_case`); the judge is a recording fake that gives a fixed verdict
(verdicts are given, not computed). The grounding checks are the real `blc.judge` ones.
"""

from __future__ import annotations

import pytest

TOOL_TEXT = "9 gallons of decaf: 5 gal cambro x 2"
GOOD_TOOL_REPLY = "You need two 5 gal cambros for 9 gallons of decaf."
CHUNK = ("data/supplies/coffee.md", "Coffee supplies are underneath the coffee machine in the beverage room.")


def custom(path, question="Is the plan fine?", history=()):
    return {"id": "X", "path": path, "history": list(history), "question": question, "reference": "Required: ok."}


# ---- EC-11: one pass and one failure per stage ---------------------------------

def test_clean_tool_case_passes(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (right), EC-11. Right kind, passing verdict, grounded numbers and no citation pass a TOOL case."""
    t = make_trace("TOOL", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(True))
    assert s.passed is True and s.stages == ()


def test_clean_docs_case_passes(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (right), EC-11. A DOCS case with an allowed citation passes."""
    reply = "Underneath the coffee machine in the beverage room (data/supplies/coffee.md)."
    t = make_trace("DOCS", reply, chunks=[CHUNK])
    s = score_case(t, case_by_id["D1"], FakeJudge(True))
    assert s.passed is True and s.stages == ()


def test_clean_both_case_passes(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (right), EC-11. A BOTH case using chunk and tool material and citing a retrieved file passes."""
    reply = "Underneath the coffee machine (coffee.md). For 6 gallons of coffee: one 5 gal cambro plus one 1 gal cambro."
    t = make_trace("BOTH", reply, chunks=[CHUNK], tool_texts=["6 gallons of coffee: 5 gal cambro x 1, 1 gal cambro x 1"])
    s = score_case(t, case_by_id["M2"], FakeJudge(True))
    assert s.passed is True and s.stages == ()


def test_wrong_route_kind_fails_with_route(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. A trace whose route kind is not the case's path fails with stage `route`."""
    t = make_trace("DOCS", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(True))
    assert s.passed is False and s.stages == ("route",)


def test_wrong_kind_still_runs_the_other_checks(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. After a route failure the other checks still run (the judge is called)."""
    judge = FakeJudge(True)
    t = make_trace("BOTH", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], judge)
    assert s.stages == ("route",)
    assert len(judge.calls) == 1


def test_failing_verdict_fails_with_judge(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. A failing verdict gives stage `judge` only, and the reason is kept."""
    t = make_trace("TOOL", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(False, "extra fact"))
    assert s.passed is False and s.stages == ("judge",)
    assert "extra fact" in s.detail


def test_ungrounded_number_fails_with_numbers(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. A number in no allowed material fails with stage `numbers` and is reported."""
    t = make_trace("TOOL", "You need 3 cambros for 9 gallons of decaf.", tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(True))
    assert s.passed is False and s.stages == ("numbers",)
    assert s.ungrounded == ("3",)


def test_unknown_source_fails_with_sources(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. A cited .md file that was not retrieved fails with stage `sources` and is reported."""
    reply = "Underneath the coffee machine (data/supplies/syrups.md)."
    t = make_trace("DOCS", reply, chunks=[CHUNK])
    s = score_case(t, case_by_id["D1"], FakeJudge(True))
    assert s.passed is False and s.stages == ("sources",)
    assert s.unknown == ("data/supplies/syrups.md",)


def test_two_failures_list_both_stages(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. A failing verdict plus an ungrounded number list both stages."""
    t = make_trace("TOOL", "You need 3 cambros for 9 gallons of decaf.", tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(False))
    assert s.passed is False and set(s.stages) == {"judge", "numbers"} and len(s.stages) == 2


def test_all_four_failures_listed(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-11. Wrong kind, failing verdict, ungrounded number and unknown source are all listed."""
    t = make_trace("DOCS", "Use 41 things (data/supplies/syrups.md).", chunks=[CHUNK])
    s = score_case(t, case_by_id["D1"], FakeJudge(False))
    assert set(s.stages) == {"judge", "numbers", "sources"}
    t2 = make_trace("TOOL", "Use 41 things (data/supplies/syrups.md).", chunks=[CHUNK])
    s2 = score_case(t2, case_by_id["D1"], FakeJudge(False))
    assert set(s2.stages) == {"route", "judge", "numbers", "sources"}


def test_reply_none_does_not_crash(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (boundary). A trace with no reply is scored as an empty reply, not a crash."""
    t = make_trace("TOOL", None, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], FakeJudge(False))
    assert s.passed is False


# ---- EC-12: allowed material per path -------------------------------------------

NUM_REPLY = "Use 41 oz."


def test_number_only_in_chunk_passes_docs_fails_tool(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (right/wrong), EC-12. A number found only in a chunk passes a DOCS case but fails a TOOL case."""
    chunk = [("data/a.md", "Use 41 oz of it.")]
    docs = score_case(make_trace("DOCS", NUM_REPLY, chunks=chunk), custom("DOCS"), FakeJudge(True))
    tool = score_case(make_trace("TOOL", NUM_REPLY, chunks=chunk), custom("TOOL"), FakeJudge(True))
    assert docs.passed is True
    assert tool.passed is False and tool.stages == ("numbers",)


def test_number_only_in_tool_text_passes_tool_fails_docs(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (right/wrong), EC-12. A number found only in a tool text passes a TOOL case but fails a DOCS case."""
    tool = score_case(make_trace("TOOL", NUM_REPLY, tool_texts=["41 oz"]), custom("TOOL"), FakeJudge(True))
    docs = score_case(make_trace("DOCS", NUM_REPLY, tool_texts=["41 oz"]), custom("DOCS"), FakeJudge(True))
    assert tool.passed is True
    assert docs.passed is False and docs.stages == ("numbers",)


def test_both_path_accepts_either_source(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (right), EC-12. A BOTH case passes with the number in a chunk, in a tool text, or in both."""
    case = custom("BOTH")
    only_chunk = score_case(make_trace("BOTH", NUM_REPLY, chunks=[("data/a.md", "41 oz")]), case, FakeJudge(True))
    only_tool = score_case(make_trace("BOTH", NUM_REPLY, tool_texts=["41 oz"]), case, FakeJudge(True))
    both = score_case(
        make_trace("BOTH", "Use 41 oz and 52 cups.", chunks=[("data/a.md", "41 oz")], tool_texts=["52 cups"]),
        case, FakeJudge(True),
    )
    assert only_chunk.passed and only_tool.passed and both.passed


def test_both_path_fails_for_number_in_neither(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (wrong), EC-12. A BOTH case fails when the number is in no chunk and no tool text."""
    s = score_case(make_trace("BOTH", NUM_REPLY, chunks=[("data/a.md", "7 oz")], tool_texts=["8 oz"]),
                   custom("BOTH"), FakeJudge(True))
    assert s.stages == ("numbers",)


@pytest.mark.parametrize("path", ["TOOL", "DOCS", "BOTH"])
def test_number_only_in_question_passes_on_every_path(score_case, make_trace, FakeJudge, path):
    """Covers: AC-3 (right), EC-12. A number found only in the question passes on every path."""
    case = custom(path, question="Is 41 oz right?")
    s = score_case(make_trace(path, NUM_REPLY, chunks=[("data/a.md", "no digits")] if path != "TOOL" else (),
                              tool_texts=["no digits"] if path != "DOCS" else ()), case, FakeJudge(True))
    assert s.passed is True and s.ungrounded == ()


@pytest.mark.parametrize("path", ["TOOL", "DOCS", "BOTH"])
def test_number_only_in_history_passes_on_every_path(score_case, make_trace, FakeJudge, path):
    """Covers: AC-3 (right), EC-12. A number found only in the history's contents is allowed on every path."""
    history = [{"role": "user", "content": "I made 41 oz earlier."}, {"role": "assistant", "content": "ok"}]
    case = custom(path, history=history)
    s = score_case(make_trace(path, NUM_REPLY, history=history), case, FakeJudge(True))
    assert s.ungrounded == () and "numbers" not in s.stages


def test_a9_history_amount_is_allowed_but_would_not_be_in_tool_text(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (right), EC-12. A9's history holds 28 oz, so a reply repeating 28 passes the numbers check (the judge is what catches it)."""
    case = case_by_id["A9"]
    t = make_trace("TOOL", "Use 28 oz.", tool_texts=["5 gallons: 35 oz"], history=case["history"])
    s = score_case(t, case, FakeJudge(True))
    assert "numbers" not in s.stages


def test_tool_stage_without_tool_text_adds_nothing(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (boundary), EC-12. With no tool text (nothing was calculated) a number is not grounded by tools."""
    s = score_case(make_trace("TOOL", NUM_REPLY), custom("TOOL"), FakeJudge(True))
    assert s.stages == ("numbers",)


# ---- EC-13: sources per path ----------------------------------------------------

@pytest.mark.parametrize("cited", ["data/supplies/coffee.md", "coffee.md", "(source: nowhere.md)"])
def test_tool_case_citing_any_md_file_fails_sources(score_case, make_trace, FakeJudge, cited):
    """Covers: AC-3 (wrong), EC-13. A TOOL case whose reply cites any .md file fails with stage `sources`, even a retrieved one."""
    t = make_trace("TOOL", f"Two 5 gal cambros ({cited}).", chunks=[CHUNK], tool_texts=["5 gal cambro x 2"])
    s = score_case(t, custom("TOOL"), FakeJudge(True))
    assert s.passed is False and s.stages == ("sources",)
    assert s.unknown


def test_tool_case_without_citation_passes_sources(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (right), EC-13. A TOOL reply with no citation has no source failure."""
    s = score_case(make_trace("TOOL", "Two 5 gal cambros.", tool_texts=["5 gal cambro x 2"]), custom("TOOL"), FakeJudge(True))
    assert s.passed is True


@pytest.mark.parametrize("path", ["DOCS", "BOTH"])
def test_docs_and_both_allow_retrieved_sources_only(score_case, make_trace, FakeJudge, path):
    """Covers: AC-3 (right/wrong), EC-11, EC-13. DOCS and BOTH accept a retrieved file (even by short name) and reject others."""
    tool = ["no digits"] if path == "BOTH" else ()
    ok = score_case(make_trace(path, "See coffee.md.", chunks=[CHUNK], tool_texts=tool), custom(path), FakeJudge(True))
    bad = score_case(make_trace(path, "See syrups.md.", chunks=[CHUNK], tool_texts=tool), custom(path), FakeJudge(True))
    assert ok.passed is True
    assert bad.stages == ("sources",) and bad.unknown == ("syrups.md",)


def test_docs_citation_with_nothing_retrieved_fails(score_case, make_trace, FakeJudge):
    """Covers: AC-3 (wrong/boundary), EC-13. With no retrieved chunks any citation is unknown."""
    s = score_case(make_trace("DOCS", "See coffee.md."), custom("DOCS"), FakeJudge(True))
    assert s.stages == ("sources",)


# ---- EC-18: the judge is called with the case's path; calibration gate ----------

@pytest.mark.parametrize("cid, path", [("A1", "TOOL"), ("D1", "DOCS"), ("M2", "BOTH")])
def test_judge_is_called_with_the_cases_path(score_case, make_trace, FakeJudge, case_by_id, cid, path):
    """Covers: AC-3 (right), EC-18. The scorer calls the judge once with the case's question, reference, the reply and its path."""
    case = case_by_id[cid]
    judge = FakeJudge(True)
    score_case(make_trace(path, "Some reply."), case, judge)
    assert len(judge.calls) == 1
    call = judge.calls[0]
    assert call["path"] == path
    assert call["question"] == case["question"] and call["reference"] == case["reference"]
    assert call["answer"] == "Some reply."


def test_judge_path_is_the_cases_not_the_routes(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-18. When the route kind differs the judge still gets the case's path."""
    judge = FakeJudge(True)
    score_case(make_trace("DOCS", "Reply."), case_by_id["A1"], judge)
    assert judge.calls[0]["path"] == "TOOL"


def test_uncalibrated_judge_grades_nothing(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (wrong), EC-18. With failed J ids no case is graded: it fails, the message names the ids, the judge is not called."""
    judge = FakeJudge(True)
    t = make_trace("TOOL", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    s = score_case(t, case_by_id["A1"], judge, failed_calibration=("J3", "J7"))
    assert s.passed is False
    assert "J3" in s.detail and "J7" in s.detail
    assert judge.calls == []


def test_uncalibrated_judge_fails_even_a_perfect_case(score_case, make_trace, FakeJudge, case_by_id):
    """Covers: AC-3 (boundary), EC-18. A single failed J id is enough to fail an otherwise perfect case."""
    t = make_trace("TOOL", GOOD_TOOL_REPLY, tool_texts=[TOOL_TEXT])
    assert score_case(t, case_by_id["A1"], FakeJudge(True)).passed is True
    assert score_case(t, case_by_id["A1"], FakeJudge(True), failed_calibration=("J1",)).passed is False


# ---- the case data itself (section 6) ------------------------------------------

def test_case_counts_and_paths(cases):
    """Covers: AC-5, AC-6, AC-7 (boundary). There are 10 cases per path: A1-A10 TOOL, D1-D10 DOCS, M1-M10 BOTH."""
    by_path = {}
    for c in cases:
        by_path.setdefault(c["path"], []).append(c["id"])
    assert by_path == {
        "TOOL": [f"A{i}" for i in range(1, 11)],
        "DOCS": [f"D{i}" for i in range(1, 11)],
        "BOTH": [f"M{i}" for i in range(1, 11)],
    }


def test_follow_up_cases_have_history(case_by_id):
    """Covers: AC-5 (boundary). A9 and A10 are follow-ups with a history; the others have none."""
    assert len(case_by_id["A9"]["history"]) == 2 and len(case_by_id["A10"]["history"]) == 2
    assert all(c["history"] == [] for cid, c in case_by_id.items() if cid not in ("A9", "A10"))
