"""Spec 033 section 6.1 LAYOUT: where the folders and files are, pyproject settings, imports."""
import importlib
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ENTRY_POINTS = ["chat.py", "ingest.py", "pull_sheet.py", "web.py"]  # spec 041: trace_flow, voice_chat removed
MODULES = ["chat", "ingest", "web", "pull_sheet", "blc.flow"]


def _pytest_options(repo_root):
    with open(repo_root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["tool"]["pytest"]["ini_options"]


# ---------------------------------------------------------------- LAYOUT-1


@pytest.mark.parametrize(
    "rel", ["backend/scripts", "backend/src/blc", "backend/tests", "frontend", "data", "evals", "docs"]
)
def test_new_folders_exist(repo_root, rel):
    """Covers: LAYOUT-1, AC-1 (right). Each folder the layout names exists under the repo root."""
    assert (repo_root / rel).is_dir(), rel


@pytest.mark.parametrize("old", ["scripts", "src", "tests"])
def test_old_root_folders_are_gone(repo_root, old):
    """Covers: LAYOUT-1, AC-1 (wrong). No scripts/, src/ or tests/ folder is left at the repo root."""
    assert not (repo_root / old).exists(), old


@pytest.mark.parametrize("name", ["pyproject.toml", "poetry.lock", "README.md", "CLAUDE.md"])
def test_root_files_stay_at_root(repo_root, name):
    """Covers: LAYOUT-1, AC-1 (right). Poetry files and docs stay at the repo root."""
    assert (repo_root / name).is_file(), name


@pytest.mark.parametrize("name", ["pyproject.toml", "poetry.lock"])
def test_poetry_files_not_copied_into_backend(repo_root, name):
    """Covers: LAYOUT-1, AC-1 (boundary). The Poetry project is not duplicated under backend/."""
    assert not (repo_root / "backend" / name).exists(), name


def test_backend_holds_only_the_three_folders_of_code(repo_root):
    """Covers: LAYOUT-1, AC-1 (boundary). backend/ has scripts, src and tests as sub-folders (extras are caches only)."""
    names = {p.name for p in (repo_root / "backend").iterdir() if p.is_dir()}
    assert {"scripts", "src", "tests"} <= names
    extras = {n for n in names - {"scripts", "src", "tests"} if not n.startswith(".") and n != "__pycache__"}
    assert extras == set(), extras


def test_blc_packages_are_under_backend_src(repo_root):
    """Covers: LAYOUT-1, AC-1 (right). backend/src/blc is a package and holds the feature packages."""
    blc = repo_root / "backend" / "src" / "blc"
    assert (blc / "__init__.py").is_file()
    for pkg in ("flow", "tools", "pull_sheet"):
        assert (blc / pkg / "__init__.py").is_file(), pkg


def test_tests_moved_with_their_subfolders(repo_root):
    """Covers: LAYOUT-1, AC-1 (right). Existing test sub-folders now live under backend/tests/."""
    for sub in ("pull_sheet", "web"):
        assert (repo_root / "backend" / "tests" / sub).is_dir(), sub


# ---------------------------------------------------------------- LAYOUT-2


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_entry_point_present(repo_root, name):
    """Covers: LAYOUT-2, AC-1 (right). Each entry point is in backend/scripts/."""
    assert (repo_root / "backend" / "scripts" / name).is_file(), name


def test_entry_point_missing_name_is_not_there(repo_root):
    """Covers: LAYOUT-2, AC-1 (wrong). A name that is not an entry point is not in backend/scripts/ (guards the check)."""
    assert not (repo_root / "backend" / "scripts" / "not_an_entry_point.py").exists()


# ---------------------------------------------------------------- LAYOUT-3


def test_pytest_testpaths(repo_root):
    """Covers: LAYOUT-3, AC-2 (right). testpaths is exactly ["backend/tests"]."""
    assert _pytest_options(repo_root)["testpaths"] == ["backend/tests"]


def test_pytest_pythonpath(repo_root):
    """Covers: LAYOUT-3, AC-2 (right). pythonpath is exactly ["backend/scripts", "backend/src"], in that order."""
    assert _pytest_options(repo_root)["pythonpath"] == ["backend/scripts", "backend/src"]


def test_pytest_old_paths_not_configured(repo_root):
    """Covers: LAYOUT-3, AC-2 (wrong). The old root-level paths no longer appear in testpaths or pythonpath."""
    opts = _pytest_options(repo_root)
    for old in ("tests", "scripts", "src"):
        assert old not in opts["testpaths"]
        assert old not in opts["pythonpath"]


def test_poetry_package_mode_unchanged(repo_root):
    """Covers: LAYOUT-3, AC-2 (boundary). The rest of pyproject.toml is untouched: package-mode is still false."""
    with open(repo_root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["poetry"]["package-mode"] is False
    assert data["project"]["name"] == "blc-chatbot"


# ---------------------------------------------------------------- LAYOUT-4


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_from_backend(repo_root, name):
    """Covers: LAYOUT-4, AC-5 (right). The module imports by its old name and its file is under <repo>/backend."""
    mod = importlib.import_module(name)
    f = Path(mod.__file__).resolve()
    backend = (repo_root / "backend").resolve()
    assert backend in f.parents, f


@pytest.mark.parametrize("name", ["chat", "ingest", "web", "pull_sheet"])
def test_entry_module_is_the_backend_scripts_file(repo_root, name):
    """Covers: LAYOUT-4, AC-5 (boundary). The entry-point module resolves to backend/scripts/<name>.py exactly."""
    mod = importlib.import_module(name)
    assert Path(mod.__file__).resolve() == (repo_root / "backend" / "scripts" / f"{name}.py").resolve()


def test_blc_is_from_backend_src(repo_root):
    """Covers: LAYOUT-4, AC-5 (boundary). blc resolves to backend/src/blc."""
    blc = importlib.import_module("blc")
    assert Path(blc.__file__).resolve().parent == (repo_root / "backend" / "src" / "blc").resolve()


def test_unknown_module_does_not_import():
    """Covers: LAYOUT-4, AC-5 (wrong). The old pre-move name pattern is not an importable module (guards the import check)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("blc_not_a_module")
