"""Loading and checking the recipe file (spec 015 4.1)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from blc.tools.recipe_tools.names import name_key

ROOT = Path(__file__).resolve().parents[4]
RECIPES_FILE = ROOT / "data" / "recipes" / "recipes.json"
_DEFAULT_FILE = RECIPES_FILE


class RecipeFileError(Exception):
    """The recipe file is missing or does not follow spec 015 section 4.1."""


@dataclass(frozen=True)
class Ingredient:
    name: str
    amount: Fraction | None  # None for a fill ingredient
    unit: str | None
    fill: bool


@dataclass(frozen=True)
class Recipe:
    name: str
    yield_gallons: Fraction
    ingredients: tuple[Ingredient, ...]
    steps: tuple[str, ...]


class RecipeBook:
    """The loaded recipes. Made only by load_recipe_book."""

    def __init__(self, recipes: tuple[Recipe, ...], by_key: dict[str, Recipe]) -> None:
        self.recipes = recipes
        self._by_key = by_key

    def find(self, requested: str) -> Recipe | None:
        return self._by_key.get(name_key(requested))

    def names(self) -> tuple[str, ...]:
        return tuple(recipe.name for recipe in self.recipes)


def _positive(value: object, what: str) -> Fraction:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RecipeFileError(f"{what} must be a number above 0")
    return Fraction(str(value))


def _ingredient(raw: object, recipe: str) -> Ingredient:
    if not isinstance(raw, dict):
        raise RecipeFileError(f"{recipe}: an ingredient must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RecipeFileError(f"{recipe}: an ingredient needs a name")
    if raw.get("fill") is True:
        return Ingredient(name, None, None, True)
    unit = raw.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise RecipeFileError(f"{recipe}: ingredient {name} needs a unit")
    return Ingredient(name, _positive(raw.get("amount"), f"{recipe}: {name} amount"), unit, False)


def _steps(raw: object, recipe: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise RecipeFileError(f"{recipe}: steps must be a non-empty list")
    if not all(isinstance(step, str) and step.strip() for step in raw):
        raise RecipeFileError(f"{recipe}: every step must be a non-empty string")
    return tuple(raw)


def _aliases(raw: object, recipe: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(a, str) and a.strip() for a in raw):
        raise RecipeFileError(f"{recipe}: also_written_as must be a list of names")
    return list(raw)


def _recipe(name: str, raw: object) -> tuple[Recipe, list[str]]:
    if not isinstance(raw, dict):
        raise RecipeFileError(f"{name}: a recipe must be an object")
    yield_gallons = _positive(raw.get("yield_gallons"), f"{name}: yield_gallons")
    ingredients = raw.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        raise RecipeFileError(f"{name}: ingredients must be a non-empty list")
    parsed = tuple(_ingredient(item, name) for item in ingredients)
    recipe = Recipe(name, yield_gallons, parsed, _steps(raw.get("steps"), name))
    return recipe, _aliases(raw.get("also_written_as"), name)


def _build(data: object) -> RecipeBook:
    recipes_raw = data.get("recipes") if isinstance(data, dict) else None
    if not isinstance(recipes_raw, dict):
        raise RecipeFileError('the file needs a "recipes" object')
    recipes: list[Recipe] = []
    by_key: dict[str, Recipe] = {}
    for name, raw in recipes_raw.items():
        recipe, aliases = _recipe(name, raw)
        recipes.append(recipe)
        for written in [name, *aliases]:
            key = name_key(written)
            if not key or key in by_key:
                raise RecipeFileError(f"the name {written!r} is blank or used twice")
            by_key[key] = recipe
    return RecipeBook(tuple(recipes), by_key)


def _default_path() -> Path:
    """RECIPES_FILE, read when called so a changed value is honoured."""
    import blc.tools.recipe_tools as package

    package_value = getattr(package, "RECIPES_FILE", _DEFAULT_FILE)
    return package_value if package_value != _DEFAULT_FILE else RECIPES_FILE


def load_recipe_book(path: Path | None = None) -> RecipeBook:
    """path=None means RECIPES_FILE. Raises RecipeFileError."""
    target = Path(path) if path is not None else _default_path()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        raise RecipeFileError(f"cannot read recipe file {target}: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise RecipeFileError(f"recipe file {target} is not valid JSON: {error}") from error
    return _build(data)
