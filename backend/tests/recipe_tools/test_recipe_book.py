"""Spec 015 AC-1: the recipe file (EC-1, EC-2). Unit; the test book lives in tmp_path."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from blc.tools.recipe_tools import (
    RECIPES_FILE,
    RecipeBook,
    RecipeFileError,
    load_recipe_book,
    scale_recipe,
)


def _patch_recipes_file(monkeypatch, path):
    """Point every RECIPES_FILE name in the recipe_tools package at path."""
    for name, mod in list(sys.modules.items()):
        if name.startswith("blc.tools.recipe_tools") and mod is not None and hasattr(mod, "RECIPES_FILE"):
            monkeypatch.setattr(mod, "RECIPES_FILE", path)


def test_recipes_file_constant():
    """Covers: AC-1 (right). RECIPES_FILE is a Path ending in data/recipes/recipes.json."""
    assert isinstance(RECIPES_FILE, Path)
    assert RECIPES_FILE.parts[-3:] == ("data", "recipes", "recipes.json")


def test_appendix_a_loads(write_book, book_a_data):
    """Covers: AC-1 (right), EC-1. Appendix A alone loads."""
    assert isinstance(load_recipe_book(write_book(book_a_data)), RecipeBook)


def test_appendix_ab_loads(write_book, book_ab_data):
    """Covers: AC-1 (right), EC-1. Appendix A+B loads."""
    assert isinstance(load_recipe_book(write_book(book_ab_data)), RecipeBook)


def test_also_written_as_may_be_missing(write_book, book_a_data):
    """Covers: AC-1 (boundary), EC-1. A recipe without also_written_as loads."""
    del book_a_data["recipes"]["Lemonade"]["also_written_as"]
    assert isinstance(load_recipe_book(write_book(book_a_data)), RecipeBook)


def test_missing_file(tmp_path):
    """Covers: AC-1 (wrong), EC-1. A missing file raises RecipeFileError."""
    with pytest.raises(RecipeFileError):
        load_recipe_book(tmp_path / "nope.json")


@pytest.mark.parametrize("text", ["{", "", "not json", "{}", '{"recipes": []}', '{"recipes": "x"}',
                                  '{"recipes": null}', "[]"])
def test_bad_top_level(write_book, text):
    """Covers: AC-1 (wrong), EC-1. Invalid JSON, no recipes, or recipes not an object."""
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(text))


def _mutate(data, fn):
    d = copy.deepcopy(data)
    fn(d["recipes"]["Lemonade"])
    return d


def _del_yield(r):
    del r["yield_gallons"]


BAD_RECIPES = {
    "yield_zero": lambda r: r.update(yield_gallons=0),
    "yield_negative": lambda r: r.update(yield_gallons=-1),
    "yield_missing": _del_yield,
    "no_unit": lambda r: r["ingredients"].__setitem__(0, {"name": "X", "amount": 5}),
    "empty_unit": lambda r: r["ingredients"].__setitem__(0, {"name": "X", "amount": 5, "unit": ""}),
    "amount_zero": lambda r: r["ingredients"].__setitem__(0, {"name": "X", "amount": 0, "unit": "oz"}),
    "amount_negative": lambda r: r["ingredients"].__setitem__(0, {"name": "X", "amount": -1, "unit": "oz"}),
    "name_only": lambda r: r["ingredients"].__setitem__(0, {"name": "X"}),
    "empty_ingredients": lambda r: r.update(ingredients=[]),
    "ingredients_not_list": lambda r: r.update(ingredients={"a": 1}),
    "ingredient_not_object": lambda r: r.update(ingredients=["Lemon concentrate"]),
    "missing_ingredients": lambda r: r.pop("ingredients"),
    "empty_steps": lambda r: r.update(steps=[]),
    "empty_step_string": lambda r: r.update(steps=["Stir.", ""]),
    "steps_not_list": lambda r: r.update(steps="Stir."),
    "step_not_string": lambda r: r.update(steps=[5]),
    "missing_steps": lambda r: r.pop("steps"),
}


@pytest.mark.parametrize("case", sorted(BAD_RECIPES))
def test_bad_recipe_rejected(write_book, book_a_data, case):
    """Covers: AC-1 (wrong), EC-1. Each section 4.1 error case raises RecipeFileError."""
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(_mutate(book_a_data, BAD_RECIPES[case])))


def test_duplicate_name_across_recipes_different_case(write_book, book_ab_data):
    """Covers: AC-1 (wrong), EC-1. One recipe's also_written_as equals another's name in a different case."""
    book_ab_data["recipes"]["Fruit punch"]["also_written_as"] = ["LEMONADE"]
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(book_ab_data))


def test_duplicate_also_written_as_across_recipes(write_book, book_ab_data):
    """Covers: AC-1 (wrong), EC-1 (extra). Two recipes share an also_written_as name ignoring case."""
    book_ab_data["recipes"]["Fruit punch"]["also_written_as"] = ["FRESH LEMONADE"]
    with pytest.raises(RecipeFileError):
        load_recipe_book(write_book(book_ab_data))


def test_scale_with_book_reads_no_other_file(monkeypatch, tmp_path, write_book, book_ab_data):
    """Covers: AC-1 (right), EC-2. With a book given, a missing RECIPES_FILE is never touched."""
    _patch_recipes_file(monkeypatch, tmp_path / "missing.json")
    with pytest.raises(RecipeFileError):  # the patch reached the loader
        load_recipe_book()
    book = load_recipe_book(write_book(book_ab_data))
    assert scale_recipe("lemonade", gallons=1, book=book).status == "ok"


def test_scale_book_none_missing_file_raises(monkeypatch, tmp_path):
    """Covers: AC-1 (wrong), EC-2. book=None with RECIPES_FILE missing: RecipeFileError propagates."""
    _patch_recipes_file(monkeypatch, tmp_path / "missing.json")
    with pytest.raises(RecipeFileError):  # the patch reached the loader
        load_recipe_book()
    with pytest.raises(RecipeFileError):
        scale_recipe("lemonade", gallons=1, book=None)


def test_load_default_path_missing_file_raises(monkeypatch, tmp_path):
    """Covers: AC-1 (wrong), EC-2 (extra). load_recipe_book() with no path uses RECIPES_FILE."""
    _patch_recipes_file(monkeypatch, tmp_path / "missing.json")
    with pytest.raises(RecipeFileError):
        load_recipe_book()


def test_book_none_uses_patched_file(monkeypatch, write_book, book_ab_data):
    """Covers: AC-1 (right), EC-2 (extra). book=None loads RECIPES_FILE: a patched file with Fruit punch works."""
    p = write_book(book_ab_data)
    _patch_recipes_file(monkeypatch, p)
    assert isinstance(load_recipe_book(), RecipeBook)  # the patch reached the loader
    assert scale_recipe("fruit punch", gallons=2, book=None).status == "ok"
