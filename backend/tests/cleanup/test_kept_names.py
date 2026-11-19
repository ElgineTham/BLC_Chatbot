"""Spec 041 section 3.2 / 6.2: kept names still import and behave (KEPT-1..6)."""

from __future__ import annotations

import importlib

import pytest

KEPT_CHAT_NAMES = [
    "main", "start_stack", "build_store", "build_domain_store", "retrieve", "is_exit_utterance",
    "normalize_utterance", "ROOT", "CHROMA_DIR", "COLLECTION_NAME", "TOP_K", "EXIT_COMMANDS",
    "EXIT_FILLERS", "APOSTROPHES", "CHAT_TEMPERATURE", "run_planned_turn", "summarize_if_long",
    "HISTORY_TOKEN_LIMIT", "check_store_model", "StoreModelMismatchError", "CHAT_MODEL",
    "EMBED_MODEL", "CHAT_API_KEY_ENV", "MissingApiKeyError", "build_chat_model",
    "build_embeddings", "load_catalog", "RuleFileError",
]


@pytest.mark.parametrize("name", KEPT_CHAT_NAMES)
def test_chat_keeps_name(name):
    """Covers: AC-3 (right), KEPT-1. `chat` still exposes the kept name."""
    import chat

    assert hasattr(chat, name), f"chat lost {name}"


@pytest.mark.parametrize("module", ["chat", "web", "ingest", "pull_sheet"])
def test_entry_points_import(module):
    """Covers: AC-3 (right), KEPT-2. Each live entry point imports without error."""
    assert importlib.import_module(module) is not None


def test_numbers_module_names_import():
    """Covers: AC-3 (right), KEPT-3. blc.tool_step.numbers keeps its four names."""
    from blc.tool_step.numbers import ALWAYS_ACCEPTED, WORD_NUMBERS, as_number, numbers_in

    assert callable(numbers_in) and callable(as_number)
    assert ALWAYS_ACCEPTED is not None and WORD_NUMBERS is not None


def test_numbers_in_still_reads_a_plain_sentence():
    """Covers: AC-3 (right), spec section 4. numbers_in finds the numbers in a simple sentence."""
    from blc.tool_step.numbers import numbers_in

    found = numbers_in("two cambros for 30 guests")
    values = {float(x) for x in found}
    assert 30.0 in values
    assert 2.0 in values


def test_numbers_in_empty_text_gives_nothing():
    """Covers: AC-3 (boundary). Text without numbers yields no numbers."""
    from blc.tool_step.numbers import numbers_in

    assert len(list(numbers_in("where is the coffee"))) == 0


@pytest.mark.parametrize(
    "name",
    ["BEV_SCHEMA", "ITEM_DESCRIPTION", "DRINKS_DESCRIPTION", "GALLONS_DESCRIPTION", "GUESTS_DESCRIPTION"],
)
def test_bev_tool_module_keeps_schema_names(name):
    """Covers: AC-3 (right), KEPT-4. blc.tools.bev_tools.tool still defines the schema and descriptions."""
    import blc.tools.bev_tools.tool as bev_tool_module

    assert hasattr(bev_tool_module, name)


def test_bev_tools_every_exported_name_resolves():
    """Covers: AC-3 (right). Every name left in blc.tools.bev_tools.__all__ resolves."""
    import blc.tools.bev_tools as bev_tools

    for name in bev_tools.__all__:
        assert hasattr(bev_tools, name), f"bev_tools.__all__ lists missing {name}"


def test_food_tools_every_exported_name_resolves():
    """Covers: AC-3 (right). Every name left in blc.tools.food_tools.__all__ resolves."""
    import blc.tools.food_tools as food_tools

    for name in food_tools.__all__:
        assert hasattr(food_tools, name), f"food_tools.__all__ lists missing {name}"


def test_recipe_tool_name():
    """Covers: AC-3 (right), KEPT-5. RECIPE_TOOL is still the scale_recipe tool and make_recipe_tool exists."""
    from blc.tools.recipe_tools import RECIPE_TOOL, make_recipe_tool

    assert RECIPE_TOOL.name == "scale_recipe"
    assert callable(make_recipe_tool)


def test_exit_utterance_right_case():
    """Covers: AC-3 (right), KEPT-6. 'bye' is an exit utterance."""
    import chat

    assert chat.is_exit_utterance("bye") is True


def test_exit_utterance_wrong_case():
    """Covers: AC-3 (wrong), KEPT-6. An ordinary question is not an exit utterance."""
    import chat

    assert chat.is_exit_utterance("where is the coffee?") is False


@pytest.mark.parametrize("package", ["blc.planner", "blc.flow", "blc.retrieval", "blc.history", "blc.ingest", "blc.llm", "blc.web", "blc.pull_sheet", "blc.judge"])
def test_live_packages_still_import(package):
    """Covers: AC-3 (right). The unchanged packages of section 3.2 still import."""
    assert importlib.import_module(package) is not None
