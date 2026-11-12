"""AC-6: the LangChain tool object, its exact schema (EC-22), invocation (EC-23) and its
registration in chat.CHAT_TOOLS.

Unit tests: no Ollama, no network, no file under data/ (NFR-3): tools are built with
make_bev_tool(<Appendix A catalog>). BEV_TOOL itself is only inspected, never invoked.
"""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.tools.bev_tools import (
    BEV_ITEMS,
    BEV_TOOL,
    BEV_TOOL_NAME,
    make_bev_tool,
    run_bev_tool,
)

PKG = "Coffee, decaf, tea, iced water & juice"
MENU_ITEMS = (
    "Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider",
    "Iced water", "Iced tea", "Orange juice", "Lemonade", "Peach tea", "Oatmilk",
)
FORBIDDEN_KEYS = {"anyOf", "oneOf", "allOf", "$ref", "$defs", "default", "title"}

EXPECTED_PARAMETERS = {
    "type": "object",
    "properties": {
        "item": {"type": "string", "enum": ["gallons", "cambros", "cups", "supplies", "everything"]},
        "drinks": {"type": "array", "items": {"type": "string"}},
        "gallons": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0}},
        "guests": {"type": "integer", "minimum": 1},
    },
    "required": ["item"],
}


def _function(tool):
    return convert_to_openai_tool(tool)["function"]


def _walk(node):
    """Yield every dict in a nested schema."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _without_descriptions(params):
    """Drop the property-level 'description' (wording is the developer's); keep everything else."""
    out = {k: v for k, v in params.items() if k != "properties"}
    out["properties"] = {
        name: {k: v for k, v in prop.items() if k != "description"}
        for name, prop in params["properties"].items()
    }
    return out


@pytest.fixture(params=["BEV_TOOL", "made"])
def any_tool(request, catalog):
    """Both the module-level tool and a tool made on the Appendix A catalog."""
    return BEV_TOOL if request.param == "BEV_TOOL" else make_bev_tool(catalog)


# ---------------------------------------------------------------- tool object

def test_tool_is_a_named_basetool():
    """Covers: AC-6 (right). BEV_TOOL is a LangChain tool named calculate_bev_item."""
    assert isinstance(BEV_TOOL, BaseTool)
    assert BEV_TOOL.name == BEV_TOOL_NAME == "calculate_bev_item"


def test_make_bev_tool_returns_named_basetool(catalog):
    """Covers: AC-6 (right). make_bev_tool(catalog) returns a BaseTool named calculate_bev_item."""
    tool = make_bev_tool(catalog)
    assert isinstance(tool, BaseTool)
    assert tool.name == BEV_TOOL_NAME


def test_chat_tools_contains_bev_tool():
    """Covers: AC-6 (right). chat.CHAT_TOOLS contains BEV_TOOL."""
    import chat

    assert BEV_TOOL in chat.CHAT_TOOLS
    assert any(t.name == BEV_TOOL_NAME for t in chat.CHAT_TOOLS)


# ---------------------------------------------------------------- EC-22 schema

def test_ec22_function_name(any_tool):
    """Covers: AC-6 (right), EC-22. The function schema is named calculate_bev_item and has a description."""
    fn = _function(any_tool)
    assert fn["name"] == BEV_TOOL_NAME
    assert fn["description"].strip()


def test_ec22_parameters_match_spec_exactly(any_tool):
    """Covers: AC-6 (right), EC-22. parameters equal the section 3.3 schema, apart from description wording."""
    params = _function(any_tool)["parameters"]
    assert _without_descriptions(params) == EXPECTED_PARAMETERS


def test_ec22_every_property_has_a_description(any_tool):
    """Covers: AC-6 (right), EC-22. Each of the four properties carries a non-empty description."""
    props = _function(any_tool)["parameters"]["properties"]
    assert set(props) == {"item", "drinks", "gallons", "guests"}
    for name, prop in props.items():
        assert isinstance(prop.get("description"), str) and prop["description"].strip(), name


def test_ec22_enum_and_required(any_tool):
    """Covers: AC-6 (right), EC-22. enum equals list(BEV_ITEMS); required equals ['item']."""
    params = _function(any_tool)["parameters"]
    assert params["properties"]["item"]["enum"] == list(BEV_ITEMS)
    assert params["required"] == ["item"]


def test_ec22_no_forbidden_keys_or_null_type(any_tool):
    """Covers: AC-6 (wrong), EC-22. No anyOf/oneOf/allOf/$ref/$defs/default/title and no 'null' type anywhere (checked recursively)."""
    params = _function(any_tool)["parameters"]
    for node in _walk(params):
        assert not (FORBIDDEN_KEYS & set(node)), set(node)
        t = node.get("type")
        assert t != "null"
        if isinstance(t, list):
            assert "null" not in t


# ---------------------------------------------------------------- descriptions (section 3.3)

def test_tool_description_has_two_example_calls(any_tool):
    """Covers: AC-6 (right). The tool description contains at least two '{' (example calls) and the words drinks, gallons, guests."""
    desc = _function(any_tool)["description"]
    assert desc.count("{") >= 2
    for word in ("drinks", "gallons", "guests"):
        assert word in desc


def test_tool_description_has_one_example_with_guests_and_no_drinks(any_tool):
    """Covers: AC-6 (right). One example has 'guests' without 'drinks' and one has 'drinks' with 'gallons'."""
    desc = _function(any_tool)["description"]
    desc = desc.replace("'", '"')  # accept Python-style or JSON-style example dicts
    examples = [part.split("}")[0] for part in desc.split("{")[1:]]
    assert any('"drinks"' in e and '"gallons"' in e for e in examples), examples
    assert any('"guests"' in e and '"drinks"' not in e for e in examples), examples


def test_tool_description_says_to_use_the_tool(any_tool):
    """Covers: AC-6 (right). The description tells the model to use the tool instead of calculating."""
    desc = _function(any_tool)["description"].lower()
    assert "calculat" in desc
    assert "instead" in desc or "must" in desc or "always" in desc


def test_drinks_description_names_every_menu_item_and_package(any_tool):
    """Covers: AC-6 (right). The drinks description names every Appendix A item and the package (case-insensitive)."""
    desc = _function(any_tool)["parameters"]["properties"]["drinks"]["description"].lower()
    for name in MENU_ITEMS + (PKG,):
        assert name.lower() in desc, name


def test_gallons_description_content(any_tool):
    """Covers: AC-6 (right). gallons says same order as drinks and that oatmilk's number is a count of pieces."""
    desc = _function(any_tool)["parameters"]["properties"]["gallons"]["description"].lower()
    assert "order" in desc
    assert "oatmilk" in desc
    assert "drinks" in desc


def test_item_description_mentions_containers(any_tool):
    """Covers: AC-6 (right). The item description contains the word "container" (revision 2)."""
    desc = _function(any_tool)["parameters"]["properties"]["item"]["description"].lower()
    assert "container" in desc


def test_item_description_explains_every_item(any_tool):
    """Covers: AC-6 (right). The item description names each of the five items it explains."""
    desc = _function(any_tool)["parameters"]["properties"]["item"]["description"].lower()
    for item in BEV_ITEMS:
        assert item in desc, item


def test_gallons_description_only_user_amounts_never_from_guests(any_tool):
    """Covers: AC-6 (right). The gallons description says to use only amounts the user said and never
    amounts worked out from guests (revision 2)."""
    desc = _function(any_tool)["parameters"]["properties"]["gallons"]["description"].lower()
    assert "guests" in desc
    assert "never" in desc or "not" in desc


@pytest.mark.parametrize("prop", ["gallons", "guests"])
def test_optional_property_descriptions_say_to_leave_out(any_tool, prop):
    """Covers: AC-6 (right). gallons and guests descriptions say to leave the argument out when not given."""
    desc = _function(any_tool)["parameters"]["properties"][prop]["description"].lower()
    assert any(w in desc for w in ("leave", "omit", "skip", "do not include", "don't include", "do not send"))


# ---------------------------------------------------------------- EC-23 invocation

ARGS_LEMONADE_7 = {"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}


def test_ec23_invoke_returns_run_bev_tool_text(catalog):
    """Covers: AC-6 (right), EC-23. Invoking the made tool returns run_bev_tool(args, catalog).text."""
    tool = make_bev_tool(catalog)
    out = tool.invoke(ARGS_LEMONADE_7)
    assert isinstance(out, str)
    assert out == run_bev_tool(ARGS_LEMONADE_7, catalog).text
    assert "5 gal cambro" in out and "2 gal cambro" in out


def test_ec23_needs_no_file_under_data(catalog, tmp_path_factory, monkeypatch):
    """Covers: AC-6 (right), EC-23, NFR-3. With the working directory somewhere without data/, the made tool still answers."""
    elsewhere = tmp_path_factory.mktemp("no_data_here")
    tool = make_bev_tool(catalog)
    monkeypatch.chdir(elsewhere)
    assert not (elsewhere / "data").exists()
    out = tool.invoke(ARGS_LEMONADE_7)
    assert out == run_bev_tool(ARGS_LEMONADE_7, catalog).text


@pytest.mark.parametrize(
    "args",
    [
        {"item": "gallons", "guests": 25},
        {"item": "cups", "guests": 70},
        {"item": "supplies", "drinks": ["coffee"]},
        {"item": "cambros", "drinks": ["coffee", "lemonade"]},
        {"item": "cambros", "drinks": ["hot chocolate"], "gallons": [4]},
        {"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5]},
        {"item": "everything", "drinks": ["coffee"], "guests": 50},
    ],
)
def test_ec23_invoke_equals_run_bev_tool_for_every_status(catalog, args):
    """Covers: AC-6 (right, boundary), EC-23. ok, need_info and not_on_menu results all come back as run_bev_tool's text, with optional arguments missing."""
    tool = make_bev_tool(catalog)
    assert tool.invoke(args) == run_bev_tool(args, catalog).text


def test_ec23_invoke_is_exactly_the_text_not_a_repr(catalog):
    """Covers: AC-6 (wrong). The tool returns plain text (a str), not a BevResult or its repr."""
    out = make_bev_tool(catalog).invoke({"item": "gallons", "guests": 25})
    assert type(out) is str
    assert "BevResult" not in out


def test_ec23_made_tool_text_is_the_spec_example(catalog):
    """Covers: AC-6 (right), EC-23, EC-1. The made tool's answer for Lemonade 7 gal names both cambro sizes once each."""
    out = make_bev_tool(catalog).invoke(ARGS_LEMONADE_7)
    assert "Lemonade: 7 gal" in out
    assert "5 gal cambro: 1" in out and "2 gal cambro: 1" in out
