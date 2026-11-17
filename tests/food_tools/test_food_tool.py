"""Spec 029 section 6.5 TOOL (AC-10): the LangChain tool object and its schema. Unit."""

from __future__ import annotations

import re

import pytest
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.tools.food_tools import FOOD_TOOL, FOOD_TOOL_NAME, make_food_tool, run_food_tool

FORBIDDEN = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title", "enum", "null"}

EXPECTED_PARAMETERS = {
    "type": "object",
    "properties": {
        "item": {"type": "string"},
        "guests": {"type": "integer", "minimum": 1},
        "meal": {"type": "string"},
    },
    "required": ["item"],
}


def _strip_descriptions(params):
    out = {k: v for k, v in params.items() if k != "properties"}
    out["properties"] = {n: {k: v for k, v in p.items() if k != "description"}
                         for n, p in params["properties"].items()}
    return out


def _walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)
    else:
        yield node


@pytest.fixture(params=["real", "made"])
def tool(request, rules):
    return FOOD_TOOL if request.param == "real" else make_food_tool(rules)


def test_tool_name():
    """Covers: AC-10 (right), TOOL-1. FOOD_TOOL is a BaseTool named calculate_food_item."""
    assert isinstance(FOOD_TOOL, BaseTool)
    assert FOOD_TOOL.name == FOOD_TOOL_NAME == "calculate_food_item"


def test_schema_exact(tool):
    """Covers: AC-10 (right), TOOL-1. parameters equal section 3.2 apart from descriptions."""
    fn = convert_to_openai_tool(tool)["function"]
    assert fn["name"] == FOOD_TOOL_NAME
    assert _strip_descriptions(fn["parameters"]) == EXPECTED_PARAMETERS


def test_properties_have_descriptions(tool):
    """Covers: AC-10 (right), TOOL-1. Each property has a non-empty description."""
    props = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
    for n in ("item", "guests", "meal"):
        assert isinstance(props[n].get("description"), str) and props[n]["description"].strip()


def test_schema_has_no_forbidden_keys(tool):
    """Covers: AC-10 (wrong), TOOL-1. No banned keywords or null type anywhere in parameters."""
    seen = set(_walk(convert_to_openai_tool(tool)["function"]["parameters"]))
    assert not (FORBIDDEN & seen)


def test_description_content(tool):
    """Covers: AC-10 (right), TOOL-2. Names the items and has a count and a napkin example call."""
    desc = convert_to_openai_tool(tool)["function"]["description"]
    low = desc.lower()
    for w in ("spoons", "forks", "knives", "small plates", "large plates", "napkins"):
        assert w in low
    assert desc.count("{") >= 2
    item_guests = re.search(r"\{[^{}]*item[^{}]*guests[^{}]*\}", desc) or \
        re.search(r"\{[^{}]*guests[^{}]*item[^{}]*\}", desc)
    item_meal = re.search(r"\{[^{}]*item[^{}]*meal[^{}]*\}", desc) or \
        re.search(r"\{[^{}]*meal[^{}]*item[^{}]*\}", desc)
    assert item_guests, "no example call with item and guests"
    assert item_meal, "no example call with item and meal"


def test_invoke_matches_run_food_tool(rules):
    """Covers: AC-10 (right), TOOL-3. invoke returns run_food_tool(...).text."""
    args = {"item": "forks", "guests": 70}
    out = make_food_tool(rules).invoke(args)
    assert out == run_food_tool(args, rules).text
    assert "120" in out


def test_invoke_napkin_yes(rules):
    """Covers: AC-10 (right), TOOL-4. Napkin call returns text with yes."""
    out = make_food_tool(rules).invoke({"item": "dinner napkins", "meal": "lunch"})
    assert re.search(r"\byes\b", out)


def test_invoke_invalid_returns_text(rules):
    """Covers: AC-10 (wrong). Invalid arguments come back as text, not an exception."""
    out = make_food_tool(rules).invoke({"item": "forks", "guests": -5})
    assert isinstance(out, str) and out.lower().startswith("invalid")


def test_invoke_need_info_returns_text(rules):
    """Covers: AC-10 (wrong). need_info text goes through the tool."""
    out = make_food_tool(rules).invoke({"item": "forks"})
    assert out.strip().endswith("?")


def test_made_tool_uses_given_rules(write_rules, appendix_a):
    """Covers: AC-10 (right), AC-11. A tool made with other rules uses them."""
    from blc.tools.food_tools import load_food_rules
    appendix_a["extras"] = [{"guests_up_to": None, "extra": 3}]
    t = make_food_tool(load_food_rules(write_rules(appendix_a)))
    assert "13" in t.invoke({"item": "forks", "guests": 10})


def test_make_tool_reads_no_file_until_invoked(point_rules_file_at_missing):
    """Covers: AC-10 (boundary), AC-12, TOOL-5. Making the tool is fine; invoking it raises."""
    from blc.tools.food_tools import FoodRulesError
    t = make_food_tool()
    assert isinstance(t, BaseTool) and t.name == FOOD_TOOL_NAME
    with pytest.raises(Exception) as exc:
        t.invoke({"item": "forks", "guests": 70})
    assert isinstance(exc.value, FoodRulesError) or isinstance(exc.value.__cause__, FoodRulesError)
