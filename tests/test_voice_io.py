"""Spec 001 (voice-io), part 2: scripts/voice_chat.py.

Unit tests only: recorder, transcriber and speaker are simple fakes; Ollama and
Chroma are faked (chat.build_store / voice_chat.ChatOllama / chat.answer_turn are
monkeypatched). Audio is built with numpy. No mic, models or network.

Revision 3: the revision-2 source-label tests from tests/test_voice_io_source_labels.py
are merged in here, with exact duplicates removed.

Revision 4: multi-word source labels (rule 5.1), X-12..X-14, EC-21, AC-27.

Revision 5: natural goodbye phrases. is_exit_command now delegates to
chat.is_exit_utterance (EC-22, AC-28). Old EC-10 assertions that "goodbye" and
"bye bye" are not exits were updated to the new behaviour.
"""

from __future__ import annotations

import copy
import importlib
import string
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from langchain_core.documents import Document

import chat
import voice_chat
from voice_chat import (
    DIDNT_CATCH,
    GOODBYE,
    TurnOutcome,
    VoiceSetupError,
    VoiceTurnResult,
    is_exit_command,
    is_too_short_or_silent,
    join_segments,
    normalize_command,
    speakable_text,
    voice_turn,
)

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Audio helpers
# --------------------------------------------------------------------------- #


def good_audio(seconds: float = 1.0, amp: float = 0.1) -> np.ndarray:
    return np.full(int(round(seconds * 16_000)), amp, dtype=np.float32)


def exact_rms_audio(nonzero: int) -> np.ndarray:
    """10_000 float64 samples (0.625 s): `nonzero` of them at 2**-6, the rest 0.

    With nonzero == 4096 the mean square is exactly 1/10000, so RMS == 0.01 exactly
    (the sum of squares is the exact dyadic value 1.0). 4095 is just below, 4097 just above.
    """
    audio = np.zeros(10_000, dtype=np.float64)
    audio[:nonzero] = 2.0 ** -6
    return audio


# --------------------------------------------------------------------------- #
# Component fakes
# --------------------------------------------------------------------------- #


def _is_exc(item) -> bool:
    return isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException))


class FakeRecorder:
    def __init__(self, items, log=None):
        self.items = list(items)
        self.log = log if log is not None else []
        self.calls = 0

    def record(self):
        self.calls += 1
        self.log.append("record")
        if not self.items:
            raise EOFError
        item = self.items.pop(0)
        if _is_exc(item):
            raise item
        return item


class FakeTranscriber:
    def __init__(self, texts, log=None):
        self.texts = list(texts)
        self.log = log if log is not None else []
        self.calls = 0
        self.audio_seen = []

    def transcribe(self, audio):
        self.calls += 1
        self.log.append("transcribe")
        self.audio_seen.append(audio)
        item = self.texts.pop(0)
        if _is_exc(item):
            raise item
        return item


class FakeSpeaker:
    def __init__(self, log=None, exc: BaseException | None = None, on_speak=None):
        self.log = log if log is not None else []
        self.exc = exc
        self.on_speak = on_speak
        self.spoken: list[str] = []

    def speak(self, text):
        self.log.append("speak")
        self.spoken.append(text)
        if self.on_speak is not None:
            self.on_speak(text)
        if self.exc is not None:
            raise self.exc


class FakeStore:
    def similarity_search(self, query, k=4, *a, **kw):
        raise AssertionError("store should not be queried in these tests")


class FakeLLM:
    def invoke(self, *a, **kw):
        raise AssertionError("llm should not be invoked in these tests")


def install_answer_turn(monkeypatch, reply="REPLY", docs=(), exc=None):
    """Monkeypatch chat.answer_turn with a recorder. Returns the list of calls."""
    calls = []

    def fake(store, llm, history, question):
        calls.append(SimpleNamespace(store=store, llm=llm, history=copy.deepcopy(history),
                                     history_obj=history, question=question))
        if exc is not None:
            raise exc
        new_hist = list(history) + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply},
        ]
        return chat.TurnResult(reply, new_hist, list(docs))

    monkeypatch.setattr(chat, "answer_turn", fake)
    return calls


def _history():
    return [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]


# --------------------------------------------------------------------------- #
# Constants and types (§3.2)
# --------------------------------------------------------------------------- #


def test_constants_match_contract():
    """Covers: §3.2 constants (right). Values are as specified."""
    assert voice_chat.SAMPLE_RATE == 16_000
    assert voice_chat.MIN_DURATION_S == 0.5
    assert voice_chat.SILENCE_RMS == 0.01
    assert voice_chat.NO_SPEECH_PROB_MAX == 0.6
    assert voice_chat.WHISPER_MODEL == "small.en"
    assert voice_chat.PIPER_VOICE == "en_US-lessac-medium"
    assert Path(voice_chat.MODELS_DIR).resolve() == (ROOT / ".models").resolve()
    assert tuple(voice_chat.SPOKEN_EXTENSIONS_TO_DROP) == (".md", ".pdf", ".txt")
    assert DIDNT_CATCH == "(didn't catch that)"
    assert GOODBYE == "Bye."


def test_types_match_contract():
    """Covers: §3.2 types (right). VoiceSetupError is a RuntimeError, TurnOutcome values,
    VoiceTurnResult is frozen with the specified fields."""
    assert issubclass(VoiceSetupError, RuntimeError)
    assert TurnOutcome.SKIPPED.value == "skipped"
    assert TurnOutcome.EXIT.value == "exit"
    assert TurnOutcome.ANSWERED.value == "answered"
    r = VoiceTurnResult(TurnOutcome.SKIPPED, [], "", None, None)
    assert (r.outcome, r.history, r.heard, r.reply, r.spoken) == (TurnOutcome.SKIPPED, [], "", None, None)
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        r.heard = "x"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-25 / NFR-1: import without audio libraries
# --------------------------------------------------------------------------- #


def test_import_succeeds_with_audio_libs_blocked(monkeypatch):
    """Covers: AC-25 (right), NFR-1 (unit). With faster_whisper, piper and sounddevice
    unimportable, `import voice_chat` still succeeds and exposes the contract names."""
    for name in ("faster_whisper", "piper", "sounddevice"):
        monkeypatch.setitem(sys.modules, name, None)  # None => ImportError on import
    monkeypatch.delitem(sys.modules, "voice_chat", raising=False)

    mod = importlib.import_module("voice_chat")

    for name in ("speakable_text", "voice_turn", "main", "SoundDeviceRecorder",
                 "WhisperTranscriber", "PiperSpeaker", "VoiceSetupError"):
        assert hasattr(mod, name), name
    # Sanity: the blocked modules really were blocked during import.
    for name in ("faster_whisper", "piper", "sounddevice"):
        assert sys.modules[name] is None


# --------------------------------------------------------------------------- #
# AC-6 / AC-26 / AC-27: normative examples X-1..X-14
# --------------------------------------------------------------------------- #

# X-12 (revision 4): the answer seen during manual check M-3.
X12_ANSWER = (
    "To make lemonade:\n"
    "\n"
    "1. Pour 7 oz of lemon concentrate into a clean 1-gallon container.\n"
    "2. Add water until the total volume reaches 1 gallon.\n"
    "3. Stir well until fully mixed.\n"
    "4. Taste and adjust if needed before service.\n"
    "\n"
    "Source path: [1] (data/recipes/lemonade.md)"
)
X12_EXPECTED = (
    "To make lemonade:\n"
    "1. Pour 7 oz of lemon concentrate into a clean 1-gallon container.\n"
    "2. Add water until the total volume reaches 1 gallon.\n"
    "3. Stir well until fully mixed.\n"
    "4. Taste and adjust if needed before service."
)

X_CASES = [
    ("X-1", "Add 1/2 cup sugar (source: data/recipes/lemonade.md).",
     ["data/recipes/lemonade.md"], "Add 1/2 cup sugar."),
    ("X-2", "The coffee is in the pantry, shelf 2 [1]. Source: data/supplies/coffee.md",
     [], "The coffee is in the pantry, shelf 2."),
    ("X-3", "**Steps:**\n- Brew 24/7 if needed\n- Use sugar and/or honey\n\nSources: recipes/chai.md and chai.md",
     [], "Steps:\nBrew 24/7 if needed\nUse sugar and/or honey"),
    ("X-4", "data/supplies/coffee.md", ["data/supplies/coffee.md"], ""),
    ("X-5", "Heat 1.5 cups to 350°F, e.g. on burner No. 2.", [],
     "Heat 1.5 cups to 350°F, e.g. on burner No. 2."),
    ("X-6", "The source of the beans is Peru.", [], "The source of the beans is Peru."),
    ("X-7", "See DATA\\Recipes\\Chai.MD.", [], "See."),
    ("X-8", "I don't know based on the available Bay Laurel documents.", [],
     "I don't know based on the available Bay Laurel documents."),
    ("X-9", "There is no source.", [], "There is no source."),
    ("X-10", "Add sugar (source).", [], "Add sugar."),
    ("X-11", "No recipe for that, sorry; check the sources folder with the chef.", [],
     "No recipe for that, sorry; check the sources folder with the chef."),
    # Revision 4 (multi-word source labels).
    ("X-12", X12_ANSWER, ["data/recipes/lemonade.md"], X12_EXPECTED),
    ("X-13", "Sources used: chai.md and lemonade.md", [], ""),
    ("X-14", "Check the source of truth: the chef.", [], "Check the source of truth: the chef."),
]


@pytest.mark.parametrize("case_id,answer,sources,expected", X_CASES, ids=[c[0] for c in X_CASES])
def test_speakable_text_normative_examples(case_id, answer, sources, expected):
    """Covers: AC-6 (right; X-4 boundary -> empty), AC-26 (right for X-10, wrong-is-kept for
    X-9/X-11), AC-27 (right for X-12, boundary -> empty for X-13, wrong-is-kept for X-14),
    EC-5 (X-6), EC-20, EC-21. Exact output for every normative example X-1..X-14
    (X-1..X-11 under revision 2, X-12..X-14 added by revision 4)."""
    assert speakable_text(answer, sources) == expected


def test_speakable_text_default_sources():
    """Covers: AC-6 (right), §3.3 signature. sources defaults to () and works when omitted."""
    assert speakable_text("The source of the beans is Peru.") == "The source of the beans is Peru."
    assert speakable_text("See DATA\\Recipes\\Chai.MD.") == "See."


# --------------------------------------------------------------------------- #
# AC-7: sources and path-like tokens (EC-3, EC-4)
# --------------------------------------------------------------------------- #


def test_speakable_text_removes_every_occurrence_of_source():
    """Covers: AC-7 (right), EC-3. A source appearing several times is removed each time."""
    out = speakable_text("Check Blue Binder, then Blue Binder again.", ["Blue Binder"])
    assert "Blue Binder" not in out
    assert out == "Check, then again."


def test_speakable_text_longest_source_removed_first():
    """Covers: AC-7 (boundary), EC-3. When one source is a prefix of another, the longer
    one is removed first and no fragment ('.bak') remains, regardless of input order."""
    answer = "See data/a.md.bak and data/a.md now."
    for sources in (["data/a.md", "data/a.md.bak"], ["data/a.md.bak", "data/a.md"]):
        out = speakable_text(answer, sources)
        assert ".bak" not in out
        assert "data/a.md" not in out
        assert out == "See and now."


def test_speakable_text_sources_matched_literally_not_as_regex():
    """Covers: AC-7 (boundary; extra edge). Sources with regex metacharacters and spaces
    are removed as exact strings."""
    src = "data/(old) menu+[1].md"
    out = speakable_text(f"Check {src} now.", [src])
    assert src not in out
    assert out == "Check now."


def test_speakable_text_source_without_path_shape_removed():
    """Covers: AC-7 (right). Rule 1 removes any exact source string, even non-path ones."""
    assert speakable_text("Use the Blue Binder today.", ["Blue Binder"]) == "Use the today."


def test_speakable_text_empty_source_strings_ignored():
    """Covers: AC-7 (boundary: empty source). Empty strings in sources are ignored."""
    assert speakable_text("Hello there.", ["", "Blue Binder"]) == "Hello there."


def test_speakable_text_accepts_any_iterable_of_sources():
    """Covers: AC-7 (right). sources may be any Iterable[str], e.g. a generator."""
    gen = (s for s in ["Blue Binder"])
    assert speakable_text("Use the Blue Binder today.", gen) == "Use the today."


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Read recipes/chai.md today.", "Read today."),               # partial path
        ("Open chai.md now.", "Open now."),                            # bare filename
        ("Open CHAI.MD now.", "Open now."),                            # uppercase extension
        ("Open Chai.Md now.", "Open now."),                            # mixed case
        ("See data\\recipes\\chai.md now.", "See now."),               # Windows backslashes
        ("See menu.pdf and notes.txt please.", "See and please."),     # .pdf and .txt
        ("See data/menus/fall-menu_v2.PDF today.", "See today."),      # - and _ inside
        ("Read chai.md.", "Read."),                                    # sentence '.' kept
        ("Read chai.md, then eat.", "Read, then eat."),                # comma after path kept
        ("chai.md", ""),                                               # only a path
    ],
)
def test_speakable_text_removes_path_like_tokens_not_in_sources(answer, expected):
    """Covers: AC-7 (right), EC-4. Paths ending .md/.pdf/.txt are removed by rule 2
    even when not in sources; trailing sentence punctuation stays."""
    assert speakable_text(answer, []) == expected


@pytest.mark.parametrize(
    "answer",
    [
        "Open file.mdx now.",      # followed by a letter
        "Open readme.md2 now.",    # followed by a digit
        "Open chai.md_old now.",   # followed by _
        "Open chai.md-old now.",   # followed by -
        "Keep data.json handy.",   # other extension
        "Use the md format.",      # extension word without dot
    ],
)
def test_speakable_text_keeps_non_matching_path_like_tokens(answer):
    """Covers: AC-7 (wrong: not a droppable path), rule 2 boundary on the following char.
    Tokens whose extension is followed by letter/digit/_/- or isn't .md/.pdf/.txt stay."""
    assert speakable_text(answer, []) == answer


# --------------------------------------------------------------------------- #
# AC-8: preservation (EC-1, EC-2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer",
    [
        "Add 1/2 cup sugar.",
        "Add 3/4 tsp salt.",
        "We are open 24/7.",
        "Use sugar and/or honey.",
        "Heat 1.5 cups.",
        "Use spices, e.g. cumin.",
        "Use burner No. 2.",
        "Bake at 350°F.",
        "Use pan #2 and 3 - 4 eggs.",
        "Mix (gently) and serve.",
        "1. Preheat the oven.\n2. Mix the batter.",
    ],
)
def test_speakable_text_preserves_ordinary_content(answer):
    """Covers: AC-8 (right), EC-1, EC-2, EC-8 (numbered markers kept). Content not matched
    by any rule is preserved character for character."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Hello   there  ,  friend.", "Hello there, friend."),
        ("Line one.\n\n\nLine two.", "Line one.\nLine two."),
        ("  Hello  \n\n  world  ", "Hello\nworld"),
        ("\t\tTabs\there", "Tabs here"),
        ("Mix ( flour ) well.", "Mix (flour) well."),
    ],
)
def test_speakable_text_only_whitespace_tidied_for_plain_text(answer, expected):
    """Covers: AC-8 (boundary: whitespace-only changes), rule 6. Plain text changes only
    by whitespace tidying."""
    assert speakable_text(answer, []) == expected


# --------------------------------------------------------------------------- #
# AC-9: citations, markdown, labels (EC-5, EC-7, EC-8)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Shelf 2 [1].", "Shelf 2."),
        ("Shelf 2 [1, 2].", "Shelf 2."),
        ("Shelf 2 [1, 2, 3].", "Shelf 2."),
        ("Shelf 2 [12] today.", "Shelf 2 today."),
    ],
)
def test_speakable_text_removes_citation_markers(answer, expected):
    """Covers: AC-9 (right), EC-7. [n] and [n, m, ...] are removed."""
    assert speakable_text(answer, []) == expected


@pytest.mark.parametrize("answer", ["See [note] here.", "See [1a] here.", "See [a, b] here."])
def test_speakable_text_keeps_non_citation_brackets(answer):
    """Covers: AC-9 (wrong: not a citation), EC-7. Brackets with other content are kept."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("**Bold** text.", "Bold text."),
        ("Run `brew` now.", "Run brew now."),
        ("Use __this__ one.", "Use this one."),
        ("*Note:* stir.", "Note: stir."),
        ("# Heading\nBody.", "Heading\nBody."),
        ("### Sub heading\nBody.", "Sub heading\nBody."),
        ("- one\n* two\n+ three", "one\ntwo\nthree"),
        ("Intro:\n    - nested item", "Intro:\nnested item"),
        ("-   spaced bullet", "spaced bullet"),
        ("1. First\n2. Second", "1. First\n2. Second"),
    ],
)
def test_speakable_text_removes_markdown(answer, expected):
    """Covers: AC-9 (right), EC-8. *, `, __, leading # and -/*/+ bullets are removed;
    numbered markers are kept."""
    assert speakable_text(answer, []) == expected


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Brew it. Source: data/x.md", "Brew it."),
        ("Brew it.\nSOURCES: a.md, b.md", "Brew it."),
        ("Use oats (sources: a.md, b.md).", "Use oats."),
        ("Mix well (source).", "Mix well."),
        ("Done.\nSource: a.md and b.pdf.", "Done."),
    ],
)
def test_speakable_text_removes_dangling_source_labels(answer, expected):
    """Covers: AC-9 (right), AC-26 (right), rule 5 (rev 2). Colon labels left with nothing
    but whitespace, punctuation or 'and' up to end of line or ')' are removed, keeping the
    ')' (then tidied); a word alone in parentheses is removed.
    Rev 2: the old row ('Mix well. sources' -> 'Mix well.') asserted the pre-revision rule
    and was moved to test_speakable_text_keeps_source_as_ordinary_word."""
    assert speakable_text(answer, []) == expected


@pytest.mark.parametrize(
    "answer",
    [
        # "The source of the beans is Peru." is asserted once, as X-6.
        "Check the sources listed in the binder.",
        "Source: the farmers market.",
        "Mix well. sources",   # rev 2: no colon, not in parens -> kept (was removed before)
    ],
)
def test_speakable_text_keeps_source_as_ordinary_word(answer):
    """Covers: AC-9 (wrong: not dangling), AC-26 (wrong: not a label), EC-5, EC-20.
    'source' followed by other words, or with no colon and not alone in parentheses, is
    kept."""
    assert speakable_text(answer, []) == answer


# --- Rule 5 (rev 2) source labels: merged from test_voice_io_source_labels.py --- #


@pytest.mark.parametrize(
    "answer,expected",
    [
        # Rule 5.1: label with a colon and nothing speakable after it.
        ("Brew it. Source:", "Brew it."),                              # EC-20 'Source:'
        ("Brew it. SOURCES: and", "Brew it."),                         # EC-20 'SOURCES: and'
        ("Brew it. Sources:  and ", "Brew it."),                       # spec example
        ("Brew it. source: .", "Brew it."),                            # only punctuation after
        ("Brew it. Source:   ", "Brew it."),                           # only whitespace after
        ("Brew it. Sources: AND, and And.", "Brew it."),               # 'and' repeated, any case
        ("Add sugar (source: ).", "Add sugar."),                       # spec example '(source: )'
        ("Brew it.\nSources: a.md, b.md and c.txt", "Brew it."),       # paths -> ', and' left
        ("(Source: a.md) Stir well.", "Stir well."),                   # span stops at ')'
        ("Brew it.\n**Source:** data/x.md", "Brew it."),               # markdown removed first
        # Rule 5.2: alone in parentheses. ("Add sugar (source)." is asserted once, as X-10.)
        ("Use oats (Sources).", "Use oats."),                          # EC-20 '(Sources)'
        ("Mix (SOURCE) well.", "Mix well."),                           # case-insensitive, mid-line
        ("Add sugar ( Sources ).", "Add sugar."),                      # whitespace inside parens
        ("Add sugar (source.).", "Add sugar."),                        # punctuation inside parens
    ],
)
def test_source_label_removed(answer, expected):
    """Covers: AC-26 (right), AC-9 (right), EC-20, §3.3 rule 5.1/5.2. A source label with a
    colon followed only by whitespace/punctuation/'and' to end of line or ')', or the word
    alone in parentheses, is removed and the leftovers tidied."""
    assert speakable_text(answer, []) == expected


def test_colon_label_span_stops_at_end_of_line():
    """Covers: AC-26 (boundary), §3.3 rule 5.1 'up to the end of the line'. A bare 'Source:'
    line is removed but the following line is untouched."""
    assert speakable_text("Brew it.\nSource:\nStir well.", []) == "Brew it.\nStir well."


@pytest.mark.parametrize(
    "answer",
    [
        # X-9, X-11, X-6 (EC-5) and "Mix well. sources" are asserted once elsewhere.
        "Is this the source?",                    # end of sentence, '?'
        "Check the source!",                      # end of sentence, '!'
        "Check the source, then stir.",           # followed by punctuation then words
        "Check the source",                       # EC-20: end of line, no colon
        "Check the source\nThen stir.",           # end of a non-final line, no colon
        "Mix well.\nSource",                      # alone on a line, no colon
    ],
)
def test_source_word_without_colon_kept(answer):
    """Covers: AC-26 (wrong: not a label), EC-20. 'source'/'sources' with no colon and not
    alone in parentheses is kept, even at the end of a sentence or line."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer",
    [
        # "Source: the farmers market." is asserted once, in
        # test_speakable_text_keeps_source_as_ordinary_word.
        "Source: Chef Maria",                     # words after the colon
        "Ask Chef. Source: Andrew",               # 'Andrew' is not the word 'and'
        "Ask (source: chef Maria).",              # words between colon and ')'
    ],
)
def test_colon_label_followed_by_words_kept(answer):
    """Covers: AC-26 (wrong: span contains words), §3.3 rule 5.1 boundary. A colon label is
    kept when anything other than whitespace, punctuation or 'and' follows it."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer",
    [
        "Use the binder (source of truth).",      # not the only word in parens
        "Ask the chef (the source).",             # another word before it
        "See (sources and notes).",               # 'and' is still another word here
        "See [source] here.",                     # square brackets are not parentheses
    ],
)
def test_source_in_brackets_with_other_words_kept(answer):
    """Covers: AC-26 (wrong: not alone in parentheses), §3.3 rule 5.2 boundary. The word is
    kept when other words share the parentheses or the brackets are not '( )'."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer",
    [
        "Use this resource.",
        "Check the binder. Resources:",
        "Check (resources) here.",
        "Beans (sourced) locally.",
    ],
)
def test_words_containing_source_kept(answer):
    """Covers: AC-26 (wrong; extra edge), §3.3 rule 5 'the word source or sources'. Longer
    words that merely contain 'source' are not labels and are kept, even with a colon or
    alone in parentheses."""
    assert speakable_text(answer, []) == answer


def test_colon_label_followed_by_text_on_same_line_keeps_word():
    """Covers: AC-26 (wrong), AC-7 (right), §3.3 rule 5.1. After the path is removed, words
    still follow on the line, so the label word stays while the path is gone."""
    out = speakable_text("Brew it. Source: a.md. Stir well.", [])
    assert "a.md" not in out
    assert "Source" in out
    assert out.endswith("Stir well.")


def test_space_before_colon_is_not_a_label():
    """Covers: AC-26 (wrong; extra edge), §3.3 rule 5.1 'immediately followed by :' and the
    known limitation 'Source : a.md'. The word is kept (only the path goes); the exact
    tidied output is unspecified, so only keep/remove is asserted."""
    out = speakable_text("Source : a.md", [])
    assert "a.md" not in out
    assert "Source" in out


def test_kept_source_word_alongside_removed_citation():
    """Covers: AC-26 (right), AC-9 (right), EC-7. Citations are still removed while a
    sentence-final 'source' is kept."""
    assert speakable_text("Shelf 2 [1]. There is no source.", []) == "Shelf 2. There is no source."


# --- Rule 5.1 (rev 4): multi-word source labels --- #


@pytest.mark.parametrize(
    "answer,expected",
    [
        # Consequences listed in revision 4, each with nothing after the colon.
        ("Brew it.\nSource path:", "Brew it."),                          # one extra word
        ("Brew it.\nSources used:", "Brew it."),
        ("Brew it.\nSource file:", "Brew it."),
        ("Brew it.\nSource files used:", "Brew it."),                    # two extra words (limit)
        ("Brew it.\nSources and notes:", "Brew it."),                    # 'and' as an extra word
        ("Brew it.\nSources:", "Brew it."),                              # zero extra words still ok
        # Case-insensitive, and spaces or tabs between the words.
        ("Brew it.\nSOURCE PATH:", "Brew it."),
        ("Brew it.\nsource Files Used:", "Brew it."),
        ("Brew it.\nSource\tpath:", "Brew it."),
        ("Brew it.\nSource \t files used:", "Brew it."),
        # Trailing span unchanged: whitespace, punctuation (not ')') or the word 'and'.
        ("Brew it.\nSource path:   ", "Brew it."),
        ("Brew it.\nSource files: and, AND .", "Brew it."),
        # Paths and citations removed by rules 1-3 first, leaving a bare label.
        ("Brew it.\nSource path: data/recipes/chai.md", "Brew it."),
        ("Brew it.\nSources used: a.md, b.pdf and c.txt", "Brew it."),
        ("Brew it.\nSource path: [1] (data/recipes/lemonade.md)", "Brew it."),  # M-3, sources=[]
        # Markdown removed by rule 4 first.
        ("Brew it.\n**Source path:** data/x.md", "Brew it."),
        ("Brew it.\n- Sources used: a.md", "Brew it."),
        # After a sentence on the same line.
        ("Brew it. Source file:", "Brew it."),
        # Span stops at ')': the ')' stays and the empty '()' is tidied away.
        ("Add sugar (source path: data/recipes/lemonade.md).", "Add sugar."),
        ("Use oats (sources used: a.md, b.md).", "Use oats."),
        # Span stops at end of line: the next line is untouched.
        ("Brew it.\nSource path:\nStir well.", "Brew it.\nStir well."),
    ],
)
def test_multiword_source_label_removed(answer, expected):
    """Covers: AC-27 (right; boundary at two extra words and zero extra words), EC-21,
    §10 Rev 4 rule 5.1. 'source'/'sources' followed by zero, one or two letters-only words
    (spaces/tabs between) and then immediately ':', with nothing speakable after it, is removed
    together with its extra words and trailing span."""
    assert speakable_text(answer, []) == expected


@pytest.mark.parametrize(
    "answer",
    [
        # Three or more extra words before the colon.
        "Source of truth for chai:",                       # spec consequence
        "Brew it.\nSource files used here:",               # three extra words (just over limit)
        "Brew it.\nSource of the day list:",               # four extra words
        # Words after the colon.
        "Source path: Chef Maria",                         # spec consequence
        "Sources used: the blue binder.",
        "Brew it.\nSources and notes: Chef Maria",
        "Ask (source path: chef Maria).",                  # words between ':' and ')'
        "Brew it.\nSource file: Andrew",                   # 'Andrew' is not the word 'and'
    ],
)
def test_multiword_source_label_with_too_many_words_or_text_after_kept(answer):
    """Covers: AC-27 (wrong: not a label; boundary at three extra words), EC-21, X-14 family.
    Labels with three or more extra words, or with words after the colon, are kept unchanged."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer",
    [
        "Check the resource path:",          # spec: 'resource path:' is not a label
        "Brew it.\nResources used:",         # whole-word only
        "Brew it.\nReferences:",             # 'reference(s)' deliberately not labels
        "Brew it.\nReference path:",
        "Brew it.\nReferences used:",
        "Brew it.\nSource v2:",              # extra word must be letters only
        "Brew it.\nSource 2:",
        "Brew it.\nSource file_name:",
        "Brew it. Source\npath:",            # newline is not a space/tab separator
    ],
)
def test_non_label_words_before_colon_kept(answer):
    """Covers: AC-27 (wrong; extra edge), §10 Rev 4 rule 5.1. Only whole-word 'source'/'sources'
    start a label; 'resource' and 'reference(s)' do not; extra words must be letters only and
    separated by spaces or tabs on the same line. These answers are returned unchanged."""
    assert speakable_text(answer, []) == answer


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Source :", "Source:"),
        ("Brew it.\nSource path :", "Brew it.\nSource path:"),
        ("Brew it.\nSources used :", "Brew it.\nSources used:"),
    ],
)
def test_space_before_colon_still_not_a_multiword_label(answer, expected):
    """Covers: AC-27 (wrong), §10 Rev 4 'Source : is still not a label'. The colon must follow
    the label immediately, so the words are kept; only the tidy step removes the space before
    ':' (rule 6.2)."""
    assert speakable_text(answer, []) == expected


def test_midline_multiword_label_known_limitation():
    """Covers: AC-27 (boundary), §10 Rev 4 known limitation. A label in the middle of a line
    with nothing after it removes the words before the colon: 'Check the source path:' is
    spoken as 'Check the'."""
    assert speakable_text("Check the source path:", []) == "Check the"


@pytest.mark.parametrize(
    "answer,sources",
    [
        ("Source path:", []),
        ("Source files used: a.md, b.pdf and c.txt", []),
        ("Source path: [1] (data/recipes/lemonade.md)", ["data/recipes/lemonade.md"]),
        ("**Sources used:** `chai.md`", []),
    ],
)
def test_multiword_label_only_answer_returns_empty(answer, sources):
    """Covers: AC-27 (boundary -> empty), AC-10, EC-6, EC-21. An answer that is only a
    multi-word label (plus paths, citations or markdown) gives ''."""
    assert speakable_text(answer, sources) == ""


def test_speakable_text_removes_empty_brackets_repeatedly():
    """Covers: AC-9/AC-10 (boundary), rule 6 'repeating until none remain'. Nested and
    punctuation-only brackets are removed."""
    assert speakable_text("Mix (  ) well [ , ] now {}.", []) == "Mix well now."
    assert speakable_text("Mix (( )) well.", []) == "Mix well."


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Buy eggs, milk,.", "Buy eggs, milk."),
        ("Buy eggs,\nmilk", "Buy eggs\nmilk"),
        ("Buy eggs ;", "Buy eggs"),
        ("Buy eggs, , milk.", "Buy eggs, milk."),
    ],
)
def test_speakable_text_removes_dangling_commas(answer, expected):
    """Covers: AC-10 (boundary), rule 6. A ',' or ';' followed by , ; . ) ] or end of line
    is removed."""
    assert speakable_text(answer, []) == expected


# --------------------------------------------------------------------------- #
# AC-10: empty results and tidy output (EC-6)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer,sources",
    [
        ("", []),
        ("   ", []),
        ("\n\n", []),
        ("...", []),
        ("**[1]** `data/a.md`", []),
        ("- \n# \n", []),
        ("Sources: a.md, b.md", []),
        ("(source: data/x.md)", ["data/x.md"]),
        # ("data/supplies/coffee.md", ["data/supplies/coffee.md"]) is asserted once, as X-4.
    ],
)
def test_speakable_text_returns_empty_when_nothing_speakable(answer, sources):
    """Covers: AC-10 (boundary: empty / nothing speakable), EC-6. Returns ''."""
    assert speakable_text(answer, sources) == ""


@pytest.mark.parametrize(
    "answer,sources",
    [
        ("Sources:", []),
        ("(source)", []),
        ("(Sources: )", []),
        ("Source: data/x.md", []),
        ("Sources: a.md and b.pdf", ["a.md"]),
    ],
)
def test_label_only_answer_returns_empty(answer, sources):
    """Covers: AC-10 (boundary), AC-26 (right), EC-6, EC-20. An answer that is only a
    removable label (plus paths) gives ''."""
    assert speakable_text(answer, sources) == ""


@pytest.mark.parametrize(
    "answer,sources",
    [
        X_CASES[0][1:3],
        X_CASES[1][1:3],
        X_CASES[2][1:3],
        ("  **Hi**  there  \n\n- item  one \n\nSource: a.md  ", []),
        ("Shelf 2 [1] , then [2] go .", []),
        ("\t# Title\n\n\n   text   with   gaps   ", []),
    ],
)
def test_speakable_text_output_is_tidy(answer, sources):
    """Covers: AC-10 (right). Result has no leading/trailing whitespace, no blank lines,
    no double spaces, and no line with surrounding whitespace."""
    out = speakable_text(answer, sources)
    assert out == out.strip()
    assert "\n\n" not in out
    assert "  " not in out
    for line in out.split("\n"):
        assert line == line.strip()
        assert line != ""


@pytest.mark.parametrize(
    "answer",
    [
        "Add sugar (source).",
        "Brew it.\nSource:\nStir well.",
        "Mix (SOURCE) well.",
        "Brew it.\nSources: a.md, b.md and c.txt",
        "Shelf 2 [1]. There is no source.",
    ],
)
def test_output_tidy_after_label_handling(answer):
    """Covers: AC-10 (right), AC-26. Results have no leading/trailing whitespace, blank lines,
    or double spaces after source-label removal."""
    out = speakable_text(answer, [])
    assert out == out.strip()
    assert "\n\n" not in out
    assert "  " not in out
    for line in out.split("\n"):
        assert line == line.strip()
        assert line != ""


# --------------------------------------------------------------------------- #
# AC-11: normalize_command / is_exit_command (EC-10)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Bye.", "bye"),
        (" EXIT! ", "exit"),
        ("Quit?", "quit"),
        ("...!!  Hello, World ?!", "hello, world"),
        ("bye, where is the coffee", "bye, where is the coffee"),
        ("", ""),
        ("  ?!. ", ""),
        ("Inner  Spaces", "inner  spaces"),
    ],
)
def test_normalize_command(text, expected):
    """Covers: AC-11 (right + boundary: empty/punctuation-only), EC-10. Casefold and strip
    outer whitespace/punctuation repeatedly; inner text untouched."""
    assert normalize_command(text) == expected


@pytest.mark.parametrize("text", ["Bye.", " EXIT! ", "Quit?", "bye", "QUIT", "\texit\n"])
def test_is_exit_command_true(text):
    """Covers: AC-11 (right), EC-10. Spoken exit commands are recognised."""
    assert is_exit_command(text) is True


_PLAIN_EXIT_COMMANDS = sorted(
    c for c in chat.EXIT_COMMANDS
    if c == c.casefold() and c == c.strip(string.whitespace + string.punctuation) and c
)


@pytest.mark.parametrize("cmd", _PLAIN_EXIT_COMMANDS)
def test_is_exit_command_true_for_every_chat_exit_command(cmd):
    """Covers: AC-11 (right). Every plain (lowercase, no outer punctuation) entry of
    chat.EXIT_COMMANDS, decorated with case/whitespace/punctuation, is an exit."""
    assert is_exit_command(f"  {cmd.upper()}!! ") is True


@pytest.mark.parametrize(
    "text",
    ["bye, where is the coffee", "", "   ", "...", "exit the kitchen"],
)
def test_is_exit_command_false(text):
    """Covers: AC-11 (wrong + boundary: empty), EC-22 (Rev 5). Phrases not fully made of
    exit entries, and inputs with no words, do not exit. (Rev 5: 'bye bye' and
    'goodbye' were removed from this list; they are now exits.)"""
    assert is_exit_command(text) is False


# --------------------------------------------------------------------------- #
# AC-28 (Rev 5): is_exit_command == chat.is_exit_utterance (EC-22)
# --------------------------------------------------------------------------- #

# EC-22 table, verbatim. "’" is the curly apostrophe from the spec row.
EC22_EXITS = [
    "Bye.", " EXIT! ", "Quit?", "Stop.",
    "Goodbye.", "Good-bye!", "Bye-bye.", "Goodnight.",
    "Bye, see you later!",
    "Okay, thanks, bye-bye.", "Thank you, good night!", "Alright, that's all, goodbye.",
    "That’s it.", "I'm done.",
    "Take care!", "Have a good one.", "See ya!", "Talk to you later.",
    "bye bye bye",
]
EC22_NON_EXITS = [
    "Thanks.", "Okay.", "Thank you, alright.",
    "Bye, where is the coffee?",
    "See you later at the bar.",
    "Good.", "Have a good day.", "That's all folks.", "Stop the timer.",
    "", "!!!",
]


@pytest.mark.parametrize("text", EC22_EXITS)
def test_is_exit_command_rev5_exit_rows(text):
    """Covers: AC-28 (right), EC-22. Every 'yes' row of EC-22 is an exit for voice, and
    matches chat.is_exit_utterance."""
    assert is_exit_command(text) is True
    assert is_exit_command(text) == chat.is_exit_utterance(text)


@pytest.mark.parametrize("text", EC22_NON_EXITS)
def test_is_exit_command_rev5_non_exit_rows(text):
    """Covers: AC-28 (wrong + boundary: '' and '!!!' have no words), EC-22. Every 'no'
    row of EC-22 is not an exit for voice, and matches chat.is_exit_utterance."""
    assert is_exit_command(text) is False
    assert is_exit_command(text) == chat.is_exit_utterance(text)


@pytest.mark.parametrize("text", ["goodbye", "bye bye", "Good bye", "see you", "thats it"])
def test_is_exit_command_old_non_exits_now_exit(text):
    """Covers: AC-28 (right), EC-22 'Now an exit' note. Phrases that EC-10 used to reject
    ('goodbye', 'bye bye') and other multi-word entries now exit."""
    assert is_exit_command(text) is True


def test_is_exit_command_looks_up_chat_is_exit_utterance_at_call_time(monkeypatch):
    """Covers: AC-28 (right + wrong), §10 Rev 5 'looked up on the chat module at call
    time'. Patching chat.is_exit_utterance changes is_exit_command's answer both ways."""
    seen = []

    def fake(text):
        seen.append(text)
        return text == "banana"

    monkeypatch.setattr(chat, "is_exit_utterance", fake)
    assert is_exit_command("banana") is True
    assert is_exit_command("bye") is False
    assert seen == ["banana", "bye"]


def test_normalize_command_not_used_for_exit_decision(monkeypatch):
    """Covers: AC-28 (wrong), §10 Rev 5 'normalize_command ... no longer used for the
    exit decision'. Breaking normalize_command does not change is_exit_command."""
    monkeypatch.setattr(voice_chat, "normalize_command", lambda text: "bye")
    assert is_exit_command("Where is the coffee?") is False
    assert is_exit_command("Goodbye.") is True


# --------------------------------------------------------------------------- #
# AC-12: is_too_short_or_silent (EC-9)
# --------------------------------------------------------------------------- #


def gate(audio, **kwargs) -> bool:
    # bool() so a numpy.bool_ return value is accepted too.
    return bool(is_too_short_or_silent(audio, **kwargs))


def test_silence_gate_empty_array():
    """Covers: AC-12 (boundary: empty), EC-9."""
    assert gate(np.array([], dtype=np.float32)) is True


def test_silence_gate_exactly_half_second_is_ok():
    """Covers: AC-12 (boundary: exactly 0.5 s, strict), EC-9."""
    assert gate(np.full(8000, 0.1, dtype=np.float32)) is False


def test_silence_gate_just_under_half_second():
    """Covers: AC-12 (boundary: just under 0.5 s), EC-9."""
    assert gate(np.full(7999, 0.1, dtype=np.float32)) is True


def test_silence_gate_loud_but_too_short():
    """Covers: AC-12 (wrong), EC-9. Loud audio shorter than 0.5 s is rejected."""
    assert gate(np.full(4000, 0.9, dtype=np.float32)) is True


@pytest.mark.parametrize("amp", [0.0, 0.005], ids=["zeros", "quiet"])
def test_silence_gate_long_but_silent(amp):
    """Covers: AC-12 (wrong), EC-9. Long audio with RMS < 0.01 is rejected."""
    assert gate(np.full(32_000, amp, dtype=np.float32)) is True


def test_silence_gate_rms_exactly_threshold_is_ok():
    """Covers: AC-12 (boundary: RMS exactly 0.01, strict), EC-9. Uses float64 samples
    whose RMS is exactly 0.01 in double precision."""
    audio = exact_rms_audio(4096)
    assert float(np.sqrt(np.mean(audio ** 2))) == 0.01  # guard on the fixture itself
    assert gate(audio) is False


def test_silence_gate_rms_just_below_and_above():
    """Covers: AC-12 (boundary: RMS just below / just above 0.01)."""
    assert gate(exact_rms_audio(4095)) is True
    assert gate(exact_rms_audio(4097)) is False


def test_silence_gate_normal_speech_ok():
    """Covers: AC-12 (right). A 1 s sine at amplitude 0.3 passes the gate."""
    t = np.arange(16_000, dtype=np.float32) / 16_000
    audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert gate(audio) is False


@pytest.mark.parametrize(
    "n,amp,expected",
    [(16_000, 0.1, False), (100, 0.1, True), (16_000, 0.0, True)],
    ids=["ok", "short", "silent"],
)
def test_silence_gate_column_shape(n, amp, expected):
    """Covers: AC-12 (boundary: shape (n, 1) is flattened first), EC-9."""
    audio = np.full((n, 1), amp, dtype=np.float32)
    assert gate(audio) is expected


def test_silence_gate_respects_sample_rate_argument():
    """Covers: AC-12 (boundary; extra edge). Duration is len/sample_rate, so 4000 samples
    are too short at 16 kHz but exactly 0.5 s at 8 kHz."""
    audio = np.full(4000, 0.1, dtype=np.float32)
    assert gate(audio) is True
    assert gate(audio, sample_rate=8000) is False
    assert gate(audio[:3999], sample_rate=8000) is True


# --------------------------------------------------------------------------- #
# AC-13: join_segments (EC-11)
# --------------------------------------------------------------------------- #


def seg(text, prob=0.1):
    return SimpleNamespace(text=text, no_speech_prob=prob)


def test_join_segments_joins_stripped_texts():
    """Covers: AC-13 (right), EC-11. Texts are stripped and joined with one space;
    empty texts do not create double spaces."""
    segs = [seg(" Where is "), seg(""), seg("   "), seg("the coffee? ")]
    assert join_segments(segs) == "Where is the coffee?"


def test_join_segments_empty_input():
    """Covers: AC-13 (boundary: no segments), EC-11."""
    assert join_segments([]) == ""


def test_join_segments_all_dropped():
    """Covers: AC-13 (wrong: all no-speech), EC-11. All segments dropped -> ''."""
    assert join_segments([seg("noise", 0.9), seg("hum", 0.61)]) == ""


def test_join_segments_threshold_is_strict():
    """Covers: AC-13 (boundary: 0.6 kept, 0.61 dropped), EC-11."""
    assert join_segments([seg("kept", 0.6), seg("dropped", 0.61)]) == "kept"
    assert join_segments([seg("a", 0.0), seg("b", 0.6000001), seg("c", 0.59)]) == "a c"


def test_join_segments_accepts_generator():
    """Covers: AC-13 (right; extra edge). faster-whisper yields a generator; any
    Iterable must work."""
    gen = (seg(t) for t in ["one", "two"])
    assert join_segments(gen) == "one two"


# --------------------------------------------------------------------------- #
# AC-14: short/silent audio is skipped
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "audio",
    [
        np.array([], dtype=np.float32),
        np.full(4000, 0.9, dtype=np.float32),
        np.zeros(32_000, dtype=np.float32),
        np.full(32_000, 0.005, dtype=np.float32),
    ],
    ids=["empty", "loud-short", "long-zeros", "long-quiet"],
)
def test_voice_turn_skips_short_or_silent_audio(monkeypatch, capsys, audio):
    """Covers: AC-14 (wrong input), EC-9. SKIPPED, prints (didn't catch that), no
    transcriber/speaker/answer_turn calls, history equal to input, heard '' and
    reply/spoken None."""
    calls = install_answer_turn(monkeypatch)
    rec, tr, sp = FakeRecorder([audio]), FakeTranscriber(["should not be used"]), FakeSpeaker()
    history = _history()
    snapshot = copy.deepcopy(history)

    result = voice_turn(FakeStore(), FakeLLM(), history, rec, tr, sp)

    assert result.outcome is TurnOutcome.SKIPPED
    assert result.history == snapshot
    assert history == snapshot
    assert result.heard == ""
    assert result.reply is None
    assert result.spoken is None
    assert tr.calls == 0
    assert sp.spoken == []
    assert calls == []
    assert DIDNT_CATCH in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# AC-15: empty transcription is skipped
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ["", "   ", "\n\t "], ids=["empty", "spaces", "ws-mix"])
def test_voice_turn_skips_empty_transcription(monkeypatch, capsys, text):
    """Covers: AC-15 (wrong/boundary), EC-10. Empty or whitespace transcription -> SKIPPED,
    prints (didn't catch that), no speaker or answer_turn calls."""
    calls = install_answer_turn(monkeypatch)
    rec, tr, sp = FakeRecorder([good_audio()]), FakeTranscriber([text]), FakeSpeaker()
    history = _history()
    snapshot = copy.deepcopy(history)

    result = voice_turn(FakeStore(), FakeLLM(), history, rec, tr, sp)

    assert result.outcome is TurnOutcome.SKIPPED
    assert result.history == snapshot
    assert history == snapshot
    assert result.heard == ""
    assert result.reply is None
    assert result.spoken is None
    assert tr.calls == 1
    assert sp.spoken == []
    assert calls == []
    out = capsys.readouterr().out
    assert DIDNT_CATCH in out
    assert "You (heard):" not in out


# --------------------------------------------------------------------------- #
# AC-16: normal question
# --------------------------------------------------------------------------- #


def test_voice_turn_answers_normal_question(monkeypatch, capsys):
    """Covers: AC-16 (right), NFR-4 (unit: print before speak). Prints heard text, calls
    answer_turn(store, llm, history, heard) once, prints the reply before speaking,
    speaks speakable_text(reply, sources) and returns ANSWERED."""
    reply = "Add 1/2 cup sugar (source: data/recipes/lemonade.md)."
    docs = [Document(page_content="x", metadata={"source": "data/recipes/lemonade.md"})]
    calls = install_answer_turn(monkeypatch, reply=reply, docs=docs)

    out_before_speak = []
    sp = FakeSpeaker(on_speak=lambda text: out_before_speak.append(capsys.readouterr().out))
    audio = good_audio()
    rec, tr = FakeRecorder([audio]), FakeTranscriber(["  How much sugar for lemonade?  "])
    store, llm = FakeStore(), FakeLLM()
    history = _history()
    snapshot = copy.deepcopy(history)

    result = voice_turn(store, llm, history, rec, tr, sp)

    # answer_turn called once with the stripped heard text
    assert len(calls) == 1
    c = calls[0]
    assert c.store is store
    assert c.llm is llm
    assert c.history == snapshot
    assert c.question == "How much sugar for lemonade?"
    # transcriber got the recorded audio
    assert tr.audio_seen and np.array_equal(np.asarray(tr.audio_seen[0]).reshape(-1), audio)
    # printed before speaking
    assert len(out_before_speak) == 1
    printed = out_before_speak[0]
    assert "You (heard): How much sugar for lemonade?" in printed
    assert f"Assistant: {reply}\n" in printed
    assert printed.index("You (heard):") < printed.index("Assistant:")
    # spoken text
    assert sp.spoken == ["Add 1/2 cup sugar."]
    # result
    assert result.outcome is TurnOutcome.ANSWERED
    assert result.heard == "How much sugar for lemonade?"
    assert result.reply == reply
    assert result.spoken == "Add 1/2 cup sugar."
    assert result.history == snapshot + [
        {"role": "user", "content": "How much sugar for lemonade?"},
        {"role": "assistant", "content": reply},
    ]
    assert history == snapshot


def test_voice_turn_spoken_equals_speakable_text_of_reply(monkeypatch):
    """Covers: AC-16 (right). Spoken text is exactly speakable_text(reply, sources_of_docs)
    for a reply with markdown, citations and several sources."""
    reply = "**Coffee** is on shelf 2 [1].\n- Use Blue Binder\nSources: data/supplies/coffee.md"
    docs = [
        Document(page_content="a", metadata={"source": "data/supplies/coffee.md"}),
        Document(page_content="b", metadata={"source": "Blue Binder"}),
    ]
    install_answer_turn(monkeypatch, reply=reply, docs=docs)
    sp = FakeSpeaker()
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where is coffee?"]), sp)

    expected = speakable_text(reply, ["data/supplies/coffee.md", "Blue Binder"])
    assert expected == "Coffee is on shelf 2.\nUse"
    assert sp.spoken == [expected]
    assert result.spoken == expected


def test_voice_turn_exit_word_inside_question_is_answered(monkeypatch):
    """Covers: AC-16 (boundary), EC-10. 'bye, where is the coffee' is a question, not exit."""
    calls = install_answer_turn(monkeypatch, reply="Shelf 2.")
    sp = FakeSpeaker()
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["bye, where is the coffee"]), sp)
    assert result.outcome is TurnOutcome.ANSWERED
    assert [c.question for c in calls] == ["bye, where is the coffee"]
    assert sp.spoken == ["Shelf 2."]


def test_voice_turn_column_shaped_audio_is_transcribed(monkeypatch):
    """Covers: AC-16 (boundary: (n, 1) audio passes the gate), EC-9."""
    install_answer_turn(monkeypatch, reply="Shelf 2.")
    tr = FakeTranscriber(["Where is coffee?"])
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([np.full((16_000, 1), 0.1, dtype=np.float32)]),
                        tr, FakeSpeaker())
    assert tr.calls == 1
    assert result.outcome is TurnOutcome.ANSWERED


# --------------------------------------------------------------------------- #
# AC-17 / EC-6: nothing speakable
# --------------------------------------------------------------------------- #


def test_voice_turn_does_not_speak_empty_text(monkeypatch, capsys):
    """Covers: AC-17 (boundary: empty speakable text), EC-6. speak not called,
    spoken is None, other fields as in AC-16."""
    reply = "data/supplies/coffee.md"
    docs = [Document(page_content="x", metadata={"source": "data/supplies/coffee.md"})]
    install_answer_turn(monkeypatch, reply=reply, docs=docs)
    sp = FakeSpeaker()

    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where is coffee?"]), sp)

    assert sp.spoken == []
    assert result.spoken is None
    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == reply
    assert result.heard == "Where is coffee?"
    assert result.history == [
        {"role": "user", "content": "Where is coffee?"},
        {"role": "assistant", "content": reply},
    ]
    assert f"Assistant: {reply}\n" in capsys.readouterr().out


# --- voice_turn with rule 5 (rev 2): merged from test_voice_io_source_labels.py --- #


@pytest.mark.parametrize(
    "reply,expected_spoken",
    [
        ("There is no source.", "There is no source."),
        ("No recipe for that, sorry; check the sources folder with the chef.",
         "No recipe for that, sorry; check the sources folder with the chef."),
        ("Add sugar (source).", "Add sugar."),
    ],
)
def test_voice_turn_speaks_rev2_text(monkeypatch, capsys, reply, expected_spoken):
    """Covers: AC-16 (right), AC-26 (right/wrong), X-9, X-10, X-11. voice_turn prints the full
    reply and speaks the revision-2 speakable text."""
    docs = [Document(page_content="x", metadata={"source": "data/x.md"})]
    install_answer_turn(monkeypatch, reply=reply, docs=docs)
    speaker = FakeSpeaker()

    result = voice_turn(object(), object(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where is it?"]), speaker)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == reply
    assert result.spoken == expected_spoken
    assert speaker.spoken == [expected_spoken]
    assert f"Assistant: {reply}" in capsys.readouterr().out


def test_voice_turn_label_only_reply_not_spoken(monkeypatch):
    """Covers: AC-17 (boundary), EC-6, EC-20. A reply that is only '(Sources)' is printed but
    gives empty speakable text, so speak is not called and spoken is None."""
    install_answer_turn(monkeypatch, reply="(Sources)", docs=[])
    speaker = FakeSpeaker()

    result = voice_turn(object(), object(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where is it?"]), speaker)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == "(Sources)"
    assert result.spoken is None
    assert speaker.spoken == []


# --- voice_turn with rule 5.1 (rev 4): multi-word source labels --- #


def test_voice_turn_speaks_x12_without_source_path_label(monkeypatch, capsys):
    """Covers: AC-27 (right), AC-16 (right), X-12, EC-21. The M-3 reply is printed in full
    (including 'Source path: ...') before speaking, and the spoken text drops the label,
    citation and path."""
    docs = [Document(page_content="x", metadata={"source": "data/recipes/lemonade.md"})]
    install_answer_turn(monkeypatch, reply=X12_ANSWER, docs=docs)
    printed_before_speak = []
    speaker = FakeSpeaker(on_speak=lambda _t: printed_before_speak.append(capsys.readouterr().out))

    result = voice_turn(object(), object(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["How do I make lemonade?"]), speaker)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == X12_ANSWER
    assert result.spoken == X12_EXPECTED
    assert speaker.spoken == [X12_EXPECTED]
    assert "Source path" not in result.spoken
    assert len(printed_before_speak) == 1
    assert f"Assistant: {X12_ANSWER}\n" in printed_before_speak[0]


def test_voice_turn_multiword_label_only_reply_not_spoken(monkeypatch, capsys):
    """Covers: AC-27 (boundary -> empty), AC-17 (boundary), X-13, EC-6, EC-21. A reply that is
    only 'Sources used: <paths>' is printed but gives empty speakable text, so speak is not
    called and spoken is None."""
    reply = "Sources used: chai.md and lemonade.md"
    install_answer_turn(monkeypatch, reply=reply, docs=[])
    speaker = FakeSpeaker()

    result = voice_turn(object(), object(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Which recipes?"]), speaker)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == reply
    assert result.spoken is None
    assert speaker.spoken == []
    assert f"Assistant: {reply}\n" in capsys.readouterr().out


def test_voice_turn_speaks_kept_multiword_label(monkeypatch):
    """Covers: AC-27 (wrong: not a label), AC-16 (right), X-14. A label followed by words
    after the colon is kept and spoken unchanged."""
    reply = "Check the source of truth: the chef."
    install_answer_turn(monkeypatch, reply=reply, docs=[])
    speaker = FakeSpeaker()

    result = voice_turn(object(), object(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Who decides?"]), speaker)

    assert result.spoken == reply
    assert speaker.spoken == [reply]


# --------------------------------------------------------------------------- #
# AC-18: exit command
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text,heard", [("Bye.", "Bye."), (" EXIT! ", "EXIT!"), ("Quit?", "Quit?")])
def test_voice_turn_exit_command(monkeypatch, capsys, text, heard):
    """Covers: AC-18 (right), EC-10. Prints and speaks 'Bye.', returns EXIT with
    spoken == 'Bye.', does not call answer_turn, history unchanged."""
    calls = install_answer_turn(monkeypatch)
    sp = FakeSpeaker()
    history = _history()
    snapshot = copy.deepcopy(history)

    result = voice_turn(FakeStore(), FakeLLM(), history, FakeRecorder([good_audio()]),
                        FakeTranscriber([text]), sp)

    assert result.outcome is TurnOutcome.EXIT
    assert result.spoken == GOODBYE
    assert result.reply is None
    assert result.heard == heard
    assert result.history == snapshot
    assert history == snapshot
    assert sp.spoken == [GOODBYE]
    assert calls == []
    out = capsys.readouterr().out
    assert f"You (heard): {heard}" in out
    assert GOODBYE in out


@pytest.mark.parametrize("text", EC22_EXITS)
def test_voice_turn_rev5_exit_utterances(monkeypatch, capsys, text):
    """Covers: AC-28 (right), AC-18, EC-22. Every EC-22 exit row (including 'goodbye'-style
    phrases, which Rev 5 turned from questions into exits) prints and speaks 'Bye.',
    returns EXIT and does not call answer_turn. History unchanged."""
    calls = install_answer_turn(monkeypatch, reply="OK.")
    sp = FakeSpeaker()
    history = _history()
    snapshot = copy.deepcopy(history)

    result = voice_turn(FakeStore(), FakeLLM(), history, FakeRecorder([good_audio()]),
                        FakeTranscriber([text]), sp)

    assert result.outcome is TurnOutcome.EXIT
    assert result.heard == text.strip()
    assert result.reply is None
    assert result.spoken == GOODBYE
    assert result.history == snapshot
    assert history == snapshot
    assert sp.spoken == [GOODBYE]
    assert calls == []
    out = capsys.readouterr().out
    assert f"You (heard): {text.strip()}" in out
    assert GOODBYE in out


@pytest.mark.parametrize("text", [t for t in EC22_NON_EXITS if t.strip()])
def test_voice_turn_rev5_non_exit_utterances_are_answered(monkeypatch, text):
    """Covers: AC-28 (wrong: not an exit), AC-16, EC-22. Non-empty EC-22 'no' rows
    (fillers only, extra words, '!!!') are sent to answer_turn and answered."""
    calls = install_answer_turn(monkeypatch, reply="Shelf 2.")
    sp = FakeSpeaker()
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber([text]), sp)
    assert result.outcome is TurnOutcome.ANSWERED
    assert [c.question for c in calls] == [text.strip()]
    assert result.reply == "Shelf 2."
    assert sp.spoken == ["Shelf 2."]


def test_voice_turn_rev5_exit_uses_chat_is_exit_utterance_at_call_time(monkeypatch):
    """Covers: AC-28 (right), §10 Rev 5. voice_turn's exit decision follows
    chat.is_exit_utterance as patched at call time."""
    calls = install_answer_turn(monkeypatch, reply="OK.")
    monkeypatch.setattr(chat, "is_exit_utterance", lambda text: text == "pineapple")
    sp = FakeSpeaker()
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["pineapple"]), sp)
    assert result.outcome is TurnOutcome.EXIT
    assert calls == []
    assert sp.spoken == [GOODBYE]


def test_main_rev5_goodbye_phrase_ends_session(monkeypatch, capsys, main_env):
    """Covers: AC-28 (right), AC-23, EC-22. In voice_chat.main, a question then
    'Bye, see you later!' answers once, then exits with return 0."""
    calls = install_answer_turn(monkeypatch, reply="Shelf 2.")
    rec = FakeRecorder([good_audio(), good_audio(), good_audio()])
    tr = FakeTranscriber(["Where is the coffee?", "Bye, see you later!", "never reached"])
    sp = FakeSpeaker()

    rc = _run_main(recorder=rec, transcriber=tr, speaker=sp)

    assert rc == 0
    assert [c.question for c in calls] == ["Where is the coffee?"]
    assert rec.calls == 2
    assert sp.spoken == ["Shelf 2.", GOODBYE]


# --------------------------------------------------------------------------- #
# AC-19 / EC-12: speaker errors
# --------------------------------------------------------------------------- #


def test_voice_turn_speaker_error_on_answer_is_swallowed(monkeypatch, capsys):
    """Covers: AC-19 (wrong: speaker fails), EC-12. No raise; '(couldn't play audio: ...)'
    on stderr; outcome, history and spoken as if speaking succeeded; reply printed."""
    install_answer_turn(monkeypatch, reply="Shelf 2.")
    sp = FakeSpeaker(exc=RuntimeError("boom"))
    history = _history()

    result = voice_turn(FakeStore(), FakeLLM(), history, FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where is coffee?"]), sp)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.spoken == "Shelf 2."
    assert result.reply == "Shelf 2."
    assert result.history == _history() + [
        {"role": "user", "content": "Where is coffee?"},
        {"role": "assistant", "content": "Shelf 2."},
    ]
    out, err = capsys.readouterr()
    assert "(couldn't play audio: boom)" in err
    assert "Assistant: Shelf 2.\n" in out


def test_voice_turn_speaker_error_on_exit_is_swallowed(monkeypatch, capsys):
    """Covers: AC-19 (wrong: speaker fails on goodbye), EC-12. Still EXIT with spoken 'Bye.'."""
    install_answer_turn(monkeypatch)
    sp = FakeSpeaker(exc=OSError("no device"))
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["bye"]), sp)
    assert result.outcome is TurnOutcome.EXIT
    assert result.spoken == GOODBYE
    assert "(couldn't play audio: no device)" in capsys.readouterr().err


@pytest.mark.parametrize("where", ["recorder", "transcriber", "answer_turn"])
def test_voice_turn_other_component_errors_propagate(monkeypatch, where):
    """Covers: §5 'Speaker errors' paragraph (wrong). Exceptions from recorder.record,
    transcriber.transcribe and chat.answer_turn propagate."""
    class Boom(Exception):
        pass

    install_answer_turn(monkeypatch, exc=Boom("x") if where == "answer_turn" else None)
    rec = FakeRecorder([Boom("x")] if where == "recorder" else [good_audio()])
    tr = FakeTranscriber([Boom("x")] if where == "transcriber" else ["Where is coffee?"])
    with pytest.raises(Boom):
        voice_turn(FakeStore(), FakeLLM(), [], rec, tr, FakeSpeaker())


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_voice_turn_recorder_interrupts_propagate(monkeypatch, exc):
    """Covers: §3.2 Recorder / §5 A.6 (wrong). EOFError/KeyboardInterrupt from record()
    escape voice_turn so main can handle them."""
    install_answer_turn(monkeypatch)
    try:
        with pytest.raises(exc):
            voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([exc]), FakeTranscriber([]), FakeSpeaker())
    except KeyboardInterrupt:  # pragma: no cover - never let a stray Ctrl+C abort the run
        pytest.fail("KeyboardInterrupt escaped pytest.raises")


# --------------------------------------------------------------------------- #
# AC-20 / EC-19: docs without source
# --------------------------------------------------------------------------- #


def test_voice_turn_ignores_docs_without_source(monkeypatch):
    """Covers: AC-20 (boundary: missing/empty source), EC-19. Docs with no or empty
    source are ignored; real sources are still removed from speech."""
    docs = [
        Document(page_content="a", metadata={}),
        Document(page_content="b", metadata={"source": ""}),
        Document(page_content="c", metadata={"source": None}),
        Document(page_content="d", metadata={"source": "Blue Binder"}),
    ]
    install_answer_turn(monkeypatch, reply="Use the Blue Binder today.", docs=docs)
    sp = FakeSpeaker()
    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["Where are the recipes?"]), sp)
    assert sp.spoken == ["Use the today."]
    assert result.spoken == "Use the today."


def test_voice_turn_only_sourceless_docs(monkeypatch):
    """Covers: AC-20 (wrong: no usable sources), EC-19. Reply spoken unchanged."""
    docs = [Document(page_content="a", metadata={}), Document(page_content="b", metadata={"source": ""})]
    install_answer_turn(monkeypatch, reply="Plain answer.", docs=docs)
    sp = FakeSpeaker()
    voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
               FakeTranscriber(["Question?"]), sp)
    assert sp.spoken == ["Plain answer."]


# --------------------------------------------------------------------------- #
# EC-13: no docs end-to-end through the real chat.answer_turn
# --------------------------------------------------------------------------- #


def test_voice_turn_no_docs_speaks_unknown_reply(monkeypatch, capsys):
    """Covers: EC-13 (right), AC-2 via voice. Real chat.answer_turn with retrieve faked to
    return []: unknown-retrieval reply is printed and spoken unchanged, history updated."""
    monkeypatch.setattr(chat, "retrieve", lambda *a, **k: [])

    def no_answer(*a, **k):
        raise AssertionError("answer_from_context must not be called")

    monkeypatch.setattr(chat, "answer_from_context", no_answer)
    unknown = chat.unknown_retrieval_reply()
    sp = FakeSpeaker()

    result = voice_turn(FakeStore(), FakeLLM(), [], FakeRecorder([good_audio()]),
                        FakeTranscriber(["What is the wifi password?"]), sp)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.reply == unknown
    assert sp.spoken == [unknown]
    assert result.spoken == unknown
    assert result.history == [
        {"role": "user", "content": "What is the wifi password?"},
        {"role": "assistant", "content": unknown},
    ]
    assert f"Assistant: {unknown}\n" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# voice_chat.main (AC-21..AC-24, NFR-4)
# --------------------------------------------------------------------------- #


@pytest.fixture
def main_env(monkeypatch, tmp_path):
    """Existing CHROMA_DIR, fake build_store and ChatOllama, safe default component
    classes that record construction."""
    env = SimpleNamespace(store=FakeStore(), llms=[], build_calls=0, constructed=[])

    monkeypatch.setattr(chat, "CHROMA_DIR", tmp_path)

    def fake_build_store(*a, **k):
        env.build_calls += 1
        return env.store

    monkeypatch.setattr(chat, "build_store", fake_build_store)

    class FakeChatOllama:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            env.llms.append(self)

        def invoke(self, *a, **k):
            raise AssertionError("llm should not be invoked")

    monkeypatch.setattr(voice_chat, "ChatOllama", FakeChatOllama)

    def make_factory(name, instance_attr):
        def factory(*a, **k):
            env.constructed.append(name)
            inst = getattr(env, instance_attr, None)
            if inst is None:
                raise AssertionError(f"{name} constructed unexpectedly")
            return inst
        return factory

    env.default_recorder = None
    env.default_transcriber = None
    env.default_speaker = None
    monkeypatch.setattr(voice_chat, "SoundDeviceRecorder", make_factory("recorder", "default_recorder"))
    monkeypatch.setattr(voice_chat, "WhisperTranscriber", make_factory("transcriber", "default_transcriber"))
    monkeypatch.setattr(voice_chat, "PiperSpeaker", make_factory("speaker", "default_speaker"))
    return env


def _run_main(**kwargs):
    try:
        return voice_chat.main(**kwargs)
    except KeyboardInterrupt:
        pytest.fail("KeyboardInterrupt escaped voice_chat.main")


def test_main_missing_chroma_returns_1(monkeypatch, tmp_path, capsys, main_env):
    """Covers: AC-21 (wrong: no store), EC-16. Returns 1, message on stderr, no component
    constructed, store not built."""
    missing = tmp_path / "no-such-chroma"
    monkeypatch.setattr(chat, "CHROMA_DIR", missing)

    rc = _run_main()

    assert rc == 1
    assert main_env.constructed == []
    assert main_env.build_calls == 0
    err = capsys.readouterr().err
    assert f"Chroma store not found at {missing}. Run scripts/ingest.py first." in err


def test_main_missing_chroma_does_not_use_injected_components(monkeypatch, tmp_path, main_env):
    """Covers: AC-21 (wrong), EC-16. With injected fakes, nothing is recorded or spoken."""
    monkeypatch.setattr(chat, "CHROMA_DIR", tmp_path / "missing")
    rec, sp = FakeRecorder([good_audio()]), FakeSpeaker()
    rc = _run_main(recorder=rec, transcriber=FakeTranscriber(["hi"]), speaker=sp)
    assert rc == 1
    assert rec.calls == 0
    assert sp.spoken == []


@pytest.mark.parametrize("failing", ["SoundDeviceRecorder", "WhisperTranscriber", "PiperSpeaker"])
def test_main_component_setup_error_returns_1(monkeypatch, capsys, main_env, failing):
    """Covers: AC-22 (wrong: setup fails), EC-17. A constructor raising VoiceSetupError
    -> its message on stderr, return 1, no turn run."""
    main_env.default_recorder = FakeRecorder([good_audio()])
    main_env.default_transcriber = FakeTranscriber(["bye"])
    main_env.default_speaker = FakeSpeaker()
    msg = f"{failing}: could not initialise test-device"

    def raiser(*a, **k):
        raise VoiceSetupError(msg)

    monkeypatch.setattr(voice_chat, failing, raiser)

    rc = _run_main()

    assert rc == 1
    assert msg in capsys.readouterr().err
    assert main_env.default_recorder.calls == 0
    assert main_env.build_calls == 0


def test_main_setup_error_with_partial_injection(monkeypatch, capsys, main_env):
    """Covers: AC-22 (wrong), §3.4. Only the None argument is built; its VoiceSetupError
    is reported and main returns 1."""
    def raiser(*a, **k):
        raise VoiceSetupError("Piper voice en_US-lessac-medium could not be downloaded")

    monkeypatch.setattr(voice_chat, "PiperSpeaker", raiser)
    rec = FakeRecorder([good_audio()])
    rc = _run_main(recorder=rec, transcriber=FakeTranscriber(["bye"]))
    assert rc == 1
    assert "Piper voice en_US-lessac-medium could not be downloaded" in capsys.readouterr().err
    assert rec.calls == 0


def test_main_runs_turns_and_carries_history(monkeypatch, capsys, main_env):
    """Covers: AC-23 (right), NFR-4 (unit: speak finishes before next record). Turns run,
    history flows from one turn to the next (also across a skipped turn), banner
    printed, store/llm built as specified, returns 0 on EXIT."""
    log: list = []
    rec = FakeRecorder([good_audio(), np.array([], dtype=np.float32), good_audio(), good_audio()], log)
    tr = FakeTranscriber(["Where is the coffee?", "And the sugar?", "quit"], log)
    sp = FakeSpeaker(log)
    calls = []

    def fake_answer_turn(store, llm, history, question):
        calls.append(SimpleNamespace(store=store, llm=llm, history=copy.deepcopy(history), question=question))
        reply = f"REPLY-{len(calls)}."
        return chat.TurnResult(reply, list(history) + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply},
        ], [])

    monkeypatch.setattr(chat, "answer_turn", fake_answer_turn)

    rc = _run_main(recorder=rec, transcriber=tr, speaker=sp)

    assert rc == 0
    assert [c.question for c in calls] == ["Where is the coffee?", "And the sugar?"]
    assert calls[0].history == []
    assert calls[1].history == [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "REPLY-1."},
    ]
    # store and llm wiring
    assert main_env.build_calls == 1
    assert len(main_env.llms) == 1
    llm = main_env.llms[0]
    assert llm.kwargs == {"model": chat.CHAT_MODEL, "temperature": 0.1}
    assert all(c.store is main_env.store and c.llm is llm for c in calls)
    # no default components were constructed
    assert main_env.constructed == []
    # loop stopped at EXIT: exactly four recordings
    assert rec.calls == 4
    assert sp.spoken == ["REPLY-1.", "REPLY-2.", GOODBYE]
    # NFR-4: every speak completes before the next record
    assert log == [
        "record", "transcribe", "speak",
        "record",
        "record", "transcribe", "speak",
        "record", "transcribe", "speak",
    ]
    out = capsys.readouterr().out
    assert "Bay Laurel Catering voice chatbot" in out
    assert "Press Enter to start talking and Enter again to stop. Say quit, exit, or bye to leave." in out
    assert out.index("Bay Laurel Catering voice chatbot") < out.index("You (heard):")


def test_main_builds_missing_components_from_module_globals(monkeypatch, main_env):
    """Covers: AC-23 (right), §3.4. Arguments left as None are built via
    SoundDeviceRecorder / WhisperTranscriber / PiperSpeaker looked up at call time."""
    install_answer_turn(monkeypatch)
    main_env.default_recorder = FakeRecorder([good_audio()])
    main_env.default_transcriber = FakeTranscriber(["exit"])
    main_env.default_speaker = FakeSpeaker()

    rc = _run_main()

    assert rc == 0
    assert sorted(main_env.constructed) == ["recorder", "speaker", "transcriber"]
    assert main_env.default_recorder.calls == 1
    assert main_env.default_speaker.spoken == [GOODBYE]


def test_main_exit_with_failing_speaker_returns_0(monkeypatch, capsys, main_env):
    """Covers: AC-23 (boundary), EC-12. Speaker failure on goodbye still exits with 0."""
    install_answer_turn(monkeypatch)
    rc = _run_main(recorder=FakeRecorder([good_audio()]), transcriber=FakeTranscriber(["Bye."]),
                   speaker=FakeSpeaker(exc=RuntimeError("dead")))
    assert rc == 0
    assert "(couldn't play audio: dead)" in capsys.readouterr().err


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
@pytest.mark.parametrize("turns_before", [0, 1], ids=["first-turn", "after-a-turn"])
def test_main_interrupt_prints_bye_and_returns_0(monkeypatch, capsys, main_env, exc, turns_before):
    """Covers: AC-24 (wrong: user interrupts), EC-18. KeyboardInterrupt/EOFError from the
    recorder -> prints Bye. and returns 0."""
    calls = install_answer_turn(monkeypatch, reply="Shelf 2.")
    items = [good_audio()] * turns_before + [exc]
    rec = FakeRecorder(items)
    tr = FakeTranscriber(["Where is coffee?"] * turns_before)

    rc = _run_main(recorder=rec, transcriber=tr, speaker=FakeSpeaker())

    assert rc == 0
    assert len(calls) == turns_before
    out = capsys.readouterr().out
    assert "\nBye." in out
