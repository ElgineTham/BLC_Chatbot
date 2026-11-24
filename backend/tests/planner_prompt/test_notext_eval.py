"""Spec 046 section 6.2 NOTEXT-1 to NOTEXT-3 (AC-5), scored by section 4.3, from the real planned flow.

Marked eval; skips when ANTHROPIC_API_KEY or GOOGLE_API_KEY is unset or .chroma/ is missing. Writes nothing.
A case that raises counts as failed.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval

SERVING = "calculate_serving_utensils"
SEARCH = "search_documents"
THRESHOLD = 2

CASES = [
    ("NOTEXT-1", "Which tongs for the tabbouleh?", "tabbouleh"),
    ("NOTEXT-2", "What serving utensils do I need for the scones?", "scone"),
    ("NOTEXT-3", "Which serving spoons for the roasted breakfast potatoes?", "potato"),
]


def score_notext(plan, keyword):
    """Set of failed checks of section 4.3 (empty set = pass)."""
    failed = set()
    if plan.fallback:
        failed.add("fallback")
    if plan.route != "TOOL":
        failed.add("route")
    tool_calls = [c for c in plan.calls if c.name != SEARCH]
    if [c.name for c in tool_calls] != [SERVING]:
        failed.add("tools")
        return failed
    args = tool_calls[0].args if isinstance(tool_calls[0].args, dict) else {}
    items = args.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        failed.add("items")
        return failed
    entry = items[0]
    if keyword not in str(entry.get("food", "")).casefold():
        failed.add("food")
    if "qty" in entry and entry.get("qty") is not None:
        failed.add("qty")
    return failed


@pytest.fixture(scope="module")
def notext_results(eval_llm, eval_store):
    from blc.flow import run_planned_turn

    results = {}
    for cid, question, keyword in CASES:
        try:
            outcome = run_planned_turn(eval_llm, eval_store, question)
            results[cid] = score_notext(outcome.plan, keyword)
        except Exception as exc:  # recorded and counted as failed
            results[cid] = {f"error: {exc!r}"}
    print("\nNOTEXT: " + ", ".join(f"{cid}: {'pass' if not f else 'fail ' + str(sorted(f))}"
                                    for cid, f in results.items()))
    return results


def test_notext_cases_meet_threshold(notext_results):
    """Covers: AC-5 (right), NOTEXT-1, NOTEXT-2, NOTEXT-3. At least 2 of 3 cases get a serving-utensils-only
    TOOL plan with no fallback, one item containing the food and no qty."""
    passed = sum(1 for f in notext_results.values() if not f)
    bad = {cid: sorted(f) for cid, f in notext_results.items() if f}
    assert passed >= THRESHOLD, f"NOTEXT {passed}/3; failed: {bad}"


def test_scorer_rejects_text_fallback_and_qty():
    """Covers: AC-5 (wrong), section 4.3. The scorer fails a fallback search, a qty, and a wrong food; it passes a
    clean plan. Pure check of the scoring rules."""
    from types import SimpleNamespace as NS

    def plan(calls, route="TOOL", fallback=False):
        return NS(calls=[NS(name=n, args=a) for n, a in calls], route=route, fallback=fallback)

    good = plan([(SERVING, {"items": [{"food": "Tabbouleh"}]})])
    assert score_notext(good, "tabbouleh") == set()
    assert score_notext(plan([(SEARCH, {"query": "tongs"})], route="DOCS", fallback=True), "tabbouleh")
    assert "qty" in score_notext(plan([(SERVING, {"items": [{"food": "tabbouleh", "qty": 3}]})]), "tabbouleh")
    assert "food" in score_notext(plan([(SERVING, {"items": [{"food": "rice"}]})]), "tabbouleh")
    both = plan([(SERVING, {"items": [{"food": "tabbouleh"}]}), (SEARCH, {"query": "x"})], route="BOTH")
    assert score_notext(both, "tabbouleh")
