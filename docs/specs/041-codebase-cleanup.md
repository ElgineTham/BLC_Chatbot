# Spec 041: Codebase cleanup (retire the router flow, voice chat and stale tests)

- **Status:** done (closed by the user on 2026-11-18). Verified: unit layer 0 failed / 0 errors / 2909 passed (baseline 78 failed, 4304 passed, 2 errors); spec 041 cleanup tests 168/168; live `claude_chat/test_live.py` 9/9; AC-5 `poetry check --lock` OK; AC-9 diff is deletions only; AC-10 `.py` lines scripts 1538→531, src 5386→4730, tests 35125→24677 (includes uncommitted spec 040 additions). Planner deletions of §2 docs files and doc updates done. Lost coverage (accepted): router-flow answer/grounding evals, `BEV_TOOL` schema tests, pytest marker check, retrieval cases `peach-juice-partial`/`mango-juice-partial` (TOP_K follow-up still open)
- **Date:** 2026-11-18

## 1. Goal
The live chat (`chat.py main()`, `web.py`) runs the planned flow (`blc.flow.run_planned_turn`, spec 019). The older router flow (spec 011: `chat.run_turn` / `answer_turn`, `blc.router`, `blc.trace`, the tool step's argument check) is kept alive only by `trace_flow.py` and `voice_chat.py`. This spec deletes both entry points, the router flow, the code only it used, unused dependencies, and every test for removed code. It also deletes the unit tests that already fail (Appendix A), as decided with the user. The live chat must behave exactly as before.

## 2. Out of scope
- Any change in behaviour of `chat.py main()`, `web.py`, `ingest.py`, `pull_sheet.py`, the planner, the planned flow, the tools' calculations or the frontend.
- Merging duplicate code (repeated `ROOT` paths, normalisers, tool-name strings, `count_tokens` in `ingest.py`). That is refactoring, for a later spec.
- Moving `blc/tool_step/numbers.py` into `blc/flow/`; renaming or regrouping test folders; merging `tests/gemini_migration/` with `tests/claude_chat/`.
- Removing public constants that tests compare against (`FLOW_NODES`, `PLAN_ROUTES`, `DOMAINS`, `*_STATUSES`, `NAPKIN_ITEMS`, `pull_sheet` `ROOT`), the eval judge (`blc/judge`) and the `eval` dependency group.
- Rebuilding a stage tracer for the planned flow (possible later spec).
- Fixing the tests in Appendix A: they are deleted, not repaired.
- **Whole-file test deletions (one-off exception, as in spec 033; decided with the user after round 1):** the tester has no shell, so the planner deletes whole test files and folders and nothing else in `backend/tests/`. Before the tester runs, the planner deletes the paths named in AC-6 and the two whole files of Appendix A. The tester makes every in-file edit (removing single tests, cases, assertions, fixtures and helpers; `web_helpers.py`). For any **other** test file that must go entirely, the tester does not edit it but lists its path under a heading **"Files to delete"** in its report; the planner deletes exactly those.
- **Planner-owned (not developer, not tester):** deleting `docs/specs/024-cli-baseline/`, `docs/specs/024-make-snapshot.py`, `docs/specs/024-recipe-snapshot.jsonl`, `docs/specs/024-baseline-failures.txt`, `docs/specs/033-baseline-failures.txt` and `docs/specs/032-assets/`; updating `CLAUDE.md`, `README.md` and `.claude/agents/*.md`. Done after the round.

## 3. Interface contract

### 3.1 Removed (must not exist afterwards)
Files and packages:
- `backend/scripts/voice_chat.py`, `backend/scripts/trace_flow.py`
- `backend/src/blc/router/` (whole package), `backend/src/blc/trace/` (whole package)
- `backend/src/blc/tool_step/check.py`
- `backend/src/blc/tools/food_tools/tool.py`

Names (`AttributeError` / `ImportError` when accessed):
- `chat`: `run_turn`, `answer_turn`, `run_stages`, `run_part`, `run_part_with_tool`, `run_tool_step`, `run_tool_call`, `run_tool_round`, `first_response`, `requested_calls`, `is_failed_result`, `part_tool_name`, `tool_step_messages`, `history_messages`, `format_tool_results`, `format_labelled_parts`, `build_final_messages`, `unknown_retrieval_reply`, `format_context`, `format_history`, `clean_question`, `log_stage`, `retrieval_stage`, `tool_stage`, `ToolCallRecord`, `PartResult`, `StepOutcome`, `TurnResult`, `CHAT_TOOLS`, `MAX_TOOL_ROUNDS`, `TOOL_LIMIT_REPLY`, `UNKNOWN_TOOL_RESULT`, `FAILED_RESULT_PREFIXES`, `TOOL_REMINDER`, `TOOL_PROMPT`, `RECIPE_TOOL_PROMPT`, `PART_INSTRUCTION`, `ANSWER_PROMPT`, `TOOL_PROMPTS`, `SUMMARIZE_PROMPT`, `count_tokens`, `history_tokens`, `summarize_history`, `CHARS_PER_TOKEN`, `FLOW_LOGGER`
- `blc.tool_step`: `check_arguments`, `REJECTED_PREFIX`
- `blc.tools.bev_tools`: `BEV_TOOL`, `make_bev_tool`; module `blc.tools.bev_tools.tool` no longer has `BevTool`, `make_bev_tool`, `BEV_TOOL`, `BEV_TOOL_DESCRIPTION`
- `blc.tools.food_tools`: `FOOD_TOOL`, `make_food_tool`; module `blc.tools.food_tools.tool` does not exist

### 3.2 Kept (must still import and behave as their own specs say)
- `chat`: `main`, `start_stack`, `build_store`, `build_domain_store`, `retrieve`, `is_exit_utterance`, `normalize_utterance`, `ROOT`, `CHROMA_DIR`, `COLLECTION_NAME`, `TOP_K`, `EXIT_COMMANDS`, `EXIT_FILLERS`, `APOSTROPHES`, `CHAT_TEMPERATURE`, and the re-exports `run_planned_turn`, `summarize_if_long`, `HISTORY_TOKEN_LIMIT`, `check_store_model`, `StoreModelMismatchError`, `CHAT_MODEL`, `EMBED_MODEL`, `CHAT_API_KEY_ENV`, `MissingApiKeyError`, `build_chat_model`, `build_embeddings`, `load_catalog`, `RuleFileError`. Signatures unchanged.
- `web`, `ingest`, `pull_sheet` entry points: unchanged public API.
- `blc.tool_step.numbers`: `numbers_in`, `as_number`, `ALWAYS_ACCEPTED`, `WORD_NUMBERS` (unchanged).
- `blc.tools.bev_tools.tool`: `BEV_SCHEMA`, `ITEM_DESCRIPTION`, `DRINKS_DESCRIPTION`, `GALLONS_DESCRIPTION`, `GUESTS_DESCRIPTION`; `blc.tools.bev_tools`: every other name in its `__all__`.
- `blc.tools.recipe_tools`: `RECIPE_TOOL`, `make_recipe_tool` (the planner uses them).
- `blc.tools.food_tools`: every name in its `__all__` except the two removed.
- `blc.planner`, `blc.flow`, `blc.retrieval`, `blc.history`, `blc.ingest`, `blc.llm`, `blc.web`, `blc.pull_sheet`, `blc.judge`: unchanged.

### 3.3 Files
- `pyproject.toml`: no `voice` dependency group; main dependencies no longer list `pypdf`, `langchain-community`, `numpy`. Everything else unchanged (the `eval` group stays `ollama` + `langchain-ollama`).
- `poetry.lock`: regenerated to match.
- `docker/Dockerfile` and `.github/workflows/ingest.yml`: install with `--without eval` (no `voice`).

## 4. Inputs and outputs
| Input | Output / effect |
|---|---|
| `import chat` / `import web` / `import ingest` / `import pull_sheet` | succeeds, no error |
| `import voice_chat` / `import trace_flow` / `import blc.router` / `import blc.trace` / `import blc.tool_step.check` / `import blc.tools.food_tools.tool` | `ModuleNotFoundError` |
| `from blc.tool_step.numbers import numbers_in` | works; `numbers_in("two cambros for 30 guests")` gives the same result as before |
| `chat.run_turn` (any removed name of §3.1) | `AttributeError` |
| unit layer `-m "not integration and not eval"` | 0 failed, 0 collection errors |

## 5. Acceptance criteria
- **AC-1 (files removed):** every file and package of §3.1 is gone.
- **AC-2 (names removed):** every name of §3.1 raises `AttributeError` / `ImportError`.
- **AC-3 (names kept):** every name of §3.2 imports; the spec 039 and 040 suites (`tests/claude_chat/`, `tests/new_recipes/`) still pass apart from tests deleted under AC-6.
- **AC-4 (no dangling references):** no `.py` file under `backend/`, nor `docker/` or `.github/`, imports or names `voice_chat`, `trace_flow`, `blc.router`, `blc.trace`, `blc.tool_step.check` or `food_tools.tool`; no test imports a removed name of §3.1, except negative tests that check it is gone.
- **AC-5 (dependencies):** `pyproject.toml` matches §3.3; `Dockerfile` and `ingest.yml` contain `--without eval` and no `voice`. *(manual: planner runs `poetry check --lock`)*
- **AC-6 (stale tests deleted):** every test whose only purpose is removed code is deleted (at least `tests/router/`, `tests/flow/`, `tests/tool_calling/`, `tests/tool_step/test_tool_step_check.py`, `tests/tool_step/test_tool_step_eval.py`, `tests/test_voice_io.py`, `tests/test_voice_io_answer_turn.py`, `tests/gemini_migration/test_router.py`); tests that only partly use removed code lose just those tests or assertions; every test in Appendix A is deleted. Fixtures and helpers left unused by the deletions are removed (e.g. Ollama-only probes). Because the planner deletes the `docs/specs/` files listed in §2, no test may read them any more: the `standalone_tools/test_same.py` case that reads `024-cli-baseline/` is deleted, and `tests/web/web_helpers.py` takes the logo from `frontend/assets/blc_logo.png` (same bytes) instead of `docs/specs/032-assets/`.
- **AC-7 (cleanup guard):** `tests/cleanup/test_removed_names.py` (spec 014) is replaced by tests for this spec's §3.1 and §3.2; names spec 014 kept that this spec removes are no longer required.
- **AC-8 (suite green):** the unit layer (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest -m "not integration and not eval"`) has **0 failures and 0 collection errors**. *(implementation-evaluator reports before/after counts; baseline: 78 failed, 4304 passed, 2 errors)*
- **AC-9 (behaviour unchanged):** no live module of §3.2 changes behaviour; the developer only deletes code, deletes imports of deleted code, and edits the files of §3.3. *(manual: planner reads the diff)*
- **AC-10 (smaller):** lines of Python under `backend/` go down; the implementation-evaluator reports before/after line counts for `backend/scripts/`, `backend/src/` and `backend/tests/`. *(manual)*
- **AC-11 (live smoke):** with API keys present, the spec 039 live tests (`tests/claude_chat/test_live.py`, minus any router test deleted under AC-6) pass. *(integration)*

## 6. Test cases

### 6.1 REMOVED
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REMOVED-1 | each file path of §3.1 | does not exist | AC-1 |
| REMOVED-2 | `import voice_chat`, `trace_flow`, `blc.router`, `blc.trace`, `blc.tool_step.check`, `blc.tools.food_tools.tool` | `ModuleNotFoundError` | AC-1 |
| REMOVED-3 | each removed `chat` name of §3.1 (parametrised) | `hasattr(chat, name)` is False | AC-2 |
| REMOVED-4 | `blc.tool_step.check_arguments`, `REJECTED_PREFIX` | absent | AC-2 |
| REMOVED-5 | `blc.tools.bev_tools.BEV_TOOL`, `make_bev_tool`; `blc.tools.food_tools.FOOD_TOOL`, `make_food_tool` | `AttributeError` | AC-2 |
| REMOVED-6 | text of every `.py` under `backend/scripts`, `backend/src`, and `docker/Dockerfile`, `.github/workflows/ingest.yml` | no `voice_chat`, `trace_flow`, `blc.router`, `blc.trace`, `tool_step.check`, `food_tools.tool` | AC-4 |

### 6.2 KEPT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| KEPT-1 | each kept `chat` name of §3.2 (parametrised) | present | AC-3 |
| KEPT-2 | `import chat, web, ingest, pull_sheet` | no error | AC-3 |
| KEPT-3 | `from blc.tool_step.numbers import numbers_in, as_number, ALWAYS_ACCEPTED, WORD_NUMBERS` | works | AC-3 |
| KEPT-4 | `blc.tools.bev_tools.tool.BEV_SCHEMA` and the four `*_DESCRIPTION` of §3.2 | present | AC-3 |
| KEPT-5 | `blc.tools.recipe_tools.RECIPE_TOOL.name` | `"scale_recipe"` | AC-3 |
| KEPT-6 | `chat.is_exit_utterance("bye")` / `("where is the coffee?")` | True / False | AC-3 |

### 6.3 DEPS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DEPS-1 | parsed `pyproject.toml` | no `voice` group; no `pypdf`, `langchain-community`, `numpy` in main deps | AC-5 |
| DEPS-2 | parsed `pyproject.toml` | `eval` group is exactly `ollama`, `langchain-ollama`; other main deps still present (`langchain-anthropic`, `langchain-google-genai`, `fastapi`) | AC-5 |
| DEPS-3 | `docker/Dockerfile`, `.github/workflows/ingest.yml` | contain `--without eval`; no `voice` | AC-5 |

### 6.4 SUITE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| SUITE-1 | every test node ID of Appendix A | no longer exists in `backend/tests/` | AC-6 |
| SUITE-2 | test files under `backend/tests/` | none imports a §3.1 name except REMOVED tests | AC-4, AC-6 |
| SUITE-3 | `tests/cleanup/` | holds only spec 041 tests | AC-7 |
| SUITE-5 | text of every file under `backend/tests/` | no path into `024-cli-baseline`, `024-recipe-snapshot`, `032-assets` | AC-6 |
| SUITE-4 | unit layer run | 0 failed, 0 errors *(implementation-evaluator)* | AC-8 |

## Appendix A: failing unit tests to delete (baseline 2026-11-18)
Besides those going with removed code (`test_voice_io*.py`):
- `no_invented/test_fill_report.py`, `no_invented/test_golden_eval.py` (whole files; collection errors)
- `domain_retrieval/test_detect_domains.py::test_real_lexicon_is_non_empty`
- `food_wiring/test_planner_tools.py::test_prompt_holds_no_eval_question`
- `layout/test_layout.py::test_pytest_markers_and_addopts_unchanged`
- `napkin_knowledge/test_detect.py::` `test_napkins_with_beverage`, `test_napkin_with_food`, `test_no_napkin_word_no_napkin_domain`, `test_no_napkin_file_food_and_beverage_unchanged`, `test_no_napkin_file_with_food_gives_food_only`
- `napkin_knowledge/test_store.py::` `test_napkin_with_beverage_filter`, `test_napkin_with_food_filter`, `test_food_question_never_adds_napkin`
- `no_invented/test_retry.py::` `test_ec21_at_most_two_planner_calls_one_answer_call`, `test_ec21_exactly_one_planner_call_without_retry`
- `planned_flow/test_contract.py::` `test_history_reaches_planner_and_answer_messages`, `test_outcome_history_extends_input_without_mutating_it`, `test_no_history_gives_two_items`
- `planned_flow/test_run.py::` `test_tool_turn_message_has_tool_text_and_no_source`, `test_tool_turn_outcome_fields`, `test_tool_status_and_text_are_recorded_and_shown_whatever_the_status`, `test_both_turn_runs_store_and_recipe_runner_and_shows_both`, `test_runner_that_raises_gives_error_result_and_the_turn_finishes`, `test_missing_runner_gives_no_runner_error_and_the_turn_finishes`, `test_a_failing_tool_does_not_hide_the_documents`
- `standalone_tools/test_same.py::test_recipe_snapshot_replay_identical`
- `test_retrieval_eval.py`: golden cases `peach-juice-partial`, `mango-juice-partial` (remove the two cases from the test's parametrisation, not the golden file)
