"""AC-3: the stage log of run_turn (EC-14, NFR-4), and AC-2's answer_turn check (EC-15).

One INFO record per stage on the logger "blc.flow", in execution order: prompt, retrieval, route,
one tool record per TOOL part, then reply (only if generated). Nothing is printed. Unit tests with a
fake store and a scripted fake model; no Ollama, no network, nothing read under data/ (NFR-2).
"""

from __future__ import annotations

import logging

import pytest

import chat
from blc.trace import format_trace
from blc.tools.bev_tools import BEV_TOOL_NAME

LOGGER = "blc.flow"
DOCS_Q = "Where is the coffee?"
TOOL_Q = "How many cambros for 6 gallons of peach tea?"
LEMON_Q = "Where are lemons kept?"
CUPS_Q = "How many cold cups for 45 guests?"
BOTH_Q = LEMON_Q + " " + CUPS_Q
TWO_TOOL_Q = TOOL_Q + " " + CUPS_Q
VALID_CAMBROS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
VALID_CUPS = {"item": "cups", "drinks": ["lemonade"], "guests": 45}
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]


@pytest.fixture
def docs(doc):
    return [doc("Coffee is under the coffee machine.", "data/supplies/coffee.md"),
            doc("Sugar is in bin 4.", "data/supplies/sugar.md")]


@pytest.fixture
def run(monkeypatch, bev_tool, FakeStore, docs, caplog):
    """run(llm, question, store=None, generate=True) -> (trace, records on logger 'blc.flow')."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    caplog.set_level(logging.INFO, logger=LOGGER)

    def _run(llm, question=DOCS_Q, store=None, generate=True):
        caplog.clear()
        trace = chat.run_turn(FakeStore(docs) if store is None else store, llm, list(HISTORY), question,
                              generate=generate)
        return trace, [r for r in caplog.records if r.name == LOGGER]

    return _run


def stage_of(record):
    msg = record.getMessage()
    assert msg.startswith("["), f"record does not start with a bracketed stage name: {msg!r}"
    return msg[1:msg.index("]")]


# ---------------------------------------------------------------- EC-14 order and format

def test_ec14_docs_question_records_in_order(run, Scripted, jparts):
    """Covers: AC-3 (right), EC-14. DOCS question: [prompt], [retrieval], [route], [reply], each at INFO, nothing else on the logger."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "Under the machine."])
    _, records = run(llm)
    assert [stage_of(r) for r in records] == ["prompt", "retrieval", "route", "reply"]
    assert all(r.levelno == logging.INFO for r in records)
    assert all(r.getMessage().startswith(f"[{stage_of(r)}]") for r in records)


def test_ec14_tool_question_has_a_tool_record(run, Scripted, jparts, ai, tc):
    """Covers: AC-3 (right), EC-14. TOOL question: one [tool] record between [route] and [reply]."""
    llm = Scripted([jparts(("TOOL", TOOL_Q)), "Bring two."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    _, records = run(llm, question=TOOL_Q)
    assert [stage_of(r) for r in records] == ["prompt", "retrieval", "route", "tool", "reply"]


def test_ec14_one_tool_record_per_tool_part(run, Scripted, jparts, ai, tc):
    """Covers: AC-3 (boundary), EC-14. Two TOOL parts give two [tool] records."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q), ("TOOL", CUPS_Q)), "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "a")]), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS, "b")])],
    )
    _, records = run(llm, question=TWO_TOOL_Q)
    assert [stage_of(r) for r in records] == ["prompt", "retrieval", "route", "tool", "tool", "reply"]


def test_ec14_both_question(run, Scripted, jparts, ai, tc):
    """Covers: AC-3 (right), EC-14. BOTH question: one [tool] record for the one TOOL part."""
    llm = Scripted([jparts(("DOCS", LEMON_Q), ("TOOL", CUPS_Q)), "Done."],
                   bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])])
    _, records = run(llm, question=BOTH_Q)
    assert [stage_of(r) for r in records] == ["prompt", "retrieval", "route", "tool", "reply"]


def test_ec14_no_reply_record_when_not_generated(run, Scripted, jparts, ai, tc):
    """Covers: AC-3 (wrong), EC-14. With generate=False there is no [reply] record, for DOCS and for TOOL questions."""
    _, docs_records = run(Scripted([jparts(("DOCS", DOCS_Q))]), generate=False)
    assert [stage_of(r) for r in docs_records] == ["prompt", "retrieval", "route"]
    llm = Scripted([jparts(("TOOL", TOOL_Q))], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    _, tool_records = run(llm, question=TOOL_Q, generate=False)
    assert [stage_of(r) for r in tool_records] == ["prompt", "retrieval", "route", "tool"]


def test_ec14_empty_store_logs_only_stages_that_ran(run, Scripted, FakeStore):
    """Covers: AC-3 (boundary), EC-14. Empty store: [prompt] then [retrieval]; no [route] or [tool] record (a [reply] record may follow when generated)."""
    _, records = run(Scripted([]), store=FakeStore([]))
    names = [stage_of(r) for r in records]
    assert names[:2] == ["prompt", "retrieval"]
    assert "route" not in names and "tool" not in names
    assert names in (["prompt", "retrieval"], ["prompt", "retrieval", "reply"])
    _, no_gen = run(Scripted([]), store=FakeStore([]), generate=False)
    assert [stage_of(r) for r in no_gen] == ["prompt", "retrieval"]


def test_ec14_stage_text_matches_format_trace_sections(run, Scripted, jparts, ai, tc):
    """Covers: AC-3 (right), EC-14, spec 4.1. Each record carries the text of that stage's section in format_trace (every non-header line of the section is in the record's message)."""
    llm = Scripted([jparts(("DOCS", LEMON_Q), ("TOOL", CUPS_Q)), "All done zzreply."],
                   bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])])
    trace, records = run(llm, question=BOTH_Q)
    sections, current = {}, None
    for line in format_trace(trace).splitlines():
        s = line.strip()
        if s.startswith("== ") and s.endswith(" =="):
            current = s[3:-3].strip()
            sections.setdefault(current, [])
        elif current is not None and s:
            sections[current].append(s)
    by_stage = {stage_of(r): r.getMessage() for r in records}
    for name in ("prompt", "route", "retrieval", "tool", "reply"):
        assert sections[name], f"section {name} has no body to compare"
        for line in sections[name]:
            assert line in by_stage[name], f"[{name}] record lacks the line {line!r}"


def test_ec14_prompt_record_shows_the_question(run, Scripted, jparts):
    """Covers: AC-3 (right), EC-14. The [prompt] record contains the question."""
    _, records = run(Scripted([jparts(("DOCS", DOCS_Q)), "ok"]))
    assert DOCS_Q in records[0].getMessage()


def test_ec14_nothing_printed(run, Scripted, jparts, ai, tc, capsys):
    """Covers: AC-3 (wrong), EC-14, NFR-4. Logging uses the logging module: nothing goes to stdout or stderr."""
    llm = Scripted([jparts(("TOOL", TOOL_Q)), "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    run(llm, question=TOOL_Q)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ec14_blank_question_logs_nothing(caplog, NoCallStore, NoCallLLM):
    """Covers: AC-3 (wrong), EC-14, EC-12. A blank question raises before any stage runs, so no record is written."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    with pytest.raises(ValueError):
        chat.run_turn(NoCallStore(), NoCallLLM(), [], "  ")
    assert [r for r in caplog.records if r.name == LOGGER] == []


# ---------------------------------------------------------------- EC-15 answer_turn unchanged

def test_ec15_answer_turn_docs(monkeypatch, bev_tool, Scripted, jparts, FakeStore, docs):
    """Covers: AC-2 (right), EC-15. answer_turn for a DOCS question returns the reply, the history with the new pair, and the retrieved docs."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    store = FakeStore(docs)
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "Under the machine."])
    history = list(HISTORY)
    result = chat.answer_turn(store, llm, history, DOCS_Q)
    assert isinstance(result, chat.TurnResult)
    assert result.reply == "Under the machine."
    assert result.history == HISTORY + [
        {"role": "user", "content": DOCS_Q},
        {"role": "assistant", "content": "Under the machine."},
    ]
    assert result.docs == docs
    assert history == HISTORY


def test_ec15_answer_turn_tool(monkeypatch, bev_tool, Scripted, jparts, ai, tc, FakeStore, docs):
    """Covers: AC-2 (right), EC-15. answer_turn for a TOOL question returns the final reply, the grown history and the retrieved docs."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    llm = Scripted([jparts(("TOOL", TOOL_Q)), "Bring two cambros."],
                   bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    result = chat.answer_turn(FakeStore(docs), llm, [], TOOL_Q)
    assert result.reply == "Bring two cambros."
    assert result.history == [
        {"role": "user", "content": TOOL_Q},
        {"role": "assistant", "content": "Bring two cambros."},
    ]
    assert result.docs == docs


def test_ec15_answer_turn_empty_store(Scripted, FakeStore):
    """Covers: AC-2 (wrong), EC-15. answer_turn with an empty store returns the unknown-retrieval reply, docs [], the grown history, and never calls the model."""
    llm = Scripted([])
    result = chat.answer_turn(FakeStore([]), llm, [], DOCS_Q)
    assert result.reply == chat.unknown_retrieval_reply()
    assert result.docs == []
    assert result.history == [
        {"role": "user", "content": DOCS_Q},
        {"role": "assistant", "content": chat.unknown_retrieval_reply()},
    ]
    assert llm.plain_invocations == [] and llm.bind_calls == []


@pytest.mark.parametrize("question", ["", "   "])
def test_ec15_answer_turn_blank_question_raises(NoCallStore, NoCallLLM, question):
    """Covers: AC-2 (wrong), EC-15. answer_turn keeps raising ValueError for a blank question before any store or model call."""
    with pytest.raises(ValueError):
        chat.answer_turn(NoCallStore(), NoCallLLM(), [], question)
