# Spec 003: Split the pull sheet into modules

- **Status:** approved (revision 1)
- **Date:** 2026-11-10

## 1. Goal
Spec 002's pull sheet works, but it is one 800-line file (`scripts/pull_sheet.py`) with one 2,200-line test file. This spec reorganises both into small, single-purpose files following the **Code structure** rules in `CLAUDE.md`: a thin entry point in `scripts/`, the feature code in `src/blc/pull_sheet/`, and tests grouped by spec area in `tests/pull_sheet/` with one shared setup file. Behaviour does not change at all: every spec 002 test must still pass.

## 2. Out of scope
- Any change in behaviour, output, error messages or the data file formats. Spec 002 (revision 1) stays the source of truth for what the program does.
- New features, new tests for new behaviour, or extra coverage beyond moving the existing tests.
- Reorganising other features (`chat.py`, `voice_chat.py`, `ingest.py`) or their tests.
- Changes to `data/pull_sheet/`.

## 3. Interface contract
The public interface is exactly spec 002's §3 (all constants, `RuleFileError`, `BeoError`, `Catalog`, `load_catalog`, `BeoLine`, `Beo`, `parse_beo`, `PullLine`, `Skipped`, `PullSheet`, `build_pull_sheet`, `format_pull_sheet`, `main`), with the same names, signatures, values and behaviour. All of it is importable from the entry point, and everything **except `main`** is also importable from the feature package:

```python
# tests and existing callers (scripts/ is on the path)
from pull_sheet import load_catalog, parse_beo, build_pull_sheet, format_pull_sheet, main  # etc.

# the feature package (src/ is on the path): everything except main
from blc.pull_sheet import load_catalog, parse_beo, build_pull_sheet, format_pull_sheet  # etc.
```

Names available from both give the **same objects** (e.g. `pull_sheet.Catalog is blc.pull_sheet.Catalog`, `pull_sheet.ROOT is blc.pull_sheet.ROOT`). `main` is defined in `scripts/pull_sheet.py` itself and is **not** part of `blc.pull_sheet` (revision 1).

CLI: unchanged, `poetry run python scripts/pull_sheet.py BEO_FILE [--rules DIR]`, same output and exit codes. It must work when run directly from the project root, without `poetry install` or extra environment variables.

Files:
- `scripts/pull_sheet.py`: the entry point and the CLI. It contains only:
  1. **path set-up**: computing the `src/` path from its own file location and adding it to `sys.path`, optionally guarded by a check that it isn't there already (e.g. `if _SRC not in sys.path:`);
  2. **imports and the re-export** of the public interface from `blc.pull_sheet`;
  3. **`main(argv=None) -> int`**, the CLI of spec 002 (argument parsing, reading the BEO file, calling `load_catalog`, `parse_beo`, `build_pull_sheet` and `format_pull_sheet`, printing, error handling and exit codes);
  4. `if __name__ == "__main__": sys.exit(main())`.

  No other functions, classes or logic: anything that computes or validates lives in the package.
- `src/blc/__init__.py`: empty.
- `src/blc/pull_sheet/__init__.py`: exposes the public interface.
- `src/blc/pull_sheet/`: the implementation, split into modules with one job each. Suggested split (the developer may adjust names or add small helper modules, but must keep the separation of jobs):

  | Module | Job |
  |---|---|
  | `errors.py` | `RuleFileError`, `BeoError` |
  | `text.py` | name normalisation, number parsing, guests → gallons rounding |
  | `json_checks.py` | reading JSON files and the shared validation helpers (types, unknown keys, entry locations) |
  | `menu.py` | validating `menu/beverages.json` |
  | `rules.py` | validating `rules/beverages.json` |
  | `catalog.py` | `Catalog`, `load_catalog` |
  | `beo.py` | `BeoLine`, `Beo`, `parse_beo` (markdown table reading) |
  | `amounts.py` | matching BEO lines, packages, placeholders, item order, cup count base |
  | `cambros.py` | cambro choice |
  | `supplies.py` | supply contributions, extras tiers, pull once |
  | `sheet.py` | `PullLine`, `Skipped`, `PullSheet`, `build_pull_sheet` |
  | `output.py` | `format_pull_sheet` |

- `pyproject.toml`: `[tool.pytest.ini_options]` gets `pythonpath = ["scripts", "src"]` and `addopts = "--import-mode=importlib"` (so test files in different feature folders may share base names like `test_cli.py`). No new dependencies.
- Tests: `tests/test_pull_sheet.py` is split into `tests/pull_sheet/`:

  | File | Contents (spec 002 sections) |
  |---|---|
  | `conftest.py` | shared fixtures and helpers: writing menu and rules files to `tmp_path`, sample catalogs, sample BEOs |
  | `test_menu_validation.py` | menu loading and errors (§4.3 menu, EC-25, EC-33, EC-35) |
  | `test_rules_validation.py` | rules loading and errors (§4.3 rules, EC-25a, EC-25b, EC-26, EC-29) |
  | `test_beo_parsing.py` | `parse_beo`, `BeoError.line` (§4.1, §4.4, EC-13, EC-27, EC-34) |
  | `test_amounts.py` | packages, placeholders, guests → gallons, own vs package (§4.5 steps 1–2, EC-1 to EC-13) |
  | `test_cambros.py` | cambros (§4.5 step 3, EC-14 to EC-16) |
  | `test_supplies.py` | add-ons, supplies, extras, cup count base, pull once, ticks, item order (§4.5 steps 4–7, EC-17 to EC-24, EC-30 to EC-32) |
  | `test_output.py` | `format_pull_sheet` (§4.6, EC-28) |
  | `test_cli.py` | `main` (AC-12) |
  | `test_determinism.py` | AC-13, NFR-1, NFR-2, NFR-4, contract constants |

  A row's contents may be split across several `test_<area>.py` files when that is needed to keep each file within 400 lines (AC-5), e.g. `test_supplies.py`, `test_supply_combining.py` and `test_cup_count_and_order.py`. The folder must **not** contain `__init__.py`. After the move, `tests/test_pull_sheet.py` is deleted (by the user; agents cannot delete files) and must contain no tests the new files lack.
- A new test `tests/pull_sheet/test_structure.py` checks the layout and size rules (AC-3 to AC-5).

## 4. Inputs and outputs
| Input | Output / effect |
|---|---|
| Any input accepted by spec 002 | Exactly the same result, output text, errors and exit codes as before |
| `from pull_sheet import X` / `from blc.pull_sheet import X` | The same object `X` |
| `poetry run python scripts/pull_sheet.py BEO_FILE` | Same stdout, stderr and exit code as before |

## 5. Edge cases
- EC-1: Running `python scripts/pull_sheet.py` from a directory other than the project root still finds the `blc` package (the entry point locates `src/` relative to its own file, not the working directory).
- EC-2: Importing `pull_sheet` twice, or importing `blc.pull_sheet` first and `pull_sheet` second, gives the same objects (no duplicate module copies, so `isinstance` and `except RuleFileError` work across both names).
- EC-3: `tests/pull_sheet/` has no `__init__.py`, so `import pull_sheet` in tests always resolves to the entry point, never to the test folder.
- EC-4: A test that used a helper defined in the old test file still works, because the helper now lives in `tests/pull_sheet/conftest.py` (as a fixture or a plain function imported via a fixture).

## 6. Acceptance criteria
- **AC-1:** Every test from the old `tests/test_pull_sheet.py` exists in `tests/pull_sheet/` with the **same assertions** (moved, not weakened or dropped), and all of them pass against the refactored code. The total number of collected spec 002 tests is the same as before the move (332), plus the new structure tests.
- **AC-2:** The public interface is importable from `pull_sheet`; every name except `main` is also importable from `blc.pull_sheet`, and both give identical objects, including `ROOT` (EC-2). `blc.pull_sheet` has no attribute `main`, and there is no `src/blc/pull_sheet/cli.py`.
- **AC-3:** `scripts/pull_sheet.py` is at most 80 lines and contains only the four parts listed in §3: path set-up (an `if` checking `sys.path` is allowed), imports and re-exports, exactly one function `main`, and the `if __name__ == "__main__"` block. No other functions, classes or top-level `if`, loop or comprehension. `main` is at most 50 lines.
- **AC-4:** Every `.py` file under `src/blc/pull_sheet/` is at most 250 lines, and every function in it is at most 50 lines (checked by parsing the files, e.g. with `ast`).
- **AC-5:** Every test file under `tests/pull_sheet/` is at most 400 lines.
- **AC-6:** The CLI behaves exactly as in spec 002 (AC-12 there), including when run from another working directory (EC-1).
- **AC-7:** Calculation modules (`amounts.py`, `cambros.py`, `supplies.py`, `sheet.py`, `output.py`) do no file reading, printing or network access.

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No behaviour change: the moved spec 002 tests all pass. | unit |
| NFR-2 | Standard library only; no new dependencies. | manual (review `pyproject.toml`) |
| NFR-3 | Calculation modules are free of I/O (AC-7). | manual (code review) |
| NFR-4 | Layout and size rules hold (AC-3 to AC-5). | unit (`test_structure.py`) |

## Revision history
- **Revision 1 (2026-11-10)**, after the first test run:
  - `main()` (the CLI) moves from `src/blc/pull_sheet/cli.py` into `scripts/pull_sheet.py`; `cli.py` is removed and `blc.pull_sheet` no longer exports `main` (§3, AC-2).
  - §3 now defines exactly what the entry point may contain, including a guarded `sys.path` insert as part of path set-up; AC-3 raises the entry point limit to 80 lines with `main` at most 50 (AC-3).
  - The same-object check includes `ROOT` (AC-2).
  - Code and tests: update the existing files in place to match. The structure tests for AC-2 and AC-3 must follow the new wording; all other moved tests stay unchanged.
