# Spec 037: Chat and embeddings on Gemini (free tier), CI re-ingests with Gemini

- **Status:** approved (revised 2026-11-17 after test review: AC-8 failure point, AC-11 scope, AC-18 plan check, AC-20 made testable with MIGRATE area)
- **Date:** 2026-11-17

## 1. Goal
The chatbot stops depending on a local Ollama: chat runs on **`gemini-3.5-flash-lite`** and embeddings on **`gemini-embedding-2` at 768 dimensions**, both through the Gemini API free tier with a `GOOGLE_API_KEY`. Every chunk records which embedding model produced it, so ingest re-embeds anything built by another model (the committed nomic store is fully replaced on the first run) and the chat entry points refuse to start on a store built by another model instead of silently retrieving garbage. The GitHub Actions ingest workflow (spec 036) uses Gemini instead of installing Ollama, and Docker no longer needs Ollama on the host.

Decided with the user: Gemini only for the app (no provider switch); the eval **judge stays on local Ollama** (`qwen2.5:7b`), so `langchain-ollama` remains only as an eval dependency.

## 2. Out of scope
- A provider switch or Ollama fallback for chat or embeddings; a paid tier; Vertex AI.
- Changing the judge (`blc/judge/`) or its model.
- Prompt tuning for Gemini; answer-quality eval runs (eval suites are migrated, not run, in this spec).
- A distinct "rate limited / quota reached" message: any model failure in the web chat keeps spec 032's `ERROR_MESSAGE`.
- Rate limiting, quota tracking, caching, retries beyond what the client library does by default.
- Changing `EMBED_DIM` later (a dimension change needs a fresh collection; not handled).
- Chunking, collection name, retrieval `k`, the flow, the planner prompts, the frontend.

## 3. Interface contract
```python
# backend/src/blc/llm/gemini.py  (exported from blc/llm/__init__.py)
API_KEY_ENV = "GOOGLE_API_KEY"
CHAT_MODEL = "gemini-3.5-flash-lite"
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768

class MissingApiKeyError(RuntimeError):
    """Message names API_KEY_ENV and never contains a key value."""

def build_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """Raises MissingApiKeyError if os.environ[API_KEY_ENV] is unset or blank. Makes no network call."""

def build_embeddings() -> Embeddings:
    """Vectors of length EMBED_DIM with unit (L2) norm. Raises MissingApiKeyError as above. Makes no network call."""
```
- The builders read only `os.environ`; they do **not** load `.env`. Each entry point's `main()` loads `.env` (python-dotenv) before building models.
- `BaseChatModel` / `Embeddings` are the `langchain_core` base classes.

```python
# backend/src/blc/ingest/stamp.py  (re-exported from backend/scripts/ingest.py and backend/scripts/chat.py)
EMBED_MODEL_KEY = "embed_model"     # chunk metadata key: the embedding model that produced the chunk

class StoreModelMismatchError(RuntimeError):
    """Message names the expected model and says to run backend/scripts/ingest.py."""

def check_store_model(store: Chroma, expected: str = EMBED_MODEL) -> None:
    """Raises StoreModelMismatchError if any chunk lacks EMBED_MODEL_KEY or has a different value.
    An empty store passes."""
```

```python
# backend/scripts/ingest.py  (spec 036 signatures, extended with embed_model)
def ingest(store: Chroma, data_dir: Path = DATA_DIR, embed_model: str = EMBED_MODEL) -> IngestPlan: ...
def ingest_file(store: Chroma, path: Path, mtime: float | None = None, embed_model: str = EMBED_MODEL) -> int: ...
```
- Every chunk written carries `EMBED_MODEL_KEY = embed_model`, plus spec 036's metadata (`source`, `category`, `domain`, `chunk_index`, `content_hash`).
- A source whose stored chunks lack `EMBED_MODEL_KEY` or carry a different value is reported in `updated` (even if its content hash matches) and fully re-embedded.

**Entry points** (`backend/scripts/chat.py`, `web.py`, `trace_flow.py`, `voice_chat.py`, `ingest.py`):
- Names importable from `chat`: `CHAT_MODEL`, `EMBED_MODEL`, `CHAT_TEMPERATURE` (unchanged value), `build_chat_model`, `build_embeddings`, `MissingApiKeyError`, `check_store_model`, `StoreModelMismatchError`. `CHAT_KEEP_ALIVE` and `chat.ChatOllama` / `chat.OllamaEmbeddings` no longer exist.
- Each entry point gets its models only by calling `chat.build_chat_model` / `chat.build_embeddings` (ingest: `ingest.build_embeddings`) at call time, so `monkeypatch.setattr(chat, "build_chat_model", fake)` takes effect.
- `main()` returns 1 and prints a message naming `GOOGLE_API_KEY` to stderr on `MissingApiKeyError`; the chat entry points (chat, web, trace_flow, voice_chat) return 1 with the `StoreModelMismatchError` message on a mismatched store. Neither error prints a traceback.
- `voice_chat` uses `build_chat_model(temperature=0.1)` (today's temperature).

**`blc.router.fast.route_fast`:** signature and behaviour unchanged, except its `llm.invoke` call carries no `options` and no `keep_alive` keyword.

**Files:**
- `pyproject.toml` / `poetry.lock`: adds `langchain-google-genai`; `langchain-ollama` and `ollama` move to a Poetry group `eval` that is **not optional**.
- `docker/Dockerfile`: installs without the `voice` and `eval` groups.
- `docker/compose.yaml` (via `docker compose -f docker/compose.yaml config --format json`): service `web` env `GOOGLE_API_KEY` = the shell's `GOOGLE_API_KEY`; no `OLLAMA_HOST`. Everything else from spec 035 unchanged.
- `.github/workflows/ingest.yml`: spec 036's contract still holds, plus: no step mentions `ollama`; the ingest step's env has `GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}`; deps installed without `voice` and `eval`; push `paths` also include `backend/src/blc/llm/**` (so an embedding-model change re-ingests).

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `GOOGLE_API_KEY` | env var / `.env` | non-blank | builders return models |
| key unset or blank | — | — | `MissingApiKeyError`; `main()` → exit 1, message, no traceback |
| `ingest` on store with chunks from another model | Chroma | — | those sources `updated`, re-embedded, stamped `EMBED_MODEL` |
| chat/web/trace/voice start on mismatched store | — | — | exit 1, message says run ingest |
| Gemini error during a web chat turn (429, bad key, down) | — | — | stream ends with spec 032 `error` line; `/api/health` stays 200 |
| embedding fails mid-ingest | — | — | `ingest` raises; a rerun brings the store fully in line |
| push to `main` touching `data/**/*.md` or `backend/src/blc/llm/**` | git push | secret set | workflow re-ingests with Gemini, commits `.chroma/` if changed |

## 5. Acceptance criteria
- **AC-1:** With `GOOGLE_API_KEY` set to any non-blank string, `build_chat_model()` returns a `BaseChatModel` and `build_embeddings()` an `Embeddings`, without any network call.
- **AC-2:** With `GOOGLE_API_KEY` unset, empty or whitespace, both builders raise `MissingApiKeyError` whose message contains `GOOGLE_API_KEY`. A `.env` file in the working directory does not change this (builders don't load it).
- **AC-3:** The key value never appears in `str()` / `repr()` of a built model or embeddings object, nor in any `MissingApiKeyError` message.
- **AC-4:** `check_store_model` passes on an empty store and on a store where every chunk has `EMBED_MODEL_KEY == expected`; it raises `StoreModelMismatchError` if any chunk has another value or no such key (including a mix of stamped and unstamped chunks). The message contains the expected model name and `ingest.py`.
- **AC-5:** Every chunk written by `ingest` / `ingest_file` carries `EMBED_MODEL_KEY` equal to the `embed_model` argument (default `EMBED_MODEL`).
- **AC-6:** `ingest(store, data_dir, embed_model="m2")` on a store whose chunks were written with `"m1"` (same file contents) returns every source in `updated`; afterwards no chunk carries `"m1"` and the chunk count per source matches a fresh ingest. A second run with `"m2"` returns all `unchanged`.
- **AC-7:** A pre-036 / pre-037 chunk (no `EMBED_MODEL_KEY`, hash matching or missing) is `updated` on the next ingest and stamped afterwards.
- **AC-8:** If the embedding function raises during `ingest` (including after it has already embedded at least one file in that run), the error propagates; running `ingest` again with a working embedding function returns a plan after which `check_store_model` passes and every file's chunks match its current content (no file left with stale or missing chunks).
- **AC-9:** `route_fast`'s single `invoke` call has no `options` and no `keep_alive` keyword argument; spec 013's other router behaviour is unchanged (existing router tests still pass apart from Ollama-specific option assertions).
- **AC-10:** `chat`, `web`, `trace_flow`, `voice_chat` and `ingest` `main()` return 1 when `build_chat_model` / `build_embeddings` raise `MissingApiKeyError`, printing a stderr message containing `GOOGLE_API_KEY` and no traceback. `ingest.main()` leaves the store untouched in that case.
- **AC-11:** `chat.main()`, `web.main()`, `trace_flow.main()` and `voice_chat.main()` return 1 (stderr contains `ingest.py`) when the store fails `check_store_model`, before reading input or starting the server.
- **AC-12:** Names listed in §3 are importable from `chat`; `CHAT_KEEP_ALIVE`, `ChatOllama`, `OllamaEmbeddings` are not attributes of `chat`; `chat.CHAT_MODEL == "gemini-3.5-flash-lite"`, `chat.EMBED_MODEL == ingest.EMBED_MODEL == "gemini-embedding-2"`.
- **AC-13:** `pyproject.toml`: `langchain-google-genai` is a main dependency; `langchain-ollama` and `ollama` are only in group `eval`, which is not optional; the `voice` group is unchanged. No module under `backend/src/blc/` other than `blc/judge/` imports `langchain_ollama` or `ollama`, and no entry point does.
- **AC-14:** Workflow YAML: no step `run` or `uses` contains `ollama` (case-insensitive); some step's `env.GOOGLE_API_KEY` is `${{ secrets.GOOGLE_API_KEY }}`; push paths include `data/**/*.md` and `backend/src/blc/llm/**` and none contain `.chroma`; spec 036's AC-12 still holds.
- **AC-15:** `docker compose -f docker/compose.yaml config --format json` run with `GOOGLE_API_KEY=dummy-key` shows service `web` env `GOOGLE_API_KEY == "dummy-key"` and no `OLLAMA_HOST`; spec 035's port and mounts unchanged. `docker/Dockerfile` installs without `voice` and `eval`.
- **AC-16** *(integration, needs `GOOGLE_API_KEY`, skipped otherwise)*: `build_embeddings().embed_query("coffee")` and `embed_documents(["a", "b"])` return vectors of length `EMBED_DIM` whose Euclidean norm is 1 (within 1e-3); `build_chat_model().invoke("Reply with OK")` returns non-empty text.
- **AC-17** *(integration, needs key)*: `ingest` of two real `data/` markdown files into a temp store with `build_embeddings()` gives `new` then `unchanged`; `check_store_model` passes; a similarity search for a phrase from one file returns a chunk of that file first.
- **AC-18** *(integration, needs key)*: The planner (spec 018/019) with `build_chat_model()` returns, for one TOOL question and one DOCS question, a plan that is not a fallback (proves Gemini accepts the planner's tool schemas via `bind_tools`). Which route the model picks is not asserted.
- **AC-19** *(integration, needs Docker)*: The image built from `docker/Dockerfile`, run with `GOOGLE_API_KEY=invalid` and a store stamped with `EMBED_MODEL`, answers `POST /api/chat` with a spec 032 `error` line, and `/api/health` returns 200 afterwards.
- **AC-20:** Existing tests are migrated: tests that build a real chat model or embeddings for the chatbot use `build_chat_model` / `build_embeddings` and skip when `GOOGLE_API_KEY` is unset; tests that build the judge keep Ollama and skip when Ollama is down; tests that use removed names (`CHAT_KEEP_ALIVE`, `OLLAMA_HOST`, `chat.ChatOllama`, `qwen2.5:7b` as the chat model) are updated or removed to match this spec. The judge's `JUDGE_MODEL == "qwen2.5:7b"` test stays. Concretely, after migration no file under `backend/tests/` uses `CHAT_KEEP_ALIVE`, `OLLAMA_HOST`, `OllamaEmbeddings` or `keep_alive`, or calls `ChatOllama(` with any model other than `JUDGE_MODEL`, except where the name appears only as a string asserting it was removed (e.g. a list of removed names). Spec 036's live ingest test uses `build_embeddings()` and skips without a key. Files known to need migration are listed in §6.7.
- **AC-21** *(manual)*: README updated: stack (Gemini, models, free tier), setup (`GOOGLE_API_KEY` in `.env`, how to get a key in AI Studio, the `GOOGLE_API_KEY` repo secret for the workflow), Docker without host Ollama, Ollama needed only for evals (judge), a note that on the free tier Google may use prompts to improve its products so questions must not contain client personal data, and that after this change `.chroma/` must be re-ingested (workflow run) before chat starts.
- **AC-22** *(manual)*: Only these change: `backend/src/blc/llm/` (new), `backend/src/blc/ingest/` (stamp + ingest changes), `backend/src/blc/router/fast.py`, the five entry points, `pyproject.toml`, `poetry.lock`, `docker/Dockerfile`, `docker/compose.yaml`, `.github/workflows/ingest.yml`, `README.md`. The builders and `check_store_model` contain no prompt or flow logic.
- **AC-23** *(manual, user)*: After merge, the user adds the `GOOGLE_API_KEY` repo secret; the workflow run (triggered by the `blc/llm/` change or `workflow_dispatch`) commits a `.chroma/` whose chunks all carry `EMBED_MODEL_KEY == "gemini-embedding-2"`.

## 6. Test cases
Unit tests: Chroma in `tmp_path` with fake embeddings (e.g. `DeterministicFakeEmbedding(size=768)`), `monkeypatch` for env vars, no network. Spec 036's tests keep passing (they call `ingest` / `ingest_file` without `embed_model`). Tests assert only what an AC states: e.g. nothing about `chat.main()`'s return value at end of input, or which route a live planner picks.

### 6.1 LLM (builders)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LLM-1 | key `"test-key"` | `build_chat_model()` is `BaseChatModel`; `build_embeddings()` is `Embeddings`; no network (sockets blocked) | AC-1 |
| LLM-2 | key unset | both raise `MissingApiKeyError`, message has `GOOGLE_API_KEY` | AC-2 |
| LLM-3 | key `""` and `"   "` | both raise `MissingApiKeyError` | AC-2 |
| LLM-4 | key unset, `tmp_path/.env` with a key, cwd = tmp_path | still raises | AC-2 |
| LLM-5 | key `"sk-secret-123"` | not in `str`/`repr` of either object | AC-3 |
| LLM-6 | constants | `CHAT_MODEL`, `EMBED_MODEL`, `EMBED_DIM`, `API_KEY_ENV` equal §3 values | AC-12 |

### 6.2 STAMP (store model + ingest)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| STAMP-1 | empty store | `check_store_model` passes | AC-4 |
| STAMP-2 | all chunks `embed_model=EMBED_MODEL` | passes | AC-4 |
| STAMP-3 | one chunk `embed_model="nomic-embed-text"` | raises; message has `gemini-embedding-2` and `ingest.py` | AC-4 |
| STAMP-4 | stamped chunks + one chunk without the key | raises | AC-4 |
| STAMP-5 | `ingest` then read metadata | every chunk `embed_model == EMBED_MODEL` | AC-5 |
| STAMP-6 | `ingest_file(store, p, 1.0, embed_model="x")` | chunks carry `"x"` | AC-5 |
| STAMP-7 | ingest with `"m1"`, then `"m2"`, same files | 2nd plan all `updated`; no `"m1"` left; count per source equal | AC-6 |
| STAMP-8 | then `"m2"` again | all `unchanged` | AC-6 |
| STAMP-9 | pre-seeded chunk with correct `content_hash`, no `embed_model` | source `updated`, then stamped | AC-7 |
| STAMP-10 | embedding fake succeeds on its 1st `embed_documents` call and raises on its 2nd (two files that both need embedding); rerun with working fake | 1st call raises; after rerun `check_store_model` passes and each file's chunks match its content | AC-8 |

### 6.3 ROUTER
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ROUTER-1 | `route_fast(fake, [], "How many hot cups for 130 guests?")` needing the model | `invoke` kwargs have no `options`, no `keep_alive` | AC-9 |

### 6.4 ENTRY (entry points)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ENTRY-1 | each of chat/web/trace_flow/voice_chat/ingest `main()`, `chat.build_chat_model` / `build_embeddings` patched to raise `MissingApiKeyError` | returns 1; stderr has `GOOGLE_API_KEY`; no `Traceback` | AC-10 |
| ENTRY-2 | `ingest.main()` with missing key, store pre-seeded | chunk ids unchanged | AC-10 |
| ENTRY-3 | `chat.main()` / `web.main()`, store with `embed_model="nomic-embed-text"` chunks, fake models | returns 1; stderr has `ingest.py`; no input read / server not started | AC-11 |
| ENTRY-4 | import `chat` | §3 names present; `CHAT_KEEP_ALIVE`, `ChatOllama`, `OllamaEmbeddings` absent | AC-12 |

### 6.5 REPO (dependencies, workflow, Docker)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REPO-1 | load `pyproject.toml` | `langchain-google-genai` in main deps; `langchain-ollama`, `ollama` only in group `eval`, not optional; `voice` unchanged | AC-13 |
| REPO-2 | scan `backend/src/blc/` (except `judge/`) and `backend/scripts/` imports | no `langchain_ollama` / `ollama` import | AC-13 |
| REPO-3 | load workflow YAML | no step mentions `ollama`; a step env `GOOGLE_API_KEY == "${{ secrets.GOOGLE_API_KEY }}"` | AC-14 |
| REPO-4 | same | paths include `data/**/*.md` and `backend/src/blc/llm/**`; none contain `.chroma`; 036 AC-12 holds | AC-14 |
| REPO-5 | compose config with `GOOGLE_API_KEY=dummy-key` (skip if no Docker) | env `GOOGLE_API_KEY == "dummy-key"`; no `OLLAMA_HOST`; port/mounts as spec 035 | AC-15 |
| REPO-6 | read `docker/Dockerfile` | the install excludes `voice` and `eval` | AC-15 |

### 6.6 LIVE (integration; skip without `GOOGLE_API_KEY` / Docker)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LIVE-1 | `embed_query("coffee")`, `embed_documents(["a","b"])` | lengths 768; each norm 1 ± 1e-3 | AC-16 |
| LIVE-2 | `build_chat_model().invoke("Reply with OK")` | non-empty content | AC-16 |
| LIVE-3 | two real data files, temp store, ingest twice | `new` then `unchanged`; `check_store_model` passes; phrase search hits own file first | AC-17 |
| LIVE-4 | planner on one TOOL and one DOCS question | each plan is not a fallback; route not asserted | AC-18 |
| LIVE-5 | container with `GOOGLE_API_KEY=invalid`, stamped temp store | `/api/chat` streams `error` line; health 200 after | AC-19 |

### 6.7 MIGRATE (existing tests, AC-20)
Files found by the planner that reference removed names or build a real Ollama chat model / embeddings (the tester may find more): `answer_grounding/conftest.py`, `bev_tools/conftest.py`, `beverage_knowledge/conftest.py`, `ci_ingest/test_ingest_store.py`, `cleanup/test_removed_names.py`, `docker/conftest.py`, `docker/docker_helpers.py`, `docker/test_compose.py`, `docker/test_image.py`, `domain_retrieval/conftest.py`, `domain_retrieval/domain_helpers.py`, `flow/conftest.py`, `food_answers/conftest.py`, `food_answers/food_answer_helpers.py`, `food_retrieval/conftest.py`, `food_retrieval/food_helpers.py`, `food_wiring/conftest.py`, `layout/test_paths.py`, `mixed_questions/conftest.py`, `napkin_knowledge/conftest.py`, `napkin_knowledge/napkin_helpers.py`, `no_invented/conftest.py`, `planned_flow/conftest.py`, `planner/conftest.py`, `router/conftest.py`, `router/test_route_fast_flow.py`, `test_generation_eval.py`, `test_voice_io.py`, `tool_calling/conftest.py`, `tool_step/conftest.py`, `web/test_integration.py` (all under `backend/tests/`).

| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| MIGRATE-1 | scan every `.py` under `backend/tests/` (excluding the scanning test itself) | no `CHAT_KEEP_ALIVE`, `OLLAMA_HOST`, `OllamaEmbeddings` or `keep_alive` outside a removed-names string list | AC-20 |
| MIGRATE-2 | same scan | every `ChatOllama(` call uses `JUDGE_MODEL` | AC-20 |
| MIGRATE-3 | chatbot live fixtures (planner, flow, web, food, bev, …) | build via `build_chat_model` / `build_embeddings`; skip when `GOOGLE_API_KEY` unset | AC-20 |
| MIGRATE-4 | judge fixtures | still `ChatOllama(model=JUDGE_MODEL)`; skip when Ollama is down | AC-20 |
| MIGRATE-5 | `router/test_route_fast_flow.py`, `test_voice_io.py`, `docker/test_image.py` | assertions on keep-alive, `voice_chat.ChatOllama`, `OLLAMA_HOST` replaced by spec 037 equivalents (e.g. voice builds via `build_chat_model(temperature=0.1)`; container gets `GOOGLE_API_KEY`) | AC-20 |
