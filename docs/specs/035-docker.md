# Spec 035: Docker image for the web chat (one image, Ollama on the host)

- **Status:** approved (revised 2026-11-17 after test review: files moved to `docker/`, single-behaviour ACs, README ingest step)
- **Date:** 2026-11-17

## 1. Goal
Package the web chat (spec 032) as **one Docker image**, so it runs the same way on any machine with Docker, started with one command (`docker compose -f docker/compose.yaml up --build`). The image holds the code and the Python dependencies only. The knowledge (`data/`) and the vector store (`.chroma/`) are mounted at run time, and **Ollama stays on the host** (the Mac's own Ollama, which can use the GPU). The image is built so it can be split later (frontend proxy, Ollama container) without rework.

## 2. Out of scope
- An Ollama container, a model-pull service, GPU settings (a later spec).
- A separate frontend image, nginx, CORS, HTTPS, login, Cloud Run, pushing to a registry.
- Building `data/`, `.chroma/`, `.env` or models into the image.
- Running the pytest suite inside the image; running as a non-root user; any image-size target.
- Any change to `backend/` or `frontend/` code (the server is started with `--host 0.0.0.0` from the image/compose, not by changing `web.py`'s default).
- Voice chat in the container (its packages are left out of the image, AC-9).
- Production storage for `.chroma/` (VM disk, baked into a private image, or a Chroma server); decided together with the deployment platform.

## 3. Interface contract
New files, all in a new `docker/` folder: `docker/Dockerfile`, `docker/Dockerfile.dockerignore` (the ignore file for that Dockerfile), `docker/compose.yaml`. The repo root gets no `Dockerfile`, `.dockerignore` or `compose.yaml`. The build context is always the **repo root**.

**Image** (built with `docker build -f docker/Dockerfile -t <tag> .` from the repo root):
```text
APP_ROOT        = /app      # the repo layout is kept under it: /app/backend/..., /app/frontend/...
DEFAULT COMMAND = serves the web chat on 0.0.0.0:8000 (spec 032's web.py)
```
- Any command given to `docker run <tag> <cmd...>` replaces the default command and runs from `/app` (no fixed entrypoint), e.g. `docker run <tag> python backend/scripts/ingest.py`.
- `python` on `PATH` has the project's locked dependencies, except the voice group (AC-9).
- Ollama is reached at the URL in env var `OLLAMA_HOST`.

**docker/compose.yaml**, read through `docker compose -f docker/compose.yaml config --format json` (run from the repo root):
```text
service name       : web            (exactly one service)
build              : context = <repo root>, dockerfile = docker/Dockerfile
published port     : host 8000 -> container 8000
bind mounts        : exactly these two:
                     <repo>/data    -> /app/data
                     <repo>/.chroma -> /app/.chroma
env OLLAMA_HOST    : value of the shell's OLLAMA_HOST if set, else
DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434"
```

**pyproject.toml:** `faster-whisper`, `piper-tts` and `sounddevice` move to a Poetry dependency group named `voice` that is **not optional**, so a plain `poetry install` on a dev machine still installs them. Version ranges are unchanged.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| `docker compose -f docker/compose.yaml up --build` | command, repo root | `data/` and `.chroma/` exist; host Ollama running | web chat on `http://localhost:8000` |
| `OLLAMA_HOST` (shell) | URL | any | overrides the container's Ollama URL |
| `docker compose -f docker/compose.yaml run --rm web python backend/scripts/ingest.py` | command | host Ollama running; `data/` and `.chroma/` exist (an empty `.chroma/` is fine) | builds/updates the host's `.chroma/` from the host's `data/` |
| `.chroma/` missing on the host | — | — | compose refuses to start `web` and names the missing path; no empty folder is created |
| host Ollama down / wrong URL | — | — | container keeps running; `/api/chat` streams spec 032's `error` line |

## 5. Acceptance criteria
Single-behaviour ACs (AC-1, AC-2, AC-3, AC-4, AC-7, AC-9, AC-11) need only the cases listed in §6; no separate wrong case is required. Tests assert only what an AC states: nothing about unknown paths, other URLs in the page, or other behaviour the spec does not define.
- **AC-1** *(integration)*: `docker build -f docker/Dockerfile .` from the repo root succeeds.
- **AC-2** *(integration)*: The image contains none of `.git`, `.venv`, `.chroma`, `.env`, `.models`, `logs`, `.pytest_cache` **directly under** `/app` (top level only), and `/app/data` is either absent or empty. It does contain `/app/backend/scripts/web.py`, `/app/frontend/index.html`, `/app/pyproject.toml` and `/app/poetry.lock`.
- **AC-3** *(integration)*: Run with no command and no mounts, the container exits with code 1 and its output mentions that the Chroma store is missing (spec 032's existing behaviour, proving the default command is the web chat).
- **AC-4** *(integration)*: Run with the default command, port 8000 published and the repo's `data/` and `.chroma/` mounted at `/app/data` and `/app/.chroma`, `GET http://localhost:8000/api/health` from the host returns 200 `{"status": "ok"}` within 60 s, and `GET /` returns the chat page.
- **AC-5** *(integration)*: As AC-4 with `OLLAMA_HOST=http://host.docker.internal:11434` and the host's Ollama running, `POST /api/chat` with "Where is the coffee kept?" streams at least one `token` line and a `done` line with a non-empty `reply`. (Its wrong case is AC-6.)
- **AC-6** *(integration)*: As AC-4 with `OLLAMA_HOST` pointing at a port where nothing listens, `POST /api/chat` returns 200 with an `error` line carrying spec 032's `ERROR_MESSAGE`, and `/api/health` still returns 200 afterwards.
- **AC-7** *(integration)*: `docker stop` on a running AC-4 container finishes within 10 s and the container's exit code is not 137 (it shuts down cleanly instead of being killed).
- **AC-8** *(integration)*: `docker run <tag> python backend/scripts/ingest.py` with a temp folder holding one markdown file mounted at `/app/data`, an empty temp folder at `/app/.chroma` and the host's Ollama reachable exits 0, and the temp `.chroma` folder is no longer empty. Success only: ingest's failure behaviour is not part of this spec.
- **AC-9** *(integration)*: In the image, `import fastapi, uvicorn, chromadb, langchain_ollama` works and `import sounddevice` fails.
- **AC-10** *(integration)*: `docker compose -f docker/compose.yaml config --format json` from the repo root shows exactly one service `web`, built with the repo root as context and `docker/Dockerfile`, publishing host 8000 to container 8000, with exactly the two bind mounts from §3.
- **AC-11** *(integration)*: In that config, `OLLAMA_HOST` for `web` equals `DEFAULT_OLLAMA_HOST` when the shell has no `OLLAMA_HOST`, and equals the shell's value (e.g. `http://example:1234`) when it is set.
- **AC-12:** No file under `frontend/` contains `localhost`, `127.0.0.1`, `0.0.0.0` or `:8000`; the page calls the API by relative path only (so a later proxy split needs no frontend change).
- **AC-13** *(manual)*: If `.chroma/` (or `data/`) is missing on the host, `docker compose -f docker/compose.yaml up` fails with an error naming the path and does not create an empty folder.
- **AC-14** *(manual)*: `docker/compose.yaml` makes `host.docker.internal` resolve on Linux Docker Engine as well as Docker Desktop.
- **AC-15** *(manual)*: The image's Python is 3.10 or newer, its dependencies are installed from `poetry.lock` (no unpinned resolve at build time), and the dependency layer is not rebuilt when only `backend/` or `frontend/` files change.
- **AC-16** *(manual)*: `README.md` has a Docker section: prerequisites (Docker, host Ollama running with `qwen2.5:7b` and `nomic-embed-text` pulled; on Linux, Ollama must listen on more than `127.0.0.1`), every command written with `-f docker/compose.yaml` from the repo root, `up --build`, running ingest in the container **including `mkdir -p .chroma` before the first ingest on a new machine** (compose refuses a missing `.chroma/`, AC-13), overriding `OLLAMA_HOST`, and rebuilding after code changes.
- **AC-17** *(manual)*: Only `docker/Dockerfile`, `docker/Dockerfile.dockerignore`, `docker/compose.yaml`, `pyproject.toml`, `poetry.lock` and `README.md` change, plus the new tests. No `Dockerfile`, `.dockerignore` or `compose.yaml` remains at the repo root. A plain `poetry install` on the Mac still installs the voice packages.
- **AC-18:** Nothing regresses: the unit tests that passed before still pass (baseline: `docs/specs/033-baseline-failures.txt`).
- **AC-19** *(manual, user)*: In a browser at `http://localhost:8000` with the container running: the page and Laurel load, a docs question, a beverage or food tool question and a follow-up all answer correctly.

## 6. Test cases
DOCKER and COMPOSE rows call the `docker` CLI via `subprocess` from the repo root, are marked `@pytest.mark.integration`, and skip when the `docker` CLI is missing or the daemon is not running. Rows needing the host's Ollama skip when `http://localhost:11434` does not answer; rows needing the repo's `.chroma/` skip when it is missing. The image is built once per test session under a test-only tag and removed afterwards; every container started is removed. Tests live in `backend/tests/docker/`.

### 6.1 DOCKER (the image and running containers)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DOCKER-1 | `docker build -f docker/Dockerfile -t <test-tag> .` (repo root) | exit 0 | AC-1 |
| DOCKER-2 | list the top level of `/app` in the image (`python -c` with `os.listdir`) | excluded names absent; `data` absent or empty; the four required files present | AC-2 |
| DOCKER-3 | `docker run --rm <tag>` (no mounts) | exit code 1; combined output mentions Chroma / ingest | AC-3 |
| DOCKER-4 | run detached with `-p <free port>:8000`, repo `data/` and `.chroma/` mounted | `/api/health` 200 `{"status":"ok"}` within 60 s; `GET /` 200 with HTML | AC-4 |
| DOCKER-5 | as DOCKER-4 + host Ollama; POST "Where is the coffee kept?" | ≥1 `token` line, `done` with non-empty `reply` | AC-5 |
| DOCKER-6 | as DOCKER-4, `OLLAMA_HOST=http://host.docker.internal:9` | 200, `error` line with `ERROR_MESSAGE`; health still 200 after | AC-6 |
| DOCKER-7 | `docker stop` a DOCKER-4 container | returns within 10 s; exit code ≠ 137 | AC-7 |
| DOCKER-8 | ingest with temp `data/` (one `.md`) and empty temp `.chroma/` mounted, host Ollama | exit 0; temp `.chroma/` non-empty | AC-8 |
| DOCKER-9 | `python -c "import fastapi, uvicorn, chromadb, langchain_ollama"` / `python -c "import sounddevice"` | exit 0 / non-zero | AC-9 |

### 6.2 COMPOSE (docker/compose.yaml, via `docker compose -f docker/compose.yaml config --format json` from the repo root)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| COMPOSE-1 | config, `OLLAMA_HOST` removed from env | services == `{"web"}`; build context = repo root, dockerfile `docker/Dockerfile`; exactly one port, published 8000 → target 8000 | AC-10 |
| COMPOSE-2 | same | exactly two bind mounts: `<repo>/data → /app/data` and `<repo>/.chroma → /app/.chroma` | AC-10 |
| COMPOSE-3 | same | `web` env `OLLAMA_HOST == DEFAULT_OLLAMA_HOST` | AC-11 |
| COMPOSE-4 | config with `OLLAMA_HOST=http://example:1234` in env | `web` env `OLLAMA_HOST == "http://example:1234"` | AC-11 |

### 6.3 FRONTEND (unit, no Docker)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| FRONTEND-1 | read every file under `frontend/` except images | none contains `localhost`, `127.0.0.1`, `0.0.0.0` or `:8000` (comments count); the page references `/api/chat` | AC-12 |

### 6.4 LOOK (manual, by the user in a browser)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| LOOK-1 | `docker compose -f docker/compose.yaml up --build`, open `http://localhost:8000` | page, logo and Laurel load | AC-19 |
| LOOK-2 | "Where is the coffee kept?", then "And the tea?" | correct answer; follow-up uses context | AC-19 |
| LOOK-3 | a beverage or food quantity question (tool path) | tool answer as outside Docker | AC-19 |
| LOOK-4 | quit Ollama on the Mac, ask a question | friendly error, page recovers after Ollama restarts | AC-6, AC-19 |
