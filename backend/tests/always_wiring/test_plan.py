"""Spec 045 section 6.3 PLAN (AC-9, AC-10, AC-19 first sentence). Unit: scripted fake model."""
from __future__ import annotations

import ast
import json

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

import always_wiring_helpers as awh
from blc.planner import (PLANNER_BEV_TOOL, PLANNER_PROMPT, PLANNER_TOOLS, SEARCH_TOOL, Plan, PlannedCall,
                         plan_question)
from blc.tools.always_tools import ALWAYS_TOOL_NAME
from blc.tools.recipe_tools import RECIPE_TOOL

ALWAYS = "calculate_always_items"
SEARCH = "search_documents"
FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title", "enum"}


def _always_tool():
    matches = [t for t in PLANNER_TOOLS if t.name == ALWAYS_TOOL_NAME]
    assert len(matches) == 1
    return matches[0]


def _fn():
    return convert_to_openai_tool(_always_tool())["function"]


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def _types(node):
    if isinstance(node, dict):
        if "type" in node and not isinstance(node["type"], dict):
            t = node["type"]
            yield from (t if isinstance(t, list) else [t])
        for v in node.values():
            yield from _types(v)
    elif isinstance(node, list):
        for v in node:
            yield from _types(v)


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


def _all_descriptions():
    tool = _always_tool()
    fn = convert_to_openai_tool(tool)["function"]
    parts = [fn["description"], tool.description]

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("description"), str):
                parts.append(node["description"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(fn["parameters"])
    return parts


# ---------------------------------------------------------------- PLAN-1 (AC-9)

def test_plan_1_tools_are_current_five_plus_always_last():
    """Covers: AC-9 (right), PLAN-1. The five current tools by identity and order, then the always tool last."""
    assert isinstance(PLANNER_TOOLS, tuple)
    assert len(PLANNER_TOOLS) == 6
    assert PLANNER_TOOLS[0] is SEARCH_TOOL
    assert PLANNER_TOOLS[1] is PLANNER_BEV_TOOL
    assert PLANNER_TOOLS[2] is RECIPE_TOOL
    assert PLANNER_TOOLS[3].name == "calculate_food_item"
    assert PLANNER_TOOLS[4].name == "calculate_serving_utensils"
    assert PLANNER_TOOLS[5].name == ALWAYS_TOOL_NAME == ALWAYS


def test_plan_1_no_duplicate_names():
    """Covers: AC-9 (wrong), PLAN-1. Exactly one always tool and six distinct names."""
    names = [t.name for t in PLANNER_TOOLS]
    assert names.count(ALWAYS) == 1
    assert len(set(names)) == len(names) == 6


def test_plan_1_plan_question_binds_exactly_the_tuple(make_llm, mk):
    """Covers: AC-9 (right), PLAN-1. plan_question binds list(PLANNER_TOOLS) once, the always tool last."""
    llm = make_llm([mk.ai((SEARCH, {"query": "where are the linens"}))])
    plan_question(llm, "Where are the linens?")
    assert len(llm.bind_calls) == 1
    assert llm.bind_calls[0] == list(PLANNER_TOOLS)
    assert llm.bind_calls[0][-1].name == ALWAYS


# ---------------------------------------------------------------- PLAN-2 (AC-9)

def test_plan_2_always_call_alone_is_tool(make_llm, mk):
    """Covers: AC-9 (right), PLAN-2. An always call alone: route TOOL, name and args exactly as sent."""
    args = {"about": "tables", "tables": 4}
    plan = plan_question(make_llm([mk.ai((ALWAYS, args))]), "Linens for 4 tables?")
    assert plan == Plan("TOOL", (PlannedCall(ALWAYS, args),), False)


def test_plan_2_always_call_with_search_is_both(make_llm, mk):
    """Covers: AC-9 (right), PLAN-2. The same call plus a search gives BOTH; both kept in order."""
    args = {"about": "tables", "tables": 4}
    search = {"query": "where are the black linens kept"}
    plan = plan_question(make_llm([mk.ai((SEARCH, search), (ALWAYS, args))]), "q")
    assert plan.route == "BOTH" and plan.fallback is False
    assert plan.calls == (PlannedCall(SEARCH, search), PlannedCall(ALWAYS, args))


def test_plan_2_search_after_always_also_both(make_llm, mk):
    """Covers: AC-9 (boundary), PLAN-2. The order of the two calls does not change the route."""
    args = {"about": "both", "tables": 2}
    search = {"query": "always box"}
    plan = plan_question(make_llm([mk.ai((ALWAYS, args), (SEARCH, search))]), "q")
    assert plan.route == "BOTH"
    assert plan.calls == (PlannedCall(ALWAYS, args), PlannedCall(SEARCH, search))


def test_plan_2_odd_args_not_cleaned(make_llm, mk):
    """Covers: AC-9 (boundary), PLAN-2. Args the tool would reject are kept unchanged by the plan."""
    args = {"about": " Drip Trays ", "tables": "two", "drip_trays": -1, "extra": 1}
    plan = plan_question(make_llm([mk.ai((ALWAYS, args))]), "q")
    assert plan.calls == (PlannedCall(ALWAYS, args),)
    assert plan.fallback is False


def test_plan_2_always_call_is_not_dropped_as_unknown(make_llm, mk):
    """Covers: AC-9 (wrong), PLAN-2. The always call is a known tool: no DOCS fallback."""
    plan = plan_question(make_llm([mk.ai((ALWAYS, {"about": "both"}))]), "What are the always items?")
    assert plan.fallback is False and plan.route == "TOOL"


# ---------------------------------------------------------------- PLAN-3 (AC-10)

def test_plan_3_schema_matches_contract():
    """Covers: AC-10 (right), PLAN-3. Stripped of descriptions, parameters equal the section 3.2 schema."""
    expected = {
        "type": "object",
        "properties": {
            "about": {"type": "string"},
            "tables": {"type": "integer"},
            "drip_trays": {"type": "integer"},
        },
        "required": ["about"],
    }
    assert _strip_descriptions(_fn()["parameters"]) == expected


def test_plan_3_no_forbidden_keywords():
    """Covers: AC-10 (wrong), PLAN-3. No anyOf, oneOf, allOf, $ref, $defs, default, title or enum key."""
    seen = set(_keys(_fn()["parameters"]))
    assert not (FORBIDDEN_KEYS & seen), FORBIDDEN_KEYS & seen


def test_plan_3_no_null_type():
    """Covers: AC-10 (wrong), PLAN-3. No type 'null', alone or in a type list."""
    assert "null" not in set(_types(_fn()["parameters"]))


def test_plan_3_descriptions_are_nonblank_strings():
    """Covers: AC-10 (boundary), PLAN-3. The tool and each of the three properties carry a description."""
    fn = _fn()
    props = fn["parameters"]["properties"]
    for d in [fn["description"]] + [props[k].get("description") for k in ("about", "tables", "drip_trays")]:
        assert isinstance(d, str) and d.strip()


# ---------------------------------------------------------------- PLAN-4 (AC-10)

def test_plan_4_at_least_three_example_calls():
    """Covers: AC-10 (boundary), PLAN-4. At least three example calls as argument dicts."""
    assert len(_example_calls(_fn()["description"])) >= 3


@pytest.mark.parametrize("scope", ["tables", "drip_trays", "both"])
def test_plan_4_one_example_per_scope(scope):
    """Covers: AC-10 (right), PLAN-4. There is an example call for each about value."""
    calls = _example_calls(_fn()["description"])
    assert any(c.get("about") == scope for c in calls), calls


def test_plan_4_an_example_leaves_a_number_out():
    """Covers: AC-10 (right), PLAN-4. At least one example has no tables key or no drip_trays key."""
    calls = _example_calls(_fn()["description"])
    assert any("tables" not in c or "drip_trays" not in c for c in calls), calls


def test_plan_4_example_numbers_are_whole_numbers_when_present():
    """Covers: AC-10 (wrong), PLAN-4. Extra: numbers in the examples are integers (the schema says integer)."""
    for c in _example_calls(_fn()["description"]):
        for key in ("tables", "drip_trays"):
            if key in c:
                assert isinstance(c[key], int) and not isinstance(c[key], bool), c


def test_description_mentions_the_three_points():
    """Covers: AC-10 (right). The descriptions name the items by scope, say never guess and mention bus tubs and
    towels (wording is the developer's; only the topics are checked)."""
    folded = "\n".join(_all_descriptions()).casefold()
    assert "black linens" in folded and "purple napkins" in folded and "black napkins" in folded
    assert "bus tubs" in folded and "towels" in folded
    assert "guess" in folded


# ---------------------------------------------------------------- PLAN-5 (AC-19 first sentence)

def _eval_questions():
    qs = [c["question"] for c in awh.CASES.values()]
    qs += [h["content"] for c in awh.CASES.values() for h in (c["history"] or []) if h["role"] == "user"]
    return qs


def test_eval_case_list_is_complete():
    """Covers: PLAN-5 (boundary). The copy of the eval cases holds all 10 (guards the copy)."""
    assert len(awh.CASES) == 10
    assert awh.CASE_IDS[0] == "EVAL-1" and awh.CASE_IDS[-1] == "EVAL-10"


def test_plan_5_prompt_and_descriptions_hold_no_eval_question():
    """Covers: AC-19 (wrong), PLAN-5. No eval question appears word for word, casefolded, in PLANNER_PROMPT or
    in the always tool's descriptions."""
    folded = "\n".join([PLANNER_PROMPT] + _all_descriptions()).casefold()
    leaked = [q for q in _eval_questions() if q.casefold() in folded]
    assert leaked == []


@pytest.mark.parametrize("question", ["What are the always items?", "ALWAYS ITEMS FOR 4 TABLES?"])
def test_leak_check_would_catch_a_casefolded_copy(question):
    """Covers: PLAN-5 (boundary). A shouted copy of an eval question inside a prompt is still detected, so the
    leak check above can fail."""
    folded = ("intro " + question.upper() + " outro").casefold()
    assert any(q.casefold() in folded for q in _eval_questions())
