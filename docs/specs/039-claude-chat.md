# Spec 039: Chat on Claude Haiku, embeddings stay on Gemini

- **Status:** approved (done: closed by the user on 2026-11-18. Verified: 178/178 spec 039 unit tests; live AC-1b, AC-10, AC-13 pass; AC-15/AC-16 checked by the planner. Not verified: AC-11 only 1 of 3 history shapes ran (other 2 hit the Gemini free-tier 429 embedding quota), AC-12 eval not run (Ollama judge). Known risk: the temperature fix pins `anthropic-version: 2023-06-01`. The 74 pre-existing unit failures and 2 collection errors in older suites predate this spec. Revised 2026-11-18 after the first round: AC-1 temperature must reach the API, AC-4 live fixtures must not expose keys, AC-14/MIGRATE-1 clarified; revised again after round-2 test review: AC-4/MIGRATE-5 cover every fixture under `backend/tests/`)
- **Date:** 2026-11-18

## 1. Goal
The chat model moves from `gemini-3.5-flash-lite` to **Claude Haiku (`claude-haiku-4-5`)** through the Anthropic API, paid from the user's Claude Console credits with an `ANTHROPIC_API_KEY`. Anthropic has no embeddings model, so embeddings stay on **`gemini-embedding-2`** (spec 037, free tier, `GOOGLE_API_KEY`). The Chroma store, ingest and the CI ingest workflow are unchanged, and no re-ingest is needed. Every chat-model user (planner, fast router, history summary, answer, voice) gets Claude through the existing `build_chat_model` seam.

Decided with the user: Claude for chat only (option A), Haiku and not Sonnet, with no provider switch or Gemini chat fallback.

## 2. Out of scope
- Changing embeddings, `EMBED_MODEL`, `EMBED_DIM`, the store stamp (spec 037) or the ingest workflow's behaviour.
- A provider switch or fallback to Gemini chat; Sonnet/Opus; Bedrock/Vertex.
- Prompt tuning for Claude (the spec 038 prompt and the planner prompts stay as they are). If AC-12 shows a quality drop, prompt work gets its own spec.
- Prompt caching, spend tracking, rate limiting, retries beyond the client library's defaults. Spend limits are set by the user in the Claude Console.
- A distinct "out of credits / rate limited" message: any model failure in the web chat keeps spec 032's `ERROR_MESSAGE`.
- The eval judge (stays on local Ollama `qwen2.5:7b`).

## 3. Interface contract
```python
# backend/src/blc/llm/  — public names exported from blc/llm/__init__.py
CHAT_API_KEY_ENV = "ANTHROPIC_API_KEY"   # new: key for the chat model
CHAT_MODEL = "claude-haiku-4-5"          # changed
API_KEY_ENV = "GOOGLE_API_KEY"           # unchanged: key for embeddings
EMBED_MODEL = "gemini-embedding-2"       # unchanged
EMBED_DIM = 768                          # unchanged

class MissingApiKeyError(RuntimeError):  # unchanged class, now used for both keys
    """Message names the missing env var (CHAT_API_KEY_ENV or API_KEY_ENV) and never contains a key value."""

def build_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """Claude chat model. Raises MissingApiKeyError if os.environ[CHAT_API_KEY_ENV] is unset or blank.
    Does not need GOOGLE_API_KEY. Makes no network call."""

def build_embeddings() -> Embeddings:
    """Unchanged from spec 037. Does not need ANTHROPIC_API_KEY."""
```
- Builders read only `os.environ` and do not load `.env` (unchanged rule). Entry points' `main()` load `.env` as today.
- The object returned by `build_chat_model` is a `langchain_anthropic.ChatAnthropic` instance.

**Entry points** (`backend/scripts/chat.py`, `web.py`, `trace_flow.py`, `voice_chat.py`, `ingest.py`):
- Importable from `chat`: every name spec 037 §3 lists, plus `CHAT_API_KEY_ENV`. `chat.CHAT_MODEL == "claude-haiku-4-5"`.
- `chat`, `web`, `trace_flow`, `voice_chat` `main()`: return 1, with a stderr message naming the missing env var and no traceback, when either key is missing.
- `ingest.main()` needs only `GOOGLE_API_KEY` and runs normally without `ANTHROPIC_API_KEY`.

**Files:**
- `pyproject.toml` / `poetry.lock`: adds `langchain-anthropic` as a main dependency; `langchain-google-genai` stays.
- `docker/compose.yaml` (via `docker compose -f docker/compose.yaml config --format json`): service `web` env has `ANTHROPIC_API_KEY` = the shell's `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY` as before.
- `.github/workflows/ingest.yml`: unchanged. It must not need `ANTHROPIC_API_KEY`.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | env var / `.env` | non-blank | `build_chat_model` returns `ChatAnthropic` |
| `ANTHROPIC_API_KEY` unset/blank | — | — | `MissingApiKeyError` naming it; chat entry points exit 1, no traceback; ingest unaffected |
| `GOOGLE_API_KEY` unset/blank | — | — | as spec 037 (embeddings and ingest fail with its name) |
| Anthropic error mid-turn (bad key, out of credits, 429, 529 overloaded) | — | — | web: spec 032 `error` line, `/api/health` stays 200 |
| history starting with an assistant message, or two user messages in a row | chat history | — | turn still answers (no Anthropic role-order error) |

## 5. Acceptance criteria
- **AC-1:** With `ANTHROPIC_API_KEY` set to any non-blank string and `GOOGLE_API_KEY` unset, `build_chat_model()` returns a `ChatAnthropic` (a `BaseChatModel`) without any network call; `build_chat_model(temperature=0.1)` has temperature 0.1.
- **AC-1b** *(integration, needs `ANTHROPIC_API_KEY`)*: The temperature reaches the Anthropic Messages API as its top-level `temperature` parameter, so a real `invoke` succeeds for both `build_chat_model()` and `build_chat_model(temperature=0.1)`. (Round 1 found every live call rejected with HTTP 400 `temperature: Extra inputs are not permitted`; the installed `langchain-anthropic` sent temperature in a form the API rejects. A direct API call with `"temperature": 0` on `claude-haiku-4-5` succeeds.)
- **AC-2:** With `ANTHROPIC_API_KEY` unset, empty or whitespace, `build_chat_model()` raises `MissingApiKeyError` whose message contains `ANTHROPIC_API_KEY`, even if `GOOGLE_API_KEY` is set and even if a `.env` in the cwd holds a key.
- **AC-3:** `build_embeddings()` works with `ANTHROPIC_API_KEY` unset (spec 037 AC-1/AC-2 still hold for it).
- **AC-4:** The Anthropic key value never appears in `str()` / `repr()` of the built chat model or in any `MissingApiKeyError` message. No pytest fixture anywhere under `backend/tests/` (any `conftest.py` or test module) returns, yields or parametrizes an API key value (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`); key fixtures only check presence and skip. A test that must pass a key on (e.g. into a Docker container's env) reads it from `os.environ` at the point of use, so a failing test's output cannot show a key.
- **AC-5:** Constants in `blc.llm` and `chat` equal the §3 values (`CHAT_MODEL == "claude-haiku-4-5"`, `CHAT_API_KEY_ENV == "ANTHROPIC_API_KEY"`, embedding constants unchanged).
- **AC-6:** `chat`, `web`, `trace_flow`, `voice_chat` `main()` return 1 when `build_chat_model` raises `MissingApiKeyError` for `ANTHROPIC_API_KEY`: stderr contains `ANTHROPIC_API_KEY`, no `Traceback`, no input read, server not started. Spec 037 AC-10/AC-11 still hold for the Google key and the store check.
- **AC-7:** `ingest.main()` with `GOOGLE_API_KEY` set, `ANTHROPIC_API_KEY` unset and fake embeddings ingests normally (exit 0, nothing printed about `ANTHROPIC_API_KEY`).
- **AC-8:** `pyproject.toml`: `langchain-anthropic` is a main dependency; `langchain-google-genai` still is; `eval` and `voice` groups unchanged. No module under `backend/src/blc/` or `backend/scripts/` builds a Gemini chat model (`ChatGoogleGenerativeAI`).
- **AC-9:** Compose config run with `ANTHROPIC_API_KEY=dummy-a GOOGLE_API_KEY=dummy-g` shows service `web` env `ANTHROPIC_API_KEY == "dummy-a"` and `GOOGLE_API_KEY == "dummy-g"`; spec 035/037 port and mounts unchanged. The ingest workflow YAML does not mention `ANTHROPIC`.
- **AC-10** *(integration, needs `ANTHROPIC_API_KEY`, skipped otherwise)*: `build_chat_model().invoke("Reply with OK")` returns non-empty text; `route_fast` with the real model on a question that needs the model returns a decision with `fallback == False`; the planner (spec 018/019) returns a non-fallback plan for one TOOL and one DOCS question (proves Claude accepts the planner's `bind_tools` schemas). Which route is picked is not asserted.
- **AC-11** *(integration, needs both keys and a store)*: `run_planned_turn` answers with non-empty text when the history (a) starts with an assistant message and (b) ends with two consecutive user messages before the question.
- **AC-12** *(eval, needs both keys and Ollama for the judge)*: The existing food-answer eval (spec 027, including spec 038's golden cases) and generation eval run on Claude and are reported against their current thresholds. A miss is reported to the user and becomes a follow-up prompt spec; it does not block this spec.
- **AC-13** *(integration)*: The web app (spec 032) with a real `build_chat_model` and `ANTHROPIC_API_KEY=invalid` (fake embeddings, stamped temp store) streams an `error` line with `ERROR_MESSAGE` for `POST /api/chat`, and `/api/health` returns 200 afterwards.
- **AC-14:** Existing tests are migrated: `gemini_migration/` assertions about the chat model (`CHAT_MODEL == "gemini-3.5-flash-lite"`, chat-model key checks, live chat invoke, entry-point stderr for a missing chat key) are updated to this spec, while its embedding, stamp, workflow and Docker assertions stay. Live fixtures that build a real chat model skip when `ANTHROPIC_API_KEY` is unset, those that build real embeddings skip when `GOOGLE_API_KEY` is unset, and fixtures building both skip when either is missing. After migration no file under `backend/tests/` asserts `gemini-3.5-flash-lite` as the chat model. Assertions that the chat model is *not* that string, and the scan itself, are allowed and must not make the scan fail.
- **AC-15** *(manual)*: README updated: stack (Claude Haiku for chat via Anthropic API / Console credits, Gemini for embeddings), setup (`ANTHROPIC_API_KEY` and `GOOGLE_API_KEY` in `.env`, where to get each key, a suggestion to set a spend limit in the Console), Docker needs both keys in the shell, CI still needs only the `GOOGLE_API_KEY` secret. The privacy note stays, reworded: questions are still sent to Google for embedding on the free tier, so they must not contain client personal data.
- **AC-16** *(manual)*: Only these change: `backend/src/blc/llm/`, the entry points (only where needed for AC-6/AC-7), `pyproject.toml`, `poetry.lock`, `docker/compose.yaml`, `README.md`, `.env.example` if it exists. No prompt, planner, router, flow or retrieval logic changes.

## 6. Test cases
Unit tests: `monkeypatch` for env vars, sockets blocked, fake embeddings and Chroma in `tmp_path`. Tests assert only what an AC states.

### 6.1 LLM (builders)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LLM-1 | `ANTHROPIC_API_KEY="test-a"`, `GOOGLE_API_KEY` unset | `build_chat_model()` is `ChatAnthropic`, no network | AC-1 |
| LLM-2 | same, `temperature=0.1` | model temperature 0.1 | AC-1 |
| LLM-3 | Anthropic key unset / `""` / `"   "`, Google key set | `MissingApiKeyError`, message has `ANTHROPIC_API_KEY` | AC-2 |
| LLM-4 | Anthropic key unset, `.env` in cwd has it | still raises | AC-2 |
| LLM-5 | Google key set, Anthropic key unset | `build_embeddings()` succeeds | AC-3 |
| LLM-6 | Anthropic key `"sk-ant-secret-123"` | not in `str`/`repr` of model nor in any error message | AC-4 |
| LLM-7 | constants in `blc.llm` and `chat` | equal §3 | AC-5 |

### 6.2 ENTRY (entry points)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| ENTRY-1 | each of chat/web/trace_flow/voice_chat `main()`, `chat.build_chat_model` raises `MissingApiKeyError` for the Anthropic key | 1; stderr has `ANTHROPIC_API_KEY`; no `Traceback`; no input read / server not started | AC-6 |
| ENTRY-2 | same four, Google key missing (embeddings raise) | 1; stderr has `GOOGLE_API_KEY` (spec 037 behaviour kept) | AC-6 |
| ENTRY-3 | `ingest.main()`, Google key set, Anthropic unset, fake embeddings | exit 0; stderr has no `ANTHROPIC_API_KEY` | AC-7 |

### 6.3 REPO
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| REPO-1 | load `pyproject.toml` | `langchain-anthropic` and `langchain-google-genai` in main deps; `eval`/`voice` groups unchanged | AC-8 |
| REPO-2 | scan `backend/src/blc/` and `backend/scripts/` | no `ChatGoogleGenerativeAI` | AC-8 |
| REPO-3 | compose config with both dummy keys (skip if no Docker) | both env values passed; port/mounts unchanged | AC-9 |
| REPO-4 | load ingest workflow YAML | no `ANTHROPIC` anywhere | AC-9 |

### 6.4 LIVE (integration / eval; skip when a needed key, store or Ollama is missing)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LIVE-1 | `build_chat_model().invoke("Reply with OK")` | non-empty content | AC-10, AC-1b |
| LIVE-1b | `build_chat_model(temperature=0.1).invoke("Reply with OK")` | non-empty content, no HTTP 400 | AC-1b |
| LIVE-2 | `route_fast(real, [], "How many hot cups for 130 guests and where is the coffee?")` | `fallback is False` | AC-10 |
| LIVE-3 | planner on one TOOL and one DOCS question | non-fallback plans | AC-10 |
| LIVE-4 | `run_planned_turn`, history `[assistant, user, user]` then a question | non-empty answer, no exception | AC-11 |
| LIVE-5 | web TestClient, `ANTHROPIC_API_KEY=invalid`, fake embeddings, stamped store | `error` line with `ERROR_MESSAGE`; health 200 after | AC-13 |
| LIVE-6 | food-answer eval + generation eval on Claude | pass rates reported against current thresholds | AC-12 |

### 6.5 MIGRATE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| MIGRATE-1 | scan `backend/tests/` | no assertion that the chat model is `gemini-3.5-flash-lite` | AC-14 |
| MIGRATE-2 | live chat-model fixtures (planner, flow, web, food, bev, router, …) | skip when `ANTHROPIC_API_KEY` unset | AC-14 |
| MIGRATE-3 | `gemini_migration/` embedding, stamp, workflow, Docker tests | still present and unchanged in meaning | AC-14 |
| MIGRATE-4 | `claude_chat/` assertions that `CHAT_MODEL != "gemini-3.5-flash-lite"` | MIGRATE-1 scan still passes | AC-14 |
| MIGRATE-5 | with `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` set to sentinels, call every key-checking fixture under `backend/tests/` (incl. `claude_chat/`, `docker/`, `gemini_migration/`) | none returns or yields a value containing a sentinel | AC-4 |
| MIGRATE-6 | static scan of every fixture under `backend/tests/` | no fixture returns/yields `os.environ[...]` / `os.getenv(...)` of either key, and no `parametrize` carries a key value | AC-4 |
