"""Loading and checking the serving utensils rules file (spec 042 4.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from blc.tools.serv_tools.result import SERV_UNITS, SERV_UTENSILS

ROOT = Path(__file__).resolve().parents[5]
SERV_RULES_FILE = ROOT / "data" / "pull_sheet" / "rules" / "serving_utensils.json"
_DEFAULT_FILE = SERV_RULES_FILE


class ServRulesError(Exception):
    """The rules file is missing or does not follow spec 042 section 4.1."""


@dataclass(frozen=True)
class UtensilRule:
    utensil: str
    count: int
    per: float | None


@dataclass(frozen=True)
class FoodRule:
    name: str
    unit: str
    utensils: tuple[UtensilRule, ...]


class ServRules:
    """The loaded rules. Made only by load_serv_rules."""

    def __init__(self, foods: dict[str, FoodRule]) -> None:
        self._foods = foods  # keyed by food_key of the name and every alias

    def find(self, name: str) -> FoodRule | None:
        return self._foods.get(food_key(name))


def food_key(name: str) -> str:
    """Case, spaces and - _ , differences do not matter."""
    cleaned = name.casefold()
    for mark in "-_,":
        cleaned = cleaned.replace(mark, " ")
    return " ".join(cleaned.split())


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _build_utensil(food: str, entry: object) -> UtensilRule:
    if not isinstance(entry, dict):
        raise ServRulesError(f"{food!r}: each utensil entry must be an object")
    utensil = entry.get("utensil")
    if utensil not in SERV_UTENSILS:
        raise ServRulesError(f"{food!r}: unknown utensil {utensil!r}")
    count = entry.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ServRulesError(f"{food!r}: 'count' must be a whole number of at least 1")
    per = entry.get("per")
    if per is not None and (not _is_number(per) or not per > 0):
        raise ServRulesError(f"{food!r}: 'per' must be null or a number above 0")
    return UtensilRule(utensil, count, None if per is None else float(per))


def _build_food(name: str, body: object) -> FoodRule:
    if not isinstance(body, dict):
        raise ServRulesError(f"{name!r}: must be an object")
    unit = body.get("unit")
    if unit not in SERV_UNITS:
        raise ServRulesError(f"{name!r}: 'unit' must be one of {', '.join(SERV_UNITS)}")
    entries = body.get("utensils")
    if not isinstance(entries, list):
        raise ServRulesError(f"{name!r}: 'utensils' must be a list")
    return FoodRule(name, unit, tuple(_build_utensil(name, e) for e in entries))


def _aliases(name: str, body: object) -> list[object]:
    aliases = body.get("aliases", []) if isinstance(body, dict) else []
    if not isinstance(aliases, list):
        raise ServRulesError(f"{name!r}: 'aliases' must be a list")
    return aliases


def _build_rules(loaded: object) -> ServRules:
    foods = loaded.get("foods") if isinstance(loaded, dict) else None
    if not isinstance(foods, dict) or not foods:
        raise ServRulesError("'foods' must be a non-empty object")
    table: dict[str, FoodRule] = {}
    for name, body in foods.items():
        rule = _build_food(name, body)
        for label in [name, *_aliases(name, body)]:
            key = food_key(label) if isinstance(label, str) else ""
            if not key:
                raise ServRulesError(f"{name!r}: blank or non-text food name or alias")
            if key in table:
                raise ServRulesError(f"the name {label!r} appears more than once")
            table[key] = rule
    return ServRules(table)


def _default_path() -> Path:
    """SERV_RULES_FILE, read when called so a changed value is honoured."""
    import blc.tools.serv_tools as package

    package_value = getattr(package, "SERV_RULES_FILE", _DEFAULT_FILE)
    return package_value if package_value != _DEFAULT_FILE else SERV_RULES_FILE


def load_serv_rules(path: Path | None = None) -> ServRules:
    """path=None means SERV_RULES_FILE. Raises ServRulesError."""
    target = Path(path) if path is not None else _default_path()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        raise ServRulesError(f"cannot read serving utensil rules {target}: {error}") from error
    try:
        loaded = json.loads(text)
    except ValueError as error:
        raise ServRulesError(f"serving utensil rules {target} are not valid JSON: {error}") from error
    return _build_rules(loaded)
