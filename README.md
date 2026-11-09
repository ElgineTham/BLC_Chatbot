# Bay Laurel Catering Chatbot

## Overview

This project is an **internal chatbot for Bay Laurel Catering employees**. It answers workplace questions from company knowledge—such as where supplies are stored, how to make drinks like lemonade, and similar day-to-day ops topics.

It uses a **RAG (Retrieval-Augmented Generation)** approach:

- Knowledge lives in markdown files under `data/` (recipes, supply locations, etc.).
- Those docs are chunked, embedded, and stored in a local **Chroma** vector database.
- At chat time, a local **Ollama** stack retrieves relevant chunks and has **Qwen 2.5 7B** answer using only that context.

No cloud LLM API is required for the current setup: embeddings use `nomic-embed-text`, chat uses `qwen2.5:7b`, and vectors stay in `.chroma/`.

| Piece | Role |
|--------|------|
| `data/` | Source of truth (markdown recipes & supplies) |
| `scripts/ingest.py` | Load → chunk → embed → store in Chroma |
| `scripts/chat.py` | Employee Q&A loop (retrieve + generate) |
| `scripts/voice_chat.py` | Push-to-talk voice version of the chat loop |
| `tests/` | Retrieval & generation eval runners (pytest) |
| `evals/` | Golden Q&A sets for measuring RAG quality |
| Chroma (`.chroma/`) | Vector database (HNSW ANN search) |
| Ollama | Local embedding + chat models |

---

## Voice chat

You can ask questions out loud and hear the answer read back:

```bash
poetry run python scripts/voice_chat.py
```

- **Push-to-talk:** press Enter to start recording, ask your question, then press Enter again to stop. The bot prints what it heard (`You (heard): …`), prints the answer, then reads it aloud. Say "quit", "exit" or "bye" (or press Ctrl+C) to leave. If the recording is too short or silent, it prints `(didn't catch that)`.
- **Spoken answers skip clutter:** file paths, `[1]`-style citations and markdown are printed but not read aloud.
- **First run downloads models** into `.models/` (gitignored): the faster-whisper `small.en` speech-to-text model and the Piper `en_US-lessac-medium` voice. After that, voice chat works fully offline and audio never leaves your machine.
- **macOS microphone permission:** the first time you record, macOS asks whether your terminal app (Terminal, iTerm, VS Code, …) may use the microphone. Allow it. If you denied it earlier, enable it under System Settings → Privacy & Security → Microphone, then restart the terminal.
- You still need the Chroma store (`scripts/ingest.py`) and Ollama running, just as for text chat.

---

## Workflow (user prompt → answer)

This is what happens each time an employee asks a question in `scripts/chat.py`:

```text
User prompt
    → (optional) summarize long chat history
    → embed the prompt
    → search Chroma for top matching chunks
    → build a grounded prompt (history + context + question)
    → Qwen generates the answer
```

### 1. User submits a prompt

The chat loop waits for input (for example: “Where is the coffee?”).  
Commands `quit`, `exit`, or `bye` end the session.

### 2. Chat history check (before retrieval)

History is an in-memory list of `{role, content}` items (`user`, `assistant`, or `summary`).  
Only prior Q&A (and summaries) are stored—not system text or retrieved chunks.

If the **existing history** is over ~2000 tokens (estimated as characters ÷ 4):

1. Qwen summarizes that prior history.
2. History is replaced with a single `{role: "summary", content: "..."}` item.
3. The **current** question is not included in the summary.

### 3. Prompt → embeddings

The current question is sent to `nomic-embed-text` via Ollama.  
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

`qwen2.5:7b` (via Ollama) reads that prompt and writes the employee-facing answer.  
It is instructed to use **only** the provided context, stay practical, and **cite source paths**.

The reply is shown in the terminal, then appended to history as:

```text
{"role": "user", "content": "<question>"}
{"role": "assistant", "content": "<answer>"}
```

### End-to-end picture

```text
┌─────────────┐     embed      ┌─────────────┐     top 3      ┌─────────────┐
│ User prompt │ ─────────────► │   Chroma    │ ─────────────► │    Qwen     │
└─────────────┘  nomic-embed   │  (.chroma)  │   text chunks  │  2.5:7b     │
                               └─────────────┘                └──────┬──────┘
                                                                     │
                                                                     ▼
                                                              Employee
                                                              answer
                                                              (+ sources)
```

**Ingest (separate, offline step):** markdown in `data/` is chunked (one short file → one chunk; long files split on `##`), embedded with `nomic-embed-text`, and written to Chroma. Chat only **reads** that store; it does not re-ingest on every question.
