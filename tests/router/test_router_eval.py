"""AC-5 (spec 010) and spec 006/007 router evals, all through route_faithfully with the real model.

Marked eval; skips (does not fail) when Ollama is not running (NFR-3). Read only.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.eval

F_CASES = [
    {"id": "F1", "history": [], "question": "I need 5 gallons of coffee and lemonade. How many cambros?",
     "contains": ("coffee", "lemonade", "5", "cambros"), "absent": ()},
    {"id": "F2", "history": [],
     "question": "We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros?",
     "contains": ("package", "70", "cambros"), "absent": ()},
    {"id": "F3", "history": [], "question": "Brewed hot cider for 100 people, what goes on the pull sheet?",
     "contains": ("pull sheet", "100"), "absent": ("gallons",)},
    {"id": "F4",
     "history": [
         {"role": "user", "content": "How many cambros do I need for coffee and lemonade?"},
         {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
     ],
     "question": "5 gallons each.", "contains": ("coffee", "lemonade", "5"), "absent": ()},
    {"id": "F6",
     "history": [
         {"role": "user", "content": "Where is the coffee?"},
         {"role": "assistant", "content": "Under the coffee machine in the beverage room."},
     ],
     "question": "How many hot cups do I need for 130 guests?", "contains": ("130", "cups"), "absent": ()},
    {"id": "F7",
     "history": [
         {"role": "user", "content": "How many cups for the coffee, decaf, tea, iced water & juice package?"},
         {"role": "assistant", "content": "How many guests?"},
     ],
     "question": "85 guests.", "contains": ("package", "85", "cups"), "absent": ()},
]
F5 = {
    "id": "F5", "history": [],
    "question": "Where is the creamer kept, and do I bring sugar for the decaf for 60 guests?",
}


def _norm(text: str) -> str:
    text = re.sub(r"\s+", " ", text.casefold()).strip()
    return text.strip(" \t.,;:!?\"'()[]")


@pytest.mark.parametrize("case", F_CASES, ids=[c["id"] for c in F_CASES])
def test_f_cases_one_tool_part_keeps_the_users_words(chat_llm, case):
    """Covers: AC-5 (right/wrong per case F1-F4, F6, F7), NFR-3 (skip). Exactly one TOOL part holding the listed words; fallback False. Reports whether unfaithful was set."""
    from blc.router import route_faithfully

    d = route_faithfully(chat_llm, case["history"], case["question"])
    texts = [p.text for p in d.parts]
    print(f"{case['id']}: unfaithful={d.unfaithful} parts={[(p.route, p.text) for p in d.parts]}")
    assert d.fallback is False, f"{case['id']}: unreadable reply. Parts: {texts}"
    assert len(d.parts) == 1, f"{case['id']}: expected one part, got {texts}"
    assert d.parts[0].route == "TOOL", f"{case['id']}: expected TOOL, got {d.parts[0].route}. Parts: {texts}"
    low = d.parts[0].text.casefold()
    for needed in case["contains"]:
        assert needed in low, f"{case['id']}: {d.parts[0].text!r} lacks {needed!r}"
    for banned in case["absent"]:
        assert banned not in low, f"{case['id']}: {d.parts[0].text!r} must not contain {banned!r}"


def test_f5_docs_then_tool_with_parts_inside_the_question(chat_llm):
    """Covers: AC-5 (right), F5, NFR-3 (skip). DOCS then TOOL; each part's text is inside the question (rule V)."""
    from blc.router import route_faithfully

    d = route_faithfully(chat_llm, F5["history"], F5["question"])
    texts = [p.text for p in d.parts]
    print(f"F5: unfaithful={d.unfaithful} parts={[(p.route, p.text) for p in d.parts]}")
    assert d.fallback is False, f"F5: unreadable reply. Parts: {texts}"
    assert tuple(p.route for p in d.parts) == ("DOCS", "TOOL"), f"F5: parts {texts}"
    q = _norm(F5["question"])
    for t in texts:
        assert _norm(t) in q, f"F5: part {t!r} is not inside the question"


def test_router_routes(chat_llm, router_case):
    """Covers: AC-5 (right/wrong per case, groups A to D and R1 to R14), NFR-3 (skip). Through route_faithfully the real model gives exactly the listed routes, in order, with fallback False."""
    from blc.router import route_faithfully

    case = router_case
    decision = route_faithfully(chat_llm, case["history"], case["question"])
    got = tuple(p.route for p in decision.parts)
    texts = [p.text for p in decision.parts]
    print(f"{case['id']}: unfaithful={decision.unfaithful}")
    assert got in case["routes"], f"{case['id']}: routes {got} not in {case['routes']}. Parts: {texts}"
    assert decision.fallback is False, f"{case['id']}: router reply could not be read. Parts: {texts}"

    for needed in case.get("text_must_contain", ()):
        assert needed in decision.parts[0].text.casefold(), (
            f"{case['id']}: rewritten text {decision.parts[0].text!r} lacks {needed!r}"
        )


def test_group_e_recipe_plus_guests(chat_llm, group_e_cases):
    """Covers: AC-5 (right), group E, NFR-3 (skip). At least 2 of the 3 group E cases give DOCS then TOOL with fallback False; the failure message lists each case's id, routes and parts' text."""
    from blc.router import route_faithfully

    passed, report = 0, []
    for case in group_e_cases:
        decision = route_faithfully(chat_llm, case["history"], case["question"])
        got = tuple(p.route for p in decision.parts)
        texts = [p.text for p in decision.parts]
        report.append(f"{case['id']}: routes={got} fallback={decision.fallback} unfaithful={decision.unfaithful} texts={texts}")
        if got in case["routes"] and decision.fallback is False:
            passed += 1
    assert passed >= 2, f"group E: only {passed} of {len(group_e_cases)} passed:\n" + "\n".join(report)
