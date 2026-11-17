"""Loading and checking the food rules file (spec 029 4.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOOD_RULES_FILE = ROOT / "data" / "pull_sheet" / "rules" / "food.json"
_DEFAULT_FILE = FOOD_RULES_FILE
NAPKIN_KINDS = ("cocktail", "dinner")


class FoodRulesError(Exception):
    """The rules file is missing or does not follow spec 029 section 4.1."""


@dataclass(frozen=True)
class _Tier:
    guests_up_to: int | None
    extra: int


class FoodRules:
    """The loaded rules. Made only by load_food_rules."""

    def __init__(self, tiers: tuple[_Tier, ...], napkins: dict[str, dict[str, bool]]) -> None:
        self._tiers = tiers
        self._napkins = napkins

    def extra_for(self, guests: int) -> int:
        for tier in self._tiers:
            if tier.guests_up_to is None or guests <= tier.guests_up_to:
                return tier.extra
        return self._tiers[-1].extra

    def meals(self) -> tuple[str, ...]:
        return tuple(self._napkins)

    def napkin(self, meal: str, kind: str) -> bool | None:
        """kind is "cocktail" or "dinner"; None when the meal is not in the rules."""
        row = self._napkins.get(meal_key(meal))
        return None if row is None else row[kind]


def meal_key(meal: str) -> str:
    """Case and surrounding spaces do not matter."""
    return meal.strip().lower()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _build_tiers(extras: object) -> tuple[_Tier, ...]:
    if not isinstance(extras, list) or not extras:
        raise FoodRulesError("'extras' must be a non-empty list")
    tiers: list[_Tier] = []
    previous: int | None = None
    for position, entry in enumerate(extras):
        if not isinstance(entry, dict):
            raise FoodRulesError(f"extras entry {position} is not an object")
        extra, limit = entry.get("extra"), entry.get("guests_up_to")
        if not _is_int(extra) or extra < 0:
            raise FoodRulesError(f"extras entry {position} needs a non-negative 'extra'")
        last = position == len(extras) - 1
        if last != (limit is None):
            raise FoodRulesError("only the last extras entry has 'guests_up_to' null")
        if limit is not None and (
            not _is_int(limit) or (previous is not None and limit <= previous)
        ):
            raise FoodRulesError(f"extras entry {position} has a bad 'guests_up_to'")
        previous = limit if limit is not None else previous
        tiers.append(_Tier(limit, extra))
    return tuple(tiers)


def _build_napkins(napkins: object) -> dict[str, dict[str, bool]]:
    if not isinstance(napkins, dict) or not napkins:
        raise FoodRulesError("'napkins' must be a non-empty object")
    table: dict[str, dict[str, bool]] = {}
    for written, row in napkins.items():
        key = meal_key(written)
        if not key or key in table:
            raise FoodRulesError(f"the meal name {written!r} is blank or used twice")
        if not isinstance(row, dict) or not all(
            isinstance(row.get(kind), bool) for kind in NAPKIN_KINDS
        ):
            raise FoodRulesError(f"meal {written!r} needs boolean 'cocktail' and 'dinner'")
        table[key] = {kind: row[kind] for kind in NAPKIN_KINDS}
    return table


def _default_path() -> Path:
    """FOOD_RULES_FILE, read when called so a changed value is honoured."""
    import blc.tools.food_tools as package

    package_value = getattr(package, "FOOD_RULES_FILE", _DEFAULT_FILE)
    return package_value if package_value != _DEFAULT_FILE else FOOD_RULES_FILE


def load_food_rules(path: Path | None = None) -> FoodRules:
    """path=None means FOOD_RULES_FILE. Raises FoodRulesError."""
    target = Path(path) if path is not None else _default_path()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        raise FoodRulesError(f"cannot read food rules {target}: {error}") from error
    try:
        loaded = json.loads(text)
    except ValueError as error:
        raise FoodRulesError(f"food rules {target} are not valid JSON: {error}") from error
    if not isinstance(loaded, dict):
        raise FoodRulesError("the food rules must be a JSON object")
    return FoodRules(_build_tiers(loaded.get("extras")), _build_napkins(loaded.get("napkins")))
