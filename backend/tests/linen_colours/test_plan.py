"""Spec 047 section 6.2 PLAN (AC-5, AC-7, AC-10 prompt part): the planner's view of the always tool and the prompt."""
from __future__ import annotations

import ast
import json
from collections import Counter

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.planner import PLANNER_PROMPT, PLANNER_TOOLS
from blc.tools.always_tools import ALWAYS_TOOL_NAME

FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title", "enum"}
MIN_EXAMPLE_NUMBER = 31

# The 11 example questions of spec 046 Appendix A, in order.
EXAMPLES = [
    "How many cups do I need for 70 guests?",
    "How much lemon concentrate for 8 gallons of lemonade?",
    "How many knives for 35 guests?",
    "Are cocktail napkins needed at dinner?",
    "Which tongs for 7 dozen bagels?",
    "How many black napkins should I pull?",
    "What goes in the Always box for 7 drip trays?",
    "Where are the lemons kept?",
    "Should I bring creamer for decaf?",
    "How many cambros for 4 gallons of coffee and what to bring?",
    "Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?",
]


def _fn():
    matches = [t for t in PLANNER_TOOLS if t.name == ALWAYS_TOOL_NAME]
    assert len(matches) == 1
    return convert_to_openai_tool(matches[0])["function"]


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def _strip_descriptions(node):
    if isinstance(node, dict):
        return {k: _strip_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_strip_descriptions(v) for v in node]
    return node


def _example_calls(text):
    """Top-level {...} blocks of the text that parse as a dict with an 'about' key (JSON or Python syntax)."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                block = text[start:i + 1]
                for parse in (json.loads, ast.literal_eval):
                    try:
                        val = parse(block)
                    except Exception:
                        continue
                    if isinstance(val, dict) and "about" in val:
                        out.append(val)
                    break
    return out


def _description_text():
    """The tool description plus each property description (each once)."""
    fn = _fn()
    props = fn["parameters"]["properties"]
    return "\n".join([fn["description"]] + [p.get("description", "") for p in props.values()])


def _ints(call):
    return [v for v in call.values() if isinstance(v, int) and not isinstance(v, bool)]


# ---------------------------------------------------------------- PLAN-1 (AC-5)

def test_plan_1_schema_matches_contract():
    """Covers: AC-5 (right), PLAN-1. Stripped of descriptions, parameters equal the section 3.2 schema exactly."""
    expected = {
        "type": "object",
        "properties": {
            "about": {"type": "string"},
            "tables": {"type": "integer"},
            "white_tables": {"type": "integer"},
            "drip_trays": {"type": "integer"},
        },
        "required": ["about"],
    }
    assert _strip_descriptions(_fn()["parameters"]) == expected


def test_plan_1_white_tables_not_required():
    """Covers: AC-5 (wrong), PLAN-1. Only 'about' is required; white_tables must not be."""
    assert _fn()["parameters"]["required"] == ["about"]


def test_plan_1_no_forbidden_keywords():
    """Covers: AC-5 (wrong), PLAN-1. No anyOf, oneOf, allOf, $ref, $defs, default, title or enum key."""
    seen = set(_keys(_fn()["parameters"]))
    assert not (FORBIDDEN_KEYS & seen), FORBIDDEN_KEYS & seen


def test_plan_1_each_property_has_a_description():
    """Covers: AC-5 (boundary), PLAN-1. The tool and its four properties carry non-blank descriptions."""
    fn = _fn()
    props = fn["parameters"]["properties"]
    for d in [fn["description"]] + [props[k].get("description") for k in ("about", "tables", "white_tables", "drip_trays")]:
        assert isinstance(d, str) and d.strip()


def test_plan_1_descriptions_explain_colours():
    """Covers: AC-5 (right), PLAN-1. Topics only (wording is the developer's): 'tables' mentions black, and
    'white_tables' mentions white."""
    props = _fn()["parameters"]["properties"]
    assert "black" in props["tables"]["description"].casefold()
    assert "white" in props["white_tables"]["description"].casefold()


# ---------------------------------------------------------------- PLAN-2 (AC-5)

def test_plan_2_has_a_white_tables_example():
    """Covers: AC-5 (right), PLAN-2. At least one example call in the descriptions has a 'white_tables' key."""
    calls = _example_calls(_description_text())
    assert any("white_tables" in c for c in calls), calls


def test_plan_2_still_three_scopes_and_a_left_out_number():
    """Covers: AC-5 (right), PLAN-2. Spec 045 rules still hold: at least three examples covering the three scopes,
    and at least one example with a number left out."""
    calls = _example_calls(_description_text())
    assert len(calls) >= 3
    assert {c.get("about") for c in calls} >= {"tables", "drip_trays", "both"}
    assert any("tables" not in c or "drip_trays" not in c for c in calls)


def test_plan_2_example_numbers_at_least_31():
    """Covers: AC-5 (boundary), PLAN-2. Every integer in every example call is 31 or more."""
    calls = _example_calls(_description_text())
    numbers = [n for c in calls for n in _ints(c)]
    assert numbers, "examples should contain numbers"
    assert all(n >= MIN_EXAMPLE_NUMBER for n in numbers), numbers


def test_plan_2_example_numbers_not_repeated_across_examples():
    """Covers: AC-5 (wrong), PLAN-2. No number appears in more than one example call."""
    calls = _example_calls(_description_text())
    counts = Counter(n for c in calls for n in set(_ints(c)))
    repeated = {n: k for n, k in counts.items() if k > 1}
    assert repeated == {}


def test_plan_2_example_numbers_are_not_bools_or_floats():
    """Covers: AC-5 (boundary), PLAN-2. Extra: numeric values in examples are whole numbers (schema says integer)."""
    for c in _example_calls(_description_text()):
        for key in ("tables", "white_tables", "drip_trays"):
            if key in c:
                assert isinstance(c[key], int) and not isinstance(c[key], bool), c


def test_plan_2_checkers_can_fail():
    """Covers: PLAN-2 (boundary). The helpers detect a small number and a repeated number in made-up examples."""
    text = '{"about": "tables", "tables": 9} and {"about": "both", "tables": 40, "drip_trays": 40}'
    calls = _example_calls(text)
    assert len(calls) == 2
    assert any(n < MIN_EXAMPLE_NUMBER for c in calls for n in _ints(c))
    again = _example_calls('{"about": "tables", "tables": 40} {"about": "both", "tables": 40}')
    assert Counter(n for c in again for n in set(_ints(c)))[40] == 2


# ---------------------------------------------------------------- PLAN-3 (AC-7, AC-10)

def test_plan_3_prompt_mentions_white_tables():
    """Covers: AC-10 (right), PLAN-3. The PLANNER_PROMPT mentions white_tables and calculate_always_items."""
    assert "white_tables" in PLANNER_PROMPT
    assert "calculate_always_items" in PLANNER_PROMPT


@pytest.mark.parametrize("example", EXAMPLES)
def test_plan_3_spec_046_examples_still_present(example):
    """Covers: AC-7 (right), PLAN-3. Each of spec 046's 11 example questions is still in PLANNER_PROMPT."""
    assert example in PLANNER_PROMPT


def test_plan_3_spec_046_examples_still_in_order():
    """Covers: AC-7 (boundary), PLAN-3. The first occurrences of the 11 examples are still strictly increasing."""
    positions = [PLANNER_PROMPT.index(e) for e in EXAMPLES]
    assert positions == sorted(positions)
    assert len(set(positions)) == 11


def test_plan_3_prompt_says_colourless_linens_are_black():
    """Covers: AC-10 (right), PLAN-3. Extra: the prompt says linens or tablecloths with no colour are black
    (topic words only; the wording is the developer's)."""
    folded = PLANNER_PROMPT.casefold()
    assert "tablecloths" in folded
    assert "black linens" in folded
