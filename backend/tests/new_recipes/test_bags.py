"""Spec 040 AC-3, AC-6, AC-7, AC-10: counted-bag format and rule (BAGS-1..7). Unit; test book in tmp_path."""

from __future__ import annotations

import copy
from fractions import Fraction

import pytest

from blc.tools.recipe_tools import BAG_UNIT, RecipeFileError, load_recipe_book, scale_recipe

BIG = "3-gallon tea bag"
SMALL = "1-gallon tea bag"

TEA_BAGS = {
    "bags": [
        {"name": BIG, "brews_from": 3, "brews_to": 4},
        {"name": SMALL, "brews_from": 1, "brews_to": 1},
    ]
}

# The section 4.2 table: rounded batch -> (3-gallon bags, 1-gallon bags)
BAG_TABLE = {
    1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 0), 5: (1, 1), 6: (2, 0), 7: (2, 0),
    8: (2, 0), 9: (3, 0), 10: (3, 0), 11: (3, 0), 12: (3, 0), 13: (4, 0),
}


def bag_book_data(bags=None) -> dict:
    return {"recipes": {
        "Lemonade": {
            "yield_gallons": 1,
            "ingredients": [
                {"name": "Lemon concentrate", "amount": 7, "unit": "oz"},
                {"name": "Water", "fill": True},
            ],
            "steps": ["Pour the concentrate.", "Add water."],
        },
        "Test Iced Tea": {
            "also_written_as": ["Test tea"],
            "yield_gallons": 1,
            "ingredients": [
                copy.deepcopy(bags if bags is not None else TEA_BAGS),
                {"name": "Test syrup", "amount": 8, "unit": "oz"},
                {"name": "Water", "fill": True},
            ],
            "steps": [
                "Place the tea bags in a sanitized bucket.",
                "Add the syrup.",
                "Pour hot water to cover the tea bags and let steep for 10 minutes.",
                "Take out the spent bags and fill the rest with cold water to the batch size.",
            ],
        },
    }}


def _counts(result):
    return {i.name: i.amount for i in result.ingredients if i.unit == BAG_UNIT}


def test_bag_unit_constant():
    """Covers: AC-7 (right), BAGS-6. BAG_UNIT is "bag"."""
    assert BAG_UNIT == "bag"


def test_bag_book_loads_and_scales(bag_book, ing):
    """Covers: AC-6 (right), BAGS-1. A counted-bag recipe loads; ingredient order is bags, syrup, water."""
    r = scale_recipe("Test Iced Tea", gallons=4, book=bag_book)
    assert r.status == "ok"
    assert ing(r) == [
        (BIG, Fraction(1), "bag", False),
        ("Test syrup", Fraction(32), "oz", False),
        ("Water", Fraction(4), "gallon", True),
    ]


@pytest.mark.parametrize("batch", sorted(BAG_TABLE))
def test_bag_table(bag_book, batch):
    """Covers: AC-3 (right/boundary), BAGS-3. Whole-gallon batches 1..13 give the section 4.2 counts."""
    r = scale_recipe("Test Iced Tea", gallons=batch, book=bag_book)
    big, small = BAG_TABLE[batch]
    counts = _counts(r)
    assert counts.get(BIG, 0) == big
    assert counts.get(SMALL, 0) == small
    # sizes with count 0 produce no ingredient
    assert (BIG in counts) == (big > 0)
    assert (SMALL in counts) == (small > 0)


def test_bag_lines_in_file_order(bag_book):
    """Covers: AC-7 (right), BAGS-3. Batch 5 lists the 3-gallon line before the 1-gallon line."""
    r = scale_recipe("Test Iced Tea", gallons=5, book=bag_book)
    assert [i.name for i in r.ingredients][:2] == [BIG, SMALL]


@pytest.mark.parametrize("gallons,big,small", [(0.5, 0, 1), (3.2, 1, 0), (2.5, 1, 0), (1.01, 0, 2)])
def test_batch_rounded_up_for_bags_only(bag_book, gallons, big, small):
    """Covers: AC-3 (boundary), BAGS-4. Bags use the batch rounded up; syrup and water use the exact batch."""
    r = scale_recipe("Test Iced Tea", gallons=gallons, book=bag_book)
    counts = _counts(r)
    assert counts.get(BIG, 0) == big
    assert counts.get(SMALL, 0) == small
    exact = Fraction(str(gallons))
    by_name = {i.name: i for i in r.ingredients}
    assert by_name["Test syrup"].amount == 8 * exact
    assert by_name["Water"].amount == exact


def test_bags_from_guests(bag_book):
    """Covers: AC-3 (right), AC-8, BAGS-5. 38 guests is 2 gallons: two 1-gallon bags, from_guests True."""
    r = scale_recipe("Test Iced Tea", guests=38, book=bag_book)
    assert r.status == "ok" and r.gallons == 2 and r.from_guests is True
    assert _counts(r) == {SMALL: 2}


def test_bag_ingredient_fields(bag_book):
    """Covers: AC-7 (right), BAGS-6. Bag lines have unit "bag", fill False and a whole Fraction amount."""
    r = scale_recipe("Test Iced Tea", gallons=5, book=bag_book)
    bags = [i for i in r.ingredients if i.unit == BAG_UNIT]
    assert len(bags) == 2
    for b in bags:
        assert b.unit == "bag" and b.fill is False
        assert isinstance(b.amount, Fraction) and b.amount.denominator == 1 and b.amount >= 1


@pytest.mark.parametrize("gallons,expected", [
    (4, ["3-gallon tea bag: 1 bag"]),
    (2, ["1-gallon tea bag: 2 bags"]),
    (6, ["3-gallon tea bag: 2 bags"]),
    (5, ["3-gallon tea bag: 1 bag", "1-gallon tea bag: 1 bag"]),
])
def test_bag_text(bag_book, gallons, expected):
    """Covers: AC-7 (right), BAGS-3. Text lines read "<name>: <count> bag(s)"; never "1 bags"."""
    t = scale_recipe("Test Iced Tea", gallons=gallons, book=bag_book).text
    for line in expected:
        assert line in t
    assert "1 bags" not in t


@pytest.mark.parametrize("gallons,absent", [(4, SMALL), (2, BIG), (9, SMALL)])
def test_text_has_no_zero_count_line(bag_book, gallons, absent):
    """Covers: AC-7 (wrong), BAGS-3. No text line for a size with count 0."""
    t = scale_recipe("Test Iced Tea", gallons=gallons, book=bag_book).text
    assert absent not in t
    assert ": 0 bag" not in t


def test_non_bag_text_rules_unchanged(bag_book):
    """Covers: AC-7 (right). Syrup and fill lines and numbered steps stay as in spec 015."""
    t = scale_recipe("Test Iced Tea", gallons=6, book=bag_book).text
    assert "Test syrup: 48 oz" in t
    assert "Water: fill to 6 gallons" in t
    assert "1." in t and "4." in t


def test_other_sizes_via_json(write_book):
    """Covers: AC-3 (boundary). The rule is generic: sizes 5-5 and 1-1, batch 11 gives 2 big + 1 small."""
    bags = {"bags": [
        {"name": "Big", "brews_from": 5, "brews_to": 5},
        {"name": "Small", "brews_from": 1, "brews_to": 1},
    ]}
    book = load_recipe_book(write_book(bag_book_data(bags)))
    r = scale_recipe("Test Iced Tea", gallons=11, book=book)
    assert _counts(r) == {"Big": 2, "Small": 1}


# ---- malformed counted-bag ingredients ----

def _with_bags(bags_value):
    d = bag_book_data()
    d["recipes"]["Test Iced Tea"]["ingredients"][0] = {"bags": bags_value}
    return d


def _sizes(**over):
    s = copy.deepcopy(TEA_BAGS["bags"])
    s[0].update(over)
    return s


def _drop(key):
    s = _sizes()
    del s[0][key]
    return s


BAD_BAGS = {
    "empty_list": [],
    "not_a_list_str": "x",
    "not_a_list_dict": {"name": "a", "brews_from": 1, "brews_to": 1},
    "missing_name": _drop("name"),
    "blank_name": _sizes(name="   "),
    "empty_name": _sizes(name=""),
    "from_zero": _sizes(brews_from=0),
    "from_negative": _sizes(brews_from=-1),
    "from_fraction": _sizes(brews_from=2.5),
    "to_fraction": _sizes(brews_to=4.5),
    "to_zero": _sizes(brews_from=3, brews_to=0),
    "from_missing": _drop("brews_from"),
    "to_missing": _drop("brews_to"),
    "from_gt_to": _sizes(brews_from=4, brews_to=3),
    "duplicate_names": [{"name": "A", "brews_from": 1, "brews_to": 1}, {"name": "A", "brews_from": 3, "brews_to": 4}],
    "no_one_one_size": [{"name": "Big", "brews_from": 3, "brews_to": 4}],
    "one_two_not_one_one": [{"name": "A", "brews_from": 1, "brews_to": 2}],
}


@pytest.mark.parametrize("case", sorted(BAD_BAGS))
def test_malformed_bags_raise(write_book, case):
    """Covers: AC-6 (wrong), BAGS-2. Each malformed counted-bag ingredient raises RecipeFileError."""
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(_with_bags(BAD_BAGS[case])))


def test_valid_extra_sizes_load(write_book):
    """Covers: AC-6 (boundary), BAGS-1. A 2-2 size plus the required 1-1 size loads."""
    sizes = [{"name": "Mid", "brews_from": 2, "brews_to": 2}, {"name": "One", "brews_from": 1, "brews_to": 1}]
    assert load_recipe_book(write_book(_with_bags(sizes)))


@pytest.mark.parametrize("breaker", [
    lambda r: r["ingredients"].append({"name": "X"}),
    lambda r: r.update(yield_gallons=0),
    lambda r: r["ingredients"].append({"name": "X", "amount": 5}),
    lambda r: r.update(steps=[]),
])
def test_spec_015_errors_still_raise_with_bag_recipe(write_book, breaker):
    """Covers: AC-6 (wrong), BAGS-7. Spec 015 file errors still raise in a book that has a valid counted-bag recipe."""
    d = bag_book_data()
    breaker(d["recipes"]["Lemonade"])
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(d))


def test_bag_book_does_not_read_data_dir(bag_book):
    """Covers: AC-10 (right), BAGS-1. The test book works with book= given, status ok, no real file involved."""
    assert scale_recipe("Test Iced Tea", gallons=1, book=bag_book).status == "ok"
