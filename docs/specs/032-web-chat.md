# Spec 032: Web chat (backend API + mobile-first chat page with Laurel)

- **Status:** approved (done: closed by the user; see closing note)
- **Date:** 2026-11-17

## 1. Goal
Give staff a browser chat instead of the terminal. A small FastAPI backend wraps the existing planned flow (`run_planned_turn`, the same flow `scripts/chat.py main()` uses) and **streams the answer word by word**. The same server hosts a single chat page: simple, elegant and cute. It has the Bay Laurel logo, the logo's greens, gentle animations, and **Laurel**, an animated bay-leaf character who reacts to the conversation. It runs on the developer's Mac with Ollama, works on a phone over Wi-Fi, and can be added to the phone's home screen. The server keeps no chat state; the browser holds the history. That is what the later Docker and Cloud Run steps need.

## 2. Out of scope
- Gemini or any other model provider, Docker, Cloud Run, HTTPS, login/auth, rate limiting (later specs).
- A trace/"details" panel, voice input/output, pull-sheet screens.
- Storing chats on the server, or across browser sessions.
- Offline support (no service worker), push notifications.
- Rendering Markdown in answers (only line breaks are kept; see AC-15).
- Any change to the flow, planner, tools, retrieval, prompts or models. `scripts/chat.py` and everything under `src/blc/` except the new `src/blc/web/` stay unchanged.

## 3. Interface contract
Everything below is importable from `web` (`scripts/web.py`, the entry point). Backend code lives in `src/blc/web/`; the page lives in `frontend/` (§4.5).

```python
@dataclass(frozen=True)
class ChatTurn:
    reply: str                          # the full answer
    history: list[dict[str, str]]       # the history to send with the next question

Answerer = Callable[[str, list[dict[str, str]], Callable[[str], None]], ChatTurn]
# answer(question, history, on_token) -> ChatTurn
# Calls on_token with each piece of the reply, in order, while it runs.

def create_app(answer: Answerer) -> fastapi.FastAPI:
    """The web app (API + page). Calls `answer` only from POST /api/chat."""

def build_answerer(llm: BaseChatModel, store, drink_catalog=None) -> Answerer:
    """The real answerer: the planned flow, exactly as chat.py main() runs it
    (history summarized when too long, then run_planned_turn with on_token)."""

def main(argv: list[str] | None = None) -> int:
    """CLI: --host (default "127.0.0.1"), --port (default 8000). Exits 1 with a
    message on stderr if .chroma/ is missing; otherwise serves until stopped."""

MAX_QUESTION_CHARS = 2000
ALLOWED_ROLES = ("user", "assistant", "summary")
ERROR_MESSAGE = "Sorry, something went wrong on my end. Please try again."
LOGO_URL = "/assets/blc_logo.png"
MANIFEST_URL = "/manifest.webmanifest"
```

**HTTP API**
| Method + path | Request | Response |
|---|---|---|
| `GET /` | — | 200 `text/html`: the chat page |
| `GET /api/health` | — | 200 JSON `{"status": "ok"}` |
| `GET` `LOGO_URL` | — | 200 `image/png`, the same bytes as `docs/specs/032-assets/blc_logo.png` |
| `GET` `MANIFEST_URL` | — | 200 JSON web app manifest (§4.3) |
| `POST /api/chat` | JSON `{"question": str, "history": list}` (`history` optional, default `[]`) | 200 `application/x-ndjson` stream (§4.2), or 400 JSON `{"error": str}` |

**Running it:** `poetry run python scripts/web.py` (Mac only), `poetry run python scripts/web.py --host 0.0.0.0` (reachable from a phone on the same Wi-Fi). Uses the same models, `.chroma/` and rules files as `scripts/chat.py`.

**Integration setup** (AC-10 / API-13 only): `llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)` and `store = build_domain_store()`, all imported from `chat` (`scripts/chat.py`), then `create_app(build_answerer(llm, store))`. Do not build a Chroma store by hand.

## 4. Inputs and outputs

### 4.1 `POST /api/chat` validation (400, `answer` never called)
| Request body | Result |
|---|---|
| `question` missing, not a string, blank or whitespace-only | 400 |
| `question` longer than `MAX_QUESTION_CHARS` after stripping | 400 |
| `history` present but not a list (including `null`); an item that is not an object with string `role` and string `content`; `role` not in `ALLOWED_ROLES` | 400 |
| body not JSON, or JSON that is not an object (e.g. `[]`, `"x"`) | 400 |
| valid | 200 stream; `answer` gets the **stripped** question and the history **exactly as sent** |

### 4.2 The stream
One JSON object per line, in order:
- zero or more `{"type": "token", "text": <piece>}`: one per `on_token` call, same text, same order;
- then exactly one final line, either
  - `{"type": "done", "reply": <ChatTurn.reply>, "history": <ChatTurn.history>}`, or
  - `{"type": "error", "message": ERROR_MESSAGE}` if `answer` raises (tokens sent before it raised stay in the stream; the exception text never appears in the response).

### 4.3 Manifest
JSON with `name` = `"Bay Laurel Catering Assistant"`, `short_name` = `"Laurel"`, `start_url` = `"/"`, `display` = `"standalone"`, a `theme_color` and `background_color`, and `icons` containing a PNG of `sizes` `"192x192"` and one of `"512x512"`; every icon `src` returns 200 with an image content type.

### 4.4 The page (look and behaviour)
- **Header:** the logo (`LOGO_URL`, alt text "Bay Laurel Catering") and a "New chat" button.
- **Palette** taken from the logo: soft leaf greens on a warm off-white, charcoal text. Elegant, calm, lots of white space. Serif headings that echo the logo. No dark or loud colours.
- **Laurel:** a small bay leaf with a face (eyes, mouth, rosy cheeks) in the logo's green, drawn in code (inline SVG + CSS, no image files, no animation library). Laurel sits by the input and next to each of the bot's messages. States:
  | State | When | Animation |
  |---|---|---|
  | idle | nothing happening | gentle bob, blinks every few seconds |
  | thinking | question sent, no token yet | tilts/wiggles, three bouncing dots |
  | talking | tokens arriving | mouth opens and closes |
  | happy | `done` received | small bounce and sparkle, then idle |
  | oops | `error` or network failure | droops, worried face, then idle |
- **Empty chat:** Laurel waves with the greeting "Hi, I'm Laurel! Ask me where things are kept, or how much to bring for an event." and three suggestion chips: "Where is the coffee kept?", "How many cups for 80 guests?", "How many forks for 70 guests?". Tapping a chip sends it.
- **Messages:** user bubbles on the right, Laurel's on the left. New bubbles fade and slide in. The reply appears piece by piece as tokens arrive, and the view keeps scrolled to the newest text.
- **Input:** Enter sends, Shift+Enter makes a new line; blank input can't be sent; the input and send button are disabled while an answer is in progress.
- **History:** after each `done`, the page keeps `history` from the response and sends it with the next question. It survives a page reload in the same tab. "New chat" clears it and shows the greeting again.

### 4.5 Layout
```
scripts/web.py              entry point: CLI + wiring (backend)
src/blc/web/                backend code (Python only)
frontend/                   the page: plain HTML/CSS/JS, no build step, no src/ or scripts/
  index.html
  style.css
  app.js
  manifest.webmanifest
  assets/                   every image: blc_logo.png (copied from docs/specs/032-assets/), app icons
```
The backend serves `frontend/`: the page at `/`, `frontend/assets/` at `/assets/`, and the manifest at `MANIFEST_URL`. Laurel is drawn inline in the page, not as an image file in `assets/`, so her eyes and mouth can be animated.

## 5. Acceptance criteria
- **AC-1:** `GET /` returns 200 HTML that references `LOGO_URL` and `MANIFEST_URL`, and does not call `answer`.
- **AC-2:** `GET /api/health` returns 200 `{"status": "ok"}` and does not call `answer`.
- **AC-3:** `GET LOGO_URL` returns 200 `image/png`, with bytes equal to `docs/specs/032-assets/blc_logo.png`.
- **AC-4:** `GET MANIFEST_URL` returns the manifest in §4.3, and each icon it lists can be fetched as an image.
- **AC-5:** Invalid chat requests (§4.1) return 400 with JSON `{"error": <non-empty string>}`, and `answer` is never called.
- **AC-6:** For a valid request, `answer` is called once, with the stripped question and the history exactly as sent. The stream has one `token` line per `on_token` call (same text, same order, including non-ASCII text, emoji and newlines inside a piece) and then one `done` line with the answerer's `reply` and `history`.
- **AC-7:** An answerer that calls `on_token` zero times still gives exactly one `done` line.
- **AC-8:** If `answer` raises, the stream ends with exactly one `error` line carrying `ERROR_MESSAGE`. Tokens sent before the error are still present, and the exception's message appears nowhere in the response. The app keeps serving the next request.
- **AC-9:** The server keeps no state between requests: each call to `answer` gets only the history sent in that request.
- **AC-10** *(integration)*: With real Ollama and `.chroma/`, `create_app(build_answerer(...))` answers "Where is the coffee kept?" with at least one `token` line and a `done` line whose `reply` is non-empty and equals the joined tokens. Sending that `done.history` with "And the tea?" also gives a `done` line. Skips when Ollama is not running or `.chroma/` is missing.
- **AC-11** *(manual)*: The page matches §4.4: logo in the header, logo palette, serif headings, greeting and three chips, bubbles that fade and slide in, word-by-word replies, and input rules.
- **AC-12** *(manual)*: Laurel is inline SVG + CSS and shows all five states in §4.4 at the right moments.
- **AC-13** *(manual)*: Follow-ups work: the page sends the last `done.history`, keeps it across a reload in the same tab, and "New chat" clears it.
- **AC-14** *(manual)*: Errors are friendly. An `error` line, a network failure or a non-200 response shows a message in Laurel's bubble and the oops state, and the input is enabled again.
- **AC-15** *(manual)*: Replies are shown as plain text with line breaks kept; a reply containing `<b>` or `<script>` shows those characters and does not run or format them.
- **AC-16** *(manual)*: Mobile-first. At 360 px wide: no sideways scrolling, tap targets at least 44 px, input pinned to the bottom and visible above the phone keyboard. It can be added to the home screen (manifest + `apple-touch-icon`).
- **AC-17** *(manual)*: Under `prefers-reduced-motion: reduce`, bobbing, wiggling, bouncing and sliding are switched off (state changes still show).
- **AC-18** *(manual)*: Accessibility: the logo has alt text, Laurel is hidden from screen readers, new messages are announced (`aria-live`), and every control has a label.
- **AC-19** *(manual)*: The page loads nothing from other sites (no CDN, web fonts or analytics), has no JS framework and needs no build step.
- **AC-20** *(manual)*: Layout as §4.5. Backend follows `CLAUDE.md`: `scripts/web.py` holds the CLI and wiring; the API is in `src/blc/web/`, split by job, with no HTML/CSS/JS in it. Every page file is under `frontend/`, and every image under `frontend/assets/`. Dependencies added: `fastapi`, `uvicorn`, and `httpx` (for tests) only. Only `scripts/web.py`, `src/blc/web/`, `frontend/`, `pyproject.toml`, `poetry.lock` and `README.md` change, plus the new tests.
- **AC-21:** Nothing regresses: the existing unit tests that passed before still pass.

## 6. Test cases
API and PAGE rows use `create_app(fake_answer)` with FastAPI's `TestClient`. A fake answerer records its arguments, calls `on_token` with scripted pieces and returns a scripted `ChatTurn` (or raises). LOOK rows are checked by hand in a browser (Mac and phone).

### 6.1 API
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| API-1 | `{"question": "  Where is the coffee?  "}`, fake emits "The ", "coffee", " is here." | `answer` got "Where is the coffee?" and `[]`; 3 token lines in order; done with fake's reply and history | AC-6 |
| API-2 | question + 2-turn history (user/assistant) | `answer` got that history unchanged; done.history = fake's returned history | AC-6 |
| API-3 | history containing a `{"role": "summary", ...}` item | accepted (200) and passed unchanged | AC-5, AC-6 |
| API-4 | pieces "café ☕", "line1\nline2" | token texts round-trip exactly | AC-6 |
| API-5 | fake emits no tokens | exactly one line, a done | AC-7 |
| API-6 | fake emits "Hi" then raises `RuntimeError("db password 123")` | token "Hi", then one error line with `ERROR_MESSAGE`; "db password 123" not in body; next request succeeds | AC-8 |
| API-7 | question `""`, `"   "`, missing, `42` | 400 with `error`; `answer` not called | AC-5 |
| API-8 | question of `MAX_QUESTION_CHARS` chars / one char more | 200 / 400 | AC-5 |
| API-9 | history `"oops"`; item `{"role": "user"}`; item `{"role": "system", "content": "x"}`; item content `5` | 400 each; `answer` not called | AC-5 |
| API-10 | body is not JSON; body is `[]`; `{"question": "hi", "history": null}` | 400 each | AC-5 |
| API-11 | two requests, first with history H1, second with `[]` | second call gets `[]` | AC-9 |
| API-12 | `GET /api/health` | 200 `{"status": "ok"}`; `answer` not called | AC-2 |
| API-13 *(integration)* | real answerer, "Where is the coffee kept?", then "And the tea?" with returned history | tokens + non-empty done; joined tokens == reply; follow-up gives done | AC-10 |

### 6.2 PAGE
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PAGE-1 | `GET /` | 200, `text/html`, body contains `LOGO_URL` and `MANIFEST_URL`; `answer` not called | AC-1 |
| PAGE-2 | `GET LOGO_URL` | 200, `image/png`, bytes == `docs/specs/032-assets/blc_logo.png` | AC-3 |
| PAGE-3 | `GET MANIFEST_URL` | name, short_name, start_url, display as §4.3; 192x192 and 512x512 PNG icons | AC-4 |
| PAGE-4 | each manifest icon `src` | 200, content type starts with `image/` | AC-4 |
| PAGE-5 | existing unit suite | still passes | AC-21 |

### 6.3 LOOK *(manual, browser)*
| ID | Situation | Expected | Covers |
|---|---|---|---|
| LOOK-1 | open the page, empty chat | logo, Laurel waving, greeting, 3 chips; idle bob + blink | AC-11, AC-12 |
| LOOK-2 | tap "How many forks for 70 guests?" | thinking → talking as words stream → happy → idle | AC-11, AC-12 |
| LOOK-3 | ask "Where is the coffee kept?" then "And the tea?" | the follow-up is understood; reload keeps the chat; New chat clears it | AC-13 |
| LOOK-4 | stop Ollama, ask something | friendly message, oops state, input usable again | AC-14 |
| LOOK-5 | read the page code that shows replies; ask a question whose answer has several lines | replies are inserted as text, never as HTML; line breaks kept | AC-15 |
| LOOK-6 | phone at 360 px over Wi-Fi (`--host 0.0.0.0`), keyboard open; add to home screen | no sideways scroll, input visible, opens full-screen with icon | AC-16 |
| LOOK-7 | OS "reduce motion" on | no bob, wiggle, bounce or slide | AC-17 |
| LOOK-8 | read the page source and network tab | no other-site requests, no framework, labels and aria-live present | AC-18, AC-19 |
| LOOK-9 | read the changed files | structure, dependencies and file list as AC-20 | AC-20 |

## Closing note (2026-11-17)
Closed by the user. All 64 API/PAGE unit tests and the API-13 integration test pass. Full unit suite: 25 failures + 2 collection errors, none in `tests/web/` and none caused by this spec (no existing source file changed; failures are the spec 024 baseline plus napkin/domain-retrieval work from spec 031 and the food-wiring CALL-5 prompt check).

Carried over to a later spec (from the planner's manual review):
- **AC-12:** Laurel is reused through SVG `<use>`, so the per-state CSS likely cannot reach her eyes, mouth or body; her states probably don't animate. Needs a browser check and a fix.
- **AC-11:** the palette is sage (`#8fb996`), not the logo's yellow-green. Palette to be decided by the user.
- **AC-20:** `blc.web.answerer.build_answerer` imports `summarize_if_long` from the `scripts/chat.py` entry point (package depending on an entry point). Move it into a package when `chat.py` is next touched.
- `uvicorn` was capped `<0.40`, downgrading it from 0.54 (already installed via chromadb). Loosen the cap.
- `README.md` has no "Web chat" section yet.
