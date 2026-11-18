"""Spec 036 section 6.3: .gitignore rules and the ingest workflow file."""

from __future__ import annotations

import subprocess

import pytest
from ci_helpers import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "ingest.yml"


def _ignored(path: str) -> bool:
    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        ".chroma/chroma.sqlite3",
        "data/x.md",
        "data/a/b/c.md",
        "data/recipes/pasta.md",
    ],
)
def test_committed_paths_not_ignored(path):
    """Covers: AC-11 (right), REPO-1. Chroma sqlite and any data markdown are not ignored."""
    assert not _ignored(path)


@pytest.mark.parametrize(
    "path",
    [
        "data/recipes/recipes.json",
        "data/pull_sheet/rules/food.json",
        "data/pull_sheet/examples/IMG_1512.jpg",
        "data/x.pdf",
        "data/a/b/c.txt",
        ".env",
        ".venv/bin/python",
        "logs/a.log",
    ],
)
def test_other_paths_still_ignored(path):
    """Covers: AC-11 (wrong), REPO-2. JSON, photos, other data files, .env, .venv and logs stay ignored."""
    assert _ignored(path)


def test_md_lookalike_suffix_still_ignored():
    """Covers: AC-11 (boundary). A non-md file named like markdown (x.md.bak) stays ignored."""
    assert _ignored("data/x.md.bak")


@pytest.fixture(scope="module")
def wf():
    yaml = pytest.importorskip("yaml")
    assert WORKFLOW.exists(), f"{WORKFLOW} missing"
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _triggers(wf):
    # PyYAML loads the bare `on:` key as boolean True.
    return wf[True] if True in wf else wf["on"]


def _blocks(wf, key):
    """Top-level value for key, plus each job's value."""
    out = []
    if key in wf:
        out.append(wf[key])
    for job in (wf.get("jobs") or {}).values():
        if isinstance(job, dict) and key in job:
            out.append(job[key])
    return out


def test_workflow_push_main_with_md_paths(wf):
    """Covers: AC-12 (right), REPO-3. Push on main, paths include data/**/*.md, none mention .chroma."""
    push = _triggers(wf)["push"]
    assert "main" in push["branches"]
    paths = push["paths"]
    assert "data/**/*.md" in paths
    assert not any(".chroma" in p for p in paths)


def test_workflow_dispatch_present(wf):
    """Covers: AC-12 (right), REPO-3. workflow_dispatch trigger exists."""
    assert "workflow_dispatch" in _triggers(wf)


def test_workflow_does_not_trigger_on_chroma_or_other_events(wf):
    """Covers: AC-12 (wrong), REPO-3. No trigger keyed on pull_request/schedule that could loop on .chroma."""
    trig = _triggers(wf)
    assert set(trig) <= {"push", "workflow_dispatch"}


def test_workflow_permissions_contents_write(wf):
    """Covers: AC-12 (right), REPO-4. contents: write."""
    perms = _blocks(wf, "permissions")
    assert perms, "no permissions block"
    assert any(isinstance(p, dict) and p.get("contents") == "write" for p in perms)


def test_workflow_concurrency_group_ingest_no_cancel(wf):
    """Covers: AC-12 (right), REPO-4. group 'ingest' and cancel-in-progress exactly False."""
    conc = _blocks(wf, "concurrency")
    assert conc, "no concurrency block"
    assert any(
        isinstance(c, dict) and c.get("group") == "ingest" and c.get("cancel-in-progress") is False
        for c in conc
    )


def test_workflow_commit_step_has_skip_ci(wf):
    """Covers: AC-12 (right), REPO-5. Some step's run command contains [skip ci]."""
    runs = []
    for job in (wf.get("jobs") or {}).values():
        for step in job.get("steps", []):
            if "run" in step:
                runs.append(step["run"])
    assert runs
    assert any("[skip ci]" in r for r in runs)
