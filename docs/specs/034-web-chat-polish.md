# Spec 034: Web chat polish (Laurel's animations, logo palette, clean-ups from 032/033)

- **Status:** approved (done: closed by the user; see closing note)
- **Date:** 2026-11-17

## 1. Goal
Finish what spec 032's review found and 033 carried over:
- **Laurel really animates.** Each of her five states has to be visible in a real browser. Spec 032's review found they probably weren't.
- **The page uses the logo's yellow-green.**
- **The web package stops importing the `chat.py` entry point.** History summarizing moves into a package.
- **`uvicorn` is no longer downgraded.**
- **One moved test runs from the right folder.**

No change to the API, the stream format, the chat flow or the answers.

## 2. Out of scope
- Any change to `POST /api/chat`, the stream lines, validation, `ERROR_MESSAGE` or the other spec 032 constants.
- Any change to what the history summary does: when it triggers, its prompt, its output.
- New UI features (trace panel, voice, dark mode), Docker, Gemini.
- The 29 baseline failures/errors (`docs/specs/033-baseline-failures.txt`).

## 3. Interface contract
**History summarizing moves to a package.**
```python
# backend/src/blc/history/  (new package, importable as blc.history)
HISTORY_TOKEN_LIMIT: int   # same value as chat.HISTORY_TOKEN_LIMIT today (2000)

def summarize_if_long(llm: BaseChatModel, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Unchanged behaviour: history at or under the limit is returned as is; over it,
    one {"role": "summary", "content": <llm summary>} item replaces it. Prints nothing."""
```
- `chat` (`backend/scripts/chat.py`) keeps exporting every name it exports today, and `chat.summarize_if_long is blc.history.summarize_if_long`.
- `blc.web` imports nothing from `chat`. Importing `blc.web` with only `backend/src` on `sys.path` works, and `"chat"` is not in `sys.modules` afterwards.

**Dependencies:** `pyproject.toml` allows `uvicorn` 0.54 or newer (below 1.0), and the locked and installed `uvicorn` is at least 0.54. Nothing else in the dependencies changes.

**Palette** (taken from the logo; exact values):
| Role | Colour |
|---|---|
| leaf (Laurel's body, outlines, user bubbles' tint) | `#D3DB7D` (logo leaf) |
| leaf light (Laurel's inner fill, soft backgrounds, borders) | `#EAF1D3` (logo leaf interior) |
| accent (send button, New chat, headings) | `#5E7A1F` deep olive (white text on it ≈ 4.9:1, WCAG AA) |
| page background | `#FAF8F1` warm off-white |
| text | `#2B2B2B` charcoal (as the logo's lettering) |
The manifest has `theme_color` = `"#5E7A1F"` and `background_color` = `"#FAF8F1"`; the page's `<meta name="theme-color">` is `#5E7A1F`.

**Laurel's animation rules** (spec 032 §4.4 states unchanged):
- **Active Laurels:** the one by the input and the one on the newest bot message. They show all five states (idle bob + blink, thinking wiggle + dots, talking mouth, happy hop + sparkle, oops droop + worried brows).
- **Laurels on older messages** sit still, apart from an occasional blink.
- Each Laurel's state is independent; changing one never changes another.

## 4. Inputs and outputs
| Situation | Before | After |
|---|---|---|
| question sent, answer streaming | Laurel likely static (CSS didn't reach the reused SVG parts) | the input Laurel and the newest bot Laurel go thinking → talking → happy → idle, visibly |
| error | Laurel likely static | both active Laurels show oops, then idle |
| third answer arrives | every Laurel on screen bobs | only the active two animate; older ones only blink |
| page colours | sage `#8FB996` / `#4F7D5C` | logo yellow-green palette (§3) |
| `import blc.web` | lazily imports `chat` when building the answerer | never imports `chat` |
| `uvicorn` | 0.39 (downgraded by spec 032) | ≥ 0.54 |

## 5. Acceptance criteria
- **AC-1:** `blc.history.summarize_if_long` exists with the signature in §3. History of at most `HISTORY_TOKEN_LIMIT` tokens (4 characters of content count as 1 token, as today; see HIST-6/7) is returned unchanged with no model call. Longer history gives one `summary` item holding the model's reply. `chat.summarize_if_long is blc.history.summarize_if_long`, and `chat.HISTORY_TOKEN_LIMIT == blc.history.HISTORY_TOKEN_LIMIT == 2000`.
- **AC-2:** `blc.web` doesn't import `chat`. In a fresh interpreter with only `backend/src` on `sys.path`, `import blc.web` succeeds and `"chat" not in sys.modules`. `build_answerer` still summarizes long history before running the turn (spec 032 API-13 still passes).
- **AC-3:** `uvicorn` installed version is at least 0.54, and `pyproject.toml`'s `uvicorn` constraint allows 0.54. `fastapi` and `httpx` constraints are unchanged.
- **AC-4:** The manifest's `theme_color` and `background_color` are the §3 accent and background. *(manual)* The page's colours follow §3, and white-on-accent text is at least 4.5:1.
- **AC-5** *(manual, real browser)*: In Chrome on the Mac, and Safari on iPhone if available, each of the five states is visibly animated on the active Laurels at the right moment (spec 032 LOOK-1, LOOK-2, LOOK-4). The planner checks this in a browser, not only by reading code.
- **AC-6** *(manual, real browser)*: After three answers, only the active two Laurels animate. Older Laurels only blink, and a state change on one Laurel doesn't change another.
- **AC-7** *(manual)*: Under `prefers-reduced-motion: reduce`, motion is still off and state changes still show (spec 032 AC-17).
- **AC-8:** The test fix carried over from spec 033: `backend/tests/pull_sheet/test_structure.py::test_ac6_cli_from_project_root` runs the CLI with the **repo root** (the folder holding `pyproject.toml`) as its working directory, and passes. Its assertions are unchanged.
- **AC-9:** Nothing regresses. The spec 032 web tests and the spec 033 layout tests all pass. The unit suite's failing/erroring IDs are exactly those in `docs/specs/033-baseline-failures.txt` (`tests/` read as `backend/tests/`).
- **AC-10** *(manual)*: Only `frontend/`, `backend/src/blc/history/`, `backend/src/blc/web/`, `backend/scripts/chat.py` (summarizing moved out, names re-exported), `pyproject.toml`, `poetry.lock` and the tests change. Structure follows `CLAUDE.md`. The page loads nothing from other sites and has no framework or build step (spec 032 AC-19).

## 6. Test cases
Unit rows use fakes, with no Ollama, Chroma or network. A **fake model** records its calls and returns a fixed `AIMessage` content (e.g. "SUMMARY"). **Long history** is user/assistant items whose total content is well over `HISTORY_TOKEN_LIMIT × 4` characters. **Short history** is two short items.

### 6.1 HIST
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| HIST-1 | `summarize_if_long(fake, short)` | returns `short` unchanged (equal); fake never called | AC-1 |
| HIST-2 | `summarize_if_long(fake, [])` | `[]`; fake never called | AC-1 |
| HIST-3 | `summarize_if_long(fake, long)` | exactly one item, `role == "summary"`, `content == "SUMMARY"`; fake called once | AC-1 |
| HIST-4 | `chat.summarize_if_long`, `chat.HISTORY_TOKEN_LIMIT` | `is blc.history.summarize_if_long`; both limits `== 2000` | AC-1 |
| HIST-5 | subprocess, `sys.path` = `backend/src` only: `import blc.web; print("chat" in sys.modules)` | exit 0, prints `False` | AC-2 |
| HIST-6 | `summarize_if_long(fake, [{"role": "user", "content": "a" * 8000}])` (exactly the limit: 4 characters = 1 token) | returned unchanged; fake never called | AC-1 |
| HIST-7 | same with `"a" * 8001` (one token over) | one `summary` item with the fake's reply; fake called once | AC-1 |

### 6.2 DEPS
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DEPS-1 | `importlib.metadata.version("uvicorn")` | ≥ 0.54 | AC-3 |
| DEPS-2 | read `pyproject.toml` dependencies | `uvicorn` constraint allows 0.54; `fastapi (>=0.115,<0.120)` and `httpx (>=0.27,<0.29)` unchanged | AC-3 |
| DEPS-3 | `GET /manifest.webmanifest` via `create_app(fake)` | `theme_color` == `#5E7A1F`, `background_color` == `#FAF8F1` (case-insensitive) | AC-4 |
| DEPS-4 | `test_ac6_cli_from_project_root` | runs with cwd = repo root; passes | AC-8 |
| DEPS-5 | full unit suite | failing/erroring IDs == baseline; web and layout tests pass | AC-9 |

### 6.3 LOOK *(manual, real browser)*
| ID | Situation | Expected | Covers |
|---|---|---|---|
| LOOK-1 | open the page | yellow-green palette; Laurel waves, then idles (bob + blink) | AC-4, AC-5 |
| LOOK-2 | ask "How many forks for 70 guests?" | input + newest Laurel: thinking wiggle and dots → talking mouth → happy hop + sparkle → idle | AC-5 |
| LOOK-3 | stop Ollama, ask something | oops droop + worried brows, then idle | AC-5 |
| LOOK-4 | ask three questions | older Laurels only blink; only the two active ones move | AC-6 |
| LOOK-5 | reduce motion on | no motion, states still visible | AC-7 |
| LOOK-6 | read the diff | file list and structure as AC-10 | AC-10 |

## Closing note (2026-11-17)
Closed by the user.

**Tests.** Test-evaluator: FAIL on the first audit (no boundary case for AC-1), fixed by adding HIST-6/7 to the spec; PASS on re-audit. Implementation-evaluator: every spec 034 test passes. The unit suite's failing/erroring IDs are identical to `033-baseline-failures.txt` (29), checked by diff.

**Browser check** (Chrome, computed styles, port 8001): AC-4 palette exact; AC-5 all five states animate, and a real turn ran thinking → talking → happy → idle; AC-6 only the active Laurels move, older ones only blink, states independent; error shows oops and the input re-enables. AC-7: the reduced-motion rules are present, but the OS setting could not be toggled, so they were not seen in action.

**Minor findings, carried over:**
1. **AC-10 not fully met (duplication):** `backend/scripts/chat.py` imports `summarize_if_long` and `HISTORY_TOKEN_LIMIT` from `blc.history`, but still keeps its own copies of `count_tokens`, `history_tokens`, `format_history`, `summarize_history` and `SUMMARIZE_PROMPT`. Those should come from `blc.history`, with the names still exported from `chat`.
2. **Dead CSS rule:** in `frontend/style.css`'s reduced-motion block, `[data-state="talking"] .mouth-sad { … opacity: 0; }` does nothing (the sad mouth is already hidden while talking), and the next line's indentation is off.
3. **Answer quality (not this spec):** "Where is the coffee kept?" opened with "The question does not specify which coffee-related supplies…" before giving the location.
4. **Observed:** a short tool answer ("Forks: 120 …") can skip the visible talking state (thinking → happy), because the whole reply arrives at once. Acceptable.
