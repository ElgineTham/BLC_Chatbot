# Spec 033: Move the backend into `backend/`

- **Status:** draft
- **Date:** 2026-11-17

## 1. Goal
Make the repo read as **frontend + backend**: all Python code, its entry points and its tests move under `backend/`, and the page stays in `frontend/`. This is a **move only**. No behaviour changes, no renames of modules or functions, and the existing `.chroma/` keeps working without a re-ingest. Project content (`data/`, `evals/`, `docs/`, `logs/`, `.chroma/`) and the Poetry project (`pyproject.toml`, `poetry.lock`, `.venv/`) stay at the repo root. The proof is the test suite: after the move, exactly the same tests pass and fail as before (`docs/specs/033-baseline-failures.txt`).

## 2. Out of scope
- Any change in behaviour, output, wording, module names, function names or signatures.
- Fixing any of the 29 baseline failures/errors.
- The spec 032 carry-overs (Laurel's animation, palette, `summarize_if_long` import, `uvicorn` cap, README web section).
- Old specs (`docs/specs/0NN-*.md`, `024-*` snapshot files): they are records and keep their old paths.
- Moving `data/`, `evals/`, `docs/`, `logs/`, `.chroma/`, `frontend/` or the Poetry files.
- Docker, Gemini, deployment.

## 3. Interface contract
No new names, and no import changes: tests and code keep importing `chat`, `ingest`, `web`, `pull_sheet`, `trace_flow`, `voice_chat` and `blc.*` exactly as today.

**Layout after the move** (from the repo root):
```
backend/
  scripts/      ← was scripts/   (chat.py, ingest.py, pull_sheet.py, trace_flow.py, voice_chat.py, web.py)
  src/blc/      ← was src/blc/   (every package, unchanged inside)
  tests/        ← was tests/     (every test file and helper, same sub-folders)
frontend/       unchanged
data/  evals/  docs/  logs/  .chroma/   unchanged, at the root
pyproject.toml  poetry.lock  README.md  CLAUDE.md   at the root
```
No `scripts/`, `src/` or `tests/` folder is left at the root.

**`pyproject.toml`:** `[tool.pytest.ini_options]` has `testpaths = ["backend/tests"]` and `pythonpath = ["backend/scripts", "backend/src"]`. Everything else in it is unchanged, including the markers and `addopts`.

**Path constants keep their values.** Each one still resolves to the same file or folder at the **repo root** (`REPO_ROOT` = the folder that holds `pyproject.toml`):
| Constant | Resolves to |
|---|---|
| `chat.ROOT`, `ingest.ROOT` | `REPO_ROOT` |
| `chat.CHROMA_DIR`, `ingest.CHROMA_DIR` | `REPO_ROOT / ".chroma"` |
| `ingest.DATA_DIR` | `REPO_ROOT / "data"` |
| `blc.tools.recipe_tools.RECIPES_FILE` | `REPO_ROOT / "data/recipes/recipes.json"` |
| `blc.tools.bev_tools.catalog.DEFAULT_RULES_DIR` | `REPO_ROOT / "data/pull_sheet"` |
| `blc.tools.food_tools.FOOD_RULES_FILE` | `REPO_ROOT / "data/pull_sheet/rules/food.json"` |
| the page the web app serves (spec 032) | files in `REPO_ROOT / "frontend"` |

**Commands after the move** (run from the repo root):
```bash
poetry run python backend/scripts/ingest.py
poetry run python backend/scripts/chat.py
poetry run python backend/scripts/web.py
poetry run python backend/scripts/trace_flow.py "Where is the coffee?"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest -m "not integration and not eval"
```

**Who does what in this round:**
1. **Planner, before the agents start:** moves the three folders as-is (`scripts/`, `src/`, `tests/` → `backend/`) and updates `.claude/hooks/agent_guard.py` and the agent instructions so every access limit covers the new paths.
2. **Developer:** makes the code under `backend/scripts/` and `backend/src/` and `pyproject.toml` work in the new place.
3. **Tester:** makes the tests under `backend/tests/` work in the new place, and adds the new LAYOUT and PATHS tests below.

## 4. Inputs and outputs
| Before | After |
|---|---|
| `scripts/<name>.py` | `backend/scripts/<name>.py`, same content except path set-up |
| `src/blc/<pkg>/…` | `backend/src/blc/<pkg>/…`, same content except root/path constants |
| `tests/<feature>/…` | `backend/tests/<feature>/…`, same assertions; only path and folder references change |
| unit suite: 3867 passed, 27 failed, 3 skipped, 2 collection errors | the same set of failing/erroring test IDs (with `tests/` read as `backend/tests/`), plus the new tests passing |

## 5. Acceptance criteria
- **AC-1:** The layout is as §3: `backend/scripts/`, `backend/src/blc/` and `backend/tests/` exist with every file that was in `scripts/`, `src/` and `tests/`. No `scripts/`, `src/` or `tests/` remains at the root. `frontend/`, `data/`, `evals/`, `docs/` and the Poetry files are where they were.
- **AC-2:** `pyproject.toml` has the `testpaths` and `pythonpath` in §3 and is otherwise unchanged. `poetry.lock` is unchanged.
- **AC-3:** Every path constant in §3 resolves to the same place at the repo root as before.
- **AC-4:** The existing `.chroma/` still works without a re-ingest. Retrieval returns chunks whose `source` is still `data/…` (repo-root relative), and `ingest.py` run on unchanged `data/` adds or re-embeds nothing (incremental by mtime, as today). *(integration)*
- **AC-5:** Imports are unchanged. `import chat`, `import ingest`, `import web`, `import pull_sheet`, `import trace_flow`, `import voice_chat` and `import blc.flow` work under pytest. Every entry point still runs when started directly with `poetry run python backend/scripts/<name>.py`, from the repo root.
- **AC-6:** **Same results.** The unit suite (`-m "not integration and not eval"`) has exactly the failing and erroring test IDs in `docs/specs/033-baseline-failures.txt` (with `tests/` read as `backend/tests/`). No new failure, no baseline failure silently fixed or removed, and no test deleted or skipped to get there. The new tests of §6 pass.
- **AC-7** *(manual)*: **Move only.** `git diff -M` shows every file as a rename. Content changes in code are limited to path set-up (`sys.path` lines and root/path constants). Content changes in existing tests are limited to path and folder references (repo-root lookups, `scripts`, `src` or `tests` folder names). No assertion, expected value or test name changes.
- **AC-8** *(manual)*: `CLAUDE.md`, `README.md`, `.claude/agents/*.md` and `.claude/hooks/agent_guard.py` name the new paths. The guard denies the same access as before, applied to the new paths: the tester and test-evaluator can't read `backend/scripts/`, `backend/src/` or `frontend/`; the developer can't read or write `backend/tests/` or `evals/`. *(Planner's job.)*

## 6. Test cases
New tests go in `backend/tests/layout/test_layout.py`. `REPO_ROOT` in tests = the folder that holds `pyproject.toml`.

### 6.1 LAYOUT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LAYOUT-1 | look at `REPO_ROOT` | `backend/scripts`, `backend/src/blc`, `backend/tests`, `frontend`, `data`, `evals`, `docs` exist; `scripts`, `src`, `tests` don't | AC-1 |
| LAYOUT-2 | `backend/scripts/` | holds `chat.py`, `ingest.py`, `pull_sheet.py`, `trace_flow.py`, `voice_chat.py`, `web.py` | AC-1 |
| LAYOUT-3 | read `pyproject.toml` | `testpaths == ["backend/tests"]`, `pythonpath == ["backend/scripts", "backend/src"]`, markers unchanged | AC-2 |
| LAYOUT-4 | import each of `chat`, `ingest`, `web`, `pull_sheet`, `trace_flow`, `voice_chat`, `blc.flow` | all import; each module's `__file__` is under `REPO_ROOT / "backend"` | AC-5 |

### 6.2 PATHS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PATHS-1 | `chat.ROOT`, `ingest.ROOT` | `== REPO_ROOT` | AC-3 |
| PATHS-2 | `chat.CHROMA_DIR`, `ingest.CHROMA_DIR`, `ingest.DATA_DIR` | `REPO_ROOT/.chroma`, `REPO_ROOT/.chroma`, `REPO_ROOT/data` | AC-3 |
| PATHS-3 | `RECIPES_FILE`, `DEFAULT_RULES_DIR`, `FOOD_RULES_FILE` | the §3 paths under `REPO_ROOT` | AC-3 |
| PATHS-4 | `create_app(fake)` from `web`; `GET /`, `GET /assets/blc_logo.png` | 200; bytes equal `REPO_ROOT/frontend/index.html` and `REPO_ROOT/frontend/assets/blc_logo.png` | AC-3 |
| PATHS-5 *(integration)* | real `build_domain_store()`; retrieve "Where is the coffee kept?" | ≥1 chunk; every `source` starts with `data/` | AC-4 |

### 6.3 SUITE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| SUITE-1 | the whole unit suite after the move | failing/erroring IDs == baseline file (`tests/` → `backend/tests/`); new LAYOUT/PATHS tests pass | AC-6 |
| SUITE-2 *(manual)* | `git diff -M --stat` and the content diffs | only renames plus the path edits AC-7 allows | AC-7 |
| SUITE-3 *(manual)* | `poetry run python backend/scripts/ingest.py` on unchanged `data/`; `backend/scripts/web.py` starts | nothing re-embedded; server serves the page | AC-4, AC-5 |
