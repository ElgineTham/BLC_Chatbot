"""Shared constants for the pull sheet (spec 002 section 3)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_DIR = ROOT / "data" / "pull_sheet"
MENU_FILE = "menu/beverages.json"
RULES_FILE = "rules/beverages.json"
GALLON = "gallon"
EACH = "each"
GUESTS_PER_GALLON = 25
PER_VALUES: tuple[str, ...] = ("event", "guest", "guest+extra", "item", "unit")
TICK = "✓"
NOT_ON_MENU = "not on beverage menu"
UNKNOWN_UNIT = "unknown unit"
