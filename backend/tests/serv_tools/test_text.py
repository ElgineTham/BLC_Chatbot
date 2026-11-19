"""Spec 042 section 6.4 TEXT (AC-8). Unit."""

from __future__ import annotations


def test_ok_text_lists_utensils(run):
    """Covers: AC-8 (right), TEXT-1. Totals appear by name; absent utensils do not."""
    r = run([{"food": "butter croissants", "qty": 2}, {"food": "assorted bagels", "qty": 2}])
    assert r.status == "ok"
    assert "Small tongs: 3" in r.text
    assert "Spreader/knives: 1" in r.text
    assert "Large tongs" not in r.text


def test_ok_text_in_utensil_order(run):
    """Covers: AC-8 (right). Lines follow SERV_UTENSILS order (small tongs before large tongs before mayo/mustard)."""
    r = run([{"food": "classic deli sandwiches", "qty": 30}, {"food": "butter croissants", "qty": 1}])
    t = r.text
    assert t.index("Small tongs") < t.index("Large tongs") < t.index("Mayo/mustard")
    assert "Mayo/mustard: 2" in t


def test_empty_ok_text(run):
    """Covers: AC-8 (boundary), TEXT-2. Nothing needed: says 'no serving utensils'."""
    r = run([{"food": "trail mix", "qty": 12}])
    assert r.status == "ok"
    assert "no serving utensils" in r.text.lower()


def test_ok_text_does_not_say_none_when_there_are_some(run):
    """Covers: AC-8 (wrong). A non-empty result does not use the empty sentence."""
    r = run([{"food": "butter croissants", "qty": 1}])
    assert "no serving utensils" not in r.text.lower()


def test_need_info_text(run):
    """Covers: AC-8 (right), TEXT-3. One question with 'how many' and the food name."""
    r = run([{"food": "bagels"}])
    assert r.status == "need_info"
    assert r.text.strip().endswith("?")
    assert "how many" in r.text.lower()
    assert "bagels" in r.text.lower()


def test_need_info_names_every_food_without_qty(run):
    """Covers: AC-8 (boundary). Two foods lacking qty are both named; a food with qty is not asked about."""
    r = run([{"food": "assorted bagels"}, {"food": "classic deli sandwiches", "qty": 0},
             {"food": "butter croissants", "qty": 3}])
    t = r.text.lower()
    assert "bagels" in t and "deli sandwiches" in t
    assert "croissants" not in t
    assert t.strip().endswith("?")


def test_invalid_text_unknown_food(run):
    """Covers: AC-8 (right), TEXT-4. Starts with 'invalid', names the food, shows the format."""
    r = run([{"food": "lasagna", "qty": 3}])
    assert r.status == "invalid"
    assert r.text.lower().startswith("invalid")
    assert "lasagna" in r.text
    assert "food" in r.text.lower()
    for key in ('"items"', '"food"', '"qty"', '"unit"'):
        assert key in r.text


def test_invalid_text_other_errors_show_format(rules):
    """Covers: AC-8 (right). Any invalid text starts with 'invalid' and shows the example call."""
    from blc.tools.serv_tools import run_serv_tool
    for args in ({"items": []}, None, {"items": [{"food": "butter croissants", "qty": -1}]},
                 {"items": [{"food": "butter croissants", "qty": 1, "unit": "pounds"}]}):
        r = run_serv_tool(args, rules=rules)
        assert r.status == "invalid"
        assert r.text.lower().startswith("invalid")
        for key in ('"items"', '"food"', '"qty"', '"unit"'):
            assert key in r.text
