"""Spec 024 section 6.1 BOUNDARY: fresh-process import checks (AC-1 to AC-5)."""
BEV_PUBLIC = [
    "BEV_TOOL_NAME", "BEV_ITEMS", "BEV_STATUSES", "DrinkRequest", "DrinkAmount", "BevResult",
    "calculate_bev_item", "run_bev_tool", "Catalog", "load_catalog", "RuleFileError", "PullLine",
    "GALLON", "EACH", "GUESTS_PER_GALLON", "guests_to_gallons",
]
RECIPE_PUBLIC = [
    "RECIPE_TOOL_NAME", "RECIPE_STATUSES", "RECIPES_FILE", "RecipeFileError", "RecipeBook",
    "load_recipe_book", "ScaledIngredient", "RecipeResult", "scale_recipe", "run_recipe_tool",
]

TOUCH_BEV = "import blc.tools.bev_tools as m\nfor n in %r:\n    getattr(m, n)\n" % (BEV_PUBLIC,)
TOUCH_RECIPE = "import blc.tools.recipe_tools as m\nfor n in %r:\n    getattr(m, n)\n" % (RECIPE_PUBLIC,)
CALL_BEV = (
    "from blc.tools.bev_tools import calculate_bev_item, run_bev_tool, DrinkRequest\n"
    "r1 = calculate_bev_item('cambros', [DrinkRequest('Coffee', 3)])\n"
    "r2 = run_bev_tool({'item': 'cups', 'guests': 30})\n"
    "assert r1.status == 'ok', r1\n"
    "assert r2.status == 'ok', r2\n"
)
CALL_RECIPE = (
    "from blc.tools.recipe_tools import run_recipe_tool, scale_recipe\n"
    "r = run_recipe_tool({'recipe': 'lemonade', 'guests': 40})\n"
    "assert r.status == 'ok', r\n"
    "r2 = scale_recipe('lemonade', gallons=2)\n"
    "assert r2.status == 'ok', r2\n"
)


def test_bev_import_loads_no_pull_sheet(fresh):
    """Covers: BOUNDARY-1, AC-1 (right). Importing bev_tools and touching public names loads no pull_sheet."""
    assert fresh(TOUCH_BEV)["pull_sheet"] == []


def test_bev_calls_load_no_pull_sheet(fresh, need_pull_sheet_data):
    """Covers: BOUNDARY-2, AC-1 (right). Calculating cambros and cups is ok and loads no pull_sheet."""
    assert fresh(TOUCH_BEV + CALL_BEV)["pull_sheet"] == []


def test_recipe_import_and_call_load_no_pull_sheet(fresh, need_recipes_data):
    """Covers: BOUNDARY-3, AC-2 (right). recipe_tools import + run_recipe_tool load no pull_sheet."""
    assert fresh(TOUCH_RECIPE + CALL_RECIPE)["pull_sheet"] == []


def test_recipe_import_alone_loads_no_pull_sheet(fresh):
    """Covers: AC-2 (boundary). Import only, no call, still loads no pull_sheet."""
    assert fresh(TOUCH_RECIPE)["pull_sheet"] == []


def test_no_langchain_after_bev_import(fresh):
    """Covers: BOUNDARY-4, AC-3 (right). bev_tools import loads no LangChain/LangGraph/chroma/ollama."""
    assert fresh(TOUCH_BEV)["forbidden"] == []


def test_no_langchain_after_bev_calls(fresh, need_pull_sheet_data):
    """Covers: BOUNDARY-4, AC-3 (right). bev calculations load no LangChain-family module."""
    assert fresh(TOUCH_BEV + CALL_BEV)["forbidden"] == []


def test_no_langchain_after_recipe_calls(fresh, need_recipes_data):
    """Covers: BOUNDARY-4, AC-3 (right). recipe calculations load no LangChain-family module."""
    assert fresh(TOUCH_RECIPE + CALL_RECIPE)["forbidden"] == []


def test_no_langchain_after_importing_both(fresh):
    """Covers: BOUNDARY-4, AC-3 (boundary). Importing both packages together loads no LangChain."""
    assert fresh(TOUCH_BEV + TOUCH_RECIPE)["forbidden"] == []


def test_accessing_bev_tool_loads_langchain(fresh):
    """Covers: BOUNDARY-5, AC-3 (wrong: lazy loading ends on access), AC-4 (right)."""
    code = (
        "import blc.tools.bev_tools as b, blc.tools.recipe_tools as r\n"
        "assert 'langchain_core' not in sys.modules\n"
        "t = b.BEV_TOOL\n"
        "assert t.name == 'calculate_bev_item', t.name\n"
    )
    report = fresh(code)
    assert any(m.startswith("langchain") for m in report["forbidden"]), report


def test_accessing_recipe_tool_loads_langchain(fresh):
    """Covers: BOUNDARY-5, AC-4 (right). RECIPE_TOOL loads LangChain on access and is named scale_recipe."""
    code = (
        "import blc.tools.recipe_tools as r\n"
        "assert 'langchain_core' not in sys.modules\n"
        "t = r.RECIPE_TOOL\n"
        "assert t.name == 'scale_recipe', t.name\n"
    )
    report = fresh(code)
    assert any(m.startswith("langchain") for m in report["forbidden"]), report


def test_from_import_of_tool_objects_works(fresh):
    """Covers: AC-4 (right). The from-import form of the LangChain names still works."""
    code = (
        "from blc.tools.bev_tools import BEV_TOOL, make_bev_tool\n"
        "from blc.tools.recipe_tools import RECIPE_TOOL, make_recipe_tool\n"
        "assert BEV_TOOL.name == 'calculate_bev_item'\n"
        "assert RECIPE_TOOL.name == 'scale_recipe'\n"
    )
    fresh(code)


def test_unknown_attribute_still_raises(fresh):
    """Covers: BOUNDARY-9, AC-4 (wrong). Lazy access must not swallow unknown names: AttributeError on both packages."""
    code = (
        "import blc.tools.bev_tools as b, blc.tools.recipe_tools as r\n"
        "for mod in (b, r):\n"
        "    try:\n        mod.NOT_A_NAME\n    except AttributeError:\n        continue\n"
        "    raise SystemExit('no AttributeError from ' + mod.__name__)\n"
    )
    fresh(code)


def test_no_langchain_after_bev_import_only(fresh):
    """Covers: BOUNDARY-4, AC-3 (right, situation a). Only importing bev_tools loads no LangChain-family module."""
    assert fresh("import blc.tools.bev_tools\n")["forbidden"] == []


def test_no_langchain_after_recipe_import_only(fresh):
    """Covers: BOUNDARY-4, AC-3 (right, situation a). Only importing recipe_tools loads no LangChain-family module."""
    assert fresh("import blc.tools.recipe_tools\n")["forbidden"] == []


def test_no_langchain_after_recipe_touching_names(fresh):
    """Covers: BOUNDARY-4, AC-3 (right, situation b). Touching every non-LangChain recipe name loads none."""
    assert fresh(TOUCH_RECIPE)["forbidden"] == []


def test_bev_import_only_loads_no_pull_sheet(fresh):
    """Covers: BOUNDARY-1, AC-1 (boundary). Import only, no name access, loads no pull_sheet."""
    assert fresh("import blc.tools.bev_tools\n")["pull_sheet"] == []


def test_control_detector_reports_pull_sheet(fresh):
    """Covers: BOUNDARY-7, AC-1/AC-2 (wrong control). Importing blc.pull_sheet is reported by the same detector."""
    report = fresh("import blc.pull_sheet\n")
    assert "blc.pull_sheet" in report["pull_sheet"]


def test_control_detector_reports_langchain(fresh):
    """Covers: BOUNDARY-8, AC-3 (wrong control). Importing langchain_core is reported by the forbidden detector."""
    report = fresh("import langchain_core\n")
    assert "langchain_core" in report["forbidden"]


def test_pull_sheet_import_loads_no_langchain(fresh):
    """Covers: BOUNDARY-6, AC-5 (right). Importing blc.pull_sheet loads no langchain*, chromadb or ollama."""
    report = fresh("import blc.pull_sheet\n")
    assert report["forbidden"] == []
