"""Spec 047 section 6.4 LINEN (AC-8, eval): real Claude planner, scored by spec 045 section 4.6 (route, tool names,
the always call run through run_always_tool, and the missing item for need_info). Threshold: at least 4 of 5.

Marked eval; skips when ANTHROPIC_API_KEY or GOOGLE_API_KEY is unset or .chroma/ is missing.
"""
from __future__ import annotations

from collections import Counter

import pytest

from blc.tools.always_tools import run_always_tool

pytestmark = pytest.mark.eval

ALWAYS = "calculate_always_items"
SEARCH = "search_documents"
THRESHOLD = 4

# id: (question, expected status, expected counts, missing items)
CASES = {
    "LINEN-1": ("how many linens", "need_info", {}, ("tables",)),
    "LINEN-2": ("How many tablecloths for 6 tables?", "ok", {"black linens": 13, "purple napkins": 12}, ()),
    "LINEN-3": ("White linens for 5 tables?", "ok", {"white linens": 11, "purple napkins": 10}, ()),
    "LINEN-4": ("We have 3 tables with black linens and 2 with white linens. How many linens?", "ok",
                {"black linens": 7, "white linens": 5, "purple napkins": 10}, ()),
    "LINEN-5": ("How many white linens do I need?", "need_info", {}, ("tables",)),
}


def _failed_checks(plan, status, counts, missing):
    failed = set()
    if plan.route != "TOOL":
        failed.add("route")
    names = Counter(c.name for c in plan.calls if c.name != SEARCH)
    if names != Counter([ALWAYS]):
        failed.add("tools")
    calls = [c for c in plan.calls if c.name == ALWAYS]
    if not calls:
        failed.add("result")
        return failed
    result = run_always_tool(calls[0].args)
    if result.status != status or result.counts != counts:
        failed.add("result")
    elif status == "need_info" and not all(m.casefold() in result.text.casefold() for m in missing):
        failed.add("result")
    return failed


@pytest.fixture(scope="module")
def linen_results(eval_llm, eval_store):
    from blc.flow import run_planned_turn

    out = {}
    for cid, (question, status, counts, missing) in CASES.items():
        try:
            outcome = run_planned_turn(eval_llm, eval_store, question, None, on_token=lambda piece: None)
            out[cid] = _failed_checks(outcome.plan, status, counts, missing)
        except Exception as exc:  # recorded as a failed case; the run goes on
            out[cid] = {f"error: {type(exc).__name__}: {exc}"}
    print("\n" + "\n".join(f"{cid}: {'pass' if not f else 'fail ' + str(sorted(f))}" for cid, f in out.items()))
    return out


def test_linen_cases_meet_threshold(linen_results):
    """Covers: AC-8 (right), LINEN-1 to LINEN-5 (eval). At least 4 of the 5 LINEN cases pass."""
    assert len(linen_results) == 5
    bad = {cid: sorted(f) for cid, f in linen_results.items() if f}
    assert 5 - len(bad) >= THRESHOLD, f"LINEN {5 - len(bad)}/5; failed: {bad}"
