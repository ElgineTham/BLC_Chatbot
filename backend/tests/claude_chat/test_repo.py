"""Spec 039 section 6.3 (REPO-1 to REPO-4): dependencies, no Gemini chat model, compose, ingest workflow."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess

import pytest
from cc_helpers import ROOT

PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "ingest.yml"
COMPOSE = "docker/compose.yaml"


def _dep_names(deps):
    """Names from a PEP 621 list of requirement strings or a Poetry table."""
    if isinstance(deps, dict):
        return {k.lower() for k in deps}
    return {re.match(r"[A-Za-z0-9_.\-]+", d).group(0).lower() for d in deps}


@pytest.fixture(scope="module")
def pyproject():
    try:
        import tomllib
    except ImportError:  # Python 3.10
        tomllib = pytest.importorskip("tomli")
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


# ---- REPO-1 / AC-8

def test_anthropic_is_main_dependency(pyproject):
    """Covers: AC-8 (right), REPO-1. langchain-anthropic is a main dependency."""
    assert "langchain-anthropic" in _dep_names(pyproject["project"]["dependencies"])


def test_genai_is_still_main_dependency(pyproject):
    """Covers: AC-8 (right), REPO-1. langchain-google-genai stays a main dependency (embeddings)."""
    assert "langchain-google-genai" in _dep_names(pyproject["project"]["dependencies"])


def test_anthropic_not_only_in_a_group(pyproject):
    """Covers: AC-8 (wrong), REPO-1. langchain-anthropic is not hidden in the eval group alone."""
    groups = pyproject["tool"]["poetry"]["group"]
    assert "langchain-anthropic" not in _dep_names(groups["eval"]["dependencies"])


def test_eval_group_unchanged(pyproject):
    """Covers: AC-8 (boundary), REPO-1; spec 041 AC-5. The eval group keeps the Ollama packages; it is the only group (voice is gone)."""
    groups = pyproject["tool"]["poetry"]["group"]
    assert set(groups) == {"eval"}
    assert _dep_names(groups["eval"]["dependencies"]) == {"ollama", "langchain-ollama"}


# ---- REPO-2 / AC-8

def _source_files():
    files = list((ROOT / "backend" / "src" / "blc").rglob("*.py"))
    files += list((ROOT / "backend" / "scripts").glob("*.py"))
    assert len(files) > 10
    return files


def test_no_gemini_chat_model_in_source():
    """Covers: AC-8 (wrong), REPO-2. No module under backend/src/blc/ or backend/scripts/ uses
    ChatGoogleGenerativeAI (found by parsing: imports, names and attributes; comments and docstrings ignored)."""
    offenders = []
    for f in _source_files():
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            hit = (
                (isinstance(node, ast.Name) and node.id == "ChatGoogleGenerativeAI")
                or (isinstance(node, ast.Attribute) and node.attr == "ChatGoogleGenerativeAI")
                or (isinstance(node, ast.alias) and node.name.split(".")[-1] == "ChatGoogleGenerativeAI")
            )
            if hit:
                offenders.append(f"{f.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_source_builds_claude_chat_model():
    """Covers: AC-8 (right), REPO-2. Some module under backend/src/blc/llm/ uses ChatAnthropic."""
    found = any(
        "ChatAnthropic" in f.read_text(encoding="utf-8")
        for f in (ROOT / "backend" / "src" / "blc" / "llm").rglob("*.py")
    )
    assert found


# ---- REPO-3 / AC-9

def _docker_ready():
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _compose(env_extra, drop=("OLLAMA_HOST", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY")):
    env = dict(os.environ)
    for k in drop:
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run(
        ["docker", "compose", "-f", COMPOSE, "config", "--format", "json"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture
def docker_cfg():
    if not _docker_ready():
        pytest.skip("docker CLI missing or daemon not running")
    return _compose({"ANTHROPIC_API_KEY": "dummy-a", "GOOGLE_API_KEY": "dummy-g"})


def test_compose_passes_both_keys(docker_cfg):
    """Covers: AC-9 (right), REPO-3. Service web env has ANTHROPIC_API_KEY=dummy-a and GOOGLE_API_KEY=dummy-g."""
    env = docker_cfg["services"]["web"]["environment"]
    assert env["ANTHROPIC_API_KEY"] == "dummy-a"
    assert env["GOOGLE_API_KEY"] == "dummy-g"


def test_compose_key_values_follow_the_shell(docker_cfg):
    """Covers: AC-9 (boundary), REPO-3. Different shell values give different env values (not hard-coded)."""
    other = _compose({"ANTHROPIC_API_KEY": "other-a", "GOOGLE_API_KEY": "other-g"})
    env = other["services"]["web"]["environment"]
    assert env["ANTHROPIC_API_KEY"] == "other-a"
    assert env["GOOGLE_API_KEY"] == "other-g"


def test_compose_port_and_mounts_unchanged(docker_cfg):
    """Covers: AC-9 (boundary), REPO-3. Specs 035/037: one service, 8000 -> 8000, exactly the data and .chroma mounts."""
    assert set(docker_cfg["services"]) == {"web"}
    web = docker_cfg["services"]["web"]
    assert [(int(p["published"]), int(p["target"])) for p in web["ports"]] == [(8000, 8000)]
    assert sorted(v["target"] for v in web["volumes"]) == ["/app/.chroma", "/app/data"]


# ---- REPO-4 / AC-9

def test_ingest_workflow_does_not_mention_anthropic():
    """Covers: AC-9 (wrong), REPO-4. The ingest workflow YAML has no ANTHROPIC anywhere (any case)."""
    assert WORKFLOW.exists(), f"{WORKFLOW} missing"
    assert "anthropic" not in WORKFLOW.read_text(encoding="utf-8").lower()


def test_ingest_workflow_still_uses_google_secret():
    """Covers: AC-9 (right), REPO-4. The workflow is otherwise unchanged: it still passes the GOOGLE_API_KEY secret."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [s for job in (wf.get("jobs") or {}).values() for s in job.get("steps", [])]
    assert any(
        (s.get("env") or {}).get("GOOGLE_API_KEY") == "${{ secrets.GOOGLE_API_KEY }}" for s in steps
    )
