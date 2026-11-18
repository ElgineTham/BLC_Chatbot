"""Spec 013 AC-2: TOOL_REGISTRY, ToolEntry, pick_tool, classifier_prompt (section 4.4, EC-14 to EC-17).

Pure functions: no model, no Ollama, no network, nothing read under data/ (NFR-2).
"""

from __future__ import annotations

import dataclasses

import pytest

from blc.router import (
    CLASSIFIER_MAX_TOKENS,
    PULL_SHEET_ITEMS,
    TOOL_REGISTRY,
    ToolEntry,
    classifier_prompt,
    pick_tool,
)

BEV = "calculate_bev_item"
RECIPE = "scale_recipe"


def entry(name):
    matches = [e for e in TOOL_REGISTRY if e.name == name]
    assert len(matches) == 1, f"expected one {name} row, got {len(matches)}"
    return matches[0]


def with_recipe_available():
    return tuple(dataclasses.replace(e, available=True) if e.name == RECIPE else e for e in TOOL_REGISTRY)


def with_recipe_unavailable():
    """Spec 016 AC-4: a custom table where scale_recipe is switched off (it is available in the default table)."""
    return tuple(dataclasses.replace(e, available=False) if e.name == RECIPE else e for e in TOOL_REGISTRY)


def with_bev_unavailable():
    return tuple(dataclasses.replace(e, available=False) if e.name == BEV else e for e in TOOL_REGISTRY)


EXTRA = ToolEntry("weigh_boxes", "Weighs boxes of supplies for a delivery.", ("weigh", "weight"), True)
EXTRA_OFF = dataclasses.replace(EXTRA, available=False)


# ---------------------------------------------------------------- the default table (EC-15)

def test_default_table_rows_and_availability():
    """Covers: AC-2 (right), EC-15; spec 016 AC-4. The default table has scale_recipe and calculate_bev_item, both available."""
    assert isinstance(TOOL_REGISTRY, tuple)
    assert entry(RECIPE).available is True
    assert entry(BEV).available is True


def test_default_table_order_recipe_then_bev():
    """Covers: AC-2 (right), EC-15. Table order is scale_recipe first, then calculate_bev_item (section 3.1)."""
    names = [e.name for e in TOOL_REGISTRY]
    assert names.index(RECIPE) < names.index(BEV)


def test_every_entry_has_a_one_line_purpose():
    """Covers: AC-2 (wrong), EC-15. Every purpose is a non-empty single line (no newline)."""
    for e in TOOL_REGISTRY:
        assert isinstance(e, ToolEntry)
        assert isinstance(e.purpose, str) and e.purpose.strip()
        assert "\n" not in e.purpose and "\r" not in e.purpose


def test_every_entry_has_lower_case_keywords():
    """Covers: AC-2 (right), EC-15. Keywords are a non-empty tuple of lower case strings."""
    for e in TOOL_REGISTRY:
        assert isinstance(e.keywords, tuple) and e.keywords
        assert all(isinstance(k, str) and k and k == k.lower() for k in e.keywords)


def test_bev_keywords_equal_the_pull_sheet_item_words():
    """Covers: AC-2 (right), EC-15. calculate_bev_item's keywords are exactly the words of PULL_SHEET_ITEMS."""
    words = {w for ws in PULL_SHEET_ITEMS.values() for w in ws}
    assert set(entry(BEV).keywords) == words


def test_recipe_keywords_are_the_contract_words():
    """Covers: AC-2 (right), EC-15. scale_recipe's keywords are the ones listed in section 3.1."""
    expected = {
        "recipe", "ingredient", "ingredients", "concentrate", "oz", "ounce", "ounces",
        "how to make", "how do i make", "how do we make", "how can i make",
    }
    assert set(entry(RECIPE).keywords) == expected


def test_tool_entry_is_a_frozen_dataclass():
    """Covers: AC-2 (wrong), section 3.1. ToolEntry is frozen and has the four fields."""
    e = ToolEntry("x", "Does x.", ("x",), True)
    assert (e.name, e.purpose, e.keywords, e.available) == ("x", "Does x.", ("x",), True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.available = False


def test_classifier_max_tokens_constant():
    """Covers: AC-2 (right), section 3.1. CLASSIFIER_MAX_TOKENS is 8."""
    assert CLASSIFIER_MAX_TOKENS == 8


# ---------------------------------------------------------------- pick_tool (EC-14)

@pytest.mark.parametrize(
    "text,expected",
    [
        ("How many cambros do I need for 7 gallons of lemonade?", BEV),
        ("Do I bring sugar for hot water?", BEV),
        ("How do I make 3 gallons of lemonade?", RECIPE),
        ("How much concentrate for 6 gallons of lemonade?", RECIPE),
        ("Where is the coffee?", None),
    ],
)
def test_pick_tool_table_rows(text, expected):
    """Covers: AC-2 (right, wrong), EC-14; spec 016 AC-4. Rows of the section 4.4 table with the default table (recipe questions with an amount now give scale_recipe)."""
    assert pick_tool(text) == expected


def test_pick_tool_recipe_row_with_recipe_available():
    """Covers: AC-2 (right), EC-14, EC-16. The same recipe question gives scale_recipe once the row is available."""
    assert pick_tool("How do I make 3 gallons of lemonade?", with_recipe_available()) == RECIPE


def test_pick_tool_explicit_default_registry_matches_default():
    """Covers: AC-2 (right), EC-14. Passing TOOL_REGISTRY explicitly is the same as the default."""
    q = "How many cups for 55 guests?"
    assert pick_tool(q, TOOL_REGISTRY) == pick_tool(q) == BEV


@pytest.mark.parametrize("text", ["HOW MANY CAMBROS FOR 5 GALLONS?", "do i bring SUGAR?", "What goes on the Pull Sheet?"])
def test_pick_tool_ignores_case_and_matches_phrases(text):
    """Covers: AC-2 (right), EC-14. Keywords match ignoring case; 'pull sheet' is a phrase."""
    assert pick_tool(text) == BEV


@pytest.mark.parametrize(
    "text",
    ["Where is the lemonade?", "Where is the cupboard?", "What is the cupcake flavor?", "Where do the mugs go?"],
)
def test_pick_tool_keywords_are_whole_words(text):
    """Covers: AC-2 (wrong, boundary), EC-14. 'lemonade' is not 'lemons', 'cupboard' is not 'cups'."""
    assert pick_tool(text) is None


def test_pick_tool_recipe_word_beats_item_word_without_falling_through():
    """Covers: AC-2 (wrong), EC-14; spec 016 AC-4. With scale_recipe switched off (custom table), a text with a recipe word and an item word matches the unavailable recipe tool and gives None; it never falls through to the bev tool. With the default table (recipe available) the same texts give scale_recipe."""
    off = with_recipe_unavailable()
    assert pick_tool("How many oz of lemonade per cup?", off) is None
    assert pick_tool("What is the recipe for 5 gallons of iced tea?", off) is None
    assert pick_tool("How many oz of lemonade per cup?") == RECIPE
    assert pick_tool("What is the recipe for 5 gallons of iced tea?") == RECIPE


def test_pick_tool_recipe_available_wins_over_bev_words():
    """Covers: AC-2 (right), EC-14, EC-16. With scale_recipe available, a text with both kinds of words gives scale_recipe (step 1 before step 2)."""
    reg = with_recipe_available()
    assert pick_tool("How much concentrate for 6 gallons of lemonade?", reg) == RECIPE
    assert pick_tool("How many cambros for 5 gallons?", reg) == BEV


@pytest.mark.parametrize("text", ["", "   ", "\n", "?", "5"])
def test_pick_tool_blank_and_odd_text_gives_none(text):
    """Covers: AC-2 (boundary), EC-14. Blank or keyword-free text gives None and never raises."""
    assert pick_tool(text) is None


# ---------------------------------------------------------------- custom registries (EC-16)

def test_pick_tool_bev_unavailable_gives_none():
    """Covers: AC-2 (wrong), EC-16. With calculate_bev_item unavailable, an item question gives None."""
    assert pick_tool("How many cups for 55 guests?", with_bev_unavailable()) is None


def test_pick_tool_empty_registry():
    """Covers: AC-2 (boundary), EC-16. An empty table never picks a tool."""
    assert pick_tool("How many cups for 55 guests?", ()) is None


def test_pick_tool_extra_available_entry_is_picked():
    """Covers: AC-2 (right), EC-16. An extra available entry is found by its keywords; the other tools still work."""
    reg = TOOL_REGISTRY + (EXTRA,)
    assert pick_tool("Please weigh the boxes", reg) == "weigh_boxes"
    assert pick_tool("How many cups for 55 guests?", reg) == BEV


def test_pick_tool_extra_unavailable_entry_is_never_picked():
    """Covers: AC-2 (wrong), EC-16. An extra entry with available=False is never picked."""
    reg = TOOL_REGISTRY + (EXTRA_OFF,)
    assert pick_tool("Please weigh the boxes", reg) is None


def test_pick_tool_does_not_change_the_registry():
    """Covers: AC-2 (boundary), NFR-5. pick_tool takes data and returns data: the table is unchanged."""
    before = tuple(TOOL_REGISTRY)
    pick_tool("How many cups?")
    assert TOOL_REGISTRY == before


# ---------------------------------------------------------------- classifier_prompt (EC-17)

def test_classifier_prompt_default():
    """Covers: AC-2 (right), section 4.4. Non-empty string of at most 1500 characters with the available purpose and the letters T and D."""
    p = classifier_prompt()
    assert isinstance(p, str) and p.strip()
    assert len(p) <= 1500
    assert entry(BEV).purpose in p
    assert "T" in p and "D" in p


def test_classifier_prompt_leaves_out_unavailable_entry():
    """Covers: AC-2 (wrong), section 4.4, EC-17; spec 016 AC-4. With scale_recipe switched off (custom table), its purpose is not in the prompt; in the default table it is."""
    assert entry(RECIPE).purpose not in classifier_prompt(with_recipe_unavailable())
    assert entry(RECIPE).purpose in classifier_prompt()


def test_classifier_prompt_matches_explicit_default():
    """Covers: AC-2 (right), EC-17. classifier_prompt() equals classifier_prompt(TOOL_REGISTRY)."""
    assert classifier_prompt() == classifier_prompt(TOOL_REGISTRY)


def test_classifier_prompt_with_recipe_available_has_both_purposes():
    """Covers: AC-2 (right), EC-17. Making scale_recipe available adds its purpose, within the length limit."""
    p = classifier_prompt(with_recipe_available())
    assert entry(RECIPE).purpose in p and entry(BEV).purpose in p
    assert len(p) <= 1500


def test_classifier_prompt_custom_registry_purposes():
    """Covers: AC-2 (right, wrong), EC-17. An extra available entry's purpose is in; an unavailable extra's purpose is not."""
    p_on = classifier_prompt(TOOL_REGISTRY + (EXTRA,))
    assert EXTRA.purpose in p_on and entry(BEV).purpose in p_on
    p_off = classifier_prompt(TOOL_REGISTRY + (EXTRA_OFF,))
    assert EXTRA_OFF.purpose not in p_off and entry(BEV).purpose in p_off


def test_classifier_prompt_bev_unavailable_leaves_out_its_purpose():
    """Covers: AC-2 (wrong), EC-17. A table where calculate_bev_item is unavailable no longer shows its purpose."""
    p = classifier_prompt(with_bev_unavailable())
    assert entry(BEV).purpose not in p
    assert isinstance(p, str) and p.strip() and "T" in p and "D" in p


def test_classifier_prompt_empty_registry_still_a_prompt():
    """Covers: AC-2 (boundary), EC-17. An empty table gives a non-empty prompt with T and D."""
    p = classifier_prompt(())
    assert p.strip() and "T" in p and "D" in p and len(p) <= 1500
