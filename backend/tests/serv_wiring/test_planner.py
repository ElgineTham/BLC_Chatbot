"""Spec 043 section 6.1 CALL-5 and CALL-6 (AC-1, AC-2, AC-3, AC-14 first sentence). Unit: scripted fake model.

CALL-1 to CALL-4 are eval cases (test_eval.py). AC-14's second sentence is manual.
"""
from __future__ import annotations

import ast
import json

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

import serv_wiring_helpers as swh
from blc.planner import (PLANNER_BEV_TOOL, PLANNER_PROMPT, PLANNER_TOOLS, SEARCH_TOOL, Plan, PlannedCall,
                         plan_question)
from blc.tools.recipe_tools import RECIPE_TOOL
from blc.tools.serv_tools import SERV_TOOL_NAME

SERV = "calculate_serving_utensils"
SEARCH = "search_documents"
FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title", "enum"}


def _serv_tool():
    matches = [t for t in PLANNER_TOOLS if t.name == SERV_TOOL_NAME]
    assert len(matches) == 1
    return matches[0]


def _fn():
    return convert_to_openai_tool(_serv_tool())["function"]


def _keys(node):
    """Every dict key in a nested dict/list."""
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
    """Top-level {...} blocks of the text that parse as a dict with an 'items' key (JSON or Python syntax)."""
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
                    if isinstance(val, dict) and "items" in val:
                        out.append(val)
                    break
    return out


def _all_descriptions():
    tool = _serv_tool()
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


# ---------------------------------------------------------------- AC-1

def test_serv_tool_name_constant():
    """Covers: AC-1 (right), CALL-5. SERV_TOOL_NAME is calculate_serving_utensils."""
    assert SERV_TOOL_NAME == SERV


def test_planner_tools_are_old_four_plus_serv_last():
    """Covers: AC-1 (right), CALL-5. The four old tools by identity and in order, then exactly one serving
    tool, last."""
    assert isinstance(PLANNER_TOOLS, tuple)
    assert len(PLANNER_TOOLS) == 6  # spec 045: the always tool is now last
    assert PLANNER_TOOLS[0] is SEARCH_TOOL
    assert PLANNER_TOOLS[1] is PLANNER_BEV_TOOL
    assert PLANNER_TOOLS[2] is RECIPE_TOOL
    assert PLANNER_TOOLS[3].name == "calculate_food_item"
    assert PLANNER_TOOLS[4].name == SERV_TOOL_NAME
    assert PLANNER_TOOLS[5].name == "calculate_always_items"


def test_exactly_one_serv_tool_and_no_duplicate_names():
    """Covers: AC-1 (wrong), CALL-5. No duplicate serving tool and no other new tool."""
    names = [t.name for t in PLANNER_TOOLS]
    assert names.count(SERV_TOOL_NAME) == 1
    assert len(set(names)) == len(names) == 6


def test_plan_question_binds_exactly_the_tuple(make_llm, mk):
    """Covers: AC-1 (right), CALL-5. plan_question binds list(PLANNER_TOOLS) once, serving tool last."""
    llm = make_llm([mk.ai((SEARCH, {"query": "where are the scones"}))])
    plan_question(llm, "Where are the scones?")
    assert len(llm.bind_calls) == 1
    assert llm.bind_calls[0] == list(PLANNER_TOOLS)
    assert llm.bind_calls[0][4].name == SERV_TOOL_NAME


# ---------------------------------------------------------------- AC-2

def test_schema_matches_the_contract_exactly():
    """Covers: AC-2 (right), CALL-5. Stripped of descriptions, parameters equal the section 3 schema."""
    expected = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"food": {"type": "string"}, "qty": {"type": "number"},
                                   "unit": {"type": "string"}},
                    "required": ["food"],
                },
            }
        },
        "required": ["items"],
    }
    assert _strip_descriptions(_fn()["parameters"]) == expected


def test_schema_has_no_forbidden_keywords():
    """Covers: AC-2 (wrong), CALL-5. No anyOf, oneOf, allOf, $ref, $defs, default, title or enum key."""
    seen = set(_keys(_fn()["parameters"]))
    assert not (FORBIDDEN_KEYS & seen), FORBIDDEN_KEYS & seen


def test_schema_has_no_null_type():
    """Covers: AC-2 (wrong), CALL-5. No type 'null', alone or in a type list."""
    assert "null" not in set(_types(_fn()["parameters"]))


def test_every_description_is_a_nonblank_string():
    """Covers: AC-2 (wrong), CALL-5. The tool, items, food, qty and unit all carry a real description."""
    fn = _fn()
    params = fn["parameters"]
    item_props = params["properties"]["items"]["items"]["properties"]
    descs = [fn["description"], params["properties"]["items"].get("description"),
             item_props["food"].get("description"), item_props["qty"].get("description"),
             item_props["unit"].get("description")]
    for d in descs:
        assert isinstance(d, str) and d.strip(), descs


def test_description_has_at_least_three_example_calls():
    """Covers: AC-2 (boundary), CALL-5. At least three example calls as argument dicts (revision 2), each
    with items of foods."""
    calls = _example_calls(_fn()["description"])
    assert len(calls) >= 3, calls
    for c in calls:
        assert isinstance(c["items"], list) and c["items"]
        assert all(isinstance(i, dict) and isinstance(i.get("food"), str) for i in c["items"]), c


def test_description_has_a_two_food_example():
    """Covers: AC-2 (right), CALL-5. One example call has two foods."""
    assert any(len(c["items"]) == 2 for c in _example_calls(_fn()["description"]))


def test_description_has_a_package_example_with_unit_each():
    """Covers: AC-2 (right), CALL-5. One example call has an item line with "unit": "each" (the breakfast
    package line)."""
    calls = _example_calls(_fn()["description"])
    assert any(str(i.get("unit", "")).strip().casefold() == "each" for c in calls for i in c["items"]), calls


def _foods_of(call):
    return [str(i.get("food", "")).casefold() for i in call["items"]]


def test_description_has_a_platter_package_example():
    """Covers: AC-2 (right), CALL-5. A package example call uses unit each and includes the 'freshly cut fruit
    platter'."""
    calls = _example_calls(_fn()["description"])
    assert any("freshly cut fruit platter" in _foods_of(c)
               and all(str(i.get("unit", "")).strip().casefold() == "each" for i in c["items"]
                       if i.get("food", "").casefold() == "freshly cut fruit platter")
               for c in calls), calls


def test_description_has_a_market_fresh_fruit_tray_example():
    """Covers: AC-2 (right), CALL-5. One example call has a '... market fresh fruit tray' food with a number
    of trays."""
    calls = _example_calls(_fn()["description"])
    tray_items = [i for c in calls for i in c["items"]
                  if str(i.get("food", "")).casefold().endswith("market fresh fruit tray")]
    assert tray_items, calls
    assert any(isinstance(i.get("qty"), (int, float)) for i in tray_items), tray_items
    assert any(str(i["food"]).casefold().split()[0] in ("small", "medium", "large") for i in tray_items)


def test_description_says_tray_vs_platter():
    """Covers: AC-2 (right), CALL-5. Outside the examples, the description says a fruit tray on its own is a
    small, medium or large market fresh fruit tray counted in trays, and the freshly cut fruit platter is only
    the fruit line of a breakfast package."""
    desc = _fn()["description"]
    folded = desc.casefold()
    assert "market fresh fruit tray" in folded
    assert "small" in folded and "medium" in folded and "large" in folded
    assert "tray" in folded and "freshly cut fruit platter" in folded
    assert "breakfast" in folded


def test_descriptions_cover_package_rule():
    """Covers: AC-2 (right), CALL-5. The descriptions mention package item lines and the unit each."""
    folded = "\n".join(_all_descriptions()).casefold()
    assert "package" in folded
    assert "each" in folded


# ---------------------------------------------------------------- AC-3

def test_serv_call_alone_is_tool_and_kept_exactly(make_llm, mk):
    """Covers: AC-3 (right), CALL-5. A serving call alone: route TOOL, name and args exactly as sent."""
    args = {"items": [{"food": "butter croissants", "qty": 3, "unit": "dozen"}]}
    plan = plan_question(make_llm([mk.ai((SERV, args))]), "Utensils for 3 dozen croissants?")
    assert plan == Plan("TOOL", (PlannedCall(SERV, args),), False)


def test_serv_call_with_odd_args_is_not_cleaned(make_llm, mk):
    """Covers: AC-3 (boundary), CALL-5. Args the tool would reject (missing qty, string qty, extra key,
    package unit) are kept unchanged."""
    args = {"items": [{"food": " Croissants ", "qty": "70", "unit": "each", "color": "red"}, {"food": "x"}],
            "extra": 1}
    plan = plan_question(make_llm([mk.ai((SERV, args))]), "q")
    assert plan.calls == (PlannedCall(SERV, args),)
    assert plan.fallback is False


def test_serv_call_with_search_is_both(make_llm, mk):
    """Covers: AC-3 (right), CALL-5. A serving call with a search call gives BOTH; both kept in order."""
    serv = {"items": [{"food": "assorted scones", "qty": 2}]}
    search = {"query": "where are the scones kept"}
    plan = plan_question(make_llm([mk.ai((SEARCH, search), (SERV, serv))]), "q")
    assert plan.route == "BOTH" and plan.fallback is False
    assert plan.calls == (PlannedCall(SEARCH, search), PlannedCall(SERV, serv))


def test_serv_then_search_is_also_both(make_llm, mk):
    """Covers: AC-3 (boundary), CALL-5. The order of the two calls does not change the route."""
    serv = {"items": [{"food": "assorted scones", "qty": 2}]}
    search = {"query": "scones"}
    plan = plan_question(make_llm([mk.ai((SERV, serv), (SEARCH, search))]), "q")
    assert plan.route == "BOTH"
    assert plan.calls == (PlannedCall(SERV, serv), PlannedCall(SEARCH, search))


def test_serv_call_is_not_dropped_as_unknown(make_llm, mk):
    """Covers: AC-3 (wrong), CALL-5. The serving call is a known tool: no DOCS fallback."""
    plan = plan_question(make_llm([mk.ai((SERV, {"items": [{"food": "bagels", "qty": 2}]}))]),
                         "Where are the bagels?")
    assert plan.fallback is False and plan.route == "TOOL"


# ---------------------------------------------------------------- CALL-6 / AC-14 (first sentence)

def _eval_questions():
    qs = [c["question"] for c in swh.CASES.values()]
    qs += [h["content"] for c in swh.CASES.values() for h in (c["history"] or []) if h["role"] == "user"]
    return qs


def test_eval_case_list_is_complete():
    """Covers: CALL-6 (boundary). The copy of the eval cases holds all 12 (guards the copy)."""
    assert len(swh.CASES) == 12
    assert swh.CASE_IDS[0] == "CALL-1" and swh.CASE_IDS[-1] == "FOLLOW-4"


def test_prompt_and_descriptions_hold_no_eval_question():
    """Covers: AC-14 (wrong), CALL-6. No eval question (or history question) appears word for word,
    casefolded, in PLANNER_PROMPT or in the serving tool's descriptions."""
    folded = "\n".join([PLANNER_PROMPT] + _all_descriptions()).casefold()
    leaked = [q for q in _eval_questions() if q.casefold() in folded]
    assert leaked == []


@pytest.mark.parametrize("question", ["What serving utensils do I need for 4 dozen muffins?",
                                      "WHERE ARE THE SCONES KEPT?"])
def test_leak_check_would_catch_a_casefolded_copy(question):
    """Covers: CALL-6 (boundary). The casefold comparison works: a shouted copy of an eval question inside a
    prompt is still detected, so the leak check above can fail."""
    folded = ("intro " + question.upper() + " outro").casefold()
    assert any(q.casefold() in folded for q in _eval_questions())
