"""Layout and size rules for the pull sheet refactor (spec 003: AC-2 to AC-7, EC-1 to EC-3, NFR-4).

Unit tests: only parse files and run small subprocesses; no network, no Ollama, no Chroma.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "scripts" / "pull_sheet.py"
PKG_DIR = ROOT / "src" / "blc" / "pull_sheet"
TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = str(ROOT / "scripts")
SRC_DIR = str(ROOT / "src")

PUBLIC_NAMES = [
    "DEFAULT_RULES_DIR", "EACH", "GALLON", "GUESTS_PER_GALLON", "MENU_FILE", "NOT_ON_MENU",
    "PER_VALUES", "RULES_FILE", "TICK", "UNKNOWN_UNIT",
    "RuleFileError", "BeoError", "Catalog", "load_catalog", "BeoLine", "Beo", "parse_beo",
    "PullLine", "Skipped", "PullSheet", "build_pull_sheet", "format_pull_sheet",
]
PACKAGE_NAMES = PUBLIC_NAMES  # everything except main (revision 1)
CALC_MODULES = ["amounts.py", "cambros.py", "supplies.py", "sheet.py", "output.py"]

BEO_TEXT = (
    "Guest Count: 70\n\n"
    "| Description | Qty | Delivery UOM |\n"
    "|---|---|---|\n"
    "| Fresh-brewed coffee | 2 | Gallon |\n"
)


def _clean_env():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def _py_files(folder):
    return sorted(folder.rglob("*.py"))


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def test_expected_files_exist():
    """Covers: §3 files (right). Entry point, package files and the test setup file exist."""
    assert ENTRY.is_file()
    assert (ROOT / "src" / "blc" / "__init__.py").is_file()
    assert (PKG_DIR / "__init__.py").is_file()
    assert (TESTS_DIR / "conftest.py").is_file()


def test_blc_init_is_empty():
    """Covers: §3 files (boundary). src/blc/__init__.py is empty."""
    assert (ROOT / "src" / "blc" / "__init__.py").read_text(encoding="utf-8").strip() == ""


def test_package_is_split_into_several_modules():
    """Covers: §3 files (right). The implementation is more than one module besides __init__.py."""
    modules = [p for p in PKG_DIR.glob("*.py") if p.name != "__init__.py"]
    assert len(modules) >= 3


def test_ec3_tests_folder_has_no_init():
    """Covers: EC-3 (wrong). tests/pull_sheet/ must not contain __init__.py."""
    assert not (TESTS_DIR / "__init__.py").exists()


def test_ec3_import_resolves_to_entry_point():
    """Covers: EC-3 (right). `import pull_sheet` in tests is the scripts/ entry point, not the test folder."""
    import pull_sheet

    assert Path(pull_sheet.__file__).resolve() == ENTRY.resolve()


# --------------------------------------------------------------------------
# AC-3: entry point
# --------------------------------------------------------------------------
def _entry_tree():
    return ast.parse(ENTRY.read_text(encoding="utf-8"))


def test_ac3_entry_point_at_most_80_lines():
    """Covers: AC-3 (boundary). scripts/pull_sheet.py has at most 80 lines."""
    assert len(ENTRY.read_text(encoding="utf-8").splitlines()) <= 80


def test_ac3_entry_point_has_exactly_one_function_main():
    """Covers: AC-3 (wrong). The only function in the entry point is `main`; no classes, and no lambdas."""
    tree = _entry_tree()
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert [f.name for f in funcs] == ["main"]
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.Lambda))]
    assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == ["main"]


def test_ac3_main_at_most_50_lines():
    """Covers: AC-3 (boundary). `main` in the entry point is at most 50 lines."""
    main_def = next(n for n in _entry_tree().body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assert main_def.end_lineno - main_def.lineno + 1 <= 50


def test_ac3_entry_point_top_level_has_no_logic():
    """Covers: AC-3 (wrong). Top-level statements are only imports, simple assignments (path set-up), the docstring,
    `main`, and `if` statements that check sys.path or __name__; no top-level loops or comprehensions."""
    tree = _entry_tree()
    banned = (ast.For, ast.While, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)
    for stmt in tree.body:
        assert not isinstance(stmt, (ast.For, ast.While, ast.AsyncFor, ast.With, ast.Try)), type(stmt).__name__
        if isinstance(stmt, ast.FunctionDef):
            continue  # main: its body is checked by the size test
        for node in ast.walk(stmt):
            assert not isinstance(node, banned), f"logic at top level: {type(node).__name__}"
        if isinstance(stmt, ast.If):
            test_src = ast.dump(stmt.test)
            assert "sys" in test_src or "__name__" in test_src, "top-level `if` must check sys.path or __name__"


def test_ac3_entry_point_calls_main_when_run_as_script():
    """Covers: AC-3 (right). The entry point ends with an `if __name__ == "__main__"` block that calls main()."""
    text = ENTRY.read_text(encoding="utf-8")
    assert "__main__" in text
    last = _entry_tree().body[-1]
    assert isinstance(last, ast.If) and "__name__" in ast.dump(last.test)
    assert "main" in ast.dump(last)


def test_ac3_entry_point_imports_from_package():
    """Covers: AC-3 (right). The entry point imports from blc.pull_sheet."""
    mods = [n.module for n in _entry_tree().body if isinstance(n, ast.ImportFrom)]
    assert any(m and m.startswith("blc.pull_sheet") for m in mods)


# --------------------------------------------------------------------------
# AC-4: package size
# --------------------------------------------------------------------------
def test_ac4_package_files_exist_to_check():
    """Covers: AC-4 (boundary). The package folder has Python files (so the checks below are not vacuous)."""
    assert len(_py_files(PKG_DIR)) >= 2


@pytest.mark.parametrize("path", _py_files(PKG_DIR), ids=lambda p: p.name)
def test_ac4_file_at_most_250_lines(path):
    """Covers: AC-4 (boundary). Every .py file under src/blc/pull_sheet/ has at most 250 lines."""
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 250


@pytest.mark.parametrize("path", _py_files(PKG_DIR), ids=lambda p: p.name)
def test_ac4_functions_at_most_50_lines(path):
    """Covers: AC-4 (boundary). Every function and method is at most 50 lines."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node.end_lineno - node.lineno + 1
            assert length <= 50, f"{path.name}:{node.name} is {length} lines"


# --------------------------------------------------------------------------
# AC-5: test file size
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", _py_files(TESTS_DIR), ids=lambda p: p.name)
def test_ac5_test_file_at_most_400_lines(path):
    """Covers: AC-5 (boundary). Every file under tests/pull_sheet/ has at most 400 lines."""
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 400


# --------------------------------------------------------------------------
# AC-2 / EC-2: both import paths give the same objects
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", PACKAGE_NAMES)
def test_ac2_same_object_from_both_imports(name):
    """Covers: AC-2 (right). `pull_sheet.X is blc.pull_sheet.X` for every public name except main (incl. ROOT)."""
    import blc.pull_sheet
    import pull_sheet

    assert hasattr(pull_sheet, name), name
    assert hasattr(blc.pull_sheet, name), name
    assert getattr(pull_sheet, name) is getattr(blc.pull_sheet, name)


def test_ac2_root_same_object_from_both_imports():
    """Covers: AC-2 (right). `ROOT` is the same object from both import paths."""
    import blc.pull_sheet
    import pull_sheet

    assert pull_sheet.ROOT is blc.pull_sheet.ROOT


def test_ac2_main_importable_from_entry_point():
    """Covers: AC-2 (right). `main` is importable from pull_sheet and is callable."""
    import pull_sheet

    assert callable(pull_sheet.main)


def test_ac2_package_has_no_main():
    """Covers: AC-2 (wrong). blc.pull_sheet has no attribute `main`, and cli.py does not exist."""
    import blc.pull_sheet

    assert not hasattr(blc.pull_sheet, "main")
    assert not (PKG_DIR / "cli.py").exists()


def test_ac2_main_defined_in_entry_point():
    """Covers: AC-2 (right). `main` is defined in scripts/pull_sheet.py itself."""
    import pull_sheet

    assert pull_sheet.main.__module__ == pull_sheet.__name__
    assert Path(pull_sheet.main.__code__.co_filename).resolve() == ENTRY.resolve()


def test_ec2_except_works_across_both_names(tmp_path, write_dir, MISSING):
    """Covers: EC-2 (right). A RuleFileError raised via `pull_sheet` is caught as `blc.pull_sheet.RuleFileError`,
    and a BeoError the other way round."""
    import blc.pull_sheet as pkg
    import pull_sheet

    with pytest.raises(pkg.RuleFileError):
        pull_sheet.load_catalog(tmp_path / "nope")
    with pytest.raises(pull_sheet.BeoError):
        pkg.parse_beo("no guest count here\n")


@pytest.mark.parametrize("order", ["pkg-first", "script-first", "twice"])
def test_ec2_import_order_gives_same_objects(order):
    """Covers: EC-2 (boundary). Fresh interpreter: any import order leaves one copy of each class."""
    steps = {
        "pkg-first": "import blc.pull_sheet as b; import pull_sheet as s",
        "script-first": "import pull_sheet as s; import blc.pull_sheet as b",
        "twice": "import pull_sheet as s; import importlib; s2 = importlib.import_module('pull_sheet'); "
                 "import blc.pull_sheet as b",
    }[order]
    code = (
        f"import sys; sys.path[:0] = [{SCRIPTS_DIR!r}, {SRC_DIR!r}]; {steps}; "
        "assert s.Catalog is b.Catalog and s.RuleFileError is b.RuleFileError "
        "and s.BeoError is b.BeoError and s.PullSheet is b.PullSheet and s.ROOT is b.ROOT"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=_clean_env())
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# AC-6 / EC-1: CLI runs from any working directory
# --------------------------------------------------------------------------
def _run_cli(cwd, *args):
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        capture_output=True, text=True, cwd=str(cwd), env=_clean_env(),
    )


def test_ac6_cli_from_other_directory_matches_in_process(tmp_path, write_dir, capsys):
    """Covers: AC-6 (right), EC-1 (right). Running the script from an unrelated cwd, with no PYTHONPATH, prints
    the same text as `main` in-process and exits 0."""
    from pull_sheet import main

    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text(BEO_TEXT, encoding="utf-8")
    assert main([str(beo), "--rules", str(base)]) == 0
    expected = capsys.readouterr().out
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = _run_cli(elsewhere, str(beo), "--rules", str(base))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == expected
    assert proc.stdout.startswith("Pull sheet for 70 guests\n")
    assert proc.stderr == ""


def test_ac6_cli_from_project_root(tmp_path, write_dir):
    """Covers: AC-6 (right). Running from the project root also works without extra environment."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text(BEO_TEXT, encoding="utf-8")
    proc = _run_cli(ROOT, str(beo), "--rules", str(base))
    assert proc.returncode == 0, proc.stderr
    assert "Pull sheet for 70 guests" in proc.stdout


def test_ac6_cli_error_exit_code_and_stderr(tmp_path, write_dir):
    """Covers: AC-6 (wrong), EC-1. A missing BEO file from another cwd -> exit 1, one `error: ` line on stderr,
    empty stdout."""
    base = write_dir(tmp_path)
    proc = _run_cli(tmp_path, str(tmp_path / "missing.md"), "--rules", str(base))
    assert proc.returncode == 1
    assert proc.stdout == ""
    lines = proc.stderr.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("error: ")


def test_ac6_cli_usage_error_exit_code(tmp_path):
    """Covers: AC-6 (wrong). No arguments -> argparse exit code 2 when run as a script."""
    proc = _run_cli(tmp_path)
    assert proc.returncode == 2


# --------------------------------------------------------------------------
# AC-7: calculation modules do no I/O (static check)
# --------------------------------------------------------------------------
BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "subprocess", "ssl", "ftplib", "smtplib"}
BANNED_CALLS = {"open", "print", "input"}
BANNED_ATTRS = {"read_text", "read_bytes", "write_text", "write_bytes", "open", "urlopen"}


def _existing_calc_modules():
    return [PKG_DIR / name for name in CALC_MODULES if (PKG_DIR / name).is_file()]


@pytest.mark.parametrize("name", CALC_MODULES)
def test_ac7_calculation_module_does_no_io(name):
    """Covers: AC-7 (wrong). amounts, cambros, supplies, sheet and output never call open/print/input, read or
    write files, or import network modules. A module that does not exist (developer chose other names) is skipped."""
    path = PKG_DIR / name
    if not path.is_file():
        pytest.skip(f"{name} not present (module names are only suggested)")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in BANNED_IMPORTS, (name, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in BANNED_IMPORTS, (name, node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in BANNED_CALLS, (name, func.id)
            elif isinstance(func, ast.Attribute):
                assert func.attr not in BANNED_ATTRS, (name, func.attr)


def test_ac7_at_least_one_calculation_module_checked():
    """Covers: AC-7 (boundary). The static check above is not vacuous: some calculation module exists."""
    assert _existing_calc_modules()
