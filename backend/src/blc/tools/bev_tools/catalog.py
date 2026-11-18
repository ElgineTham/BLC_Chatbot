"""The validated catalog and its loader."""

from __future__ import annotations

from pathlib import Path

from blc.tools.bev_tools.json_checks import read_json
from blc.tools.bev_tools.menu import parse_menu
from blc.tools.bev_tools.catalog_entries import Cambro, Item, Package, Supply
from blc.tools.bev_tools.rules import parse_rules

ROOT = Path(__file__).resolve().parents[5]
DEFAULT_RULES_DIR = ROOT / "data" / "pull_sheet"
MENU_FILE = "menu/beverages.json"
RULES_FILE = "rules/beverages.json"


class Catalog:
    """Opaque: the validated menu and rules. Build only with load_catalog()."""

    def __init__(
        self,
        items: dict[str, Item],
        names: dict[str, tuple[str, str]],
        packages: dict[str, Package],
        cambros: tuple[Cambro, ...],
        supplies: tuple[Supply, ...],
        extras: tuple[tuple[int | None, int], ...],
    ) -> None:
        self._items = items
        self._names = names
        self._packages = packages
        self._cambros = cambros
        self._supplies = supplies
        self._extras = extras


def load_catalog(base_dir: Path = DEFAULT_RULES_DIR) -> Catalog:
    """Read and validate base_dir/MENU_FILE and base_dir/RULES_FILE."""
    menu_path, menu_data = read_json(base_dir, MENU_FILE)
    rules_path, rules_data = read_json(base_dir, RULES_FILE)
    items, names, packages = parse_menu(menu_path, menu_data)
    cambros, supplies, extras = parse_rules(rules_path, rules_data, items)
    return Catalog(items, names, packages, cambros, supplies, extras)
