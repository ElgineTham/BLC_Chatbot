"""Spec 037 section 6.7 (MIGRATE-1 to MIGRATE-5): existing tests no longer use the removed Ollama names.

The scan parses every test file with `ast`, so comments and docstrings never count. A removed name may
appear only as a string inside a list/tuple/set literal or as an operand of `in` / `not in` (a
"removed names" list or an absence assertion). Unit tests; no network.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
REMOVED = ("CHAT_KEEP_ALIVE", "OLLAMA_HOST", "OllamaEmbeddings", "keep_alive")


def _test_files():
    files = sorted(p for p in TESTS_DIR.rglob("*.py") if p.resolve() != THIS_FILE)
    assert files
    return files


def _parse(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return tree, parents


def _removed_name_hits(path: Path) -> list[str]:
    tree, parents = _parse(path)
    hits = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Name) and node.id in REMOVED:
            hits.append(f"{path.name}:{line} name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in REMOVED:
            hits.append(f"{path.name}:{line} attribute {node.attr}")
        elif isinstance(node, ast.keyword) and node.arg in REMOVED:
            hits.append(f"{path.name}:{line} keyword {node.arg}")
        elif isinstance(node, ast.alias) and (node.name in REMOVED or (node.asname in REMOVED)):
            hits.append(f"{path.name}:{line} import {node.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not any(r in node.value for r in REMOVED):
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Expr):  # docstring or bare string statement
                continue
            exact = node.value in REMOVED
            allowed = isinstance(parent, (ast.List, ast.Tuple, ast.Set)) or (
                isinstance(parent, ast.Compare)
                and all(isinstance(op, (ast.In, ast.NotIn)) for op in parent.ops)
            )
            if not (exact and allowed):
                hits.append(f"{path.name}:{line} string {node.value!r}")
    return hits


def test_scan_finds_the_test_files():
    """Covers: AC-20 (boundary), MIGRATE-1. The scan sees a realistic number of files (guards a vacuous pass)."""
    assert len(_test_files()) > 50


def test_no_removed_names_in_tests():
    """Covers: AC-20 (wrong), MIGRATE-1. No CHAT_KEEP_ALIVE, OLLAMA_HOST, OllamaEmbeddings or keep_alive anywhere
    under backend/tests/, except as a string in a removed-names list or an `in` / `not in` assertion."""
    hits = [h for path in _test_files() for h in _removed_name_hits(path)]
    assert hits == []


def _is_judge_model(node) -> bool:
    return (isinstance(node, ast.Name) and node.id == "JUDGE_MODEL") or (
        isinstance(node, ast.Attribute) and node.attr == "JUDGE_MODEL"
    )


def _chat_ollama_calls(path: Path):
    tree, _ = _parse(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name == "ChatOllama":
            yield node


def test_every_chat_ollama_call_uses_judge_model():
    """Covers: AC-20 (wrong), MIGRATE-2, MIGRATE-4. Every ChatOllama(...) call in the tests has model=JUDGE_MODEL
    (or passes JUDGE_MODEL as the first argument); none builds a chatbot model."""
    bad = []
    for path in _test_files():
        for call in _chat_ollama_calls(path):
            kw = {k.arg: k.value for k in call.keywords}
            model = kw.get("model") or (call.args[0] if call.args else None)
            if model is None or not _is_judge_model(model):
                bad.append(f"{path.name}:{call.lineno}")
    assert bad == []


def test_judge_model_test_stays():
    """Covers: AC-20 (right), MIGRATE-4. The judge's JUDGE_MODEL == 'qwen2.5:7b' test is still present."""
    text = (TESTS_DIR / "beverage_knowledge" / "test_judge.py").read_text(encoding="utf-8")
    assert "JUDGE_MODEL ==" in text and "qwen2.5:7b" in text


@pytest.mark.parametrize(
    "rel",
    [
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
        "tool_step/conftest.py",
    ],
)
def test_live_chat_fixtures_use_build_chat_model_and_key_skip(rel):
    """Covers: AC-20 (right), MIGRATE-3. Chatbot live fixtures build the model through build_chat_model and
    skip when GOOGLE_API_KEY is unset."""
    text = (TESTS_DIR / rel).read_text(encoding="utf-8")
    assert "build_chat_model" in text, rel
    assert "ANTHROPIC_API_KEY" in text, rel  # spec 039: chat model runs on Claude
    if rel != "tool_step/conftest.py":  # that fixture builds no embeddings
        assert "GOOGLE_API_KEY" in text, rel
    assert "pytest.skip" in text, rel


def test_voice_test_builds_model_through_chat_builder():
    """Covers: AC-20 (right), MIGRATE-5. test_voice_io fakes chat.build_chat_model and checks temperature 0.1."""
    text = (TESTS_DIR / "test_voice_io.py").read_text(encoding="utf-8")
    assert '"build_chat_model"' in text
    assert "0.1" in text
    assert "voice_chat, \"ChatOllama\"" not in text


def test_docker_image_tests_pass_google_api_key():
    """Covers: AC-20 (right), MIGRATE-5. docker/test_image.py gives containers GOOGLE_API_KEY, not OLLAMA_HOST."""
    text = (TESTS_DIR / "docker" / "test_image.py").read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY" in text
