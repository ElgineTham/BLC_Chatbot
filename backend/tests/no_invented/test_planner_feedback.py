"""Spec 021, AC-3 (planner contract): EC-19 and EC-20, plus NFR-5.

Unit tests: scripted fake model, no network. Schema facts are read from the tool's OpenAI function form.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.flow import FLOW_ANSWER_PROMPT
from blc.planner import (
    NO_INVENTED_RULE,
    PLANNER_BEV_TOOL,
    PLANNER_PROMPT,
    plan_question,
)

Q = "How many cambros for 60 guests of peach tea?"
FB = "FEEDBACK-MARKER: calculate_bev_item gallons 6"


def _llm(make_llm):
    return make_llm([AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "x"}, "id": "c1"}])])


def _params(tool):
    return convert_to_openai_tool(tool)["function"]["parameters"]


def _item_enum(tool):
    item = _params(tool)["properties"]["item"]
    if "enum" in item:
        return item["enum"]
    for key in ("anyOf", "allOf", "oneOf"):
        for sub in item.get(key, []):
            if "enum" in sub:
                return sub["enum"]
    raise AssertionError(f"no enum for item: {item}")


def _shape(msgs):
    return [(type(m).__name__, str(m.content)) for m in msgs]


# ---------------------------------------------------------------- EC-19

def test_ec19_feedback_none_sends_the_same_messages(make_llm):
    """Covers: AC-3 (right), EC-19. feedback=None sends exactly the messages of a call without the argument."""
    a, b = _llm(make_llm), _llm(make_llm)
    plan_question(a, Q)
    plan_question(b, Q, feedback=None)
    assert _shape(a.invoke_calls[0]) == _shape(b.invoke_calls[0])


def test_ec19_feedback_none_same_with_history(make_llm):
    """Covers: AC-3 (right), EC-19. Same with a history."""
    hist = [{"role": "user", "content": "hello 12"}, {"role": "assistant", "content": "hi"}]
    a, b = _llm(make_llm), _llm(make_llm)
    plan_question(a, Q, hist)
    plan_question(b, Q, hist, feedback=None)
    assert _shape(a.invoke_calls[0]) == _shape(b.invoke_calls[0])


def test_ec19_feedback_without_it_has_no_marker(make_llm, text_of):
    """Covers: AC-3 (wrong), EC-19. Without feedback, no marker text is in the messages."""
    llm = _llm(make_llm)
    plan_question(llm, Q)
    assert "FEEDBACK-MARKER" not in text_of(llm.invoke_calls[0])


def test_ec19_feedback_in_messages_after_the_question(make_llm, text_of):
    """Covers: AC-3 (right), EC-19. The feedback appears verbatim, after the question."""
    llm = _llm(make_llm)
    plan_question(llm, Q, feedback=FB)
    text = text_of(llm.invoke_calls[0])
    assert FB in text
    assert text.rindex(FB) > text.rindex(Q)


def test_ec19_feedback_positional(make_llm, text_of):
    """Covers: AC-3 (right), EC-19. feedback may be the fourth positional argument."""
    llm = _llm(make_llm)
    plan_question(llm, Q, None, FB)
    assert FB in text_of(llm.invoke_calls[0])


def test_ec19_feedback_still_one_bind_and_one_invoke(make_llm):
    """Covers: AC-3 (boundary), EC-19. With feedback there is still one bind_tools and one invoke."""
    llm = _llm(make_llm)
    plan_question(llm, Q, feedback=FB)
    assert len(llm.bind_calls) == 1
    assert len(llm.invoke_calls) == 1


def test_ec19_feedback_keeps_history_and_question(make_llm, text_of):
    """Covers: AC-3 (right), EC-19. History content and the question are still in the messages."""
    hist = [{"role": "user", "content": "earlier-question-text"}, {"role": "assistant", "content": "earlier-reply-text"}]
    llm = _llm(make_llm)
    plan_question(llm, Q, hist, feedback=FB)
    text = text_of(llm.invoke_calls[0])
    for part in ("earlier-question-text", "earlier-reply-text", Q):
        assert part in text


def test_ec19_empty_question_still_raises_with_feedback(make_llm):
    """Covers: AC-3 (wrong), EC-19. A blank question is rejected before any model call, feedback or not."""
    llm = _llm(make_llm)
    with pytest.raises(ValueError):
        plan_question(llm, "   ", feedback=FB)
    assert llm.bind_calls == [] and llm.invoke_calls == []


# ---------------------------------------------------------------- EC-20

def test_rule_text_is_exact():
    """Covers: AC-3 (right), EC-20. NO_INVENTED_RULE is the sentence of the spec."""
    assert NO_INVENTED_RULE == "Don't invent arguments or numbers that aren't there!"


def test_ec20_description_contains_rule():
    """Covers: AC-3 (right), EC-20. PLANNER_BEV_TOOL.description contains the rule verbatim."""
    assert NO_INVENTED_RULE in PLANNER_BEV_TOOL.description


def test_ec20_name_and_schema_unchanged():
    """Covers: AC-3 (right), EC-20. Same name, properties, required list and item enum as spec 018."""
    assert PLANNER_BEV_TOOL.name == "calculate_bev_item"
    params = _params(PLANNER_BEV_TOOL)
    assert set(params["properties"]) == {"item", "drinks", "gallons", "guests"}
    assert params["required"] == ["item"]
    assert list(_item_enum(PLANNER_BEV_TOOL)) == ["gallons", "cambros", "cups", "everything"]


def test_ec20_other_description_text_kept():
    """Covers: AC-3 (boundary), EC-20. The scale_recipe pointer of spec 018 is still in the description."""
    assert "scale_recipe" in PLANNER_BEV_TOOL.description


def test_ec20_rule_not_in_the_prompt():
    """Covers: AC-3 (wrong), EC-20. PLANNER_PROMPT is unchanged: it does not contain the rule."""
    assert NO_INVENTED_RULE not in PLANNER_PROMPT


def test_ec20_rule_not_in_the_answer_prompt():
    """Covers: AC-3 (wrong), EC-20. FLOW_ANSWER_PROMPT does not contain the rule either."""
    assert NO_INVENTED_RULE not in FLOW_ANSWER_PROMPT


# ---------------------------------------------------------------- NFR-5

def test_nfr5_no_golden_question_in_prompts_or_descriptions(golden_cases):
    """Covers: NFR-5 (wrong). No eval question appears word for word in the planner prompt,
    the planner tool's descriptions or the flow answer prompt."""
    haystack = "\n".join([PLANNER_PROMPT, PLANNER_BEV_TOOL.description,
                          json.dumps(_params(PLANNER_BEV_TOOL)), FLOW_ANSWER_PROMPT]).casefold()
    assert len(golden_cases) == 30
    for case in golden_cases:
        assert case["question"].strip().casefold() not in haystack, case["id"]
