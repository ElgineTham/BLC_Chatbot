"""Spec 024 section 6.2 API: public names, re-exports, guests_to_gallons (AC-4 to AC-7)."""
import importlib
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = ["Catalog", "load_catalog", "RuleFileError", "PullLine", "GALLON", "EACH", "GUESTS_PER_GALLON"]
BEV_PUBLIC = [
    "BEV_TOOL_NAME", "BEV_ITEMS", "BEV_STATUSES", "DrinkRequest", "DrinkAmount", "BevResult",
    "calculate_bev_item", "run_bev_tool", "make_bev_tool", "BEV_TOOL",
    "Catalog", "load_catalog", "RuleFileError", "PullLine", "GALLON", "EACH", "GUESTS_PER_GALLON",
    "guests_to_gallons",
]
BEV_LANGCHAIN = []
RECIPE_PUBLIC = [
    "RECIPE_TOOL_NAME", "RECIPE_STATUSES", "RECIPES_FILE", "RecipeFileError", "RecipeBook",
    "load_recipe_book", "ScaledIngredient", "RecipeResult", "scale_recipe", "run_recipe_tool",
    "make_recipe_tool", "RECIPE_TOOL",
]
RECIPE_LANGCHAIN = []


@pytest.mark.parametrize("name", BEV_PUBLIC + BEV_LANGCHAIN)
def test_bev_names_import(name):
    """Covers: API-1, AC-5 (right). Every bev_tools public name is importable."""
    mod = importlib.import_module("blc.tools.bev_tools")
    assert getattr(mod, name) is not None


@pytest.mark.parametrize("name", RECIPE_PUBLIC + RECIPE_LANGCHAIN)
def test_recipe_names_import(name):
    """Covers: API-1, AC-5 (right). Every recipe_tools public name is importable."""
    mod = importlib.import_module("blc.tools.recipe_tools")
    assert getattr(mod, name) is not None


def test_missing_name_is_not_importable():
    """Covers: API-1, AC-5 (wrong). A name that is not public must not import."""
    with pytest.raises((ImportError, AttributeError)):
        from blc.tools.bev_tools import definitely_not_public  # noqa: F401


PULL_SHEET_ALL = [
    "BeoError", "RuleFileError", "Catalog", "load_catalog", "menu_names", "BeoLine", "Beo", "parse_beo",
    "PullLine", "Skipped", "PullSheet", "build_pull_sheet", "format_pull_sheet", "ROOT",
    "DEFAULT_RULES_DIR", "MENU_FILE", "RULES_FILE", "GALLON", "EACH", "GUESTS_PER_GALLON",
    "PER_VALUES", "TICK", "NOT_ON_MENU", "UNKNOWN_UNIT",
]


def test_pull_sheet_all_is_exact_list():
    """Covers: API-2, AC-5 (right). __all__ equals the 24-name list from the spec, same order."""
    import blc.pull_sheet as ps
    assert list(ps.__all__) == PULL_SHEET_ALL
    assert len(PULL_SHEET_ALL) == 24


@pytest.mark.parametrize("name", PULL_SHEET_ALL)
def test_pull_sheet_names_import(name):
    """Covers: API-1, AC-5 (right). Every name in blc.pull_sheet.__all__ is importable from it."""
    import blc.pull_sheet as ps
    assert hasattr(ps, name), name


@pytest.mark.parametrize("name", SHARED)
def test_pull_sheet_reexports_same_object(name):
    """Covers: API-3, AC-6 (right). blc.pull_sheet re-exports the very same object as bev_tools."""
    import blc.pull_sheet as ps
    import blc.tools.bev_tools as bt
    assert getattr(ps, name) is getattr(bt, name)


def test_default_rules_dir():
    """Covers: API-5, AC-5 (right). DEFAULT_RULES_DIR is <repo>/data/pull_sheet."""
    import blc.pull_sheet as ps
    assert ps.DEFAULT_RULES_DIR.resolve() == (ROOT / "data" / "pull_sheet").resolve()


def test_tool_names():
    """Covers: API-6, AC-4 (right). Tool factories and RECIPE_TOOL carry the documented names."""
    from blc.tools.bev_tools import make_bev_tool
    from blc.tools.recipe_tools import RECIPE_TOOL, make_recipe_tool
    assert make_bev_tool().name == "calculate_bev_item"
    assert make_recipe_tool().name == "scale_recipe"
    assert RECIPE_TOOL.name == "scale_recipe"


def test_tool_names_are_not_swapped():
    """Covers: API-6, AC-4 (wrong). The bev tool is not the recipe tool."""
    from blc.tools.bev_tools import BEV_TOOL
    from blc.tools.recipe_tools import RECIPE_TOOL
    assert BEV_TOOL.name != RECIPE_TOOL.name


def test_catalog_from_pull_sheet_works_with_calculate(need_pull_sheet_data):
    """Covers: API-4, AC-6 (right). A catalog from blc.pull_sheet.load_catalog gives the same result as the default."""
    import blc.pull_sheet as ps
    from blc.tools.bev_tools import DrinkRequest, calculate_bev_item
    drinks = [DrinkRequest("Coffee", 3)]
    with_cat = calculate_bev_item("cambros", drinks, catalog=ps.load_catalog())
    default = calculate_bev_item("cambros", drinks)
    assert with_cat == default
    assert default.status == "ok"
    assert default.lines


def test_catalog_from_bev_tools_works_with_calculate(need_pull_sheet_data):
    """Covers: API-4, AC-6 (right). A catalog from bev_tools.load_catalog gives the same result as the default."""
    import blc.tools.bev_tools as bt
    drinks = [bt.DrinkRequest("Coffee", 3)]
    assert (bt.calculate_bev_item("cambros", drinks, catalog=bt.load_catalog())
            == bt.calculate_bev_item("cambros", drinks))


def _example_beo_text():
    examples = sorted((ROOT / "data" / "pull_sheet" / "examples").glob("*.md"))
    if not examples:
        pytest.skip("no example BEOs")
    return examples[0].read_text(encoding="utf-8")


def test_build_pull_sheet_same_with_either_catalog(need_pull_sheet_data):
    """Covers: API-4b, AC-6 (right). build_pull_sheet gives equal sheets for either load_catalog."""
    import blc.pull_sheet as ps
    import blc.tools.bev_tools as bt
    beo = ps.parse_beo(_example_beo_text())
    a = ps.build_pull_sheet(bt.load_catalog(), beo)
    b = ps.build_pull_sheet(ps.load_catalog(), beo)
    assert a == b
    assert a.lines


def test_load_catalog_empty_dir_raises_rule_file_error(tmp_path):
    """Covers: API-8, AC-6 (wrong). A folder without the menu file raises RuleFileError, catchable on either package."""
    import blc.pull_sheet as ps
    import blc.tools.bev_tools as bt
    with pytest.raises(bt.RuleFileError):
        bt.load_catalog(tmp_path)
    with pytest.raises(ps.RuleFileError):
        bt.load_catalog(tmp_path)
    with pytest.raises(bt.RuleFileError):
        ps.load_catalog(tmp_path)
    with pytest.raises(ps.RuleFileError):
        ps.load_catalog(tmp_path)
    assert issubclass(bt.RuleFileError, ValueError)


def test_pull_line_is_frozen_dataclass():
    """Covers: AC-6 (right/wrong). PullLine(supply, quantity, reasons) holds values; assignment is rejected."""
    from blc.tools.bev_tools import PullLine
    line = PullLine("hot-cups", 120, ("a",))
    assert (line.supply, line.quantity, line.reasons) == ("hot-cups", 120, ("a",))
    assert PullLine("Creamer", None, ()).quantity is None
    with pytest.raises(Exception):
        line.supply = "x"


def test_constants_values():
    """Covers: AC-6, AC-7 (right). Constants keep their documented values."""
    from blc.tools.bev_tools import EACH, GALLON, GUESTS_PER_GALLON
    assert (GALLON, EACH, GUESTS_PER_GALLON) == ("gallon", "each", 25)


@pytest.mark.parametrize("guests,expected", [
    (1, 1), (12, 1), (37, 1), (38, 2), (50, 2), (62, 2), (63, 3), (100, 4), (Fraction(75, 2), 2),
])
def test_guests_to_gallons(guests, expected):
    """Covers: API-7, AC-7 (right, boundary). Rounds half up at 37/38 and 62/63; minimum 1; Fraction result."""
    from blc.tools.bev_tools import guests_to_gallons
    result = guests_to_gallons(guests)
    assert isinstance(result, Fraction)
    assert result == expected


def test_guests_to_gallons_never_below_one():
    """Covers: AC-7 (boundary). Smallest input gives the floor of 1 gallon."""
    from blc.tools.bev_tools import guests_to_gallons
    assert guests_to_gallons(1) == 1
