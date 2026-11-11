"""Shared setup for the pull sheet tests (specs 002 and 003). Written from the specs only.

Unit tests: no Ollama, no Chroma, no network. Catalog files are written to tmp_path.

The helpers are plain functions here, exposed to tests as fixtures (spec 003 EC-4), so test
files never import this module directly. Fixture names equal the old helper names.

Probe technique: to observe the ordered amount of each item independently of
cambro packing, the "probe" catalog adds a unique tag per item and one
`per: unit` supply rule per item (`G:<item>`, qty 1). Its quantity is
ceil(ordered amount) of that item (spec 002 §4.5 step 5, `unit`).
"""
import json
import re
from fractions import Fraction

import pytest

from pull_sheet import (
    MENU_FILE,
    RULES_FILE,
    Beo,
    BeoLine,
    build_pull_sheet,
    load_catalog,
)

PKG = "Coffee, decaf, tea, iced water & juice"
MISSING = object()


def default_menu():
    return {
        "items": {
            "Coffee": {
                "unit": "gallon",
                "also_written_as": ["Fresh-brewed coffee"],
                "tags": ["HOT", "COFFEE"],
            },
            "Decaf": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "COFFEE"]},
            "Hot water": {
                "unit": "gallon",
                "also_written_as": [
                    "Hot water with an assortment of black, green, and herbal tea bags"
                ],
                "tags": ["HOT", "HOT-WATER"],
            },
            "Iced water": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
            "Pomegranate juice": {
                "unit": "gallon",
                "also_written_as": [],
                "tags": ["COLD", "JUICE"],
            },
            "Iced tea": {
                "unit": "gallon",
                "also_written_as": ["Iced tea with lemon wedges"],
                "tags": ["COLD", "TEA"],
            },
            "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []},
        },
        "packages": {
            PKG: {
                "includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
                "placeholders": {"JUICE": "Orange juice"},
            }
        },
    }


def default_rules():
    return {
        "cambros": [
            {"supply": "5 gal cambro", "gallons": 5},
            {"supply": "2 gal cambro", "gallons": 2},
            {"supply": "1 gal cambro", "gallons": 1},
        ],
        "supplies": [
            {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
            {"supply": "cold-cups", "qty": 1, "per": "guest+extra", "when_tagged": "COLD"},
            {"supply": "Cocktail napkins", "tick": True},
            {"supply": "Creamer", "tick": True, "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        ],
        "extras": [
            {"guests_up_to": 20, "extra": 10},
            {"guests_up_to": 50, "extra": 20},
            {"guests_up_to": 100, "extra": 50},
            {"guests_up_to": None, "extra": 100},
        ],
    }


def _slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def add_probes(menu, rules):
    rules.setdefault("supplies", [])
    for name, item in menu["items"].items():
        tag = "P-" + _slug(name).upper()
        item["tags"] = list(item["tags"]) + [tag]
        rules["supplies"].append(
            {"supply": "G:" + name, "qty": 1, "per": "unit", "when_tagged": tag}
        )


def _write(path, content):
    if content is MISSING:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


def write_dir(tmp_path, menu=None, rules=None, name="rules_dir"):
    base = tmp_path / name
    _write(base / MENU_FILE, default_menu() if menu is None else menu)
    _write(base / RULES_FILE, default_rules() if rules is None else rules)
    return base


def make_catalog(tmp_path, menu=None, rules=None, probe=False):
    menu = default_menu() if menu is None else menu
    rules = default_rules() if rules is None else rules
    if probe:
        add_probes(menu, rules)
    return load_catalog(write_dir(tmp_path, menu, rules))


def mk_beo(guests, lines):
    return Beo(guests, tuple(BeoLine(n, Fraction(q), u) for n, q, u in lines))


def run(tmp_path, guests, lines, menu=None, rules=None, probe=True):
    cat = make_catalog(tmp_path, menu, rules, probe=probe)
    return build_pull_sheet(cat, mk_beo(guests, lines))


def qtys(sheet):
    return {l.supply: l.quantity for l in sheet.lines}


def names(sheet):
    return [l.supply for l in sheet.lines]


def line_of(sheet, supply):
    for l in sheet.lines:
        if l.supply == supply:
            return l
    raise AssertionError(f"no line {supply!r} in {names(sheet)}")


def gal(sheet, item):
    """Ordered gallons (ceil) of an item, via the probe supply; 0 if absent."""
    return qtys(sheet).get("G:" + item, 0)


def rules_with(supplies, extras=MISSING, cambros=None):
    r = default_rules()
    r["supplies"] = supplies
    if extras is MISSING:
        pass
    elif extras is None:
        r.pop("extras")
    else:
        r["extras"] = extras
    if cambros is not None:
        r["cambros"] = cambros
    return r


def beo_md(guests_line="Guest Count: 70", rows=(), header="| Description | Qty | Delivery UOM |"):
    out = []
    if guests_line is not None:
        out += [guests_line, ""]
    if header is not None:
        out += [header, "|---|---|---|"]
        out += list(rows)
    return "\n".join(out) + "\n"


EXAMPLE_BEO = (
    "Guest Count: 70\n\n"
    "| Description | Qty | Delivery UOM |\n"
    "|---|---|---|\n"
    "| ~Beverages~ | 0 | |\n"
    "| Coffee, decaf, tea, iced water & juice | 70 | |\n"
    "| Orange juice | 70 | |\n"
    "| Fresh-brewed coffee | 2 | Gallon |\n"
    "| Oatmilk | 1 | Each |\n"
    "| Cascade Breakfast | 70 | Packages |\n"
)

EXAMPLE_OUT = (
    "Pull sheet for 70 guests\n"
    "\n"
    "Beverages\n"
    "- 5 gal cambro: 5\n"
    "- Oatmilk: 1\n"
    "- hot-cups: 120\n"
    "- cold-cups: 120\n"
    "- Cocktail napkins: ✓\n"
    "- Creamer: ✓\n"
    "- Stir sticks: 1\n"
    "- Sugar: 1\n"
    "\n"
    "Not used (check by hand):\n"
    "- Cascade Breakfast, 70 Packages: not on beverage menu\n"
)


def _provide(name, value):
    @pytest.fixture(name=name)
    def _fixture():
        return value

    return _fixture


default_menu_fixture = _provide("default_menu", default_menu)
default_rules_fixture = _provide("default_rules", default_rules)
write_dir_fixture = _provide("write_dir", write_dir)
make_catalog_fixture = _provide("make_catalog", make_catalog)
mk_beo_fixture = _provide("mk_beo", mk_beo)
run_fixture = _provide("run", run)
qtys_fixture = _provide("qtys", qtys)
names_fixture = _provide("names", names)
line_of_fixture = _provide("line_of", line_of)
gal_fixture = _provide("gal", gal)
rules_with_fixture = _provide("rules_with", rules_with)
beo_md_fixture = _provide("beo_md", beo_md)
missing_fixture = _provide("MISSING", MISSING)
example_beo_fixture = _provide("EXAMPLE_BEO", EXAMPLE_BEO)
example_out_fixture = _provide("EXAMPLE_OUT", EXAMPLE_OUT)
