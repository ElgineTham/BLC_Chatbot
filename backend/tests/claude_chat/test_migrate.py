"""Spec 039 section 6.5 (MIGRATE-1 to MIGRATE-3): existing tests migrated from the Gemini chat model to Claude.

The scan parses every test file with `ast`, so comments and docstrings never count. Unit tests; no network.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
OLD_CHAT_MODEL = "gemini-3.5-flash-lite"


def _test_files():
    files = sorted(p for p in TESTS_DIR.rglob("*.py") if p.resolve() != THIS_FILE)
    assert len(files) > 50  # guards a vacuous pass
    return files


# ---- MIGRATE-1 / AC-14

def _is_negative_comparison(node, parents) -> bool:
    """True when the constant is an operand of `!=` / `not in` (an assertion that the model is NOT the string)."""
    parent = parents.get(node)
    return isinstance(parent, ast.Compare) and all(
        isinstance(op, (ast.NotEq, ast.NotIn)) for op in parent.ops
    )


def test_no_test_mentions_old_chat_model_outside_docstrings():
    """Covers: AC-14 (wrong), MIGRATE-1, MIGRATE-4. No test file under backend/tests/ (but this one) asserts
    'gemini-3.5-flash-lite' as the chat model: docstrings, comments and `!=` assertions are allowed."""
    hits = []
    for path in _test_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and OLD_CHAT_MODEL in node.value
                and not isinstance(parents.get(node), ast.Expr)
                and not _is_negative_comparison(node, parents)
            ):
                hits.append(f"{path.name}:{node.lineno}")
    assert hits == []


def test_scan_still_catches_a_positive_assertion():
    """Covers: AC-14 (boundary), MIGRATE-4. The negative-comparison allowance does not hide `== old model`."""
    tree = ast.parse(f'assert CHAT_MODEL == "{OLD_CHAT_MODEL}"\nassert CHAT_MODEL != "{OLD_CHAT_MODEL}"')
    parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    consts = [n for n in ast.walk(tree) if isinstance(n, ast.Constant)]
    assert [_is_negative_comparison(c, parents) for c in consts] == [False, True]


def test_claude_chat_negative_assertions_present():
    """Covers: AC-14 (right), MIGRATE-4. claude_chat/ asserts CHAT_MODEL != the old model, and the scan passes."""
    text = (TESTS_DIR / "claude_chat" / "test_llm.py").read_text(encoding="utf-8")
    assert f'CHAT_MODEL != "{OLD_CHAT_MODEL}"' in text


# ---- MIGRATE-5 / AC-4

def test_live_key_fixtures_never_return_a_key_value(monkeypatch, request):
    """Covers: AC-4 (wrong), MIGRATE-5. With sentinel keys in the environment, the live-key fixtures in
    claude_chat/ return nothing that contains a sentinel."""
    anth, goog = "sk-ant-SENTINEL-111", "goog-SENTINEL-222"
    monkeypatch.setenv("ANTHROPIC_API_KEY", anth)
    monkeypatch.setenv("GOOGLE_API_KEY", goog)
    for name in ("live_anthropic_key", "live_both_keys"):
        value = request.getfixturevalue(name)
        rendered = repr(value) + str(value)
        assert anth not in rendered, name
        assert goog not in rendered, name


def test_chat_model_assertions_use_claude():
    """Covers: AC-14 (right), MIGRATE-1. The migrated entry-point test asserts the Claude chat model name."""
    text = (TESTS_DIR / "gemini_migration" / "test_entry.py").read_text(encoding="utf-8")
    assert "claude-haiku-4-5" in text


# ---- MIGRATE-2 / AC-14

CHAT_AND_EMBED_FIXTURES = [
    "answer_grounding/conftest.py",
    "bev_tools/conftest.py",
    "beverage_knowledge/conftest.py",
    "flow/conftest.py",
    "food_answers/conftest.py",
    "food_wiring/conftest.py",
    "mixed_questions/conftest.py",
    "no_invented/conftest.py",
    "planned_flow/conftest.py",
    "planner/conftest.py",
    "router/conftest.py",
    "tool_calling/conftest.py",
    "test_generation_eval.py",
    "web/test_integration.py",
]


@pytest.mark.parametrize("rel", CHAT_AND_EMBED_FIXTURES)
def test_fixtures_building_both_skip_on_either_missing_key(rel):
    """Covers: AC-14 (right), MIGRATE-2. Fixtures that build a real chat model and real embeddings skip when
    ANTHROPIC_API_KEY or GOOGLE_API_KEY is unset."""
    text = (TESTS_DIR / rel).read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in text, rel
    assert "GOOGLE_API_KEY" in text, rel
    assert "pytest.skip" in text, rel


def test_chat_only_fixture_skips_on_anthropic_key():
    """Covers: AC-14 (right), MIGRATE-2. The tool_step fixture builds only a chat model: it skips on ANTHROPIC_API_KEY."""
    text = (TESTS_DIR / "tool_step" / "conftest.py").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in text
    assert "pytest.skip" in text


@pytest.mark.parametrize(
    "rel",
    [
        "domain_retrieval/conftest.py",
        "food_retrieval/conftest.py",
        "napkin_knowledge/conftest.py",
        "ci_ingest/test_ingest_store.py",
    ],
)
def test_embedding_only_fixtures_do_not_need_anthropic_key(rel):
    """Covers: AC-14 (boundary), MIGRATE-2. Fixtures that build only real embeddings skip on GOOGLE_API_KEY and do
    not require ANTHROPIC_API_KEY."""
    text = (TESTS_DIR / rel).read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY" in text, rel
    assert "ANTHROPIC_API_KEY" not in text, rel


# ---- MIGRATE-3 / AC-14

@pytest.mark.parametrize(
    "rel,needle",
    [
        ("gemini_migration/test_llm.py", "def test_unset_key_raises"),
        ("gemini_migration/test_llm.py", "def test_blank_key_raises"),
        ("gemini_migration/test_stamp_check.py", "def test_"),
        ("gemini_migration/test_stamp_ingest.py", "def test_"),
        ("gemini_migration/test_repo.py", "def test_ingest_step_has_google_api_key_secret"),
        ("gemini_migration/test_repo.py", "def test_compose_port_and_mounts_unchanged"),
        ("gemini_migration/test_repo.py", "def test_dockerfile_install_excludes_voice_and_eval"),
        ("gemini_migration/test_entry.py", "def test_mismatched_store_returns_1"),
        ("gemini_migration/test_live.py", "def test_embeddings_have_768_unit_vectors"),
    ],
)
def test_embedding_stamp_workflow_docker_tests_remain(rel, needle):
    """Covers: AC-14 (right), MIGRATE-3. The Gemini migration's embedding, stamp, workflow and Docker tests are
    still present after the chat-model migration."""
    assert needle in (TESTS_DIR / rel).read_text(encoding="utf-8")
