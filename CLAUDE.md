# Bay Laurel Catering Chatbot

Internal RAG chatbot for Bay Laurel Catering employees. See `README.md` for the full flow.

## Stack
- Python 3.10+, Poetry (`package-mode = false`, venv in `.venv/`)
- LangChain + LangGraph + `langchain-chroma`
- Chat: Claude Haiku via `langchain-anthropic` (`ANTHROPIC_API_KEY`, spec 039); embeddings: Gemini via `langchain-google-genai` (`GOOGLE_API_KEY`, spec 037)
- Ollama (`qwen2.5:7b`) only as the eval judge (`eval` dependency group)
- Chroma vector store in `.chroma/` (committed; rebuilt by the ingest workflow)
- Knowledge source: markdown under `data/` (`data/**/*.md` committed; JSON tool data and photos gitignored)

## Layout
The repo is split into `backend/` (all Python) and `frontend/` (the web page). Project content and the Poetry project stay at the root.
- `backend/scripts/` — entry points:
  - `ingest.py` — chunk + embed `data/**/*.md` into Chroma (incremental by mtime)
  - `chat.py` — terminal chat; `main()` runs the planned flow (`blc.flow.run_planned_turn`, spec 019). Also holds the shared startup (`start_stack`, `build_store`, `retrieve`) used by `web.py` and tests
  - `web.py` — web chat: FastAPI API + serves `frontend/` (spec 032)
  - `pull_sheet.py` — beverage pull sheet from a BEO (spec 002); menu and rules in `data/pull_sheet/`
- `backend/src/blc/` — feature packages the entry points import (e.g. `flow/`, `planner/`, `tools/`, `retrieval/`, `history/`, `llm/`, `ingest/`, `pull_sheet/`, `judge/`, `web/`)
- `backend/tests/` — pytest suites
- `frontend/` — the web chat page: plain HTML/CSS/JS, no build step; every image in `frontend/assets/`
- Root: `data/` (knowledge), `evals/` (golden sets), `docs/specs/` (specs; `TEMPLATE.md` is the format), `logs/`, `.chroma/`, `pyproject.toml`, `poetry.lock`

## Commands
```bash
poetry install
poetry run python backend/scripts/ingest.py
poetry run python backend/scripts/chat.py
poetry run python backend/scripts/web.py            # web chat on http://127.0.0.1:8000 (--host 0.0.0.0 for phones)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest            # all tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest -m "not integration and not eval"   # unit only
```
`pyproject.toml` sets `pythonpath = ["backend/scripts", "backend/src"]`, so tests import modules directly (e.g. `from chat import retrieve`, `import blc.flow`).

## Code structure
Applies to all new code and tests unless a spec says otherwise.
- **Entry points live in `backend/scripts/`; feature code lives in `backend/src/blc/<feature>/`; page code lives in `frontend/`.** An entry point (e.g. `backend/scripts/pull_sheet.py`) holds the CLI and nothing else: it puts `backend/src/` on `sys.path`, re-exports the feature's public API (so `from pull_sheet import …` keeps working for tests), defines `main()` (argument parsing, reading input files, calling the package, printing, exit codes) and runs it under `if __name__ == "__main__"`. Everything that computes or validates lives in the package. The package sits under `blc/` so its name never clashes with the entry point's name.
- **Split modules by purpose, i.e. by the job the code does** (e.g. `units.py` converts units, `cambros.py` chooses cambros, `sheet.py` builds the full sheet from the rules), not by kind of thing. Each module keeps its own constants, errors and small data classes at the top of the same file. Don't create catch-all modules such as `constants.py`, `errors.py`, `models.py`, `types.py` or `utils.py`. Something used by several modules lives in the module whose job owns it (e.g. a file-format error lives with the code that reads that file), and the others import it from there.
- **Calculation modules do no I/O:** no file reading, printing or network access; they take data in and return data out. Reading files and printing happen at the edges (the loaders and the entry point's CLI).
- **Size guideline, not a hard rule:** aim for about 250 lines per file. Split a file when it starts doing more than one job, not just to hit a number. Keep functions readable rather than counting their lines.
- **Tests** live in `backend/tests/<feature>/test_<area>.py`, grouped by spec section (not by code module), with shared fixtures and helpers in `backend/tests/<feature>/conftest.py`. About 400 lines per test file. Tests still import only the spec's interface contract.

## Test layers
- **Unit:** chat model, embeddings and Chroma mocked/faked; deterministic; no network.
- **Integration:** real Anthropic/Gemini/Chroma; mark `@pytest.mark.integration`; skip if the needed API key (or, for the judge, Ollama) is unavailable.
- **Eval:** golden-set quality metrics; mark `@pytest.mark.eval`; judged against thresholds, not per-case.

## Team workflow
The **planner** runs as the main session, started with `claude --agent planner`. A plain `claude` session is not the planner: it lacks the planner instructions and is not restricted by the guard. Features go through a spec in `docs/specs/NNN-<name>.md`, approved by the user, then:

1. `developer` (implements the spec, never sees `backend/tests/`) and `tester` (writes tests from the spec only, never sees source code, runs nothing) start at the same time.
2. When the tester finishes, `test-evaluator` audits the tests against the spec (no source). A FAIL stops the round and goes to the user.
3. Once the test-evaluator passes and the developer is done, `implementation-evaluator` runs the tests against the code and diagnoses failures.
4. The planner reports to the user.

Agents are briefed only with the spec path; they never receive each other's outputs.
Access limits are enforced by `.claude/hooks/agent_guard.py`.
