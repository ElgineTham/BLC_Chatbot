"""Spec 041 section 3.3 / 6.3: dependency and install-file changes (DEPS-1..3)."""

from __future__ import annotations

import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import pytest


def _pyproject(repo):
    with open(repo / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _main_dep_names(repo):
    names = set()
    for spec in _pyproject(repo)["project"]["dependencies"]:
        match = re.match(r"\s*([A-Za-z0-9_.\-]+)", spec)
        names.add(match.group(1).lower())
    return names


def test_no_voice_group(repo):
    """Covers: AC-5 (wrong), DEPS-1. pyproject has no voice dependency group."""
    groups = _pyproject(repo)["tool"]["poetry"].get("group", {})
    assert "voice" not in groups


@pytest.mark.parametrize("name", ["pypdf", "langchain-community", "numpy"])
def test_unused_main_dependency_removed(repo, name):
    """Covers: AC-5 (wrong), DEPS-1. The dropped package is not a main dependency."""
    assert name not in _main_dep_names(repo)


@pytest.mark.parametrize("name", ["faster-whisper", "piper-tts", "sounddevice"])
def test_voice_packages_not_anywhere(repo, name):
    """Covers: AC-5 (wrong), DEPS-1. No voice-only package is listed in any group."""
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert name not in text


def test_eval_group_is_exactly_ollama_pair(repo):
    """Covers: AC-5 (right), DEPS-2. The eval group holds exactly ollama and langchain-ollama."""
    eval_group = _pyproject(repo)["tool"]["poetry"]["group"]["eval"]["dependencies"]
    assert set(eval_group) == {"ollama", "langchain-ollama"}


@pytest.mark.parametrize("name", ["langchain-anthropic", "langchain-google-genai", "fastapi"])
def test_needed_main_dependency_still_present(repo, name):
    """Covers: AC-5 (right), DEPS-2. The live dependencies are still listed."""
    assert name in _main_dep_names(repo)


@pytest.mark.parametrize("rel", ["docker/Dockerfile", ".github/workflows/ingest.yml"])
def test_install_files_skip_eval_group(repo, rel):
    """Covers: AC-5 (right), DEPS-3. The install command uses --without eval."""
    assert "--without eval" in (repo / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", ["docker/Dockerfile", ".github/workflows/ingest.yml"])
def test_install_files_do_not_mention_voice(repo, rel):
    """Covers: AC-5 (wrong), DEPS-3. The install files no longer mention voice."""
    assert "voice" not in (repo / rel).read_text(encoding="utf-8").lower()
