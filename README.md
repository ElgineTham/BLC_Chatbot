# Bay Laurel Catering Chatbot

## Overview

This project is an **internal chatbot for Bay Laurel Catering employees**. It answers workplace questions from company knowledge—such as where supplies are stored, how to make drinks like lemonade, and similar day-to-day ops topics.

It uses a **RAG (Retrieval-Augmented Generation)** approach:

- Knowledge lives in markdown files under `data/` (recipes, supply locations, etc.).
- Those docs are chunked, embedded, and stored in a local **Chroma** vector database.
- At chat time, retrieval finds relevant chunks and **Gemini** (`gemini-3.5-flash-lite`) answers using only that context.

Chat and embeddings run on the Gemini API **free tier**: chat uses `gemini-3.5-flash-lite`, embeddings use `gemini-embedding-2` at 768 dimensions, and vectors stay in `.chroma/`. Ollama is no longer needed to run the chatbot; it is only needed for evals (the judge uses local `qwen2.5:7b`).

**Setup:**
1. Get a free key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Put it in a `.env` file in the repo root: `GOOGLE_API_KEY=your-key`.
3. For the GitHub Actions ingest workflow, add the same key as the repo secret `GOOGLE_API_KEY`.
4. Every chunk records the embedding model that built it. The committed `.chroma/` was built with `nomic-embed-text`, so it must be re-ingested (run the workflow, or `backend/scripts/ingest.py`) before chat starts; the chat entry points refuse to start on a store built by another model.

**Privacy:** on the free tier Google may use prompts to improve its products, so questions must not contain client personal data.

| Piece | Role |
|--------|------|
| `data/` | Source of truth (markdown recipes & supplies) |
| `backend/scripts/ingest.py` | Load → chunk → embed → store in Chroma |
| `backend/scripts/chat.py` | Employee Q&A loop in the terminal |
| `backend/scripts/web.py` | Web chat: API + the page in `frontend/` (spec 032) |
| `backend/scripts/voice_chat.py` | Push-to-talk voice version of the chat loop |
| `backend/src/blc/` | Feature packages the scripts use |
| `backend/tests/` | pytest suites (unit, integration, eval) |
| `frontend/` | The web chat page (HTML/CSS/JS, images in `frontend/assets/`) |
| `evals/` | Golden Q&A sets for measuring RAG quality |
| Chroma (`.chroma/`) | Vector database (HNSW ANN search) |
| Gemini API | Chat + embedding models (free tier, `GOOGLE_API_KEY`) |
| Ollama | Local judge model for evals only |

---

## Web chat

```bash
poetry run python backend/scripts/web.py                 # http://127.0.0.1:8000 on this Mac
poetry run python backend/scripts/web.py --host 0.0.0.0  # also reachable from a phone on the same Wi-Fi
```
Needs `GOOGLE_API_KEY` and the Chroma store (`backend/scripts/ingest.py`). The chat history lives in the browser tab; "New chat" clears it.

---

## Docker

One image runs the web chat. It holds the code and Python dependencies only; `data/` and `.chroma/` are mounted from the host, and no Ollama is needed on the host (the model calls go to Gemini).

**Prerequisites:** Docker; `GOOGLE_API_KEY` set in your shell (compose passes it to the container); `data/` and `.chroma/` present in the repo root (compose refuses to start if either is missing).

Run every command from the repo root:

```bash
mkdir -p .chroma    # first time on a new machine: compose refuses a missing .chroma/
docker compose -f docker/compose.yaml run --rm web python backend/scripts/ingest.py   # build/update .chroma/ from data/
docker compose -f docker/compose.yaml up --build        # web chat on http://localhost:8000
docker compose -f docker/compose.yaml up --build        # rebuild after code changes
```

---

## Knowledge and vector store in git

- The markdown knowledge files (`data/**/*.md`) and the Chroma store (`.chroma/`) are **committed**, so a fresh clone already has an up-to-date vector store. **The repo is public**, so everything under `data/` and `.chroma/` (which stores chunk text verbatim) is publicly readable.
- Ingest detects changes by file **content hash**, not modification time: it re-embeds only files whose content changed and removes the chunks of deleted files.
- The GitHub Actions workflow `.github/workflows/ingest.yml` owns `.chroma/`. When a `data/**/*.md` file is added, changed or deleted on `main`, it re-ingests and commits the updated `.chroma/` (commit message contains `[skip ci]`). Don't commit local `.chroma/` changes; run `git restore .chroma` before pulling if you ran ingest locally.
- Only `data/**/*.md` is committed. JSON tool data (recipes, pull-sheet menu and rules) and photos stay gitignored, so copy them to a new machine by hand.

## Voice chat

You can ask questions out loud and hear the answer read back:

```bash
poetry run python backend/scripts/voice_chat.py
```

- **Push-to-talk:** press Enter to start recording, ask your question, then press Enter again to stop. The bot prints what it heard (`You (heard): …`), prints the answer, then reads it aloud. Say "quit", "exit" or "bye" (or press Ctrl+C) to leave. If the recording is too short or silent, it prints `(didn't catch that)`.
- **Spoken answers skip clutter:** file paths, `[1]`-style citations and markdown are printed but not read aloud.
- **First run downloads models** into `.models/` (gitignored): the faster-whisper `small.en` speech-to-text model and the Piper `en_US-lessac-medium` voice. After that, voice chat works fully offline and audio never leaves your machine.
- **macOS microphone permission:** the first time you record, macOS asks whether your terminal app (Terminal, iTerm, VS Code, …) may use the microphone. Allow it. If you denied it earlier, enable it under System Settings → Privacy & Security → Microphone, then restart the terminal.
- You still need the Chroma store (`backend/scripts/ingest.py`) and `GOOGLE_API_KEY` set, just as for text chat.

---

## Workflow (user prompt → answer)

This is what happens each time an employee asks a question in `backend/scripts/chat.py`:

```text
User prompt
    → (optional) summarize long chat history
    → embed the prompt
    → search Chroma for top matching chunks
    → build a grounded prompt (history + context + question)
    → Gemini generates the answer
```

### 1. User submits a prompt

The chat loop waits for input (for example: “Where is the coffee?”).  
Commands `quit`, `exit`, or `bye` end the session.

### 2. Chat history check (before retrieval)

History is an in-memory list of `{role, content}` items (`user`, `assistant`, or `summary`).  
Only prior Q&A (and summaries) are stored—not system text or retrieved chunks.

If the **existing history** is over ~2000 tokens (estimated as characters ÷ 4):

1. Gemini summarizes that prior history.
2. History is replaced with a single `{role: "summary", content: "..."}` item.
3. The **current** question is not included in the summary.

### 3. Prompt → embeddings

The current question is sent to `gemini-embedding-2` (Gemini API).  
That model turns the text into a vector (a list of numbers representing meaning).  
This is the **same embedding model** used at ingest time, so questions and documents share one vector space.

### 4. Vector search in Chroma

Chroma compares the question embedding to stored chunk embeddings using its default **HNSW** approximate nearest-neighbor index and returns the **top 3** most similar documents.

Each hit includes:

- the chunk text (`page_content`)
- metadata such as `source` (e.g. `data/supplies/coffee.md`)

If nothing is retrieved, the bot says it doesn’t know and suggests rephrasing—without inventing an answer.

### 5. Build the LLM prompt

The app assembles a grounded prompt shaped like:

```text
System: answer only from context; cite sources; …
Chat history: …
Context:
[1] (data/supplies/coffee.md)
…
[2] …
Question: …
Answer:
```

Embeddings are **not** passed to the LLM. Only the **retrieved text** (plus history and the question) is.

### 6. Generate the result

`gemini-3.5-flash-lite` reads that prompt and writes the employee-facing answer.  
It is instructed to use **only** the provided context, stay practical, and **cite source paths**.

The reply is shown in the terminal, then appended to history as:

```text
{"role": "user", "content": "<question>"}
{"role": "assistant", "content": "<answer>"}
```

### End-to-end picture

```text
┌─────────────┐     embed      ┌─────────────┐     top 3      ┌─────────────┐
│ User prompt │ ─────────────► │   Chroma    │ ─────────────► │   Gemini    │
└─────────────┘  embed query   │  (.chroma)  │   text chunks  │ 3.5 flash   │
                               └─────────────┘                └──────┬──────┘
                                                                     │
                                                                     ▼
                                                              Employee
                                                              answer
                                                              (+ sources)
```

**Ingest (separate, offline step):** markdown in `data/` is chunked (one short file → one chunk; long files split on `##`), embedded with `gemini-embedding-2`, and written to Chroma. Chat only **reads** that store; it does not re-ingest on every question.
