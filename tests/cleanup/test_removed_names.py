"""Spec 014: dead code removed, kept names still exist (EC-2, EC-3, EC-4, NFR-2). Written from the spec only.

Unit tests: imports and attribute checks only; no Ollama, no Chroma, no network.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

KEPT_ROUTER_NAMES = [
    "route_fast", "split_clauses", "is_follow_up", "quick_label", "TOOL_REGISTRY", "pick_tool",
    "classifier_prompt", "RoutedPart", "RouteDecision", "kind_of", "ROUTES", "ROUTE_KINDS",
    "pull_sheet_items_in", "PULL_SHEET_ITEMS",
]
KEPT_CHAT_NAMES = [
    "run_turn", "run_stages", "answer_turn", "retrieve", "run_tool_step", "run_part",
    "build_final_messages", "summarize_if_long", "summarize_history", "CHAT_MODEL", "CHAT_KEEP_ALIVE",
    "CHAT_TEMPERATURE", "TOOL_PROMPT", "ANSWER_PROMPT", "CHAT_TOOLS", "main",
]
REMOVED_ROUTER_NAMES = [
    "route_question", "route_faithfully", "check_fidelity", "FIDELITY_PREFIX", "parse_reply",
    "ROUTER_PROMPT", "ROUTER_SCHEMA", "build_router_messages", "MENU_DRINKS", "menu_drinks_in",
]
REMOVED_CHAT_NAMES = ["answer_from_context", "answer_with_tools", "ToolAnswer", "maybe_summarize", "SYSTEM_PROMPT"]
REMOVED_ROUTER_MODULES = ["route", "faithful", "fidelity", "parsing", "prompt", "drinks"]


@pytest.mark.parametrize("name", KEPT_ROUTER_NAMES)
def test_blc_router_still_exports_kept_names(name):
    """Covers: EC-2 (right), NFR-2. blc.router exports every kept name of section 3."""
    import blc.router as router

    assert hasattr(router, name), f"blc.router lost {name}"


def test_route_decision_and_routed_part_import():
    """Covers: EC-2 (right). `from blc.router import RouteDecision, RoutedPart` works and the types build."""
    from blc.router import RouteDecision, RoutedPart

    part = RoutedPart("DOCS", "q")
    decision = RouteDecision((part,), "DOCS", False)
    assert decision.parts == (part,) and decision.kind == "DOCS" and decision.fallback is False


@pytest.mark.parametrize("name", REMOVED_ROUTER_NAMES)
def test_blc_router_no_longer_exports_removed_names(name):
    """Covers: AC-1 (wrong), section 4.1. The old JSON router's names are gone from blc.router."""
    import blc.router as router

    assert not hasattr(router, name), f"blc.router still exports {name}"


@pytest.mark.parametrize("module", REMOVED_ROUTER_MODULES)
def test_old_router_modules_are_gone(module):
    """Covers: AC-1 (wrong), section 4.1. blc.router.<module> can no longer be imported."""
    with pytest.raises(ImportError):
        importlib.import_module(f"blc.router.{module}")


@pytest.mark.parametrize("name", KEPT_CHAT_NAMES)
def test_chat_still_has_kept_names(name):
    """Covers: EC-3 (right), EC-4, NFR-2. import chat works and keeps every name of section 3."""
    import chat

    assert hasattr(chat, name), f"chat lost {name}"


@pytest.mark.parametrize("name", REMOVED_CHAT_NAMES)
def test_chat_no_longer_has_removed_names(name):
    """Covers: AC-1 (wrong), section 4.3. The old chat-flow names are gone from chat."""
    import chat

    assert not hasattr(chat, name), f"chat still has {name}"


def test_voice_chat_imports_and_lost_normalize_command():
    """Covers: EC-3 (right), section 4.3 (wrong). import voice_chat works, is_exit_command is kept,
    normalize_command is gone."""
    import voice_chat

    assert callable(voice_chat.is_exit_command)
    assert not hasattr(voice_chat, "normalize_command")


def test_trace_flow_imports():
    """Covers: EC-3 (right). import trace_flow works (no leftover import of a deleted name)."""
    importlib.import_module("trace_flow")


def test_registry_lost_max_prompt_chars():
    """Covers: AC-1 (wrong), section 4.3. MAX_PROMPT_CHARS is gone from blc.router.registry."""
    import blc.router.registry as registry

    assert not hasattr(registry, "MAX_PROMPT_CHARS")


def test_kept_router_modules_import():
    """Covers: EC-4 (right), section 4.1. decision, items, clauses, labels, registry and fast still import."""
    for module in ("decision", "items", "clauses", "labels", "registry", "fast"):
        importlib.import_module(f"blc.router.{module}")
