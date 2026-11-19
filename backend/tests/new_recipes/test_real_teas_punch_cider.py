"""Spec 040 AC-3, AC-4, AC-7, AC-8: real iced teas, punch, cider and tool paths (REAL-6..16, 20). Skips without the file."""

from __future__ import annotations

from fractions import Fraction as Fr

import pytest

from blc.tools.recipe_tools import RECIPE_TOOL, make_recipe_tool, run_recipe_tool, scale_recipe

BIG = "3-gallon tea bag"
SMALL = "1-gallon tea bag"


def _ing(r):
    return [(i.name, i.amount, i.unit, i.fill) for i in r.ingredients]


def _names(r):
    return [i.name for i in r.ingredients]


def test_mango_tea_1_gallon(real_book):
    """Covers: AC-3, AC-7 (right), REAL-6. One 1-gallon bag, no 3-gallon line."""
    r = scale_recipe("Mango Iced Tea", gallons=1, book=real_book)
    assert _ing(r) == [
        (SMALL, Fr(1), "bag", False),
        ("Mango syrup", Fr(8), "oz", False),
        ("Water", Fr(1), "gallon", True),
    ]
    assert BIG not in _names(r)


def test_mango_tea_4_gallons(real_book):
    """Covers: AC-3, AC-7 (right), REAL-7. One 3-gallon bag, no 1-gallon line; text says "1 bag"."""
    r = scale_recipe("Mango Iced Tea", gallons=4, book=real_book)
    assert _ing(r) == [
        (BIG, Fr(1), "bag", False),
        ("Mango syrup", Fr(32), "oz", False),
        ("Water", Fr(4), "gallon", True),
    ]
    assert "3-gallon tea bag: 1 bag" in r.text
    assert "1 bags" not in r.text
    assert SMALL not in r.text


def test_raspberry_tea_5_gallons(real_book):
    """Covers: AC-3 (right), REAL-8. A 3-gallon bag then a 1-gallon bag; 40 oz syrup."""
    r = scale_recipe("Raspberry Iced Tea", gallons=5, book=real_book)
    assert _ing(r) == [
        (BIG, Fr(1), "bag", False),
        (SMALL, Fr(1), "bag", False),
        ("Raspberry syrup", Fr(40), "oz", False),
        ("Water", Fr(5), "gallon", True),
    ]


def test_raspberry_tea_9_gallons_tie_rule(real_book):
    """Covers: AC-3 (boundary), REAL-9. Three 3-gallon bags and no 1-gallon line; 72 oz syrup."""
    r = scale_recipe("Raspberry Iced Tea", gallons=9, book=real_book)
    assert _ing(r)[0] == (BIG, Fr(3), "bag", False)
    assert SMALL not in _names(r)
    assert [i.amount for i in r.ingredients if i.name == "Raspberry syrup"] == [72]


def test_raspberry_tea_2_gallons(real_book):
    """Covers: AC-3, AC-7 (boundary), REAL-10. Two 1-gallon bags; 16 oz syrup; text "2 bags"."""
    r = scale_recipe("Raspberry Iced Tea", gallons=2, book=real_book)
    assert _ing(r)[0] == (SMALL, Fr(2), "bag", False)
    assert BIG not in _names(r)
    assert [i.amount for i in r.ingredients if i.name == "Raspberry syrup"] == [16]
    assert "1-gallon tea bag: 2 bags" in r.text


def test_mango_tea_fractional_batch(real_book):
    """Covers: AC-3 (boundary), REAL-11. 2.5 gallons: one 3-gallon bag; syrup and water use exact 2.5."""
    r = scale_recipe("Mango Iced Tea", gallons=2.5, book=real_book)
    assert _ing(r) == [
        (BIG, Fr(1), "bag", False),
        ("Mango syrup", Fr(20), "oz", False),
        ("Water", Fr(5, 2), "gallon", True),
    ]


def test_mango_tea_7_gallons(real_book):
    """Covers: AC-3 (right), REAL-12. Two 3-gallon bags, no 1-gallon line; 56 oz syrup."""
    r = scale_recipe("Mango Iced Tea", gallons=7, book=real_book)
    assert _ing(r)[0] == (BIG, Fr(2), "bag", False)
    assert SMALL not in _names(r)
    assert [i.amount for i in r.ingredients if i.name == "Mango syrup"] == [56]


def test_mango_tea_6_gallons_text(real_book):
    """Covers: AC-3, AC-7 (right), REAL-20. Text lines, numbered steps, no 1-gallon line."""
    t = scale_recipe("Mango Iced Tea", gallons=6, book=real_book).text
    assert "3-gallon tea bag: 2 bags" in t
    assert "Mango syrup: 48 oz" in t
    assert "Water: fill to 6 gallons" in t
    for n in ("1.", "2.", "3.", "4."):
        assert n in t
    assert SMALL not in t


@pytest.mark.parametrize("gallons", range(1, 14))
def test_real_tea_bag_counts_match_table(real_book, gallons):
    """Covers: AC-3 (boundary). Real tea bag counts match the section 4.2 table for 1..13 gallons."""
    table = {
        1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 0), 5: (1, 1), 6: (2, 0), 7: (2, 0),
        8: (2, 0), 9: (3, 0), 10: (3, 0), 11: (3, 0), 12: (3, 0), 13: (4, 0),
    }
    r = scale_recipe("Raspberry Iced Tea", gallons=gallons, book=real_book)
    got = {i.name: i.amount for i in r.ingredients if i.unit == "bag"}
    big, small = table[gallons]
    assert got.get(BIG, 0) == big and got.get(SMALL, 0) == small


def test_punch_4_gallons(real_book):
    """Covers: AC-4 (right), REAL-13. Three concentrates 100 oz, Water fill, Sprite 96 oz, in file order."""
    r = scale_recipe("Citrus Fruit Punch", gallons=4, book=real_book)
    assert _ing(r) == [
        ("Pineapple juice concentrate", Fr(100), "oz", False),
        ("Lemonade concentrate", Fr(100), "oz", False),
        ("Orange juice concentrate", Fr(100), "oz", False),
        ("Water", Fr(4), "gallon", True),
        ("Sprite", Fr(96), "oz", False),
    ]


def test_punch_1_5_gallons(real_book):
    """Covers: AC-4 (boundary), REAL-14. Each concentrate 75/2 oz, Sprite 36 oz, text "37.5 oz"."""
    r = scale_recipe("Citrus Fruit Punch", gallons=1.5, book=real_book)
    amounts = {i.name: i.amount for i in r.ingredients}
    for n in ("Pineapple juice concentrate", "Lemonade concentrate", "Orange juice concentrate"):
        assert amounts[n] == Fr(75, 2)
    assert amounts["Sprite"] == 36
    assert "37.5 oz" in r.text


def test_cider(real_book):
    """Covers: AC-4 (right), REAL-15. Cider fill 1 and 4; ginger 3/4 and 3 cups; 1-gal text "0.75 cups"."""
    r1 = scale_recipe("Apple Cider with Ginger", gallons=1, book=real_book)
    assert _ing(r1) == [
        ("Apple cider", Fr(1), "gallon", True),
        ("Grated fresh ginger", Fr(3, 4), "cups", False),
    ]
    assert "0.75 cups" in r1.text
    r4 = scale_recipe("Apple Cider with Ginger", gallons=4, book=real_book)
    assert _ing(r4) == [
        ("Apple cider", Fr(4), "gallon", True),
        ("Grated fresh ginger", Fr(3), "cups", False),
    ]


def test_punch_sprite_not_concentrate_rate_and_no_bags(real_book):
    """Covers: AC-4 (wrong), REAL-13. Sprite is 24 oz/gal (96 at 4 gal), never 100 oz; no bag line."""
    r = scale_recipe("Citrus Fruit Punch", gallons=4, book=real_book)
    sprite = [i for i in r.ingredients if i.name == "Sprite"]
    assert len(sprite) == 1
    assert sprite[0].amount != 100
    assert sprite[0].amount == 96
    assert not [i for i in r.ingredients if i.unit == "bag"]
    assert "bag" not in r.text.lower()


def test_cider_is_fill_line_not_measured(real_book):
    """Covers: AC-4 (wrong), REAL-15. Apple cider is a fill line in gallons (not oz or cups); at 4 gal the
    text says "Apple cider: fill to 4 gallons" and the ginger line has no "oz"."""
    r = scale_recipe("Apple Cider with Ginger", gallons=4, book=real_book)
    cider = [i for i in r.ingredients if i.name == "Apple cider"]
    assert len(cider) == 1
    assert cider[0].fill is True and cider[0].unit == "gallon"
    assert cider[0].unit not in ("oz", "cups")
    assert "Apple cider: fill to 4 gallons" in r.text
    ginger_lines = [ln for ln in r.text.splitlines() if "Grated fresh ginger" in ln]
    assert ginger_lines
    assert all("oz" not in ln for ln in ginger_lines)


def test_cider_one_gallon_text_singular(real_book):
    """Covers: AC-4 (boundary). Text never has "1 gallons"."""
    t = scale_recipe("Apple Cider with Ginger", gallons=1, book=real_book).text
    assert "1 gallons" not in t


@pytest.mark.parametrize("name", ["Mango Iced Tea", "Citrus Fruit Punch", "Apple Cider with Ginger"])
def test_need_info_without_amount(real_book, name):
    """Covers: AC-8 (wrong). No gallons and no guests gives need_info."""
    r = scale_recipe(name, book=real_book)
    assert r.status == "need_info" and r.ingredients == ()


# ---- run_recipe_tool / RECIPE_TOOL ----

def test_run_recipe_tool_guests_path(real_book):
    """Covers: AC-8 (right), REAL-16. 130 guests is 5 gallons; bags 1 + 1; syrup 40 oz."""
    r = run_recipe_tool({"recipe": "raspberry iced tea", "guests": 130}, real_book)
    assert r.status == "ok" and r.gallons == 5 and r.from_guests is True
    assert _ing(r)[:3] == [
        (BIG, Fr(1), "bag", False),
        (SMALL, Fr(1), "bag", False),
        ("Raspberry syrup", Fr(40), "oz", False),
    ]


def test_tool_invoke_matches_run(real_book):
    """Covers: AC-8 (right), REAL-16. make_recipe_tool(book).invoke returns run_recipe_tool's text."""
    args = {"recipe": "raspberry iced tea", "guests": 130}
    assert make_recipe_tool(real_book).invoke(args) == run_recipe_tool(args, real_book).text


def test_recipe_tool_default_uses_real_file(real_book):
    """Covers: AC-8 (right), REAL-16. RECIPE_TOOL (real file) returns the 5-gallon tea text."""
    text = RECIPE_TOOL.invoke({"recipe": "raspberry iced tea", "guests": 130})
    assert "3-gallon tea bag: 1 bag" in text and "1-gallon tea bag: 1 bag" in text
    assert "Raspberry syrup: 40 oz" in text and "from 130 guests" in text


@pytest.mark.parametrize("args", [
    {"recipe": "mango iced tea", "gallons": -1},
    {"recipe": "mango iced tea", "gallons": "six"},
    {"recipe": "mango iced tea", "guests": 2.5},
    {"recipe": "raspberry lemonade", "gallons": 2},
    {"recipe": "mango iced tea"},
    {},
])
def test_bad_args_never_raise_with_new_recipes(real_book, args):
    """Covers: AC-8 (wrong). Bad arguments give a status, never an exception, and the tool returns text."""
    r = run_recipe_tool(args, real_book)
    assert r.status in ("invalid", "no_recipe", "need_info")
    assert isinstance(make_recipe_tool(real_book).invoke(args), str)
