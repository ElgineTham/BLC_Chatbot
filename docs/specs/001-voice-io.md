# Spec 001: Push-to-talk voice chat

- **Status:** approved (revision 5, see §10)
- **Date:** 2026-11-08

## 1. Goal
Let employees talk to the chatbot and hear the answer. A new terminal app, `scripts/voice_chat.py`, records a spoken question (push-to-talk), transcribes it locally with faster-whisper, runs it through the existing RAG pipeline, prints the answer, then speaks it with Piper, skipping file paths and markdown. To share the pipeline, the per-question logic in `scripts/chat.py` moves into one function, `answer_turn`, used by both apps. Text chat behaviour is unchanged.

## 2. Out of scope
- Hands-free listening (wake word or automatic end-of-speech detection). Recording starts and stops only on Enter.
- Interrupting the voice mid-answer, or a maximum recording length.
- Choosing a voice, speed or language at runtime (English only, fixed voice).
- Streaming (speaking while the LLM is still generating).
- Web, mobile or GUI interfaces.
- Removing URLs, or paths that contain spaces, unless they exactly match a retrieved source (§3.3, rule 1). Known limitation: a non-source path with a space, such as `my notes.md`, has only its last word removed by rule 2, so it is spoken as `my`.
- Changes to retrieval, prompts, models, ingest or history summarization.
- Integration and eval tests (see §9).

## 3. Interface contract

### 3.1 `scripts/chat.py` (refactor)

All existing names and signatures stay unchanged (`count_tokens`, `history_tokens`, `format_history`, `format_context`, `build_store`, `retrieve`, `summarize_history`, `maybe_summarize`, `answer_from_context`, `unknown_retrieval_reply`, `main`, and all module constants). Add:

```python
# scripts/chat.py
from dataclasses import dataclass

@dataclass(frozen=True)
class TurnResult:
    reply: str                      # the assistant's answer, exactly as printed
    history: list[dict[str, str]]   # new history after this turn
    docs: list[Document]            # docs returned by retrieve(); [] if none

def answer_turn(
    store: Chroma,
    llm: ChatOllama,
    history: list[dict[str, str]],
    question: str,
) -> TurnResult:
    """Run one question through the RAG pipeline.

    Raises ValueError if question is empty or whitespace-only (before any
    store or llm call).
    """
```

Behaviour of `answer_turn`. Let `q = question.strip()`.
1. If `q == ""`, raise `ValueError`. No store or llm calls are made.
2. `prior = maybe_summarize(llm, history)`.
3. `docs = retrieve(store, q)`.
4. If `docs` is empty, `reply = unknown_retrieval_reply()` and `answer_from_context` is **not** called. Otherwise `reply = answer_from_context(llm, prior, docs, q)`.
5. Return `TurnResult(reply, list(prior) + [{"role": "user", "content": q}, {"role": "assistant", "content": reply}], docs)`.
6. The `history` list passed in is **never mutated**.

`answer_turn` prints nothing itself. The existing `"(history over 2000 tokens — summarizing prior chat…)"` message printed by `maybe_summarize` still appears.

After summarizing, `prior` is the one-item list `[{"role": "summary", "content": <summary>}]` returned by the existing `maybe_summarize`. The returned history is therefore exactly 3 items: summary, user, assistant.

`chat.main()` keeps its current behaviour and output. For reference, that behaviour is:
- Inputs are read with `input("You: ")` and stripped.
- Empty input is ignored and the next line is read.
- An input whose `casefold()` is in `chat.EXIT_COMMANDS` (currently `{"quit", "exit", "bye"}`) prints `Bye.` and returns `0`.
- `EOFError` or `KeyboardInterrupt` from `input` prints `\nBye.` and returns `0`.

For each non-empty, non-exit input `raw` (already stripped) it calls `answer_turn(store, llm, history, raw)`, looked up as a module global at call time, then prints `f"Assistant: {result.reply}\n"` and sets `history = result.history`.

### 3.2 `scripts/voice_chat.py` (new): constants and types

```python
# scripts/voice_chat.py
import chat                              # pipeline is reached as chat.<name>
from langchain_ollama import ChatOllama  # module-level, so tests can patch voice_chat.ChatOllama

SAMPLE_RATE: int = 16_000                # Hz, mono
MIN_DURATION_S: float = 0.5
SILENCE_RMS: float = 0.01                # RMS of float32 samples in [-1.0, 1.0]
NO_SPEECH_PROB_MAX: float = 0.6
WHISPER_MODEL: str = "small.en"
PIPER_VOICE: str = "en_US-lessac-medium"
MODELS_DIR: Path                         # <project root>/.models
SPOKEN_EXTENSIONS_TO_DROP: tuple[str, ...] = (".md", ".pdf", ".txt")
DIDNT_CATCH: str = "(didn't catch that)"
GOODBYE: str = "Bye."

class VoiceSetupError(RuntimeError):
    """A microphone, speaker or model could not be initialised. The message says which."""

class Recorder(Protocol):
    def record(self) -> np.ndarray: ...
    # Blocks for one push-to-talk recording. Returns 1-D float32 mono audio at
    # SAMPLE_RATE (may be empty). May raise KeyboardInterrupt or EOFError.

class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...

class Speaker(Protocol):
    def speak(self, text: str) -> None: ...
    # Blocks until playback has finished.

class TurnOutcome(enum.Enum):
    SKIPPED = "skipped"     # nothing usable was heard
    EXIT = "exit"           # an exit command was spoken
    ANSWERED = "answered"   # the pipeline produced a reply

@dataclass(frozen=True)
class VoiceTurnResult:
    outcome: TurnOutcome
    history: list[dict[str, str]]
    heard: str              # stripped transcription; "" if transcription was skipped or empty
    reply: str | None       # printed reply; None unless ANSWERED
    spoken: str | None      # exact text passed to speaker.speak; None if speak was not called
```

### 3.3 `scripts/voice_chat.py`: pure functions

```python
def speakable_text(answer: str, sources: Iterable[str] = ()) -> str: ...
```
Returns the text to speak. Rules are applied in this order:
1. **Exact sources.** Remove every occurrence of each non-empty string in `sources`, longest first.
2. **Path-like tokens.** Remove every substring that:
   - consists only of characters from `[A-Za-z0-9_./\\-]`,
   - is not immediately preceded by one of those characters,
   - ends in `.md`, `.pdf` or `.txt` (case-insensitive), and
   - is not immediately followed by a letter, digit, `_`, `/`, `\` or `-`.

   Sentence punctuation after the extension (e.g. the final `.` in `chai.md.`) is therefore not part of the path and stays. This covers `data/recipes/chai.md`, `recipes/chai.md`, `chai.md`, `DATA\Recipes\Chai.MD`.
3. **Citation markers.** Remove `[` + digits + zero or more `,` + digits groups + `]`. Spaces or tabs are allowed around each comma but not directly inside the brackets. So `[1]`, `[1,2]`, `[1, 2]` and `[1 , 2]` are removed, while `[ 1 ]`, `[1a]` and `[note]` are not matched by this rule. (The tidy step later removes spaces just inside brackets, so `[ 1 ]` ends up as `[1]` in the final output.)
4. **Markdown**, in this order:
   1. Remove a heading marker at the start of a line: optional spaces/tabs, one or more `#`, then any spaces/tabs.
   2. Remove a bullet at the start of a line: optional indentation, then `-`, `*` or `+`, followed by at least one space/tab (removed too) or the end of the line. The indentation is kept and later stripped by the tidy step. A marker with no space after it is **not** a bullet, so `-5°F overnight` keeps its minus sign.
   3. Remove every remaining `*` and `` ` `` character, and every `__`.

   Numbered list markers like `1.` are kept.
5. **Dangling source labels.** Matching is case-insensitive and whole-word only, so `resource`, `Resources:` and `(resources)` are never labels. The word `source` or `sources` is removed only in these two cases:
   1. **Label with a colon.** The word is immediately followed by `:`, and everything after the colon up to the end of the line or the next `)` is only whitespace, punctuation (except `)`), or the whole word `and`. `and` may appear any number of times and is matched case-insensitively. That trailing span is removed with it, but not the `)`. Examples: `Source: `, `Sources:  and `, `(source: )`.

      Rule 5 is checked before tidying, so it only sees text as it stands after rules 1–4. Known limitation: when a label is kept because words follow it on the same line, the removed path can leave odd leftovers. For example, `Source: a.md. Stir well.` and `Source : a.md` keep the word `Source` and may keep stray punctuation. Their exact outputs are not specified.
   2. **Alone in parentheses.** The word is the only word inside a `( … )` pair, apart from whitespace and punctuation (not counting `(` and `)`). Any other word, including `and`, means it is not alone, so `(sources and notes)` is kept. Only round parentheses count (`[source]` is kept), and nested parentheses are not specified. Example: `(source)`. The leftover `()` is removed by the tidy step.

   In every other case the word is kept. That includes `source` used as an ordinary word (`The source of the beans…`) and at the end of a sentence (`There is no source.`).
6. **Tidy**, in this order:
   1. Remove brackets `()`, `[]`, `{}` whose content is only whitespace and/or punctuation, repeating until none remain.
   2. Apply the following as one pass, repeating the pass until the text stops changing:
      - collapse runs of spaces/tabs into one space;
      - remove spaces directly before `, . ; : ! ?`;
      - remove spaces directly after an opening bracket and directly before a closing bracket;
      - remove a `,` or `;` followed (ignoring spaces/tabs) by another `,` `;` `.` `)` `]` or the end of a line.
   3. Strip each line, drop lines that contain no letter or digit, and join the remaining lines with `"\n"`.
7. If the result contains no letter or digit, return `""`.

Content not matched by the rules is preserved character for character. In particular fractions (`1/2`), `24/7`, `and/or`, decimals (`1.5`), `e.g.`, `350°F` and `No. 2` survive unchanged.

**Normative examples.** In the table, `\n` means a newline character, and backslashes in X-7 are literal single backslashes.

| # | `answer` | `sources` | Returns |
|---|---|---|---|
| X-1 | `Add 1/2 cup sugar (source: data/recipes/lemonade.md).` | `["data/recipes/lemonade.md"]` | `Add 1/2 cup sugar.` |
| X-2 | `The coffee is in the pantry, shelf 2 [1]. Source: data/supplies/coffee.md` | `[]` | `The coffee is in the pantry, shelf 2.` |
| X-3 | `**Steps:**\n- Brew 24/7 if needed\n- Use sugar and/or honey\n\nSources: recipes/chai.md and chai.md` | `[]` | `Steps:\nBrew 24/7 if needed\nUse sugar and/or honey` |
| X-4 | `data/supplies/coffee.md` | `["data/supplies/coffee.md"]` | `` (empty) |
| X-5 | `Heat 1.5 cups to 350°F, e.g. on burner No. 2.` | `[]` | unchanged |
| X-6 | `The source of the beans is Peru.` | `[]` | unchanged |
| X-7 | `See DATA\Recipes\Chai.MD.` | `[]` | `See.` |
| X-8 | `I don't know based on the available Bay Laurel documents.` | `[]` | unchanged |
| X-9 | `There is no source.` | `[]` | unchanged |
| X-10 | `Add sugar (source).` | `[]` | `Add sugar.` |
| X-11 | `No recipe for that, sorry; check the sources folder with the chef.` | `[]` | unchanged |

```python
def normalize_command(text: str) -> str:
    """Casefold, then strip leading/trailing whitespace and string.punctuation
    characters until neither remains. Inner text is untouched."""

def is_exit_command(text: str) -> bool:
    """True iff normalize_command(text) is in chat.EXIT_COMMANDS."""

def is_too_short_or_silent(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bool:
    """audio: 1-D, or 2-D with shape (n, 1) (flattened first), float samples.
    The input is converted to float64 before any calculation, and
    RMS = sqrt(mean(x**2)) is computed in float64.
    True if len(audio) == 0, or len(audio) / sample_rate < MIN_DURATION_S,
    or the audio is silent. Silent means RMS < SILENCE_RMS and NOT
    math.isclose(RMS, SILENCE_RMS, rel_tol=1e-6). The tolerance stops a
    float32 recording of exactly 0.01 being called silent because of
    rounding. Both comparisons are strict, so exactly 0.5 s, or an RMS
    equal to 0.01 (within that tolerance), is NOT too short or silent."""

def join_segments(segments: Iterable[Any]) -> str:
    """segments: objects with .text: str and .no_speech_prob: float
    (faster-whisper Segment, or any duck-typed fake).
    Drop segments whose no_speech_prob > NO_SPEECH_PROB_MAX (strict; exactly
    0.6 is kept). Strip each kept .text, drop empty ones, join with one space.
    Returns "" if nothing is kept."""
```

### 3.4 `scripts/voice_chat.py`: turn and main

```python
def voice_turn(
    store: Chroma,
    llm: ChatOllama,
    history: list[dict[str, str]],
    recorder: Recorder,
    transcriber: Transcriber,
    speaker: Speaker,
) -> VoiceTurnResult: ...
```
See §5, Workflow B. `voice_turn` never mutates `history`. For SKIPPED and EXIT it returns a history equal to the input.

```python
def main(
    recorder: Recorder | None = None,
    transcriber: Transcriber | None = None,
    speaker: Speaker | None = None,
) -> int: ...
```
See §5, Workflow A. Any argument left as `None` is built with `SoundDeviceRecorder()`, `WhisperTranscriber()` or `PiperSpeaker()`, looked up as module globals at call time. The store comes from `chat.build_store()` and the LLM from `ChatOllama(model=chat.CHAT_MODEL, temperature=0.1)`.

### 3.5 `scripts/voice_chat.py`: concrete components (not unit-tested)

```python
class SoundDeviceRecorder:        # implements Recorder
    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None: ...  # VoiceSetupError if no input device
    def record(self) -> np.ndarray: ...

class WhisperTranscriber:         # implements Transcriber
    def __init__(self, model_name: str = WHISPER_MODEL, models_dir: Path = MODELS_DIR) -> None: ...
    def transcribe(self, audio: np.ndarray) -> str: ...

class PiperSpeaker:               # implements Speaker
    def __init__(self, voice: str = PIPER_VOICE, models_dir: Path = MODELS_DIR) -> None: ...
    def speak(self, text: str) -> None: ...
```
- `SoundDeviceRecorder.record`: prints `Press Enter to talk...` and waits for Enter. Prints `Listening... press Enter to stop.` and records from the default input device until Enter. Returns 1-D float32 at `sample_rate`. `EOFError` and `KeyboardInterrupt` from `input()` propagate.
- `WhisperTranscriber`: uses `faster_whisper.WhisperModel(model_name, device="cpu", compute_type="int8", download_root=models_dir / "whisper")`. `transcribe` calls `model.transcribe(audio, language="en", vad_filter=True)` and returns `join_segments(segments)`.
- `PiperSpeaker`: uses the Piper voice files `<voice>.onnx` and `<voice>.onnx.json` in `models_dir / "piper"`, downloading them if missing. `speak` synthesises and plays through the default output device with `sounddevice`, blocking until done.
- If a model can't be loaded or downloaded, or no audio device exists, the constructor raises `VoiceSetupError` with a message naming the model or device.
- `faster_whisper`, `piper` and `sounddevice` are imported **inside** these classes, never at module level.

### CLI, files, dependencies
- Run: `poetry run python scripts/voice_chat.py` (no arguments).
- Reads `.chroma/` (via `chat`). Writes model files under `.models/` on first run. Add `.models/` to `.gitignore`.
- Add to `pyproject.toml` dependencies: `faster-whisper`, `piper-tts`, `sounddevice`, `numpy` (compatible with Python 3.10+). Update `poetry.lock`.
- `README.md`: add a short "Voice chat" section covering how to run it, push-to-talk, first-run model download, and macOS microphone permission for the terminal.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| Spoken question | mic audio, mono, 16 kHz float32 | ≥ 0.5 s and RMS ≥ 0.01 | transcribed text, printed as `You (heard): …` |
| Short or silent recording | same | < 0.5 s, or RMS < 0.01, or empty | `(didn't catch that)` printed, transcriber not called |
| Transcription | `str` | any | stripped; empty → skip; exit command → `Bye.`; else sent to `chat.answer_turn` |
| Reply | `str` from pipeline | any | printed as `Assistant: {reply}\n`, then `speakable_text(reply, sources)` spoken if non-empty |
| `sources` | `doc.metadata["source"]` of each retrieved doc | missing or empty values ignored | exact strings removed from spoken text |

## 5. Workflows

**A. `voice_chat.main()`**
1. If `chat.CHROMA_DIR` does not exist, print `Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py first.` to stderr and return `1`. No recorder, transcriber or speaker is constructed.
2. Build any missing components (recorder, transcriber, speaker). On `VoiceSetupError`, print its message to stderr and return `1`.
3. `store = chat.build_store()`, `llm = ChatOllama(model=chat.CHAT_MODEL, temperature=0.1)`, `history = []`.
4. Print the banner: `Bay Laurel Catering voice chatbot` / `Press Enter to start talking and Enter again to stop. Say quit, exit, or bye to leave.`
5. Loop: `result = voice_turn(...)`, then `history = result.history`. If `result.outcome is TurnOutcome.EXIT`, return `0`.
6. If `KeyboardInterrupt` or `EOFError` escapes `voice_turn`, print `\nBye.` and return `0`.

**B. `voice_turn(...)`**, with intermediate states:
1. **Recording.** `audio = recorder.record()`.
2. **Gate.** If `is_too_short_or_silent(audio)`, print `DIDNT_CATCH` and return `SKIPPED` (`heard=""`, `reply=None`, `spoken=None`). Transcriber and speaker are not called.
3. **Transcribing.** `heard = transcriber.transcribe(audio).strip()`. If `heard == ""`, print `DIDNT_CATCH` and return `SKIPPED`.
4. Print `You (heard): {heard}`.
5. **Exit check.** If `is_exit_command(heard)`, print `GOODBYE`, call `speaker.speak(GOODBYE)`, and return `EXIT` (`spoken=GOODBYE`). `chat.answer_turn` is not called.
6. **Answering.** `turn = chat.answer_turn(store, llm, history, heard)`, looked up on the `chat` module at call time.
7. **Printing.** Print `f"Assistant: {turn.reply}\n"`. This happens **before** any `speak` call.
8. **Speaking.** `sources = [d.metadata.get("source") for d in turn.docs]`, with falsy values dropped. `spoken = speakable_text(turn.reply, sources)`. If `spoken` is non-empty, call `speaker.speak(spoken)`. Otherwise do not call it and set `spoken=None`.
9. Return `ANSWERED` with `history=turn.history`, `reply=turn.reply`, `heard`, `spoken`.

**Output streams.** Everything printed in Workflows A and B goes to stdout, except where stderr is named.

**Speaker errors.** In steps 5 and 8, if `speaker.speak` raises any `Exception`, print `(couldn't play audio: {exc})` to stderr and continue as if it had succeeded. The outcome, history and `spoken` value are unchanged. Exceptions from `recorder.record`, `transcriber.transcribe` and `chat.answer_turn` propagate.

## 6. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | Importing `voice_chat` loads no models, opens no audio device and makes no network call. It succeeds even if `faster_whisper`, `piper` and `sounddevice` are unimportable. | unit (block those modules in `sys.modules`, then import) |
| NFR-2 | Works fully offline after the first-run model download. Audio and text never leave the machine. | manual (disconnect network, run M-1) |
| NFR-3 | On an Apple Silicon dev Mac, a ~5 s question is transcribed in ≤ 2 s after the stop key. Speech starts ≤ 1 s after a ≤ 3-sentence answer is printed. | manual (M-4) |
| NFR-4 | No recording happens during playback, because `speak` blocks before the next turn starts. | unit (order of fake calls) + manual |
| NFR-5 | Text chat (`chat.py`) behaviour and output are unchanged by the refactor. | unit (AC-1–AC-5) + manual (M-6) |
| NFR-6 | Transcription is accurate enough for retrieval: at least 9 of 10 checklist questions are transcribed well enough to get the right answer. | manual (M-2) |

## 7. Known edge cases
- EC-1: Fractions and slashed words (`1/2 cup`, `3/4 tsp`, `24/7`, `and/or`) are spoken unchanged.
- EC-2: Decimals and abbreviations (`1.5`, `e.g.`, `No. 2`, `350°F`) are spoken unchanged.
- EC-3: A source appearing several times is removed every time. When one source is a prefix of another (`data/a.md` and `data/a.md.bak`), the longer one is removed first and no fragment remains.
- EC-4: Paths not in `sources` (partial path, bare filename, uppercase extension, Windows backslashes) are removed by rule 2. `.pdf` and `.txt` are removed too.
- EC-5: `source` used as an ordinary word (`The source of the beans…`) is kept.
- EC-6: An answer that is only paths, labels or markdown gives `""`, so `speak` is not called and `spoken is None`.
- EC-7: `[1]` and `[1, 2]` are removed. `[note]` is kept.
- EC-8: `**bold**`, backticks, `#` headings and `-`/`*`/`+` bullets are removed. `1.` numbered markers are kept.
- EC-9: Audio boundaries: empty array, exactly 0.5 s, just under 0.5 s, loud but too short, long but silent, RMS exactly 0.01, and shape `(n, 1)`.
- EC-10: Transcriptions `"   "` or `""` are skipped. `"Bye."`, `" EXIT! "` and `"Quit?"` exit. `"bye bye"`, `"goodbye"` and `"bye, where is the coffee"` do not.
- EC-11: `join_segments` drops all segments → `""`. A `no_speech_prob` of exactly `0.6` is kept, `0.61` is dropped. Empty segment texts are skipped without creating double spaces.
- EC-12: `speaker.speak` raises → the reply is already printed, a warning goes to stderr, the outcome is still `ANSWERED` (or `EXIT`) and history is updated.
- EC-13: No docs retrieved → the unknown-retrieval reply is printed and spoken (unchanged by `speakable_text`), and history is updated.
- EC-14: History over the token limit is summarized before answering, and the caller's history list is not mutated.
- EC-15: `answer_turn` with an empty or whitespace question raises `ValueError` with no store or llm calls. A question with surrounding whitespace is stripped before retrieval and in history.
- EC-16: Missing `.chroma/` → `main` returns 1 without constructing any voice component.
- EC-17: A component constructor raising `VoiceSetupError` → message on stderr, `main` returns 1.
- EC-18: `KeyboardInterrupt` or `EOFError` during recording → `main` prints `Bye.` and returns 0.
- EC-19: A retrieved doc with no `source` metadata (or an empty one) is ignored when building `sources`.
- EC-20 (rev 2): `source`/`sources` without a colon and not alone in parentheses is kept: at the end of a sentence (`There is no source.`), before other words (`the sources folder`), or at the end of a line with no colon (`Check the source`). With a colon and nothing after it (`Source:`, `SOURCES: and`), or alone in parentheses (`(source)`, `(Sources)`), it is removed.

## 8. Acceptance criteria

**`chat.answer_turn` and `chat.main`**
- **AC-1:** With docs retrieved, `answer_turn` returns `reply` equal to `answer_from_context(llm, prior, docs, q)`, `docs` equal to the retrieved list, and `history == prior + [user q, assistant reply]`.
- **AC-2:** With no docs retrieved, `reply == unknown_retrieval_reply()`, `docs == []`, the LLM is not asked for an answer, and history still gains the user and assistant entries.
- **AC-3:** The input `history` list is never mutated, in the under-limit, over-limit and no-docs paths alike. When over the limit, the returned history starts with the single summary item.
- **AC-4:** An empty or whitespace `question` raises `ValueError` before any store or llm call. A padded question is stripped in retrieval, the answer prompt and history.
- **AC-5:** `chat.main` sends each non-empty, non-exit input to `chat.answer_turn`, prints `Assistant: {reply}` and passes the returned history into the next turn. Exit commands, empty input, EOF and `KeyboardInterrupt` behave as listed in §3.1.

**`speakable_text`**
- **AC-6:** Returns exactly the expected output for every normative example X-1 to X-11.
- **AC-7:** Every string in `sources` is absent from the result. Paths ending in `.md`/`.pdf`/`.txt` are removed whether or not they are in `sources` (EC-3, EC-4).
- **AC-8:** Fractions, slashed words, decimals and abbreviations are preserved (EC-1, EC-2). Text without paths, citations, markdown or labels is returned unchanged apart from whitespace tidying.
- **AC-9:** Citation markers, markdown and dangling source labels are removed as in rules 3–5, with the exceptions of EC-5, EC-7 and EC-8.
- **AC-10:** Returns `""` when nothing speakable remains (EC-6). The result never has leading or trailing whitespace, blank lines, or double spaces.
- **AC-26 (rev 2):** Source labels follow revised rule 5 exactly. Every case in EC-20 gives the stated result, and X-9 to X-11 hold.

**Pure helpers**
- **AC-11:** `normalize_command` and `is_exit_command` behave as in EC-10.
- **AC-12:** `is_too_short_or_silent` follows the strict boundaries in §3.3 for all cases in EC-9.
- **AC-13:** `join_segments` behaves as in EC-11.

**`voice_turn`**
- **AC-14:** For short or silent audio it returns `SKIPPED`, prints `(didn't catch that)`, doesn't call the transcriber, speaker or `chat.answer_turn`, and returns history equal to the input.
- **AC-15:** For an empty or whitespace transcription it returns `SKIPPED`, prints `(didn't catch that)`, and calls neither the speaker nor `chat.answer_turn`.
- **AC-16:** For a normal question it prints `You (heard): {heard}`, calls `chat.answer_turn(store, llm, history, heard)` once, and prints `Assistant: {reply}` **before** `speaker.speak` is called. It speaks exactly `speakable_text(reply, sources_of_docs)` and returns `ANSWERED` with `turn.history`, `reply`, `heard` and `spoken`.
- **AC-17:** If the speakable text is empty, `speak` is not called and `spoken is None`. Other fields are as in AC-16.
- **AC-18:** For a spoken exit command it prints and speaks `Bye.`, returns `EXIT`, and does not call `chat.answer_turn`.
- **AC-19:** If `speaker.speak` raises, `voice_turn` doesn't raise, writes `(couldn't play audio` to stderr, and returns the same outcome, history and `spoken` as if speaking had succeeded.
- **AC-20:** Docs without a `source` are ignored when building `sources` (EC-19).

**`voice_chat.main`**
- **AC-21:** If `.chroma/` is missing, it returns 1 with the message on stderr and constructs no components.
- **AC-22:** If constructing a component raises `VoiceSetupError`, it returns 1 with the message on stderr.
- **AC-23:** With injected fakes, it runs turns, carries history from one turn to the next, and returns 0 on an `EXIT` turn.
- **AC-24:** `KeyboardInterrupt` or `EOFError` from the recorder → prints `Bye.` and returns 0.
- **AC-25:** NFR-1 holds: `import voice_chat` succeeds with `faster_whisper`, `piper` and `sounddevice` blocked.

## 9. Test layers
- **Unit:** everything in §8. Ollama and Chroma are faked: a store with `similarity_search(query, k)` returning `Document`s, and an llm with `invoke(messages)` returning an object with `.content`, or `chat.answer_turn` monkeypatched. Recorder, transcriber and speaker are simple fakes. Audio is built with `numpy`. Output is captured with `capsys`. No mic, models or network.
- **Integration:** none for this spec.
- **Eval:** none for this spec.

**Manual checklist**, run by the user after implementation:
- M-1: `poetry run python scripts/voice_chat.py` starts, downloads models on first run, and push-to-talk works end to end.
- M-2 (NFR-6): Ask 10 real questions (supplies, recipes, quantities with fractions). At least 9 are transcribed well enough to get the right answer.
- M-3: The spoken answer matches the printed answer, minus file paths, `[n]` markers and markdown. Fractions are read out.
- M-4 (NFR-3): Transcription and speech start times feel within the targets.
- M-5: Saying "bye" exits. Pressing Enter twice quickly prints `(didn't catch that)`. Ctrl+C exits cleanly.
- M-6 (NFR-5): `scripts/chat.py` text chat behaves exactly as before.

## 10. Revisions

### Revision 2 (2026-11-08)
Revision 1 was implemented and passed review and all unit tests. Revision 2 has two parts.

**A. Behaviour change. This round implements and tests this part only.**
- §3.3 rule 5 (dangling source labels) is narrowed. Previously, `source` was removed whenever only punctuation or whitespace followed it on its line, so `There is no source.` lost its last word. Now it is removed only as a label with a colon, or alone in parentheses.
- New: normative examples X-9 to X-11, EC-20 and AC-26.
- Everything else in `speakable_text` must keep its current behaviour, and X-1 to X-8 must still pass. Existing tests that assert the **old** rule 5 behaviour (for example, a no-colon `source`/`sources` at the end of a line being removed) must be updated to the new rule. All other existing tests must pass unchanged.

**B. Clarifications that match the existing implementation. No code or test changes are expected for these.**
- §3.1: what the summary item looks like, and what `chat.main` does on exit, empty input and EOF.
- §3.3 rule 3: spacing allowed in citation markers.
- §3.3 rule 4: order of the markdown steps; a bullet needs a space after it.
- §3.3 rule 6: order of the tidy steps, and the repeat-until-stable pass.
- §3.3 `is_too_short_or_silent`: float64 calculation and the `rel_tol=1e-6` boundary tolerance.
- §5: output streams.
- §2: known limitation for paths containing spaces.

### Revision 3 (2026-11-08): test housekeeping only
No spec behaviour changes and no code changes. The tester is explicitly allowed to modify existing test files for this revision.
- **R3-1:** Move every test from `tests/test_voice_io_source_labels.py` into `tests/test_voice_io.py`, grouped next to the existing `speakable_text` and `voice_turn` tests. Keep their assertions and expected values unchanged.
- **R3-2:** Remove exact duplicates: two tests (or parametrized cases) with the same input and the same expected result. Keep one copy. In particular, X-1 to X-8 are currently asserted in both files; after the merge they are asserted once, with X-1 to X-11 in a single normative-examples test. Do not remove a case that differs in any way.
- **R3-3:** Test names in the merged file must be unique, and each test's `Covers:` docstring stays accurate.
- **R3-4:** Replace the contents of `tests/test_voice_io_source_labels.py` with only a module docstring saying it was merged into `tests/test_voice_io.py`. The tester can't delete files, so the user deletes it afterwards.
- **R3-5:** `tests/test_voice_io_answer_turn.py` is not touched.
- **Verified by:** the test evaluator confirms nothing in scope lost coverage. The implementation evaluator confirms that all tests pass, and that the total drops from 267 only by the number of duplicates the tester reports.

### Revision 4 (2026-11-08), approved: multi-word source labels
Only `source`/`sources` start a label. `reference`/`references` are deliberately **not** labels. New tests go in `tests/test_voice_io.py`.
**Why:** found during manual check M-3. The model ended an answer with `Source path: [1] (data/recipes/lemonade.md)`. Rules 1–4 reduce this to `Source path:`, which rule 5.1 does not match because the word after `Source` is not `:`. The voice then spoke "Source path" at the end of the answer.

**Change to §3.3 rule 5.1 (label with a colon).** The label is `source` or `sources`, optionally followed by **one or two** more words, then immediately `:`.
- Each extra word is ASCII letters only (`[A-Za-z]`). Words are separated by one or more spaces or tabs, all on the same line. `and` counts as an ordinary extra word here, so `Sources and notes:` is a label. In rule 5.2, by contrast, `and` stops `source` from being alone in its parentheses.
- The trailing-span condition is unchanged: up to the end of the line or the next `)`, only whitespace, punctuation (except `)`), or the whole word `and`.
- The whole label, extra words included, is removed together with the trailing span.
- Matching stays case-insensitive and whole-word, so `resource path:` is not a label.
- Rule 5.2 (alone in parentheses) is unchanged.

**Consequences, which are intended:**
- `Source path:`, `Sources used:`, `Source file:`, `Source files used:` and `Sources and notes:` (with nothing after them) are removed.
- `Source of truth for chai:` (more than two extra words) is kept.
- `Source path: Chef Maria` (words after the colon) is kept.
- `Source :` (space before the colon) is still not a label, so its words are kept. Rule 6 still removes the space before the colon, so `Source :` → `Source:` and `Source path :` → `Source path:`.

**Known limitation:** a label in the middle of a line, with nothing after it, also removes the words before the colon. For example, `Check the source path:` is spoken as `Check the`. This is rare in model output, so it is accepted.

**New normative examples** (`\n` = newline):

| # | `answer` | `sources` | Returns |
|---|---|---|---|
| X-12 | `To make lemonade:\n\n1. Pour 7 oz of lemon concentrate into a clean 1-gallon container.\n2. Add water until the total volume reaches 1 gallon.\n3. Stir well until fully mixed.\n4. Taste and adjust if needed before service.\n\nSource path: [1] (data/recipes/lemonade.md)` | `["data/recipes/lemonade.md"]` | `To make lemonade:\n1. Pour 7 oz of lemon concentrate into a clean 1-gallon container.\n2. Add water until the total volume reaches 1 gallon.\n3. Stir well until fully mixed.\n4. Taste and adjust if needed before service.` |
| X-13 | `Sources used: chai.md and lemonade.md` | `[]` | `` (empty) |
| X-14 | `Check the source of truth: the chef.` | `[]` | unchanged |

**New edge case and acceptance criterion:**
- **EC-21:** Labels with zero, one or two extra words before the colon, followed by nothing speakable, are removed. Labels with three or more extra words, or with words after the colon, are kept.
- **AC-27:** Rule 5.1 follows Revision 4 exactly. EC-21 holds, X-12 to X-14 hold, and X-1 to X-11 and EC-20 still hold. Existing tests that assert the old one-word-only behaviour, if any, must be updated. All others must pass unchanged.

### Revision 5 (2026-11-08), approved: natural goodbye phrases
**Why:** found during manual testing. Saying "Goodbye." got an answer instead of ending the session, because only the exact words `quit`, `exit` and `bye` counted. People naturally say "goodbye", "see you later" or "Bye, see you later!". This revision **replaces** the exit behaviour in §3.1, §3.3 and EC-10 for both voice chat and text chat, which share one list.

**Interface changes in `scripts/chat.py`:**
```python
EXIT_COMMANDS: frozenset[str] = frozenset({
    "bye", "bye bye", "goodbye", "good bye",
    "see you", "see ya", "see you later", "see you soon", "talk to you later",
    "quit", "exit", "stop", "im done", "thats all", "thats it",
    "take care", "good night", "goodnight", "have a good one",
})
EXIT_FILLERS: frozenset[str] = frozenset({
    "okay", "ok", "alright", "all right", "thanks", "thank you",
})

def normalize_utterance(text: str) -> str:
    """1. casefold.
    2. Delete apostrophes (' and U+2019 ’), so "that's" becomes "thats" and "I'm" becomes "im".
    3. Replace every other character that is not a letter, digit or whitespace with a space,
       so "bye-bye!" becomes "bye bye". "Letter or digit" means Python's str.isalnum()
       (Unicode). Only ' and U+2019 count as apostrophes; any other quote mark is
       punctuation.
    4. Collapse whitespace runs to one space and strip.
    Returns "" for input with no letters or digits."""

def is_exit_utterance(text: str) -> bool:
    """Split normalize_utterance(text) into words. Return True iff
    (a) there is at least one word,
    (b) the words can be split, front to back, into consecutive items, each of which is a
        whole entry of EXIT_COMMANDS or EXIT_FILLERS (multi-word entries match consecutive
        words; entries may repeat and appear in any order), and
    (c) at least one item is from EXIT_COMMANDS.
    If several splits exist, any valid split that meets (c) counts."""
```
- Entries in both sets are stored already normalized: lowercase, no apostrophes or punctuation, single spaces.
- `chat.main`: an input exits (prints `Bye.` and returns `0`) iff `is_exit_utterance(raw)`. This replaces `raw.casefold() in EXIT_COMMANDS`. Everything else in `chat.main` is unchanged.

**Interface changes in `scripts/voice_chat.py`:**
- `is_exit_command(text)` now returns exactly `chat.is_exit_utterance(text)`, looked up on the `chat` module at call time.
- `normalize_command` is unchanged and remains public, but is no longer used for the exit decision.
- The banners in both apps are unchanged.

**EC-10 is replaced by EC-22 below.**
- Still true: `"   "` and `""` are skipped (voice) or ignored (text) before any exit check.
- Now an exit: `"goodbye"` and `"bye bye"`. EC-10 previously said they were not.

**EC-22 (Rev 5), exit decisions.** Each case gives the same result in voice (`is_exit_command`) and text (`chat.main`).

| Input | Exit? | Why |
|---|---|---|
| `Bye.` / ` EXIT! ` / `Quit?` / `Stop.` | yes | a single command |
| `Goodbye.` / `Good-bye!` / `Bye-bye.` / `Goodnight.` | yes | punctuation turns into spaces |
| `Bye, see you later!` | yes | two commands |
| `Okay, thanks, bye-bye.` / `Thank you, good night!` / `Alright, that's all, goodbye.` | yes | fillers plus commands |
| `That’s it.` (curly apostrophe) / `I'm done.` | yes | apostrophes deleted |
| `Take care!` / `Have a good one.` / `See ya!` / `Talk to you later.` | yes | |
| `bye bye bye` | yes | entries may repeat |
| `Thanks.` / `Okay.` / `Thank you, alright.` | **no** | fillers only |
| `Bye, where is the coffee?` | **no** | `where…` is not an entry |
| `See you later at the bar.` | **no** | `at the bar` is not an entry |
| `Good.` / `Have a good day.` / `That's all folks.` / `Stop the timer.` | **no** | not fully covered by entries |
| `""` / `"!!!"` | **no** | no words |

**AC-28 (Rev 5):**
- `normalize_utterance` and `is_exit_utterance` behave exactly as specified, for every row of EC-22.
- `voice_chat.is_exit_command` returns the same value as `chat.is_exit_utterance` for every row.
- In `voice_turn`, an exit utterance prints and speaks `Bye.`, returns `EXIT`, and does not call `chat.answer_turn` (as AC-18). A non-exit utterance is answered.

**AC-29 (Rev 5):**
- `chat.main` exits with `Bye.` and return value `0` for exit utterances from EC-22, such as `Goodbye.` and `Bye, see you later!`.
- It sends non-exit inputs such as `Thanks.` and `Bye, where is the coffee?` to `answer_turn`.
- Empty input, EOF and `KeyboardInterrupt` behave as in §3.1.

**Tests:** existing tests that assert the **old** behaviour must be updated to Revision 5. Examples are `goodbye`/`bye bye` as non-exits, or `Bye.` in text chat being answered. All other existing tests must pass unchanged. New tests for `voice_chat` go in `tests/test_voice_io.py`. New tests for `chat` go in `tests/test_voice_io_answer_turn.py`.

**NFR-5 note:** text chat's exit behaviour changes on purpose in this revision. Everything else in text chat stays unchanged.
