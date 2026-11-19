"""Spec 041 section 6.4: stale tests are deleted and tests do not use removed code (SUITE-1, 2, 3, 5)."""

from __future__ import annotations

import ast
import re

import pytest

THIS_DIR_NAME = "cleanup"

REMOVED_TEST_PATHS = [
    "router",
    "flow",
    "tool_calling",
    "tool_step/test_tool_step_check.py",
    "tool_step/test_tool_step_eval.py",
    "test_voice_io.py",
    "test_voice_io_answer_turn.py",
    "gemini_migration/test_router.py",
    "no_invented/test_fill_report.py",
    "no_invented/test_golden_eval.py",
]

# file (relative to backend/tests) -> test function names that must be gone
APPENDIX_A_FUNCTIONS = {
    "domain_retrieval/test_detect_domains.py": ["test_real_lexicon_is_non_empty"],
    "food_wiring/test_planner_tools.py": ["test_prompt_holds_no_eval_question"],
    "layout/test_layout.py": ["test_pytest_markers_and_addopts_unchanged"],
    "napkin_knowledge/test_detect.py": [
        "test_napkins_with_beverage", "test_napkin_with_food", "test_no_napkin_word_no_napkin_domain",
        "test_no_napkin_file_food_and_beverage_unchanged", "test_no_napkin_file_with_food_gives_food_only",
    ],
    "napkin_knowledge/test_store.py": [
        "test_napkin_with_beverage_filter", "test_napkin_with_food_filter",
        "test_food_question_never_adds_napkin",
    ],
    "no_invented/test_retry.py": [
        "test_ec21_at_most_two_planner_calls_one_answer_call",
        "test_ec21_exactly_one_planner_call_without_retry",
    ],
    "planned_flow/test_contract.py": [
        "test_history_reaches_planner_and_answer_messages",
        "test_outcome_history_extends_input_without_mutating_it",
        "test_no_history_gives_two_items",
    ],
    "planned_flow/test_run.py": [
        "test_tool_turn_message_has_tool_text_and_no_source", "test_tool_turn_outcome_fields",
        "test_tool_status_and_text_are_recorded_and_shown_whatever_the_status",
        "test_both_turn_runs_store_and_recipe_runner_and_shows_both",
        "test_runner_that_raises_gives_error_result_and_the_turn_finishes",
        "test_missing_runner_gives_no_runner_error_and_the_turn_finishes",
        "test_a_failing_tool_does_not_hide_the_documents",
    ],
    "standalone_tools/test_same.py": ["test_recipe_snapshot_replay_identical"],
}

REMOVED_CHAT_NAMES = {
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
}
REMOVED_MODULE_PREFIXES = ("voice_chat", "trace_flow", "blc.router", "blc.trace", "blc.tool_step.check",
                           "blc.tools.food_tools.tool")


def _other_test_files(repo):
    tests = repo / "backend" / "tests"
    return [p for p in sorted(tests.rglob("*.py"))
            if "__pycache__" not in p.parts and THIS_DIR_NAME not in p.relative_to(tests).parts[:1]]


@pytest.mark.parametrize("rel", REMOVED_TEST_PATHS)
def test_stale_test_path_deleted(repo, rel):
    """Covers: AC-6 (wrong), SUITE-1. Test folders and files that only served removed code or failed at baseline are gone."""
    path = repo / "backend" / "tests" / rel
    if path.is_dir():
        assert not list(path.rglob("test_*.py")), f"{rel} still holds tests"
    else:
        assert not path.exists(), f"{rel} still exists"


@pytest.mark.parametrize("rel", sorted(APPENDIX_A_FUNCTIONS))
def test_appendix_a_functions_deleted(repo, rel):
    """Covers: AC-6 (wrong), SUITE-1. Each failing test of Appendix A is no longer defined in its file."""
    path = repo / "backend" / "tests" / rel
    if not path.exists():
        return  # whole file gone also satisfies the spec
    defined = {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    still = [name for name in APPENDIX_A_FUNCTIONS[rel] if name in defined]
    assert not still, f"{rel} still defines {still}"


@pytest.mark.parametrize("case", ["peach-juice-partial", "mango-juice-partial"])
def test_retrieval_eval_cases_removed_from_test(repo, case):
    """Covers: AC-6 (wrong), SUITE-1. The two failing golden cases are not in test_retrieval_eval.py's parametrisation."""
    import importlib.util

    path = repo / "backend/tests/test_retrieval_eval.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("retrieval_eval_under_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ids = [c["id"] for c in module.RETRIEVAL_CASES + module.ABSTAIN_ONLY_CASES]
    assert case not in ids
    assert ids, "the parametrisation is empty"


def test_golden_file_keeps_the_two_cases(repo):
    """Covers: AC-6 (boundary), SUITE-1. Only the test's parametrisation changes; the golden data itself is not edited."""
    found = [p for p in (repo / "evals").rglob("*") if p.is_file()
             and "peach-juice-partial" in p.read_text(encoding="utf-8", errors="replace")]
    assert found, "evals/ no longer holds the peach-juice-partial golden case"


def test_tests_import_no_removed_chat_name(repo):
    """Covers: AC-4 (wrong), SUITE-2. No test does `from chat import <removed name>`."""
    offenders = []
    for path in _other_test_files(repo):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "chat":
                bad = [a.name for a in node.names if a.name in REMOVED_CHAT_NAMES]
                if bad:
                    offenders.append(f"{path.name}: {bad}")
    assert not offenders, "; ".join(offenders)


def test_tests_import_no_removed_module(repo):
    """Covers: AC-4 (wrong), SUITE-2. No test imports a removed module."""
    offenders = []
    for path in _other_test_files(repo):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
                if node.module == "blc.tool_step":
                    modules += [f"blc.tool_step.{a.name}" for a in node.names]
                if node.module == "blc.tools.food_tools":
                    modules += [f"blc.tools.food_tools.{a.name}" for a in node.names]
            for mod in modules:
                if any(mod == p or mod.startswith(p + ".") for p in REMOVED_MODULE_PREFIXES):
                    offenders.append(f"{path.name}: {mod}")
    assert not offenders, "; ".join(offenders)


def test_tests_import_no_removed_tool_step_or_tool_names(repo):
    """Covers: AC-4 (wrong), SUITE-2. No test imports check_arguments, REJECTED_PREFIX, BEV_TOOL, make_bev_tool, FOOD_TOOL or make_food_tool."""
    banned = {"check_arguments", "REJECTED_PREFIX", "BEV_TOOL", "make_bev_tool", "FOOD_TOOL", "make_food_tool"}
    offenders = []
    for path in _other_test_files(repo):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                bad = [a.name for a in node.names if a.name in banned]
                if bad:
                    offenders.append(f"{path.name}: {bad}")
    assert not offenders, "; ".join(offenders)


def test_cleanup_folder_holds_only_spec_041_tests(repo):
    """Covers: AC-7 (right), SUITE-3. tests/cleanup/ no longer holds spec 014 tests."""
    folder = repo / "backend" / "tests" / "cleanup"
    texts = {p.name: p.read_text(encoding="utf-8") for p in folder.glob("test_*.py")}
    assert texts, "tests/cleanup/ is empty"
    for name, text in texts.items():
        old_marker = "Spec " + "014:"
        old_list = "KEPT_ROUTER" + "_NAMES"
        assert old_marker not in text and old_list not in text, f"{name} is a spec 014 test"
        assert "Spec 041" in text or "spec 041" in text, f"{name} is not marked as a spec 041 test"


@pytest.mark.parametrize("needle", ["024-cli-baseline", "024-recipe-snapshot", "032-assets"])
def test_no_test_file_reads_deleted_spec_assets(repo, needle):
    """Covers: AC-6 (wrong), SUITE-5. No file under backend/tests/ points into the spec files the planner deletes."""
    offenders = []
    for path in (repo / "backend" / "tests").rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.parent.name == "cleanup":
            continue  # this guard names the paths on purpose
        if needle in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(repo)))
    assert not offenders, f"{needle} still referenced in: {offenders}"


def test_web_helpers_take_logo_from_frontend_assets(repo):
    """Covers: AC-6 (right), SUITE-5. tests/web/web_helpers.py reads frontend/assets/blc_logo.png."""
    text = (repo / "backend/tests/web/web_helpers.py").read_text(encoding="utf-8")
    assert re.search(r"frontend.*assets.*blc_logo\.png|blc_logo\.png", text)
    assert "032-assets" not in text
    assert (repo / "frontend/assets/blc_logo.png").is_file()
