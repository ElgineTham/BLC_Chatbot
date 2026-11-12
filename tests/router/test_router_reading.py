"""AC-2, AC-3, AC-4: JSON reply reading, the guard, call shape and prompt (EC-5 to EC-11).

Unit tests with a fake model; no Ollama, no network, nothing read under data/.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from blc.router import PULL_SHEET_ITEMS, ROUTER_PROMPT, ROUTER_SCHEMA, route_question

Q = "How many cups do I need for 45 guests?"
Q_NO_ITEM = "Where is the mint kept?"
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]


class FakeModel:
    """Has only invoke (no bind, bind_tools or with_structured_output). Records messages, args and kwargs."""

    def __init__(self, reply):
        self.reply = reply
        self.messages = []
        self.args = []
        self.kwargs = []

    def invoke(self, messages, *args, **kwargs):
        self.messages.append(list(messages))
        self.args.append(args)
        self.kwargs.append(kwargs)
        return AIMessage(content=self.reply)


def jparts(*parts):
    return json.dumps({"parts": [{"route": r, "text": t} for r, t in parts]})


def route(reply, question=Q, history=None):
    return route_question(FakeModel(reply), [] if history is None else history, question)


def pairs(d):
    return [(p.route, p.text) for p in d.parts]


# ---------------------------------------------------------------- EC-5: the section 4.1 table

def test_json_single_tool():
    """Covers: AC-2 (right), EC-5. One TOOL part from JSON."""
    d = route(jparts(("TOOL", "How many cups for 45 guests?")))
    assert pairs(d) == [("TOOL", "How many cups for 45 guests?")]
    assert d.kind == "TOOL"
    assert d.fallback is False


def test_json_lowercase_route_docs_then_tool():
    """Covers: AC-2 (right), EC-5. Route 'docs' in lower case is accepted; order kept; kind BOTH."""
    d = route(jparts(("docs", "Where is the tea kept?"), ("TOOL", "How many napkins should I bring?")))
    assert pairs(d) == [("DOCS", "Where is the tea kept?"), ("TOOL", "How many napkins should I bring?")]
    assert d.kind == "BOTH"
    assert d.fallback is False


@pytest.mark.parametrize("route_name", ["tool", "Tool", "tOOL"])
def test_json_route_any_case(route_name):
    """Covers: AC-2 (right, boundary), EC-5. Any case of TOOL is read as TOOL."""
    d = route(jparts((route_name, "How many cups for 45 guests?")))
    assert [p.route for p in d.parts] == ["TOOL"]


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_json_blank_text_uses_whole_question(text):
    """Covers: AC-2 (boundary), EC-5. A part with empty or blank text takes the whole question; not a fallback."""
    d = route(jparts(("DOCS", text)))
    assert pairs(d) == [("DOCS", Q)]
    assert d.fallback is False


def test_json_blank_tool_text_uses_whole_question_then_guard_sees_it():
    """Covers: AC-2 (boundary), AC-3 (right), EC-5, EC-7. Blank TOOL text becomes the question; Q has an item so it stays TOOL."""
    d = route(jparts(("TOOL", "")))
    assert pairs(d) == [("TOOL", Q)]


def test_json_blank_tool_text_with_question_without_item_becomes_docs():
    """Covers: AC-3 (wrong), EC-5, EC-7. Blank TOOL text becomes a question with no item, so the guard makes it DOCS."""
    d = route(jparts(("TOOL", "")), question=Q_NO_ITEM)
    assert pairs(d) == [("DOCS", Q_NO_ITEM)]
    assert d.kind == "DOCS"
    assert d.fallback is False


@pytest.mark.parametrize(
    "reply",
    [
        jparts(("MAYBE", "x")),
        json.dumps({"parts": []}),
        json.dumps({"parts": "oops"}),
        json.dumps([1, 2]),
        json.dumps({"other": 1}),
        json.dumps({"parts": None}),
        json.dumps("TOOL"),
        json.dumps(5),
        "",
        "   ",
        "not json at all",
        "{not valid json",
    ],
)
def test_unreadable_replies_fall_back(reply):
    """Covers: AC-2 (wrong), EC-5, EC-10. Unusable JSON or text gives one DOCS part with the whole question, fallback=True."""
    d = route(reply)
    assert pairs(d) == [("DOCS", Q)]
    assert d.kind == "DOCS"
    assert d.fallback is True


def test_label_lines_are_the_second_chance():
    """Covers: AC-2 (right), EC-5. A non-JSON reply in the old format is read."""
    d = route("DOCS: Where is the tea kept?")
    assert pairs(d) == [("DOCS", "Where is the tea kept?")]
    assert d.fallback is False


def test_label_lines_tool_and_docs_both_read():
    """Covers: AC-2 (right), EC-5. Label lines with items give TOOL then DOCS, kind BOTH."""
    d = route("TOOL: How many cups for 25 guests?\nDOCS: Where is the tea kept?")
    assert pairs(d) == [("TOOL", "How many cups for 25 guests?"), ("DOCS", "Where is the tea kept?")]
    assert d.kind == "BOTH"


def test_json_items_that_are_invalid_are_ignored():
    """Covers: AC-2 (wrong), EC-5. Non-objects, items missing a key, with another route or a non-string text are dropped; valid ones stay."""
    reply = json.dumps(
        {
            "parts": [
                1,
                "TOOL",
                None,
                {"route": "TOOL"},
                {"text": "no route"},
                {"route": "MAYBE", "text": "x"},
                {"route": "DOCS", "text": 5},
                {"route": "DOCS", "text": "Where is the tea kept?"},
            ]
        }
    )
    d = route(reply)
    assert pairs(d) == [("DOCS", "Where is the tea kept?")]
    assert d.fallback is False


def test_json_only_invalid_items_falls_back():
    """Covers: AC-2 (wrong), EC-5. When no item is usable the fallback applies."""
    d = route(json.dumps({"parts": [{"route": "TOOL"}, 3]}))
    assert pairs(d) == [("DOCS", Q)]
    assert d.fallback is True


def test_json_extra_keys_are_harmless():
    """Covers: AC-2 (boundary), EC-5. Unknown keys in the object or the item do not stop reading."""
    reply = json.dumps({"parts": [{"route": "DOCS", "text": "Where is the tea kept?", "why": "x"}], "note": 1})
    assert pairs(route(reply)) == [("DOCS", "Where is the tea kept?")]


def test_json_three_parts_keep_order():
    """Covers: AC-2 (right), EC-5. Parts keep the reply's order, repeated routes included."""
    d = route(jparts(("TOOL", "How many cups?"), ("DOCS", "Where?"), ("TOOL", "How many napkins?")))
    assert [p.route for p in d.parts] == ["TOOL", "DOCS", "TOOL"]
    assert d.kind == "BOTH"


def test_json_text_is_kept_as_given():
    """Covers: AC-2 (boundary), EC-5. Text with colons and quotes is kept whole."""
    text = 'Cambros: how many for "4" gallons?'
    d = route(jparts(("TOOL", text)))
    assert pairs(d) == [("TOOL", text)]


# ---------------------------------------------------------------- EC-6: the section 4.2 table

def test_guard_keeps_tool_with_items():
    """Covers: AC-3 (right), EC-6. A TOOL part that mentions cambros and gallons stays TOOL."""
    d = route("TOOL: How many cambros for 3 gallons of mocha?")
    assert pairs(d) == [("TOOL", "How many cambros for 3 gallons of mocha?")]
    assert d.kind == "TOOL"


def test_guard_turns_tool_without_item_into_docs():
    """Covers: AC-3 (wrong), EC-6. A TOOL part with no item becomes DOCS with the same text."""
    d = route(f"TOOL: {Q_NO_ITEM}")
    assert pairs(d) == [("DOCS", Q_NO_ITEM)]
    assert d.kind == "DOCS"


def test_guard_tool_plus_docs_stays_both():
    """Covers: AC-3 (right), EC-6. TOOL with item plus DOCS stays BOTH."""
    d = route(f"TOOL: How many cups for 25 guests?\nDOCS: {Q_NO_ITEM}")
    assert pairs(d) == [("TOOL", "How many cups for 25 guests?"), ("DOCS", Q_NO_ITEM)]
    assert d.kind == "BOTH"


def test_guard_first_of_two_tools_becomes_docs_and_kind_is_both():
    """Covers: AC-3 (right), EC-6. Item-less TOOL then TOOL with item gives DOCS, TOOL, kind BOTH."""
    d = route(f"TOOL: {Q_NO_ITEM}\nTOOL: How many cups for 25 guests?")
    assert pairs(d) == [("DOCS", Q_NO_ITEM), ("TOOL", "How many cups for 25 guests?")]
    assert d.kind == "BOTH"


def test_guard_lone_item_less_tool_gives_docs_not_fallback():
    """Covers: AC-3 (wrong), EC-6. One DOCS part, kind DOCS, fallback stays False."""
    d = route(f"TOOL: {Q_NO_ITEM}")
    assert len(d.parts) == 1
    assert d.parts[0].route == "DOCS"
    assert d.kind == "DOCS"
    assert d.fallback is False


def test_guard_two_item_less_tools_all_become_docs():
    """Covers: AC-3 (wrong), EC-6. Several item-less TOOL parts all become DOCS; kind DOCS."""
    d = route(f"TOOL: {Q_NO_ITEM}\nTOOL: Where is the mint stored?")
    assert [p.route for p in d.parts] == ["DOCS", "DOCS"]
    assert d.kind == "DOCS"


def test_guard_whole_word_only():
    """Covers: AC-3 (wrong), EC-6. A TOOL part that only says 'lemonade' has no item and becomes DOCS."""
    d = route("TOOL: How is the lemonade made?")
    assert pairs(d) == [("DOCS", "How is the lemonade made?")]


def test_guard_item_match_ignores_case():
    """Covers: AC-3 (right), EC-6. 'CUPS' in a TOOL part keeps it TOOL."""
    assert route("TOOL: HOW MANY CUPS FOR 30?").kind == "TOOL"


def test_guard_everything_word_keeps_tool():
    """Covers: AC-3 (right), EC-6. 'bring' is in the set (everything), so a bring question stays TOOL."""
    d = route("TOOL: What should I bring for the coffee station?")
    assert d.kind == "TOOL"


# ---------------------------------------------------------------- EC-7: guard on JSON

def test_json_tool_without_item_becomes_docs_and_kind_follows():
    """Covers: AC-3 (wrong), EC-7. A JSON TOOL part with no item becomes DOCS."""
    d = route(jparts(("TOOL", Q_NO_ITEM)))
    assert pairs(d) == [("DOCS", Q_NO_ITEM)]
    assert d.kind == "DOCS"
    assert d.fallback is False


def test_json_docs_mentioning_item_stays_docs():
    """Covers: AC-3 (right), EC-7. A DOCS part is never changed, even when it mentions items."""
    d = route(jparts(("DOCS", "How to make 3 gallons of lemonade?")))
    assert pairs(d) == [("DOCS", "How to make 3 gallons of lemonade?")]
    assert d.kind == "DOCS"


def test_json_mixed_guard_and_kind():
    """Covers: AC-3 (right), EC-7. DOCS(item) + TOOL(no item) + TOOL(item): order kept, middle part turned DOCS, kind BOTH."""
    d = route(
        jparts(
            ("DOCS", "How much sugar goes in a batch?"),
            ("TOOL", Q_NO_ITEM),
            ("TOOL", "How many cups for 25 guests?"),
        )
    )
    assert [p.route for p in d.parts] == ["DOCS", "DOCS", "TOOL"]
    assert [p.text for p in d.parts] == [
        "How much sugar goes in a batch?",
        Q_NO_ITEM,
        "How many cups for 25 guests?",
    ]
    assert d.kind == "BOTH"


def test_guard_does_not_change_fallback_flag_for_read_reply():
    """Covers: AC-3 (boundary), EC-7. A guard-changed decision from a readable reply has fallback False."""
    assert route(jparts(("TOOL", Q_NO_ITEM))).fallback is False
    assert route(f"TOOL: {Q_NO_ITEM}").fallback is False


# ---------------------------------------------------------------- EC-10: fallback and guard

def test_fallback_is_docs_with_whole_question_even_with_items():
    """Covers: AC-2 (wrong), EC-10. An unreadable reply gives DOCS with the whole question and fallback=True, whatever the question holds."""
    for question in (Q, Q_NO_ITEM):
        d = route("nonsense", question=question)
        assert pairs(d) == [("DOCS", question)]
        assert d.kind == "DOCS"
        assert d.fallback is True


# ---------------------------------------------------------------- EC-8: call shape

def test_exactly_one_invoke_with_format_schema_only():
    """Covers: AC-4 (right), EC-8. One invoke; keyword arguments are exactly {'format': ROUTER_SCHEMA}; no positional extras."""
    model = FakeModel(jparts(("TOOL", "How many cups?")))
    route_question(model, HISTORY, Q)
    assert len(model.messages) == 1
    assert model.kwargs[0] == {"format": ROUTER_SCHEMA}
    assert model.args[0] == ()


def test_format_is_sent_also_for_empty_history_and_unreadable_reply():
    """Covers: AC-4 (boundary), EC-8. The call shape does not change with empty history or a bad reply; still one call."""
    model = FakeModel("garbage")
    route_question(model, [], Q)
    assert len(model.messages) == 1
    assert model.kwargs[0] == {"format": ROUTER_SCHEMA}


def test_fake_without_bind_methods_works():
    """Covers: AC-4 (right), EC-8. A model that has only invoke is enough: no bind, bind_tools or with_structured_output is used."""
    model = FakeModel(jparts(("DOCS", "Where?")))
    assert not any(hasattr(model, n) for n in ("bind", "bind_tools", "with_structured_output"))
    assert route_question(model, [], Q).kind == "DOCS"


def test_messages_are_system_prompt_then_one_human_message():
    """Covers: AC-4 (right), EC-8. System message is ROUTER_PROMPT; one human message holds the history content and the question."""
    model = FakeModel(jparts(("DOCS", "Where?")))
    route_question(model, HISTORY, "Where is the stirrer kept please")
    msgs = model.messages[0]
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == ROUTER_PROMPT
    assert isinstance(msgs[1], HumanMessage)
    body = str(msgs[1].content)
    for needle in ("earlier question zebra", "earlier answer giraffe", "Where is the stirrer kept please"):
        assert needle in body


def test_no_documents_in_messages():
    """Covers: AC-4 (boundary), EC-8. Only the system prompt, history and question are sent (two messages)."""
    model = FakeModel(jparts(("DOCS", "Where?")))
    route_question(model, [], Q)
    assert [type(m) for m in model.messages[0]] == [SystemMessage, HumanMessage]


# ---------------------------------------------------------------- EC-9: blank question

@pytest.mark.parametrize("question", ["", " ", "\n\t  "])
def test_blank_question_raises_before_any_call(question):
    """Covers: AC-2 (wrong, boundary), EC-9. A blank question raises ValueError and the model is never invoked."""
    model = FakeModel(jparts(("DOCS", "x")))
    with pytest.raises(ValueError):
        route_question(model, [], question)
    assert model.messages == []


def test_route_question_prints_nothing_and_keeps_history(capsys):
    """Covers: AC-2 (boundary). Nothing is printed and the history is unchanged."""
    history = [dict(m) for m in HISTORY]
    route_question(FakeModel(jparts(("TOOL", Q))), history, Q)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == HISTORY


# ---------------------------------------------------------------- EC-11: prompt and schema

def test_prompt_is_non_empty_string_with_every_item_key_and_route_words():
    """Covers: AC-4 (right), EC-11. ROUTER_PROMPT is a non-empty string naming every item key, TOOL and DOCS."""
    assert isinstance(ROUTER_PROMPT, str) and ROUTER_PROMPT.strip()
    for key in PULL_SHEET_ITEMS:
        assert key in ROUTER_PROMPT, key
    assert "TOOL" in ROUTER_PROMPT
    assert "DOCS" in ROUTER_PROMPT


def test_schema_is_a_json_dict_that_mentions_parts_route_and_text():
    """Covers: AC-4 (right), EC-8. ROUTER_SCHEMA is a JSON-serialisable dict describing parts, route and text."""
    assert isinstance(ROUTER_SCHEMA, dict)
    dumped = json.dumps(ROUTER_SCHEMA)
    for word in ("parts", "route", "text", "TOOL", "DOCS"):
        assert word in dumped
