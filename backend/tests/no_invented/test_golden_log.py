"""Spec 021, AC-7 and revision 2 (unit): the golden eval's log writer and report, with no model.

Uses fake outcomes and real-shaped tool results (Fraction amounts, lines whose quantity is None for tick items).
"""
from fractions import Fraction
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

BEV = "calculate_bev_item"
REC = "scale_recipe"


@pytest.fixture
def by_id(golden_cases):
    return {c["id"]: c for c in golden_cases}


def _plan(route, calls=()):
    return SimpleNamespace(route=route, calls=[SimpleNamespace(name=n, args=a) for n, a in calls])


def _outcome(route="TOOL", calls=(), searches=(), rejected=(), retried=False, reply="Bring it."):
    plan = _plan(route, calls)
    tools = tuple(SimpleNamespace(name=n, args=a, status="ok", text="") for n, a in calls if n != "search_documents")
    srch = tuple(SimpleNamespace(query=q, chunks=tuple(Document(page_content="x", metadata={"source": s})
                                                        for s in srcs)) for q, srcs in searches)
    return SimpleNamespace(plan=plan, first_plan=plan, tools=tools, searches=srch, rejected=tuple(rejected),
                           retried=retried, reply=reply)


def _runner(outcome):
    return lambda case, on_token: outcome


class ExplodingOutcome:
    """An outcome whose attributes raise only when the log formatter reads them (scoring reads plan/tools first)."""

    def __init__(self, good):
        self._good = good

    plan = property(lambda self: self._good.plan)
    tools = property(lambda self: self._good.tools)
    searches = property(lambda self: self._good.searches)
    rejected = property(lambda self: self._good.rejected)
    retried = property(lambda self: self._good.retried)

    @property
    def first_plan(self):
        raise RuntimeError("boom in formatting")

    reply = "x"


def _g8_outcome():
    return _outcome("TOOL", [(BEV, {"item": "everything", "drinks": ["decaf"], "guests": 55})])


def _g8_result(mkres):
    """Real shape: Fraction amounts and tick lines whose quantity is None."""
    return mkres.bev([("Decaf", Fraction(2))],
                     [("2 gal cambro", Fraction(1)), ("hot-cups", Fraction(105)), ("Stir sticks", Fraction(1)),
                      ("Sugar", Fraction(1)), ("Cocktail napkins", None), ("Creamer", None)])


def test_none_line_quantity_shows_bring_and_does_not_raise(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (right), revision 2 item 1/3. A bev result with quantity=None lines gives a part 3 section
    that shows 'bring' and keeps the real facts, without raising."""
    r = golden_log.run_case(scorer, by_id["G8"], _runner(_g8_outcome()), lambda n, a: _g8_result(mkres))
    assert r["error"] is None
    sec = "\n".join(r["section"])
    part3 = sec.split("### Part 3, required outcome")[1].split("### Answer")[0]
    assert "bring" in part3
    assert "required" in part3 and "actual" in part3
    assert "(subset match)" in part3 and "(Stir sticks: 1)" in part3
    assert r["score"]["part3"] is True           # extra tick lines are allowed by the everything subset rule


def test_none_quantity_does_not_break_the_exact_comparison(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (boundary), revision 2 item 1. A None quantity in an exact-match item (cambros) is shown as
    'bring', fails that fact, and raises nothing."""
    out = _outcome("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85})])
    res = mkres.bev([("Brewed hot cider", Fraction(3))], [("5 gal cambro", Fraction(1)), ("5 gal cambro", None)])
    r = golden_log.run_case(scorer, by_id["G1"], _runner(out), lambda n, a: res)
    assert r["error"] is None
    part3 = "\n".join(r["section"]).split("### Part 3, required outcome")[1]
    assert "bring" in part3
    assert any(l.startswith("  - lines (exact match)") and l.endswith(": fail") for l in part3.splitlines())
    assert r["score"]["part3"] is False


def test_none_drink_recipe_and_ingredient_amounts_are_guarded(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (boundary), revision 2 item 1. None drink gallons, recipe gallons and ingredient amount are
    shown without raising, and the fact fails."""
    out = _outcome("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85})])
    r = golden_log.run_case(scorer, by_id["G1"], _runner(out),
                            lambda n, a: mkres.bev([("Brewed hot cider", None)], [("5 gal cambro", Fraction(1))]))
    assert r["error"] is None and r["score"]["part3"] is False
    out = _outcome("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5})])
    r = golden_log.run_case(scorer, by_id["G6"], _runner(out), lambda n, a: mkres.rec(None, None))
    assert r["error"] is None and r["score"]["part3"] is False
    part3 = "\n".join(r["section"]).split("### Part 3, required outcome")[1]
    assert "bring" in part3 or "None" in part3


def test_fraction_amounts_are_shown_by_value(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (right), revision 2 item 3. Fraction(35, 2) oz is shown as 17.5 (never 35/2) and passes."""
    out = _outcome("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5})])
    r = golden_log.run_case(scorer, by_id["G6"], _runner(out),
                            lambda n, a: mkres.rec(Fraction(5, 2), Fraction(35, 2)))
    part3 = "\n".join(r["section"]).split("### Part 3, required outcome")[1].split("### Answer")[0]
    assert "17.5" in part3 and "35/2" not in part3 and "5/2" not in part3
    facts = [l for l in part3.splitlines() if l.startswith("  - ") and "required" in l]
    assert facts and all(l.endswith(": pass") for l in facts)


def test_fraction_amount_on_a_wrong_value_shows_fail(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (wrong), revision 2 item 3. Wrong concentrate (17 oz) shows its actual value and a fail."""
    out = _outcome("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5})])
    r = golden_log.run_case(scorer, by_id["G6"], _runner(out),
                            lambda n, a: mkres.rec(Fraction(5, 2), Fraction(17)))
    part3 = "\n".join(r["section"]).split("### Part 3, required outcome")[1]
    assert any(l.startswith("  - lemon concentrate oz") and "17" in l and l.endswith(": fail")
               for l in part3.splitlines())


def test_formatting_error_is_recorded_and_the_next_case_still_written(golden_log, scorer, by_id, mkres, tmp_path):
    """Covers: AC-7 (wrong), revision 2 item 2/3. A case whose formatting raises is recorded as an error in its
    section and report line, counts as failed, and the next case is still written."""
    bad = ExplodingOutcome(_g8_outcome())
    ok_out = _outcome("DOCS", [], searches=[("coffee", ["data/supplies/coffee.md"])])
    tool = lambda n, a: _g8_result(mkres)
    r1 = golden_log.run_case(scorer, by_id["G8"], _runner(bad), tool)
    r2 = golden_log.run_case(scorer, by_id["L1"], _runner(ok_out), tool)
    assert r1["error"] and "boom in formatting" in r1["error"]
    assert r1["outcome"] is None and r1["score"] is None
    assert r2["error"] is None and r2["score"]["passed"] is True
    report = golden_log.report([r1, r2])
    assert "G8: fail" in report and "boom in formatting" in report and "L1: pass" in report
    path = golden_log.write_log([r1, r2], report, tmp_path)
    text = path.read_text(encoding="utf-8")
    g8, l1 = text.split("## G8")[1].split("## L1")
    assert "- Error:" in g8 and "boom in formatting" in g8
    assert by_id["L1"]["question"] in l1 and "### Verdict" in l1


def test_run_error_is_recorded_and_the_run_continues(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (wrong). A turn that raises is recorded with its message; the next case runs normally."""
    def boom(case, on_token):
        raise ValueError("model down")

    r1 = golden_log.run_case(scorer, by_id["G8"], boom, lambda n, a: None)
    r2 = golden_log.run_case(scorer, by_id["G8"], _runner(_g8_outcome()), lambda n, a: _g8_result(mkres))
    assert "ValueError: model down" in r1["error"] and r1["outcome"] is None
    assert r2["error"] is None


def test_scoring_error_is_recorded_as_a_failed_case(golden_log, scorer, by_id):
    """Covers: AC-7 (wrong), revision 2 item 2. If the tool re-run function raises while scoring, the case is
    recorded as an error and fails; nothing propagates."""
    def tool(n, a):
        raise RuntimeError("tool exploded")

    r = golden_log.run_case(scorer, by_id["G8"], _runner(_g8_outcome()), tool)
    assert r["error"] is not None or r["score"]["passed"] is False
    assert golden_log.report([r])          # building the report does not raise


def test_report_totals_count_passes_parts_retries_and_drops(golden_log, scorer, by_id, mkres):
    """Covers: AC-7 (right). One line per case, per-path pass counts, per-part counts, first-plan inventions,
    retries and still-dropped values."""
    good = _outcome("TOOL", [(BEV, {"item": "everything", "drinks": ["decaf"], "guests": 55})])
    # G1 retried: the planned call had gallons [0] (invented), the run call dropped it.
    planned = _plan("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85, "gallons": [0]})])
    dropped = _outcome("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85})],
                       rejected=[SimpleNamespace(name=BEV, args={}, invented={"gallons": (0,)})], retried=True)
    dropped.first_plan = planned
    dropped.plan = planned
    r_g8 = golden_log.run_case(scorer, by_id["G8"], _runner(good), lambda n, a: _g8_result(mkres))
    r_g1 = golden_log.run_case(
        scorer, by_id["G1"], _runner(dropped),
        lambda n, a: mkres.bev([("Brewed hot cider", Fraction(3))], [("5 gal cambro", Fraction(1))]))
    rep = golden_log.report([r_g8, r_g1])
    lines = rep.splitlines()
    assert lines[0].startswith("G8: pass") and "route=TOOL" in lines[0] and "retried=no" in lines[0]
    assert "part1=pass" in lines[0] and "part2=pass" in lines[0] and "part3=pass" in lines[0]
    assert lines[1].startswith("G1: pass") and "retried=yes" in lines[1]
    assert "TOOL: 2 of 10 passed" in rep
    assert "DOCS: 0 of 10 passed" in rep and "BOTH: 0 of 10 passed" in rep
    assert "First plans that invented a number: 1" in rep
    assert "Cases that retried: 1" in rep
    assert "still dropped a value after the retry: 1" in rep
