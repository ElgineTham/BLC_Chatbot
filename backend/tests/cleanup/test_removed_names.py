"""Spec 041 section 3.1 / 6.1: removed files, modules and names are gone (REMOVED-1..6).

Replaces the spec 014 guard. Unit tests: file-system checks, imports and attribute checks only.
"""

from __future__ import annotations

import importlib
import re

import pytest

REMOVED_FILES = [
    "backend/scripts/voice_chat.py",
    "backend/scripts/trace_flow.py",
    "backend/src/blc/router",
    "backend/src/blc/trace",
    "backend/src/blc/tool_step/check.py",
    "backend/src/blc/tools/food_tools/tool.py",
]

REMOVED_MODULES = [
    "voice_chat",
    "trace_flow",
    "blc.router",
    "blc.trace",
    "blc.tool_step.check",
    "blc.tools.food_tools.tool",
]

REMOVED_CHAT_NAMES = [
    "run_turn", "answer_turn", "run_stages", "run_part", "run_part_with_tool", "run_tool_step",
    "run_tool_call", "run_tool_round", "first_response", "requested_calls", "is_failed_result",
    "part_tool_name", "tool_step_messages", "history_messages", "format_tool_results",
    "format_labelled_parts", "build_final_messages", "unknown_retrieval_reply", "format_context",
    "format_history", "clean_question", "log_stage", "retrieval_stage", "tool_stage",
    "ToolCallRecord", "PartResult", "StepOutcome", "TurnResult", "CHAT_TOOLS", "MAX_TOOL_ROUNDS",
    "TOOL_LIMIT_REPLY", "UNKNOWN_TOOL_RESULT", "FAILED_RESULT_PREFIXES", "TOOL_REMINDER",
    "TOOL_PROMPT", "RECIPE_TOOL_PROMPT", "PART_INSTRUCTION", "ANSWER_PROMPT", "TOOL_PROMPTS",
    "SUMMARIZE_PROMPT", "count_tokens", "history_tokens", "summarize_history", "CHARS_PER_TOKEN",
    "FLOW_LOGGER",
]

DANGLING_PATTERNS = {
    "voice_chat": re.compile(r"voice_chat"),
    "trace_flow": re.compile(r"trace_flow"),
    "blc.router": re.compile(r"blc\.router\b"),
    "blc.trace": re.compile(r"blc\.trace\b"),
    "tool_step.check": re.compile(r"tool_step\.check\b"),
    "food_tools.tool": re.compile(r"food_tools\.tool\b"),
}


@pytest.mark.parametrize("rel", REMOVED_FILES)
def test_removed_path_does_not_exist(repo, rel):
    """Covers: AC-1 (wrong), REMOVED-1. Each removed file or package directory is gone."""
    assert not (repo / rel).exists(), f"{rel} still exists"


@pytest.mark.parametrize("module", REMOVED_MODULES)
def test_removed_module_cannot_be_imported(module):
    """Covers: AC-1 (wrong), REMOVED-2. Importing a removed module raises ModuleNotFoundError."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


@pytest.mark.parametrize("name", REMOVED_CHAT_NAMES)
def test_chat_no_longer_has_removed_name(name):
    """Covers: AC-2 (wrong), REMOVED-3. `chat` does not expose the removed name."""
    import chat

    assert not hasattr(chat, name), f"chat still has {name}"


@pytest.mark.parametrize("name", ["check_arguments", "REJECTED_PREFIX"])
def test_tool_step_no_longer_has_check_names(name):
    """Covers: AC-2 (wrong), REMOVED-4. blc.tool_step does not expose the argument-check names."""
    import blc.tool_step as tool_step

    assert not hasattr(tool_step, name), f"blc.tool_step still has {name}"


@pytest.mark.parametrize("name", ["BEV_TOOL", "make_bev_tool"])
def test_bev_tools_package_lost_tool_names(name):
    """Covers: AC-2 (wrong), REMOVED-5. blc.tools.bev_tools does not expose the removed names."""
    import blc.tools.bev_tools as bev_tools

    with pytest.raises(AttributeError):
        getattr(bev_tools, name)
    assert name not in getattr(bev_tools, "__all__", [])


@pytest.mark.parametrize("name", ["FOOD_TOOL", "make_food_tool"])
def test_food_tools_package_lost_tool_names(name):
    """Covers: AC-2 (wrong), REMOVED-5. blc.tools.food_tools does not expose the removed names."""
    import blc.tools.food_tools as food_tools

    with pytest.raises(AttributeError):
        getattr(food_tools, name)
    assert name not in getattr(food_tools, "__all__", [])


@pytest.mark.parametrize("name", ["BevTool", "make_bev_tool", "BEV_TOOL", "BEV_TOOL_DESCRIPTION"])
def test_bev_tool_module_lost_names(name):
    """Covers: AC-2 (wrong), REMOVED-5. blc.tools.bev_tools.tool no longer defines the tool object names."""
    import blc.tools.bev_tools.tool as bev_tool_module

    assert not hasattr(bev_tool_module, name), f"bev_tools.tool still has {name}"


def test_no_live_file_mentions_removed_modules(repo):
    """Covers: AC-4 (wrong), REMOVED-6. No .py under backend/scripts or backend/src, nor Dockerfile or ingest.yml, names a removed module."""
    files = []
    for sub in ("backend/scripts", "backend/src"):
        files += [p for p in (repo / sub).rglob("*.py") if "__pycache__" not in p.parts]
    for extra in ("docker/Dockerfile", ".github/workflows/ingest.yml"):
        path = repo / extra
        if path.exists():
            files.append(path)
    assert files, "found no files to scan"
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in DANGLING_PATTERNS.items():
            if pattern.search(text):
                hits.append(f"{path.relative_to(repo)}: {label}")
    assert not hits, "dangling references: " + "; ".join(hits)


def test_scan_sees_the_live_entry_points(repo):
    """Covers: AC-4 (boundary), REMOVED-6. Sanity check: the scanned tree includes chat.py and the blc package, so an empty hit list is meaningful."""
    assert (repo / "backend/scripts/chat.py").is_file()
    assert (repo / "backend/src/blc/flow").is_dir()
