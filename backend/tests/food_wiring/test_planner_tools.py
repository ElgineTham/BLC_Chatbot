"""Spec 030 section 6.1 CALL-7 and CALL-8 (AC-1, AC-2, AC-3, AC-15). Unit: scripted fake model."""
from __future__ import annotations

import re

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

import food_wiring_helpers as fwh
from blc.planner import (PLANNER_BEV_TOOL, PLANNER_PROMPT, PLANNER_TOOLS, SEARCH_TOOL, Plan, PlannedCall,
                         plan_question)
from blc.tools.food_tools import FOOD_TOOL_NAME
from blc.tools.recipe_tools import RECIPE_TOOL

FOOD = "calculate_food_item"
SEARCH = "search_documents"
FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title"}


def _food_tool():
    matches = [t for t in PLANNER_TOOLS if t.name == FOOD_TOOL_NAME]
    assert len(matches) == 1
    return matches[0]


def _fn():
    return convert_to_openai_tool(_food_tool())["function"]


def _walk(node):
    """Yield every key and every leaf value of a nested dict/list."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)
    else:
        yield node


# ---------------------------------------------------------------- AC-1

def test_food_tool_name_constant():
    """Covers: AC-1 (right), CALL-7. FOOD_TOOL_NAME is calculate_food_item."""
    assert FOOD_TOOL_NAME == FOOD


def test_planner_tools_are_old_three_plus_food_last():
    """Covers: AC-1 (right), CALL-7. Old three by identity and in order, then exactly one food tool, last."""
    assert isinstance(PLANNER_TOOLS, tuple)
    assert len(PLANNER_TOOLS) == 4
    assert PLANNER_TOOLS[0] is SEARCH_TOOL
    assert PLANNER_TOOLS[1] is PLANNER_BEV_TOOL
    assert PLANNER_TOOLS[2] is RECIPE_TOOL
    assert PLANNER_TOOLS[3].name == FOOD_TOOL_NAME


def test_exactly_one_food_tool_in_planner_tools():
    """Covers: AC-1 (wrong), CALL-7. No duplicate food tool and no other new tool."""
    names = [t.name for t in PLANNER_TOOLS]
    assert names.count(FOOD_TOOL_NAME) == 1
    assert len(set(names)) == len(names) == 4


def test_plan_question_binds_exactly_the_tuple(make_llm, mk):
    """Covers: AC-1 (right), CALL-7. plan_question binds list(PLANNER_TOOLS), food tool included, once."""
    llm = make_llm([mk.ai((SEARCH, {"query": "where are the forks"}))])
    plan_question(llm, "Where are the forks?")
    assert len(llm.bind_calls) == 1
    assert llm.bind_calls[0] == list(PLANNER_TOOLS)
    assert llm.bind_calls[0][-1].name == FOOD_TOOL_NAME


# ---------------------------------------------------------------- AC-2

def test_schema_properties_and_required():
    """Covers: AC-2 (right), CALL-7. properties are exactly item, guests, meal; required == ['item']."""
    params = _fn()["parameters"]
    assert set(params["properties"]) == {"item", "guests", "meal"}
    assert params["required"] == ["item"]


def test_schema_has_no_forbidden_keywords():
    """Covers: AC-2 (wrong), CALL-7. No anyOf, oneOf, allOf, $ref, $defs, default, title anywhere."""
    seen = {x for x in _walk(_fn()["parameters"]) if isinstance(x, str)}
    assert not (FORBIDDEN_KEYS & seen), FORBIDDEN_KEYS & seen


def test_schema_has_no_null_type():
    """Covers: AC-2 (wrong), CALL-7. No type 'null', alone or in a type list."""
    def types(node):
        if isinstance(node, dict):
            if "type" in node:
                t = node["type"]
                yield from (t if isinstance(t, list) else [t])
            for v in node.values():
                yield from types(v)
        elif isinstance(node, list):
            for v in node:
                yield from types(v)

    assert "null" not in set(types(_fn()["parameters"]))


def _example_dicts(description):
    return re.findall(r"\{[^{}]*\}", description)


def test_description_has_a_count_example_and_a_napkin_example():
    """Covers: AC-2 (right), CALL-7. The description has an example dict with item and guests, and one with
    item and meal."""
    dicts = _example_dicts(_fn()["description"])
    assert any("item" in d and "guests" in d for d in dicts), dicts
    assert any("item" in d and "meal" in d for d in dicts), dicts


def test_description_has_at_least_two_example_dicts():
    """Covers: AC-2 (boundary), CALL-7. At least two example calls as argument dicts."""
    assert len(_example_dicts(_fn()["description"])) >= 2


def test_description_is_a_nonblank_string():
    """Covers: AC-2 (wrong), CALL-7. The description is a real string."""
    d = _fn()["description"]
    assert isinstance(d, str) and d.strip()


# ---------------------------------------------------------------- AC-3

def test_food_call_alone_is_tool_and_kept_exactly(make_llm, mk):
    """Covers: AC-3 (right), CALL-7. A food call alone: route TOOL, name and args exactly as sent."""
    args = {"item": "forks", "guests": 70}
    plan = plan_question(make_llm([mk.ai((FOOD, args))]), "How many forks do I need for 70 guests?")
    assert plan == Plan("TOOL", (PlannedCall(FOOD, args),), False)


def test_napkin_call_kept_exactly(make_llm, mk):
    """Covers: AC-3 (right), CALL-7. A napkin call with item and meal is kept as sent."""
    args = {"item": "dinner napkins", "meal": "lunch"}
    plan = plan_question(make_llm([mk.ai((FOOD, args))]), "Do I need dinner napkins for a lunch?")
    assert plan.calls == (PlannedCall(FOOD, args),)
    assert plan.route == "TOOL"


def test_food_call_with_odd_args_is_not_cleaned(make_llm, mk):
    """Covers: AC-3 (boundary), CALL-7. Args the tool would reject (case, spelled number, extra key) are kept
    unchanged: the plan does not clean them."""
    args = {"item": " Forks ", "guests": "seventy", "meal": "lunch", "extra": 1}
    plan = plan_question(make_llm([mk.ai((FOOD, args))]), "q")
    assert plan.calls == (PlannedCall(FOOD, args),)
    assert plan.calls[0].args == args


def test_food_call_with_search_is_both(make_llm, mk):
    """Covers: AC-3 (right), CALL-7. A food call with a search call gives BOTH; both calls kept in order."""
    food = {"item": "forks", "guests": 70}
    search = {"query": "where are the forks kept"}
    plan = plan_question(make_llm([mk.ai((SEARCH, search), (FOOD, food))]), "q")
    assert plan.route == "BOTH" and plan.fallback is False
    assert plan.calls == (PlannedCall(SEARCH, search), PlannedCall(FOOD, food))


def test_search_then_food_and_food_then_search_both_are_both(make_llm, mk):
    """Covers: AC-3 (boundary), CALL-7. The order of the two calls does not change the route."""
    food = {"item": "knives", "guests": 20}
    search = {"query": "knives"}
    plan = plan_question(make_llm([mk.ai((FOOD, food), (SEARCH, search))]), "q")
    assert plan.route == "BOTH"
    assert plan.calls == (PlannedCall(FOOD, food), PlannedCall(SEARCH, search))


def test_two_food_calls_are_tool(make_llm, mk):
    """Covers: AC-3 (boundary), extra. Two food calls (knives and forks) with no search: route TOOL, both kept."""
    a = {"item": "knives", "guests": 60}
    b = {"item": "forks", "guests": 60}
    plan = plan_question(make_llm([mk.ai((FOOD, a), (FOOD, b))]), "q")
    assert plan.route == "TOOL"
    assert plan.calls == (PlannedCall(FOOD, a), PlannedCall(FOOD, b))


def test_food_call_is_not_dropped_as_unknown(make_llm, mk):
    """Covers: AC-3 (wrong), CALL-7. The food call is a known tool: no DOCS fallback."""
    plan = plan_question(make_llm([mk.ai((FOOD, {"item": "spoons", "guests": 10}))]), "Where are the spoons?")
    assert plan.fallback is False and plan.route == "TOOL"


# ---------------------------------------------------------------- CALL-8 / AC-15

def _all_questions():
    return [c["question"] for c in fwh.CASES.values()]


def test_eval_question_list_is_complete():
    """Covers: CALL-8 (boundary). The copy of the eval questions holds all 25 cases (guards the copy)."""
    assert len(fwh.CASES) == 25
    assert fwh.CASE_IDS[0] == "CALL-1" and fwh.CASE_IDS[-1] == "FD-6"


def test_food_tool_description_holds_no_eval_question():
    """Covers: AC-15 (wrong), CALL-8. No eval question appears in the food tool's description (tool and
    property descriptions), casefolded."""
    tool = _food_tool()
    fn = convert_to_openai_tool(tool)["function"]
    parts = [fn["description"], tool.description]
    parts += [p.get("description", "") for p in fn["parameters"]["properties"].values()]
    folded = "\n".join(parts).casefold()
    leaked = [cid for cid, c in fwh.CASES.items() if c["question"].casefold() in folded]
    assert leaked == []


@pytest.mark.parametrize("question", ["How many forks do I need for 70 guests?", "WHERE ARE THE CROISSANTS KEPT?"])
def test_leak_check_would_catch_a_casefolded_copy(question):
    """Covers: CALL-8 (boundary). The casefold comparison works: a shouted copy of a prompt is still detected
    when it contains the question, so the checks above can fail."""
    folded = ("intro " + question.upper() + " outro").casefold()
    assert any(q.casefold() in folded for q in _all_questions() if q.casefold() == question.casefold())
