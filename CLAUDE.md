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
