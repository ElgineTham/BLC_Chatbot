"""Spec 013 AC-6: route_fast eval on the real model (cases K1 to K31), timings reported.

Marked eval; skips (does not fail) when Ollama is not running (NFR-3). The model is warmed up once by the
`fast_llm` fixture (conftest.py) before any timing (NFR-7). Judged against the threshold (at least 28 of
31), not per case. No time limit applies: every case's time, parts and tools are printed.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.eval

BEV = "calculate_bev_item"
H_HOT_DECAF = [
    {"role": "user", "content": "How many cambros do I need for hot water and decaf?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]
H_OJ = [
    {"role": "user", "content": "How many cups do I need for the orange juice?"},
    {"role": "assistant", "content": "How many guests?"},
]
H_LEMON = [
    {"role": "user", "content": "Where is the lemon stored?"},
    {"role": "assistant", "content": "In the beverage cooler."},
]
H_COFFEE = [
    {"role": "user", "content": "Where is the coffee?"},
    {"role": "assistant", "content": "Under the coffee machine in the beverage room."},
]


def _k(cid, question, routes, history=(), contains=(), equals=False):
    """routes: tuple of 'DOCS'/'TOOL' per expected part."""
    return {"id": cid, "history": list(history), "question": question, "routes": tuple(routes),
            "contains": tuple(contains), "equals": equals}


K_CASES = [
    _k("K1", "Where do we keep the napkins?", ("DOCS",)),
    _k("K2", "What does Oatmilk come in?", ("DOCS",)),
    _k("K3", "How do I clean the coffee urn?", ("DOCS",)),
    _k("K4", "When does setup start for the 6 pm event?", ("DOCS",)),
    _k("K5", "Where do the 5 gallon cambros go?", ("DOCS",)),
    _k("K6", "How many cambro sizes do we have?", ("DOCS",)),
    _k("K7", "What's in the coffee, decaf, tea, iced water & juice package?", ("DOCS",)),
    _k("K8", "Thanks!", ("DOCS",)),
    _k("K9", "How many gallons of decaf should I make for 110 people?", ("TOOL",)),
    _k("K10", "Which cambros hold 9 gallons of orange juice?", ("TOOL",)),
    _k("K11", "How many cold cups do I need for 65 guests?", ("TOOL",)),
    _k("K12", "Do I bring creamer for the coffee?", ("TOOL",)),
    _k("K13", "What goes on the pull sheet for peach tea for 45 guests?", ("TOOL",)),
    _k("K14", "How many cups do I need for the iced water?", ("TOOL",)),
    _k("K15", "How many gallons do I make for about 50 people?", ("TOOL",)),
    _k("K16", "What do I need to bring?", ("TOOL",)),
    _k("K17", "Where is the creamer kept, and how many cups do I need for 55 guests?", ("DOCS", "TOOL")),
    _k("K18", "How do I clean a cambro? How many cambros do I need for 8 gallons of iced tea?", ("DOCS", "TOOL")),
    _k("K19", "What flavors of syrup do we have; do I bring sugar for hot water for 30 guests?", ("DOCS", "TOOL")),
    _k("K20", "I need 6 gallons of coffee and orange juice. How many cambros?", ("TOOL",)),
    _k("K21", "The coffee, decaf, tea, iced water & juice package is for 85 guests. How many cups?", ("TOOL",)),
    _k("K22", "4 gallons each.", ("TOOL",), H_HOT_DECAF, ("hot water", "decaf", "4 gallons each")),
    _k("K23", "75 guests.", ("TOOL",), H_OJ, ("cups", "75")),
    _k("K24", "And the syrups?", ("DOCS",), H_LEMON, ("lemon", "syrups")),
    _k("K25", "How many hot cups do I need for 40 guests?", ("TOOL",), H_COFFEE, equals=True),
    _k("K26", "How do I make lemonade?", ("DOCS",)),
    _k("K27", "How do I make 3 gallons of lemonade?", ("DOCS",)),
    _k("K28", "How much lemon concentrate do I need for 6 gallons of lemonade?", ("DOCS",)),
    _k("K29", "How do I make lemonade for 90 guests?", ("DOCS",)),
    _k("K30", "How many cambors do I need for 7 gallons of lemonade?", ("TOOL",)),
    _k("K31", "What is the difference between regular and decaf coffee?", ("DOCS",)),
]


def _problems(case, decision):
    problems = []
    routes = tuple(p.route for p in decision.parts)
    if routes != case["routes"]:
        problems.append(f"routes {routes} != {case['routes']}")
    for p in decision.parts:
        if p.route == "TOOL" and p.tool != BEV:
            problems.append(f"TOOL part has tool {p.tool!r}, expected {BEV!r}")
        if p.route == "DOCS" and p.tool is not None:
            problems.append(f"DOCS part has tool {p.tool!r}")
    if len(case["routes"]) == 1 and len(decision.parts) == 1:
        text = decision.parts[0].text
        low = text.casefold()
        for needed in case["contains"]:
            if needed not in low:
                problems.append(f"text {text!r} lacks {needed!r}")
        if case["equals"] and text != case["question"]:
            problems.append(f"text {text!r} != question")
    return problems


def test_k_cases_accuracy_and_timings(fast_llm):
    """Covers: AC-6 (right/wrong per case K1-K31), NFR-3, NFR-7. At least 28 of the 31 cases give the listed kind, parts and tools; each case's time, parts and tools are printed (no time limit)."""
    from blc.router import route_fast

    passed, failed, times = 0, [], []
    for case in K_CASES:
        started = time.perf_counter()
        decision = route_fast(fast_llm, case["history"], case["question"])
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        problems = _problems(case, decision)
        parts = [(p.route, p.text, p.tool) for p in decision.parts]
        print(f"{case['id']}: {elapsed:.2f}s fallback={decision.fallback} kind={decision.kind} parts={parts}"
              f"{' PROBLEMS: ' + '; '.join(problems) if problems else ''}")
        if problems:
            failed.append((case["id"], problems))
        else:
            passed += 1
    print(f"passed {passed} of {len(K_CASES)}; total {sum(times):.2f}s; slowest {max(times):.2f}s; fastest {min(times):.2f}s")
    assert len(K_CASES) == 31
    assert passed >= 28, f"only {passed} of 31 passed: {failed}"
