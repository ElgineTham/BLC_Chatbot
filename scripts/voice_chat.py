"""Push-to-talk voice chat for Bay Laurel Catering knowledge.

Records a spoken question, transcribes it locally with faster-whisper, runs it
through the shared RAG pipeline in ``chat``, prints the answer, then speaks it
with Piper (skipping file paths, citation markers and markdown).

Heavy audio/model libraries (faster_whisper, piper, sounddevice) are imported
only inside the concrete component classes, so importing this module is cheap
and works without them.
"""

from __future__ import annotations

import enum
import math
import re
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama

import chat

SAMPLE_RATE: int = 16_000  # Hz, mono
MIN_DURATION_S: float = 0.5
SILENCE_RMS: float = 0.01  # RMS of float32 samples in [-1.0, 1.0]
NO_SPEECH_PROB_MAX: float = 0.6
WHISPER_MODEL: str = "small.en"
PIPER_VOICE: str = "en_US-lessac-medium"
MODELS_DIR: Path = chat.ROOT / ".models"
SPOKEN_EXTENSIONS_TO_DROP: tuple[str, ...] = (".md", ".pdf", ".txt")
DIDNT_CATCH: str = "Didn't catch that. Please try again."
GOODBYE: str = "Bye."

BANNER_LINES: tuple[str, ...] = (
    "Bay Laurel Catering voice chatbot",
    "Press Enter to start talking and Enter again to stop. "
    "Say quit, exit, or bye to leave.",
)

# Relative tolerance for the RMS silence boundary, so that audio whose RMS is
# SILENCE_RMS up to float32 rounding is treated as exactly on the boundary.
_RMS_REL_TOL = 1e-6

# --- speakable_text regexes -------------------------------------------------

_PATH_CHARS = r"A-Za-z0-9_./\\\-"
_EXT_ALTERNATION = "|".join(
    re.escape(ext.lstrip(".")) for ext in SPOKEN_EXTENSIONS_TO_DROP
)
_PATH_RE = re.compile(
    rf"(?<![{_PATH_CHARS}])[{_PATH_CHARS}]*\.(?:{_EXT_ALTERNATION})(?![A-Za-z0-9_/\\\-])",
    re.IGNORECASE,
)
_CITATION_RE = re.compile(r"\[\d+(?:[ \t]*,[ \t]*\d+)*\]")
_HEADING_RE = re.compile(r"^[ \t]*#+[ \t]*", re.MULTILINE)
_BULLET_RE = re.compile(r"^([ \t]*)[-*+](?:[ \t]+|$)", re.MULTILINE)

_PUNCT_NO_CLOSE_PAREN = re.escape(string.punctuation.replace(")", ""))
_PUNCT_NO_PARENS = re.escape(string.punctuation.replace("(", "").replace(")", ""))
# Rule 5.1: "source(s)" label, optionally followed by one or two extra
# letters-only words (separated by spaces/tabs), then immediately ":", followed
# only by whitespace, punctuation (not ")") or "and" up to the end of the line
# or the next ")". The whole label and trailing span are removed; ")" is kept.
_LABEL_EXTRA_WORDS_MAX = 2
_SOURCE_COLON_LABEL_RE = re.compile(
    rf"\bsources?(?:[ \t]+[A-Za-z]+){{0,{_LABEL_EXTRA_WORDS_MAX}}}:"
    rf"(?:[ \t{_PUNCT_NO_CLOSE_PAREN}]|\band\b)*(?=\)|$)",
    re.IGNORECASE | re.MULTILINE,
)
# Rule 5.2: "source(s)" as the only word inside a "( ... )" pair. Only the word
# is removed; the leftover brackets are removed by the tidy step.
_SOURCE_IN_PARENS_RE = re.compile(
    rf"\(([\s{_PUNCT_NO_PARENS}]*)\bsources?\b([\s{_PUNCT_NO_PARENS}]*)\)",
    re.IGNORECASE,
)

_BRACKET_PUNCT = re.escape(
    "".join(ch for ch in string.punctuation if ch not in "()[]{}")
)
_EMPTY_BRACKETS_RE = re.compile(
    rf"\([\s{_BRACKET_PUNCT}]*\)|\[[\s{_BRACKET_PUNCT}]*\]|\{{[\s{_BRACKET_PUNCT}]*\}}"
)
_SPACE_RUN_RE = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +(?=[,.;:!?])")
_SPACE_AFTER_OPEN_RE = re.compile(r"(?<=[(\[{]) +")
_SPACE_BEFORE_CLOSE_RE = re.compile(r" +(?=[)\]}])")
_DANGLING_SEPARATOR_RE = re.compile(r"[,;](?=[ \t]*(?:[,;.)\]]|$))", re.MULTILINE)


class VoiceSetupError(RuntimeError):
    """A microphone, speaker or model could not be initialised. The message says which."""


class Recorder(Protocol):
    def record(self) -> np.ndarray:
        """Block for one push-to-talk recording.

        Returns 1-D float32 mono audio at SAMPLE_RATE (may be empty).
        May raise KeyboardInterrupt or EOFError.
        """
        ...


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


class Speaker(Protocol):
    def speak(self, text: str) -> None:
        """Block until playback has finished."""
        ...


class TurnOutcome(enum.Enum):
    SKIPPED = "skipped"  # nothing usable was heard
    EXIT = "exit"  # an exit command was spoken
    ANSWERED = "answered"  # the pipeline produced a reply


@dataclass(frozen=True)
class VoiceTurnResult:
    outcome: TurnOutcome
    history: list[dict[str, str]]
    heard: str  # stripped transcription; "" if transcription was skipped or empty
    reply: str | None  # printed reply; None unless ANSWERED
    spoken: str | None  # exact text passed to speaker.speak; None if not called


# --- pure functions ---------------------------------------------------------


def _has_alnum(text: str) -> bool:
    return any(ch.isalnum() for ch in text)


def _remove_sources(text: str, sources: Iterable[str]) -> str:
    unique = {src for src in sources if src}
    for src in sorted(unique, key=len, reverse=True):
        text = text.replace(src, "")
    return text


def _remove_markdown(text: str) -> str:
    text = _HEADING_RE.sub("", text)
    text = _BULLET_RE.sub(r"\1", text)
    text = text.replace("*", "").replace("`", "").replace("__", "")
    return text


def _remove_empty_brackets(text: str) -> str:
    while True:
        new_text = _EMPTY_BRACKETS_RE.sub("", text)
        if new_text == text:
            return text
        text = new_text


def _tidy_spacing(text: str) -> str:
    while True:
        new_text = _SPACE_RUN_RE.sub(" ", text)
        new_text = _SPACE_BEFORE_PUNCT_RE.sub("", new_text)
        new_text = _SPACE_AFTER_OPEN_RE.sub("", new_text)
        new_text = _SPACE_BEFORE_CLOSE_RE.sub("", new_text)
        new_text = _DANGLING_SEPARATOR_RE.sub("", new_text)
        if new_text == text:
            return text
        text = new_text


def _remove_source_labels(text: str) -> str:
    text = _SOURCE_COLON_LABEL_RE.sub("", text)
    return _SOURCE_IN_PARENS_RE.sub(r"(\1\2)", text)


def _tidy(text: str) -> str:
    text = _remove_empty_brackets(text)
    text = _tidy_spacing(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if _has_alnum(line))


def speakable_text(answer: str, sources: Iterable[str] = ()) -> str:
    """Return the part of ``answer`` worth speaking aloud.

    Removes exact source strings, path-like tokens ending in .md/.pdf/.txt,
    citation markers, markdown and dangling source labels, then tidies
    whitespace and punctuation. Returns "" if nothing speakable remains.
    """
    text = _remove_sources(answer, sources)
    text = _PATH_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = _remove_markdown(text)
    text = _remove_source_labels(text)
    text = _tidy(text)
    return text if _has_alnum(text) else ""


def is_exit_command(text: str) -> bool:
    """True iff chat.is_exit_utterance(text) (looked up at call time)."""
    return chat.is_exit_utterance(text)


def is_too_short_or_silent(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bool:
    """audio: 1-D, or 2-D with shape (n, 1) (flattened first), float samples.
    True if len(audio) == 0, or len(audio) / sample_rate < MIN_DURATION_S,
    or RMS(audio) < SILENCE_RMS. Both comparisons are strict, so exactly
    0.5 s or an RMS of exactly 0.01 is NOT too short or silent."""
    samples = np.asarray(audio, dtype=np.float64).ravel()
    if len(samples) == 0:
        return True
    if len(samples) / sample_rate < MIN_DURATION_S:
        return True
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if math.isclose(rms, SILENCE_RMS, rel_tol=_RMS_REL_TOL, abs_tol=0.0):
        return False
    return rms < SILENCE_RMS


def join_segments(segments: Iterable[Any]) -> str:
    """segments: objects with .text: str and .no_speech_prob: float
    (faster-whisper Segment, or any duck-typed fake).
    Drop segments whose no_speech_prob > NO_SPEECH_PROB_MAX (strict; exactly
    0.6 is kept). Strip each kept .text, drop empty ones, join with one space.
    Returns "" if nothing is kept."""
    kept: list[str] = []
    for segment in segments:
        if segment.no_speech_prob > NO_SPEECH_PROB_MAX:
            continue
        text = segment.text.strip()
        if text:
            kept.append(text)
    return " ".join(kept)


# --- turn and main ----------------------------------------------------------


def _safe_speak(speaker: Speaker, text: str) -> None:
    try:
        speaker.speak(text)
    except Exception as exc:  # noqa: BLE001 - playback failure must not end the chat
        print(f"(couldn't play audio: {exc})", file=sys.stderr)


def _doc_sources(docs: Iterable[Any]) -> list[str]:
    sources: list[str] = []
    for doc in docs:
        metadata = getattr(doc, "metadata", None) or {}
        source = metadata.get("source")
        if source:
            sources.append(source)
    return sources


def _skipped(history: list[dict[str, str]]) -> VoiceTurnResult:
    print(DIDNT_CATCH)
    return VoiceTurnResult(
        outcome=TurnOutcome.SKIPPED,
        history=list(history),
        heard="",
        reply=None,
        spoken=None,
    )


def voice_turn(
    store: Chroma,
    llm: ChatOllama,
    history: list[dict[str, str]],
    recorder: Recorder,
    transcriber: Transcriber,
    speaker: Speaker,
) -> VoiceTurnResult:
    """Record, transcribe, answer and speak one push-to-talk turn."""
    audio = recorder.record()
    if is_too_short_or_silent(audio):
        return _skipped(history)

    heard = transcriber.transcribe(audio).strip()
    if heard == "":
        return _skipped(history)

    print(f"You (heard): {heard}")

    if is_exit_command(heard):
        print(GOODBYE)
        _safe_speak(speaker, GOODBYE)
        return VoiceTurnResult(
            outcome=TurnOutcome.EXIT,
            history=list(history),
            heard=heard,
            reply=None,
            spoken=GOODBYE,
        )

    turn = chat.answer_turn(store, llm, history, heard)
    print(f"Assistant: {turn.reply}\n")

    spoken: str | None = speakable_text(turn.reply, _doc_sources(turn.docs))
    if spoken:
        _safe_speak(speaker, spoken)
    else:
        spoken = None

    return VoiceTurnResult(
        outcome=TurnOutcome.ANSWERED,
        history=turn.history,
        heard=heard,
        reply=turn.reply,
        spoken=spoken,
    )


def main(
    recorder: Recorder | None = None,
    transcriber: Transcriber | None = None,
    speaker: Speaker | None = None,
) -> int:
    if not chat.CHROMA_DIR.exists():
        print(
            f"Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py first.",
            file=sys.stderr,
        )
        return 1

    try:
        if recorder is None:
            recorder = SoundDeviceRecorder()
        if transcriber is None:
            transcriber = WhisperTranscriber()
        if speaker is None:
            speaker = PiperSpeaker()
    except VoiceSetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    store = chat.build_store()
    llm = ChatOllama(model=chat.CHAT_MODEL, temperature=0.1)
    history: list[dict[str, str]] = []

    for line in BANNER_LINES:
        print(line)

    try:
        while True:
            result = voice_turn(store, llm, history, recorder, transcriber, speaker)
            history = result.history
            if result.outcome is TurnOutcome.EXIT:
                return 0
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        return 0


# --- concrete components (need audio hardware / models; not unit-tested) ----


class SoundDeviceRecorder:
    """Push-to-talk recorder using the default input device via sounddevice."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001 - includes missing PortAudio
            raise VoiceSetupError(
                f"Microphone unavailable: could not load sounddevice ({exc})"
            ) from exc
        try:
            sd.query_devices(kind="input")
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Microphone unavailable: no default input device found ({exc})"
            ) from exc
        self._sd = sd
        self.sample_rate = sample_rate

    def record(self) -> np.ndarray:
        input("Press Enter to talk...")
        print("Listening... press Enter to stop.")
        chunks: list[np.ndarray] = []

        def _callback(indata: np.ndarray, frames: int, time: Any, status: Any) -> None:
            chunks.append(indata[:, 0].copy())

        stream = self._sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=_callback,
        )
        stream.start()
        try:
            input()
        finally:
            stream.stop()
            stream.close()

        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)


class WhisperTranscriber:
    """Local speech-to-text using faster-whisper on CPU (int8)."""

    def __init__(
        self, model_name: str = WHISPER_MODEL, models_dir: Path = MODELS_DIR
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Whisper model '{model_name}' unavailable: could not load faster_whisper ({exc})"
            ) from exc
        download_root = models_dir / "whisper"
        try:
            download_root.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(download_root),
            )
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Whisper model '{model_name}' could not be loaded or downloaded ({exc})"
            ) from exc

    def transcribe(self, audio: np.ndarray) -> str:
        samples = np.asarray(audio, dtype=np.float32).ravel()
        segments, _info = self._model.transcribe(samples, language="en", vad_filter=True)
        return join_segments(segments)


class PiperSpeaker:
    """Local text-to-speech using a Piper voice, played via sounddevice."""

    def __init__(self, voice: str = PIPER_VOICE, models_dir: Path = MODELS_DIR) -> None:
        try:
            import sounddevice as sd
            from piper import PiperVoice
            from piper.download_voices import download_voice
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Piper voice '{voice}' unavailable: could not load piper/sounddevice ({exc})"
            ) from exc

        try:
            sd.query_devices(kind="output")
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Speaker unavailable: no default output device found ({exc})"
            ) from exc

        voice_dir = models_dir / "piper"
        model_path = voice_dir / f"{voice}.onnx"
        config_path = voice_dir / f"{voice}.onnx.json"
        try:
            if not _nonempty_file(model_path) or not _nonempty_file(config_path):
                voice_dir.mkdir(parents=True, exist_ok=True)
                print(f"(downloading Piper voice {voice}…)")
                download_voice(voice, voice_dir)
            self._voice = PiperVoice.load(model_path, config_path=config_path)
        except Exception as exc:  # noqa: BLE001
            raise VoiceSetupError(
                f"Piper voice '{voice}' could not be loaded or downloaded ({exc})"
            ) from exc
        self._sd = sd

    def speak(self, text: str) -> None:
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return
        audio = np.concatenate([chunk.audio_float_array for chunk in chunks])
        self._sd.play(audio.astype(np.float32, copy=False), samplerate=chunks[0].sample_rate)
        self._sd.wait()


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


if __name__ == "__main__":
    raise SystemExit(main())
