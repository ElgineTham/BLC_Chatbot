"""Spec 037 section 6.5 (REPO-1 to REPO-6): dependencies, imports, workflow, Docker."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest
from gm_helpers import ROOT

PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "ingest.yml"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
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


# ---- REPO-1 / AC-13

def test_genai_is_main_dependency(pyproject):
    """Covers: AC-13 (right), REPO-1. langchain-google-genai is a main dependency."""
    assert "langchain-google-genai" in _dep_names(pyproject["project"]["dependencies"])


def test_ollama_not_in_main_dependencies(pyproject):
    """Covers: AC-13 (wrong), REPO-1. langchain-ollama and ollama are not main dependencies."""
    names = _dep_names(pyproject["project"]["dependencies"])
    assert "langchain-ollama" not in names
    assert "ollama" not in names


def test_ollama_in_eval_group_not_optional(pyproject):
    """Covers: AC-13 (right), REPO-1. Group eval holds both and is not optional."""
    eval_group = pyproject["tool"]["poetry"]["group"]["eval"]
    assert {"langchain-ollama", "ollama"} <= _dep_names(eval_group["dependencies"])
    assert eval_group.get("optional", False) is False


def test_ollama_only_in_eval_group(pyproject):
    """Covers: AC-13 (boundary), REPO-1. No other group (e.g. voice) lists the Ollama packages."""
    for gname, group in pyproject["tool"]["poetry"]["group"].items():
        if gname == "eval":
            continue
        names = _dep_names(group.get("dependencies", {}))
        assert "langchain-ollama" not in names and "ollama" not in names, gname


# ---- REPO-2 / AC-13

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(?:langchain_ollama|ollama)\b", re.M)


def test_no_ollama_imports_outside_judge():
    """Covers: AC-13 (wrong), REPO-2. No module under blc/ except judge/, and no entry point, imports Ollama."""
    offenders = []
    blc = ROOT / "backend" / "src" / "blc"
    files = [f for f in blc.rglob("*.py") if f.relative_to(blc).parts[0] != "judge"]
    files += list((ROOT / "backend" / "scripts").glob("*.py"))
    assert files
    for f in files:
        if IMPORT_RE.search(f.read_text(encoding="utf-8")):
            offenders.append(str(f.relative_to(ROOT)))
    assert offenders == []


# ---- REPO-3 / REPO-4 / AC-14

@pytest.fixture(scope="module")
def wf():
    yaml = pytest.importorskip("yaml")
    assert WORKFLOW.exists(), f"{WORKFLOW} missing"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(wf):
    return [s for job in (wf.get("jobs") or {}).values() for s in job.get("steps", [])]


def _trigger(wf):
    return wf[True] if True in wf else wf["on"]


def test_no_step_mentions_ollama(wf):
    """Covers: AC-14 (wrong), REPO-3. No step run/uses mentions ollama, case-insensitively."""
    for s in _steps(wf):
        text = f"{s.get('run', '')} {s.get('uses', '')}".lower()
        assert "ollama" not in text, s


def test_ingest_step_has_google_api_key_secret(wf):
    """Covers: AC-14 (right), REPO-3. Some step's env.GOOGLE_API_KEY is the repo secret."""
    assert any(
        (s.get("env") or {}).get("GOOGLE_API_KEY") == "${{ secrets.GOOGLE_API_KEY }}" for s in _steps(wf)
    )


def test_key_step_runs_ingest(wf):
    """Covers: AC-14 (boundary), REPO-3. The step carrying the key is the one that runs ingest.py."""
    keyed = [s for s in _steps(wf) if "GOOGLE_API_KEY" in (s.get("env") or {})]
    assert any("ingest.py" in s.get("run", "") for s in keyed)


def test_deps_installed_without_voice_and_eval(wf):
    """Covers: AC-14 (right), REPO-3; spec 041 AC-5. The poetry install excludes the eval group (the voice group is gone)."""
    installs = [s["run"] for s in _steps(wf) if "run" in s and "poetry install" in s["run"]]
    assert installs
    for run in installs:
        assert "--without" in run and "eval" in run


def test_push_paths_include_llm_and_data(wf):
    """Covers: AC-14 (right), REPO-4. Push paths include data markdown and the llm package; none mention .chroma."""
    paths = _trigger(wf)["push"]["paths"]
    assert "data/**/*.md" in paths
    assert "backend/src/blc/llm/**" in paths
    assert not any(".chroma" in p for p in paths)


def test_spec_036_workflow_contract_still_holds(wf):
    """Covers: AC-14 (boundary), REPO-4. Spec 036 AC-12: main push, dispatch, contents write, concurrency, [skip ci]."""
    trig = _trigger(wf)
    assert "main" in trig["push"]["branches"]
    assert "workflow_dispatch" in trig
    perms = [wf.get("permissions")] + [j.get("permissions") for j in wf["jobs"].values()]
    assert any(isinstance(p, dict) and p.get("contents") == "write" for p in perms)
    concs = [wf.get("concurrency")] + [j.get("concurrency") for j in wf["jobs"].values()]
    assert any(
        isinstance(c, dict) and c.get("group") == "ingest" and c.get("cancel-in-progress") is False for c in concs
    )
    assert any("[skip ci]" in s.get("run", "") for s in _steps(wf))


# ---- REPO-5 / REPO-6 / AC-15

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
    return _compose({"GOOGLE_API_KEY": "dummy-key"})


def test_compose_passes_google_api_key(docker_cfg):
    """Covers: AC-15 (right), REPO-5. Service web env GOOGLE_API_KEY equals the shell value."""
    assert docker_cfg["services"]["web"]["environment"]["GOOGLE_API_KEY"] == "dummy-key"


REMOVED_ENV = ["OLLAMA_HOST"]


def test_compose_has_no_ollama_host(docker_cfg, monkeypatch):
    """Covers: AC-15 (wrong), REPO-5. No OLLAMA_HOST in the web environment, even with a host value set."""
    assert "OLLAMA_HOST" not in docker_cfg["services"]["web"]["environment"]
    monkeypatch.setenv(REMOVED_ENV[0], "http://example:1234")
    other = _compose({"GOOGLE_API_KEY": "dummy-key"}, drop=("GOOGLE_API_KEY", "ANTHROPIC_API_KEY"))
    assert "OLLAMA_HOST" not in other["services"]["web"]["environment"]


def test_compose_port_and_mounts_unchanged(docker_cfg):
    """Covers: AC-15 (boundary), REPO-5. Spec 035: one service, 8000 -> 8000, exactly the data and .chroma mounts."""
    assert set(docker_cfg["services"]) == {"web"}
    web = docker_cfg["services"]["web"]
    assert [(int(p["published"]), int(p["target"])) for p in web["ports"]] == [(8000, 8000)]
    assert sorted(v["target"] for v in web["volumes"]) == ["/app/.chroma", "/app/data"]


def test_dockerfile_install_excludes_voice_and_eval():
    """Covers: AC-15 (right), REPO-6; spec 041 AC-5. Every poetry install in the Dockerfile is --without eval (the voice group is gone)."""
    text = DOCKERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    installs = [ln for ln in text.splitlines() if "poetry install" in ln]
    assert installs
    for ln in installs:
        assert "--without" in ln and "eval" in ln, ln
