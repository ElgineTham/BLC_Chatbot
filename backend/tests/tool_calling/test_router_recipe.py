"""Spec 016 AC-1: the router with scale_recipe available (EC-1 to EC-4). Unit; no Ollama, nothing read under data/."""

from __future__ import annotations

import dataclasses
import re

import pytest

from blc.router import RoutedPart, TOOL_REGISTRY, ToolEntry, classifier_prompt, pick_tool, route_fast

BEV = "calculate_bev_item"
RECIPE = "scale_recipe"
RECIPE_KEYWORDS = {
    "recipe", "ingredient", "ingredients", "concentrate", "oz", "ounce", "ounces",
    "how to make", "how do i make", "how do we make", "how can i make",
}


def entry(name):
    matches = [e for e in TOOL_REGISTRY if e.name == name]
    assert len(matches) == 1
    return matches[0]


# ---------------------------------------------------------------- EC-1 the default table

def test_default_table_order_and_availability():
    """Covers: AC-1 (right), EC-1. Default table: scale_recipe then calculate_bev_item, both available."""
    assert [e.name for e in TOOL_REGISTRY] == [RECIPE, BEV]
    assert all(e.available is True for e in TOOL_REGISTRY)


def test_recipe_row_keeps_name_purpose_and_keywords():
    """Covers: AC-1 (right), EC-1. scale_recipe keeps its spec 013 keywords; its purpose is a non-empty single line."""
    e = entry(RECIPE)
    assert set(e.keywords) == RECIPE_KEYWORDS
    assert e.purpose.strip() and "\n" not in e.purpose


def test_bev_row_is_unchanged_and_available():
    """Covers: AC-1 (right), EC-1. calculate_bev_item stays available with its keywords and purpose."""
    e = entry(BEV)
    assert e.available is True and e.keywords and e.purpose.strip()


def test_switching_recipe_off_in_a_copy_does_not_change_the_default():
    """Covers: AC-1 (boundary), EC-1, EC-3. A custom table is a copy: the default table stays available."""
    off = tuple(dataclasses.replace(e, available=False) if e.name == RECIPE else e for e in TOOL_REGISTRY)
    assert off[0].available is False
    assert entry(RECIPE).available is True


# ---------------------------------------------------------------- EC-2 pick_tool

@pytest.mark.parametrize(
    "text,expected",
    [
        ("How do I make 3 gallons of lemonade?", RECIPE),
        ("How much concentrate for 6 gallons of lemonade?", RECIPE),
        ("How many oz of lemon concentrate for 40 guests?", RECIPE),
        ("How many cambros do I need for 7 gallons of lemonade?", BEV),
        ("Where is the coffee?", None),
    ],
)
def test_pick_tool_rows(text, expected):
    """Covers: AC-1 (right, wrong), EC-2. The five rows of EC-2 with the default table."""
    assert pick_tool(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("What is the recipe for 4 gallons of lemonade?", RECIPE),
        ("HOW DO I MAKE 8 GALLONS OF LEMONADE?", RECIPE),
        ("How many cups for 55 guests?", BEV),
        ("Do I bring sugar for hot water?", BEV),
    ],
)
def test_pick_tool_extra_rows(text, expected):
    """Covers: AC-1 (right), EC-2. Extra: a recipe word picks scale_recipe ignoring case; item words still pick the beverage tool."""
    assert pick_tool(text) == expected


# ---------------------------------------------------------------- EC-3 classifier prompt

def test_classifier_prompt_has_both_purposes_and_letters():
    """Covers: AC-1 (right), EC-3. The default prompt holds both purposes, T and D, and is at most 1500 characters."""
    p = classifier_prompt()
    assert entry(RECIPE).purpose in p and entry(BEV).purpose in p
    assert re.search(r"\bT\b", p) and re.search(r"\bD\b", p)  # whole words, not inside other words
    assert len(p) <= 1500


def test_classifier_prompt_custom_registry_leaves_out_unavailable_purpose():
    """Covers: AC-1 (wrong), EC-3. A custom registry with an unavailable extra entry leaves that purpose out; an available one is in."""
    off = ToolEntry("weigh_boxes", "Weighs boxes of supplies for a delivery.", ("weigh",), False)
    on = dataclasses.replace(off, available=True)
    assert off.purpose not in classifier_prompt(TOOL_REGISTRY + (off,))
    p = classifier_prompt(TOOL_REGISTRY + (on,))
    assert on.purpose in p and entry(RECIPE).purpose in p


def test_classifier_prompt_leaves_out_switched_off_recipe():
    """Covers: AC-1 (wrong), EC-3. With scale_recipe switched off in a custom table its purpose is not in the prompt."""
    off = tuple(dataclasses.replace(e, available=False) if e.name == RECIPE else e for e in TOOL_REGISTRY)
    p = classifier_prompt(off)
    assert entry(RECIPE).purpose not in p and entry(BEV).purpose in p


# ---------------------------------------------------------------- EC-4 route_fast

def test_route_fast_t_reply_makes_a_recipe_tool_part(Scripted):
    """Covers: AC-1 (right), EC-4. A scripted T on a recipe question with an amount gives one TOOL part with tool scale_recipe."""
    q = "How do I make 3 gallons of lemonade?"
    llm = Scripted(["T"])
    d = route_fast(llm, [], q)
    assert d.parts == (RoutedPart("TOOL", q, RECIPE),)
    assert d.kind == "TOOL" and d.fallback is False
    assert len(llm.plain_invocations) == 1


def test_route_fast_how_much_concentrate_is_a_recipe_tool_part(Scripted):
    """Covers: AC-1 (right), EC-4. 'How much concentrate for 6 gallons of lemonade?' with T is scale_recipe."""
    q = "How much concentrate for 6 gallons of lemonade?"
    d = route_fast(Scripted(["T"]), [], q)
    assert d.parts == (RoutedPart("TOOL", q, RECIPE),)


def test_route_fast_plain_how_do_i_make_is_docs_without_a_call(Scripted):
    """Covers: AC-1 (wrong), EC-4. 'How do I make lemonade?' (no amount) is DOCS and the model is never called."""
    q = "How do I make lemonade?"
    llm = Scripted([])
    d = route_fast(llm, [], q)
    assert d.parts == (RoutedPart("DOCS", q, None),)
    assert d.kind == "DOCS" and d.fallback is False
    assert llm.plain_invocations == []


def test_route_fast_d_reply_keeps_a_recipe_question_in_docs(Scripted):
    """Covers: AC-1 (wrong), EC-4. A D reply for a recipe question with an amount gives a DOCS part with no tool."""
    q = "How do I make 3 gallons of lemonade?"
    d = route_fast(Scripted(["D"]), [], q)
    assert d.parts == (RoutedPart("DOCS", q, None),)


def test_route_fast_two_clauses_give_two_different_tools(Scripted):
    """Covers: AC-1 (right), EC-4. Extra: one reply TT labels a cambros clause and a concentrate clause: tools calculate_bev_item then scale_recipe."""
    q = "How many cambros for 6 gallons of lemonade; how much concentrate for 6 gallons of lemonade?"
    llm = Scripted(["TT"])
    d = route_fast(llm, [], q)
    assert [p.route for p in d.parts] == ["TOOL", "TOOL"]
    assert [p.tool for p in d.parts] == [BEV, RECIPE]
    assert len(llm.plain_invocations) == 1


def test_route_fast_follow_up_with_amount_is_a_recipe_tool_part(Scripted):
    """Covers: AC-1 (right), EC-4. Extra: 'And for 7 gallons?' after a recipe question joins it and the part is a scale_recipe TOOL part."""
    history = [
        {"role": "user", "content": "How do I make lemonade?"},
        {"role": "assistant", "content": "Pour 7 oz of lemon concentrate into a clean 1-gallon container."},
    ]
    d = route_fast(Scripted(["T"]), history, "And for 7 gallons?")
    assert len(d.parts) == 1
    assert d.parts[0].route == "TOOL" and d.parts[0].tool == RECIPE
    assert "How do I make lemonade?" in d.parts[0].text and "7 gallons" in d.parts[0].text
