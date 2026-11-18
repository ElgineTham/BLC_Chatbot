"""Spec 015 AC-5: the LangChain tool object and its schema (EC-17, EC-18). Unit."""

from __future__ import annotations

import sys

import pytest
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.tools.recipe_tools import (
    RECIPE_TOOL,
    RECIPE_TOOL_NAME,
    RecipeFileError,
    load_recipe_book,
    make_recipe_tool,
    run_recipe_tool,
)

FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title"}

EXPECTED_PARAMETERS = {
    "type": "object",
    "properties": {
        "recipe": {"type": "string"},
        "gallons": {"type": "number", "exclusiveMinimum": 0},
        "guests": {"type": "integer", "minimum": 1},
    },
    "required": ["recipe"],
}


def _strip_descriptions(params):
    out = {k: v for k, v in params.items() if k != "properties"}
    out["properties"] = {n: {k: v for k, v in p.items() if k != "description"}
                         for n, p in params["properties"].items()}
    return out


def _walk(node):
    """Yield every key and every scalar value in a nested JSON structure."""
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
def tool(request, book):
    return RECIPE_TOOL if request.param == "real" else make_recipe_tool(book)


def test_tool_name(tool):
    """Covers: AC-5 (right), EC-17. The tool is a BaseTool named scale_recipe."""
    assert isinstance(tool, BaseTool)
    assert tool.name == RECIPE_TOOL_NAME == "scale_recipe"


def test_schema_exact(tool):
    """Covers: AC-5 (right), EC-17. parameters equal section 3.3 apart from descriptions."""
    fn = convert_to_openai_tool(tool)["function"]
    assert fn["name"] == RECIPE_TOOL_NAME
    params = fn["parameters"]
    assert _strip_descriptions(params) == EXPECTED_PARAMETERS


def test_properties_have_descriptions(tool):
    """Covers: AC-5 (right), EC-17. Each property has a non-empty description and nothing else extra."""
    props = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
    for name in ("recipe", "gallons", "guests"):
        assert isinstance(props[name].get("description"), str) and props[name]["description"].strip()


def test_schema_has_no_forbidden_keys(tool):
    """Covers: AC-5 (wrong), EC-17. No anyOf/oneOf/allOf/$ref/$defs/default/title or 'null' anywhere."""
    params = convert_to_openai_tool(tool)["function"]["parameters"]
    seen = set(_walk(params))
    assert not (FORBIDDEN_KEYS & seen)
    assert "null" not in seen


def test_description_content(tool):
    """Covers: AC-5 (right), EC-17. The description mentions recipe, gallons, guests and has 2+ example dicts."""
    desc = convert_to_openai_tool(tool)["function"]["description"]
    assert desc.count("{") >= 2
    low = desc.lower()
    for word in ("recipe", "gallons", "guests"):
        assert word in low
    assert '"gallons"' in desc or "'gallons'" in desc or "gallons:" in low
    assert '"guests"' in desc or "'guests'" in desc or "guests:" in low


def test_invoke_matches_run_recipe_tool(book):
    """Covers: AC-5 (right), EC-18. invoke returns run_recipe_tool(...).text."""
    t = make_recipe_tool(book)
    args = {"recipe": "lemonade", "gallons": 6}
    out = t.invoke(args)
    assert out == run_recipe_tool(args, book).text
    assert "Lemon concentrate: 42 oz" in out


def test_invoke_invalid_returns_text(book):
    """Covers: AC-5 (wrong), EC-18. A negative gallons returns an 'invalid' text and does not raise."""
    out = make_recipe_tool(book).invoke({"recipe": "lemonade", "gallons": -1})
    assert isinstance(out, str) and out.lower().startswith("invalid")


def test_invoke_guests_and_no_recipe(book):
    """Covers: AC-5 (right), EC-18 (extra). Guests and unknown-recipe paths go through the tool too."""
    t = make_recipe_tool(book)
    assert "from 70 guests" in t.invoke({"recipe": "lemonade", "guests": 70})
    assert "no recipe" in t.invoke({"recipe": "iced tea", "gallons": 2}).lower()


def test_made_tool_uses_given_book(book):
    """Covers: AC-5 (right), EC-18, NFR-3. A tool made with the test book knows Fruit punch."""
    out = make_recipe_tool(book).invoke({"recipe": "fruit punch", "gallons": 3})
    assert "Orange concentrate: 15 oz" in out


def test_make_tool_reads_no_file(monkeypatch, tmp_path):
    """Covers: AC-5 (boundary), EC-18, NFR-2. make_recipe_tool() with no book loads nothing when made."""
    for name, mod in list(sys.modules.items()):
        if name.startswith("blc.tools.recipe_tools") and mod is not None and hasattr(mod, "RECIPES_FILE"):
            monkeypatch.setattr(mod, "RECIPES_FILE", tmp_path / "missing.json")
    with pytest.raises(RecipeFileError):  # the patch reached the loader
        load_recipe_book()
    t = make_recipe_tool()  # must not raise although the file is missing
    assert isinstance(t, BaseTool) and t.name == RECIPE_TOOL_NAME


def test_missing_real_file_surfaces_when_run(monkeypatch, tmp_path):
    """Covers: AC-5 (wrong), EC-18 (extra). Loaded when the tool runs: a missing file raises RecipeFileError then."""
    for name, mod in list(sys.modules.items()):
        if name.startswith("blc.tools.recipe_tools") and mod is not None and hasattr(mod, "RECIPES_FILE"):
            monkeypatch.setattr(mod, "RECIPES_FILE", tmp_path / "missing.json")
    with pytest.raises(RecipeFileError):  # the patch reached the loader
        load_recipe_book()
    t = make_recipe_tool()
    with pytest.raises(Exception) as exc:
        t.invoke({"recipe": "lemonade", "gallons": 2})
    assert isinstance(exc.value, RecipeFileError) or isinstance(exc.value.__cause__, RecipeFileError)
