# Bay Laurel Catering Chatbot

Internal RAG chatbot for Bay Laurel Catering employees. See `README.md` for the full flow.

## Stack
- Python 3.10+, Poetry (`package-mode = false`, venv in `.venv/`)
- LangChain + `langchain-chroma` + `langchain-ollama`
- Ollama models: `nomic-embed-text` (embeddings), `qwen2.5:7b` (chat)
- Chroma vector store persisted in `.chroma/` (gitignored)
- Knowledge source: markdown under `data/` (gitignored)

## Layout
- `scripts/ingest.py` — chunk + embed `data/**/*.md` into Chroma (incremental by mtime)
- `scripts/chat.py` — interactive retrieve + generate loop
- `scripts/voice_chat.py` — push-to-talk voice chat (spec 001)
- `scripts/pull_sheet.py` — beverage pull sheet from a BEO (spec 002); menu and rules in `data/pull_sheet/`
- `src/blc/` — feature packages (e.g. `src/blc/pull_sheet/`); entry points in `scripts/` import from here
- `tests/` — pytest suites
- `evals/retrieval/golden.jsonl` — golden Q&A cases
- `docs/specs/` — feature specs (`TEMPLATE.md` is the format)

## Commands
```bash
poetry install
poetry run python scripts/ingest.py
poetry run python scripts/chat.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest            # all tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest -m "not integration and not eval"   # unit only
```
`pyproject.toml` sets `pythonpath = ["scripts"]`, so tests import modules directly (e.g. `from chat import retrieve`).

## Code structure
Applies to all new code and tests unless a spec says otherwise.
- **Entry points live in `scripts/`; feature code lives in `src/blc/<feature>/`.** An entry point (e.g. `scripts/pull_sheet.py`) holds the CLI and nothing else: it puts `src/` on `sys.path`, re-exports the feature's public API (so `from pull_sheet import …` keeps working for tests), defines `main()` (argument parsing, reading input files, calling the package, printing, exit codes) and runs it under `if __name__ == "__main__"`. Everything that computes or validates lives in the package. The package sits under `blc/` so its name never clashes with the entry point's name.
- **Split modules by purpose, i.e. by the job the code does** (e.g. `units.py` converts units, `cambros.py` chooses cambros, `sheet.py` builds the full sheet from the rules), not by kind of thing. Each module keeps its own constants, errors and small data classes at the top of the same file. Don't create catch-all modules such as `constants.py`, `errors.py`, `models.py`, `types.py` or `utils.py`. Something used by several modules lives in the module whose job owns it (e.g. a file-format error lives with the code that reads that file), and the others import it from there.
- **Calculation modules do no I/O:** no file reading, printing or network access; they take data in and return data out. Reading files and printing happen at the edges (the loaders and the entry point's CLI).
- **Size guideline, not a hard rule:** aim for about 250 lines per file. Split a file when it starts doing more than one job, not just to hit a number. Keep functions readable rather than counting their lines.
- **Tests** live in `tests/<feature>/test_<area>.py`, grouped by spec section (not by code module), with shared fixtures and helpers in `tests/<feature>/conftest.py`. About 400 lines per test file. Tests still import only the spec's interface contract.

## Test layers
- **Unit:** Ollama and Chroma mocked/faked; deterministic; no network.
- **Integration:** real Ollama/Chroma; mark `@pytest.mark.integration`; skip if Ollama is not running.
- **Eval:** golden-set quality metrics; mark `@pytest.mark.eval`; judged against thresholds, not per-case.

## Team workflow
The **planner** runs as the main session, started with `claude --agent planner`. A plain `claude` session is not the planner: it lacks the planner instructions and is not restricted by the guard. Features go through a spec in `docs/specs/NNN-<name>.md`, approved by the user, then:

1. `developer` implements the spec (never edits `tests/`).
2. `tester` writes tests from the spec only (never sees source code, runs nothing).
3. `test-evaluator` (tests vs spec, no source) and `code-evaluator` (source vs spec, no tests) run in parallel.
4. If both pass, `implementation-evaluator` runs the tests against the code and diagnoses failures.
5. The planner cross-checks results and reports to the user.

Agents are briefed only with the spec path; they never receive each other's outputs.
Access limits are enforced by `.claude/hooks/agent_guard.py`.
