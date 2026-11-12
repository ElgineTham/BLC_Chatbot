"""Spec 001 (voice-io), part 1: the chat.py refactor (answer_turn, TurnResult, main).

Revision 5: EXIT_COMMANDS / EXIT_FILLERS, normalize_utterance, is_exit_utterance and
chat.main's new exit decision (EC-22, AC-28, AC-29) are tested at the end of this file.

Spec 014: the answer_turn tests no longer patch `answer_from_context` / `maybe_summarize` (deleted).
They run the real flow (answer_turn -> run_turn -> run_stages) with a fake store
(similarity_search(query, k=...)) and a scripted fake model, and read what the model was sent
(ScriptLLM.invocations) to check the same things the old wiring assertions checked:
  - "answer_from_context got (llm, prior, docs, q)"  -> the final model call holds the history, the
    retrieved chunk text and the question;
  - "maybe_summarize(llm, history) ran once"          -> a short history gives exactly one model call
    (no summary call); a long one gives a summary call first;
  - "the summarized history (not the raw one) is what goes on" -> the final call holds the summary text
    and none of the raw long history.
Spec 014 EC-6: each script holds exactly the model calls the flow makes. Most questions are DOCS questions
with no number and no item word (spec 013: no router call), so the replies are [final] or, for a long
history, [summary, final]. "Where is sugar?" has an item word, so its script is [summary, "D", final].

Unit tests only. Ollama and Chroma are faked.
"""

from __future__ import annotations

import copy
import dataclasses
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

import chat


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class RecordingObject:
    """Records any attribute access / call made on it. Used to prove no calls happen."""

    def __init__(self) -> None:
        object.__setattr__(self, "accessed", [])

    def __getattr__(self, name):
        self.accessed.append(name)

        def _call(*args, **kwargs):
            self.accessed.append(f"{name}()")
            raise AssertionError(f"unexpected call to {name}")

        return _call


class ScriptLLM:
    """Scripted chat model: each invoke pops the next reply (a str becomes an AIMessage) and records the
    messages. Has no bind_tools, so any tool step would fail the test."""

    def __init__(self, *replies) -> None:
        self.script = list(replies)
        self.invocations: list = []

    def invoke(self, messages, *args, **kwargs):
        self.invocations.append(list(messages))
        if not self.script:
            raise AssertionError("llm.invoke was called more times than scripted")
        reply = self.script.pop(0)
        return AIMessage(content=reply) if isinstance(reply, str) else reply


class FakeStore:
    def __init__(self, docs=None) -> None:
        self.docs = list(docs or [])
        self.calls: list = []

    def similarity_search(self, query, k=4, *args, **kwargs):
        self.calls.append((query, k))
        return list(self.docs)


def _text(messages) -> str:
    return "\n".join(str(getattr(m, "content", "")) for m in messages)


def _docs():
    return [
        Document(page_content="Coffee is on shelf 2.", metadata={"source": "data/supplies/coffee.md"}),
        Document(page_content="Sugar is in bin 4.", metadata={"source": "data/supplies/sugar.md"}),
    ]


def _small_history():
    return [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ]


def _big_history():
    # ~8000 words: over a 2000-token limit under any reasonable token counter.
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "catering menu details " * 130}
        for i in range(20)
    ]


# --------------------------------------------------------------------------- #
# TurnResult
# --------------------------------------------------------------------------- #


def test_turn_result_fields_and_frozen():
    """Covers: §3.1 TurnResult (right). Has reply/history/docs fields and is frozen."""
    tr = chat.TurnResult("r", [{"role": "user", "content": "q"}], [])
    assert tr.reply == "r"
    assert tr.history == [{"role": "user", "content": "q"}]
    assert tr.docs == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        tr.reply = "other"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-1: docs retrieved
# --------------------------------------------------------------------------- #


def test_answer_turn_with_docs_returns_answer_docs_and_history():
    """Covers: AC-1 (right). reply is the model's final reply, docs is the retrieved list,
    history == prior + [user q, assistant reply]. The store is searched once with (q, TOP_K); the
    model is called once (no summary call for a short history) and that call holds the history,
    the retrieved text and the question."""
    store = FakeStore(_docs())
    llm = ScriptLLM("ANSWER-REPLY")
    history = _small_history()

    result = chat.answer_turn(store, llm, history, "Where is the coffee?")

    assert isinstance(result, chat.TurnResult)
    assert result.reply == "ANSWER-REPLY"
    assert result.docs == _docs()
    assert result.history == history + [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "ANSWER-REPLY"},
    ]
    assert store.calls == [("Where is the coffee?", chat.TOP_K)]
    assert len(llm.invocations) == 1
    sent = _text(llm.invocations[0])
    assert "Hello! How can I help?" in sent  # the history
    assert "Coffee is on shelf 2." in sent and "Sugar is in bin 4." in sent  # the docs
    assert "Where is the coffee?" in sent  # the question


def test_answer_turn_uses_summarized_history_for_answer_and_history():
    """Covers: AC-1 (right), §3.1 steps 2/4/5. For a long history the summary (not the raw input)
    is what the answer call holds and what the returned history starts with."""
    # EC-6: "Where is sugar?" has a pull sheet item word, so the flow makes a router call between the
    # summary call and the final call: summary, router letter (D), final.
    llm = ScriptLLM("PRIOR-SUMMARY", "D", "ANSWER-REPLY")
    big = _big_history()

    result = chat.answer_turn(FakeStore(_docs()), llm, big, "Where is sugar?")

    assert len(llm.invocations) == 3  # summary call, router call, then the final call
    final = _text(llm.invocations[-1])
    assert "PRIOR-SUMMARY" in final
    assert "catering menu details" not in final
    assert "PRIOR-SUMMARY" in result.history[0]["content"]
    assert result.history[1:] == [
        {"role": "user", "content": "Where is sugar?"},
        {"role": "assistant", "content": "ANSWER-REPLY"},
    ]


def test_answer_turn_prints_nothing_under_limit(capsys):
    """Covers: §3.1 'answer_turn prints nothing itself' (right)."""
    chat.answer_turn(FakeStore(_docs()), ScriptLLM("ok"), _small_history(), "Where is the coffee?")
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


# --------------------------------------------------------------------------- #
# AC-2 / EC-13: no docs
# --------------------------------------------------------------------------- #


def test_answer_turn_no_docs_uses_unknown_reply():
    """Covers: AC-2 (right), EC-13. No docs -> unknown_retrieval_reply(), docs == [],
    the model is never called, history gains user + assistant entries."""
    llm = ScriptLLM()  # any invoke fails the test
    history = _small_history()

    result = chat.answer_turn(FakeStore([]), llm, history, "What is the wifi password?")

    expected = chat.unknown_retrieval_reply()
    assert result.reply == expected
    assert result.docs == []
    assert llm.invocations == []
    assert result.history == history + [
        {"role": "user", "content": "What is the wifi password?"},
        {"role": "assistant", "content": expected},
    ]


def test_answer_turn_no_docs_does_not_invoke_llm():
    """Covers: AC-2 (wrong path guarded). With a short history and no docs, the LLM is never
    asked for an answer."""
    llm = ScriptLLM()
    result = chat.answer_turn(FakeStore([]), llm, _small_history(), "Unknown thing?")
    assert result.reply == chat.unknown_retrieval_reply()
    assert llm.invocations == []


# --------------------------------------------------------------------------- #
# AC-3 / EC-14: no mutation, summary path
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("with_docs", [True, False], ids=["docs", "no-docs"])
def test_answer_turn_does_not_mutate_history_under_limit(with_docs):
    """Covers: AC-3 (right), §3.1 step 6. Under-limit and no-docs paths leave the
    caller's history list unchanged and return a different list object."""
    store = FakeStore(_docs() if with_docs else [])
    llm = ScriptLLM("ok") if with_docs else ScriptLLM()
    history = _small_history()
    snapshot = copy.deepcopy(history)
    history_id = id(history)

    result = chat.answer_turn(store, llm, history, "Where is the coffee?")

    assert history == snapshot
    assert len(history) == 2
    assert result.history is not history
    assert id(history) == history_id


def test_answer_turn_over_limit_summarizes_without_mutation(capsys):
    """Covers: AC-3 (boundary: over token limit), EC-14. Real summarizing with a scripted llm:
    returned history starts with the summary item, ends with the new user/assistant pair, caller's
    list is untouched, the answer call holds the summary (not the raw history), and the existing
    summarizing message is still printed."""
    history = _big_history()
    snapshot = copy.deepcopy(history)
    llm = ScriptLLM("SUMMARY-XYZ", "ANSWER-REPLY")

    result = chat.answer_turn(FakeStore(_docs()), llm, history, "Where is the coffee?")

    assert history == snapshot, "caller's history must not be mutated"
    assert len(llm.invocations) == 2, "summarization should have asked the llm for a summary, then answered"
    first = result.history[0]
    assert isinstance(first, dict)
    assert "SUMMARY-XYZ" in first["content"]
    assert first not in snapshot
    assert result.history[-2:] == [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "ANSWER-REPLY"},
    ]
    assert len(result.history) == 3  # summary, user, assistant
    # the history the answer call saw is the summarized history
    answer_call = _text(llm.invocations[-1])
    assert "SUMMARY-XYZ" in answer_call
    assert "catering menu details" not in answer_call
    out = capsys.readouterr().out
    assert "history over 2000 tokens" in out


def test_answer_turn_over_limit_no_docs_does_not_mutate():
    """Covers: AC-3 (boundary: over limit + no docs). Caller history untouched,
    reply is the unknown-retrieval reply, summary item first."""
    history = _big_history()
    snapshot = copy.deepcopy(history)
    llm = ScriptLLM("SUMMARY-XYZ")  # the summary call only; no answer call without docs

    result = chat.answer_turn(FakeStore([]), llm, history, "Unknown?")

    assert history == snapshot
    assert "SUMMARY-XYZ" in result.history[0]["content"]
    assert result.history[-1] == {"role": "assistant", "content": chat.unknown_retrieval_reply()}
    assert result.docs == []


# --------------------------------------------------------------------------- #
# AC-4 / EC-15: empty and padded questions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("question", ["", " ", "   ", "\n\t  "], ids=["empty", "space", "spaces", "ws-mix"])
def test_answer_turn_empty_question_raises_before_any_call(question):
    """Covers: AC-4 (wrong), EC-15 (boundary: empty / whitespace-only).
    ValueError and no store or llm calls; the history is unchanged."""
    store, llm = RecordingObject(), RecordingObject()
    history = _small_history()
    snapshot = copy.deepcopy(history)

    with pytest.raises(ValueError):
        chat.answer_turn(store, llm, history, question)

    assert store.accessed == []
    assert llm.accessed == []
    assert history == snapshot


def test_answer_turn_padded_question_is_stripped_everywhere():
    """Covers: AC-4 (right), EC-15. Surrounding whitespace is stripped for retrieval,
    the answer prompt and history."""
    store = FakeStore(_docs())
    llm = ScriptLLM("ok")
    result = chat.answer_turn(store, llm, [], "  \tWhere is the coffee?\n ")

    assert store.calls[0][0] == "Where is the coffee?"
    assert "Where is the coffee?" in str(llm.invocations[0][-1].content)
    assert "\tWhere" not in _text(llm.invocations[0])
    assert result.history[0] == {"role": "user", "content": "Where is the coffee?"}


def test_answer_turn_single_char_question_accepted():
    """Covers: AC-4 (boundary: smallest non-empty question). One visible char is valid."""
    result = chat.answer_turn(FakeStore(_docs()), ScriptLLM("ANSWER-REPLY"), [], " ? ")
    assert result.history[0] == {"role": "user", "content": "?"}
    assert result.reply == "ANSWER-REPLY"


# --------------------------------------------------------------------------- #
# AC-5: chat.main
# --------------------------------------------------------------------------- #


@pytest.fixture
def chat_main_env(monkeypatch, tmp_path):
    """Make chat.main runnable offline: existing CHROMA_DIR, fake store, fake answer_turn,
    scripted input()."""
    env = SimpleNamespace(inputs=[], consumed=0, turn_calls=[], replies=[], store=FakeStore())

    monkeypatch.setattr(chat, "CHROMA_DIR", tmp_path)
    monkeypatch.setattr(chat, "build_store", lambda *a, **k: env.store)

    def fake_input(*args, **kwargs):
        if env.consumed >= len(env.inputs):
            raise AssertionError("input() called more times than scripted")
        item = env.inputs[env.consumed]
        env.consumed += 1
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item
        return item

    monkeypatch.setattr("builtins.input", fake_input)

    def fake_answer_turn(store, llm, history, question):
        env.turn_calls.append((store, llm, history, question))
        n = len(env.turn_calls)
        reply = f"REPLY-{n}"
        new_hist = list(history) + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply},
        ]
        return chat.TurnResult(reply, new_hist, [])

    monkeypatch.setattr(chat, "answer_turn", fake_answer_turn)
    return env


def _an_exit_command() -> str:
    return sorted(chat.EXIT_COMMANDS)[0]


def test_chat_main_routes_turns_through_answer_turn(chat_main_env, capsys):
    """Covers: AC-5 (right), NFR-5. Each non-empty, non-exit input goes to
    chat.answer_turn (module global), 'Assistant: {reply}' is printed, and the
    returned history is passed into the next turn."""
    env = chat_main_env
    env.inputs = ["Where is the coffee?", "And the sugar?", _an_exit_command()]

    chat.main()

    assert [c[3] for c in env.turn_calls] == ["Where is the coffee?", "And the sugar?"]
    assert env.turn_calls[0][0] is env.store
    assert env.turn_calls[0][2] == []
    assert env.turn_calls[1][2] == [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "REPLY-1"},
    ]
    out = capsys.readouterr().out
    assert "Assistant: REPLY-1\n" in out
    assert "Assistant: REPLY-2\n" in out
    assert out.index("Assistant: REPLY-1") < out.index("Assistant: REPLY-2")


def test_chat_main_input_is_stripped_before_answer_turn(chat_main_env):
    """Covers: AC-5 (boundary: padded input). raw is already stripped when passed on."""
    env = chat_main_env
    env.inputs = ["   Where is the coffee?   ", _an_exit_command()]
    chat.main()
    assert [c[3] for c in env.turn_calls] == ["Where is the coffee?"]


def test_chat_main_exit_command_stops_without_answer(chat_main_env):
    """Covers: AC-5 (wrong: exit input is not a question). Exit command ends the loop,
    answer_turn not called, no further input read."""
    env = chat_main_env
    env.inputs = [_an_exit_command(), "should never be read"]
    chat.main()
    assert env.turn_calls == []
    assert env.consumed == 1


@pytest.mark.parametrize("blank", ["", "   ", "\t"], ids=["empty", "spaces", "tab"])
def test_chat_main_empty_input_is_ignored(chat_main_env, blank):
    """Covers: AC-5 (boundary: empty input). Empty/whitespace input is not sent to
    answer_turn and the loop keeps reading."""
    env = chat_main_env
    env.inputs = [blank, "Where is the coffee?", _an_exit_command()]
    chat.main()
    assert [c[3] for c in env.turn_calls] == ["Where is the coffee?"]
    assert env.consumed == 3


def test_chat_main_eof_exits_cleanly(chat_main_env):
    """Covers: AC-5 (wrong: EOF on input). EOFError ends main without raising and
    without calling answer_turn."""
    env = chat_main_env
    env.inputs = [EOFError]
    chat.main()
    assert env.turn_calls == []


# --------------------------------------------------------------------------- #
# Revision 5: exit sets, normalize_utterance, is_exit_utterance (AC-28, EC-22)
# --------------------------------------------------------------------------- #

SPEC_EXIT_COMMANDS = frozenset({
    "bye", "bye bye", "goodbye", "good bye",
    "see you", "see ya", "see you later", "see you soon", "talk to you later",
    "quit", "exit", "stop", "im done", "thats all", "thats it",
    "take care", "good night", "goodnight", "have a good one",
})
SPEC_EXIT_FILLERS = frozenset({
    "okay", "ok", "alright", "all right", "thanks", "thank you",
})

# EC-22 table, verbatim, with the normalized form each row must produce.
# "’" is the curly apostrophe from the spec row.
EC22_EXIT_ROWS = [
    ("Bye.", "bye"),
    (" EXIT! ", "exit"),
    ("Quit?", "quit"),
    ("Stop.", "stop"),
    ("Goodbye.", "goodbye"),
    ("Good-bye!", "good bye"),
    ("Bye-bye.", "bye bye"),
    ("Goodnight.", "goodnight"),
    ("Bye, see you later!", "bye see you later"),
    ("Okay, thanks, bye-bye.", "okay thanks bye bye"),
    ("Thank you, good night!", "thank you good night"),
    ("Alright, that's all, goodbye.", "alright thats all goodbye"),
    ("That’s it.", "thats it"),
    ("I'm done.", "im done"),
    ("Take care!", "take care"),
    ("Have a good one.", "have a good one"),
    ("See ya!", "see ya"),
    ("Talk to you later.", "talk to you later"),
    ("bye bye bye", "bye bye bye"),
]
EC22_NON_EXIT_ROWS = [
    ("Thanks.", "thanks"),
    ("Okay.", "okay"),
    ("Thank you, alright.", "thank you alright"),
    ("Bye, where is the coffee?", "bye where is the coffee"),
    ("See you later at the bar.", "see you later at the bar"),
    ("Good.", "good"),
    ("Have a good day.", "have a good day"),
    ("That's all folks.", "thats all folks"),
    ("Stop the timer.", "stop the timer"),
    ("", ""),
    ("!!!", ""),
]


def test_exit_commands_match_spec():
    """Covers: AC-28 (right), §10 Rev 5 interface. EXIT_COMMANDS is a frozenset with
    exactly the listed entries."""
    assert isinstance(chat.EXIT_COMMANDS, frozenset)
    assert chat.EXIT_COMMANDS == SPEC_EXIT_COMMANDS


def test_exit_fillers_match_spec():
    """Covers: AC-28 (right), §10 Rev 5 interface. EXIT_FILLERS is a frozenset with
    exactly the listed entries, disjoint from EXIT_COMMANDS."""
    assert isinstance(chat.EXIT_FILLERS, frozenset)
    assert chat.EXIT_FILLERS == SPEC_EXIT_FILLERS
    assert not (chat.EXIT_FILLERS & chat.EXIT_COMMANDS)


@pytest.mark.parametrize("entry", sorted(SPEC_EXIT_COMMANDS | SPEC_EXIT_FILLERS))
def test_exit_entries_are_already_normalized(entry):
    """Covers: AC-28 (right), §10 Rev 5 'entries stored already normalized'.
    normalize_utterance leaves every entry unchanged."""
    assert chat.normalize_utterance(entry) == entry


@pytest.mark.parametrize("text,expected", EC22_EXIT_ROWS + EC22_NON_EXIT_ROWS)
def test_normalize_utterance_ec22_rows(text, expected):
    """Covers: AC-28 (right + boundary: '' and '!!!'), EC-22. Every EC-22 row normalizes
    to its casefolded, apostrophe-free, punctuation-to-space, collapsed form."""
    assert chat.normalize_utterance(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("bye-bye!", "bye bye"),                 # docstring example
        ("that's", "thats"),                     # docstring example
        ("I'm", "im"),                           # docstring example
        ("That’s", "thats"),                # curly apostrophe deleted, not spaced
        ("rock 'n' roll", "rock n roll"),        # apostrophes deleted, not turned into spaces
        ("don't-stop", "dont stop"),
        ("  Hello,\t\tWorld \n ", "hello world"),  # whitespace collapsed and stripped
        ("a.b,c;d", "a b c d"),
        ("24/7", "24 7"),                        # digits kept
        ("Bye 2", "bye 2"),
        ("STRASSE Straße", "strasse strasse"),   # casefold, not just lower
        ("   ", ""),
        ("'’", ""),                         # only apostrophes
        ("?!.,;:-", ""),
    ],
)
def test_normalize_utterance_rules(text, expected):
    """Covers: AC-28 (right + boundary: no letters/digits -> ''). Steps 1-4 of
    normalize_utterance, including apostrophe deletion before punctuation replacement."""
    assert chat.normalize_utterance(text) == expected


@pytest.mark.parametrize("text,_norm", EC22_EXIT_ROWS)
def test_is_exit_utterance_ec22_exit_rows(text, _norm):
    """Covers: AC-28 (right), EC-22. Every 'yes' row is an exit."""
    assert chat.is_exit_utterance(text) is True


@pytest.mark.parametrize("text,_norm", EC22_NON_EXIT_ROWS)
def test_is_exit_utterance_ec22_non_exit_rows(text, _norm):
    """Covers: AC-28 (wrong + boundary: '' and '!!!' have no words), EC-22. Every 'no'
    row is not an exit."""
    assert chat.is_exit_utterance(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "see you later",              # longer entry must win over 'see you' + 'later'
        "talk to you later",
        "Talk-to-you-later!",
        "see you soon",
        "all right, bye",             # multi-word filler then command
        "bye, thanks",                # command then filler (any order)
        "ok ok goodbye",              # filler repeated
        "goodbye goodbye",            # command repeated
        "Good\nbye",                  # newline collapses to a single space -> 'good bye'
        "GOODNIGHT",
        "that’s all",
        "have a good one, thank you",
        "thank you, take care, see ya",
        "  exit  ",
        "Bye bye-bye!",
    ],
)
def test_is_exit_utterance_extra_exits(text):
    """Covers: AC-28 (right), EC-22 rule (b)/(c). Splits into consecutive whole entries,
    any order, repeats allowed, multi-word entries over consecutive words."""
    assert chat.is_exit_utterance(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "thanks thanks",              # fillers only, repeated
        "all right",                  # multi-word filler only
        "ok, thank you, alright",     # several fillers, no command
        "see you later later",        # trailing word not an entry
        "goodbye see",                # 'see' alone is not an entry
        "byebye",                     # not an entry (no separator)
        "bye 2",                      # digit word is not an entry
        "exiting",                    # whole words only
        "good by",
        "see",
        "good",
        "'",
        "   ",
    ],
)
def test_is_exit_utterance_extra_non_exits(text):
    """Covers: AC-28 (wrong + boundary: no words), EC-22 rules (a)-(c). Not fully covered
    by entries, fillers only, or no words."""
    assert chat.is_exit_utterance(text) is False


# --------------------------------------------------------------------------- #
# AC-29 (Rev 5): chat.main exit decision
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text,_norm", EC22_EXIT_ROWS)
def test_chat_main_rev5_exit_utterances(chat_main_env, capsys, text, _norm):
    """Covers: AC-29 (right), EC-22. Each EC-22 exit row ends text chat: prints 'Bye.',
    returns 0, answer_turn not called, no further input read."""
    env = chat_main_env
    env.inputs = [text, "should never be read"]

    rc = chat.main()

    assert rc == 0
    assert env.turn_calls == []
    assert env.consumed == 1
    assert "Bye." in capsys.readouterr().out


@pytest.mark.parametrize("text,_norm", [r for r in EC22_NON_EXIT_ROWS if r[0].strip()])
def test_chat_main_rev5_non_exit_inputs_are_answered(chat_main_env, capsys, text, _norm):
    """Covers: AC-29 (wrong: not an exit), EC-22. Non-empty 'no' rows ('Thanks.',
    'Bye, where is the coffee?', '!!!', ...) are sent to answer_turn and answered."""
    env = chat_main_env
    env.inputs = [text, "bye"]

    rc = chat.main()

    assert rc == 0
    assert [c[3] for c in env.turn_calls] == [text.strip()]
    assert "Assistant: REPLY-1\n" in capsys.readouterr().out


def test_chat_main_rev5_exit_after_a_question(chat_main_env, capsys):
    """Covers: AC-29 (right). 'Goodbye.' after a normal question ends the loop."""
    env = chat_main_env
    env.inputs = ["Where is the coffee?", "Goodbye.", "should never be read"]

    rc = chat.main()

    assert rc == 0
    assert [c[3] for c in env.turn_calls] == ["Where is the coffee?"]
    assert env.consumed == 2
    out = capsys.readouterr().out
    assert out.index("Assistant: REPLY-1") < out.rindex("Bye.")


def test_chat_main_rev5_padded_exit_utterance(chat_main_env):
    """Covers: AC-29 (boundary: surrounding whitespace). '   Bye, see you later!  ' exits."""
    env = chat_main_env
    env.inputs = ["   Bye, see you later!  ", "should never be read"]
    assert chat.main() == 0
    assert env.turn_calls == []


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_chat_main_rev5_empty_input_still_ignored(chat_main_env, blank):
    """Covers: AC-29 (boundary: empty input), EC-22 'still true'. Empty input is ignored
    before any exit check; the loop reads on and a later goodbye exits."""
    env = chat_main_env
    env.inputs = [blank, "Goodbye.", "should never be read"]
    assert chat.main() == 0
    assert env.turn_calls == []
    assert env.consumed == 2


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_chat_main_rev5_eof_and_interrupt_print_bye_return_0(chat_main_env, capsys, exc):
    """Covers: AC-29 (wrong: input interrupted), §3.1. EOFError or KeyboardInterrupt
    from input prints '\\nBye.' and returns 0 without calling answer_turn."""
    env = chat_main_env
    env.inputs = [exc]

    rc = chat.main()

    assert rc == 0
    assert env.turn_calls == []
    assert "\nBye." in capsys.readouterr().out
