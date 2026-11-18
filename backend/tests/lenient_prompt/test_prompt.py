"""Spec 038, section 6.1 (PROMPT): PROMPT-1 to PROMPT-4; AC-1, AC-2, AC-3. Unit."""
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from blc.flow import FLOW_ANSWER_PROMPT
from blc.planner import NO_INVENTED_RULE

EXPECTED = """You are Bay Laurel Catering's internal assistant for employees.
Answer the question from the documents shown. Other parts of the user's request are answered elsewhere; do not mention them.
Keep the answer simple, straightforward and grounded in the documents.
For a yes or no question, start the answer with "Yes" or "No".
Keep the information complete: include everything the documents say that answers the question, such as items that go together.
Don't invent numbers.
If the documents do not cover the question, say you don't know.
Cite the source paths of the documents you used."""


def test_prompt_1_equals_spec_text():
    """Covers: AC-1 (right), PROMPT-1. The prompt equals the section 3 text exactly."""
    assert FLOW_ANSWER_PROMPT == EXPECTED


def test_prompt_1_is_a_non_empty_string():
    """Covers: AC-1 (boundary), PROMPT-1. It is a str, not empty, with no stray outer whitespace."""
    assert isinstance(FLOW_ANSWER_PROMPT, str)
    assert FLOW_ANSWER_PROMPT == FLOW_ANSWER_PROMPT.strip() != ""


@pytest.mark.parametrize("phrase", [
    "simple", "straightforward", "grounded", '"yes" or "no"', "don't invent numbers", "don't know",
])
def test_prompt_2_lowercase_phrases(phrase):
    """Covers: AC-1 (right), AC-2 (right), PROMPT-2. Each required phrase is in the lowercased prompt."""
    assert phrase in FLOW_ANSWER_PROMPT.lower()


@pytest.mark.parametrize("old", ["NO_INVENTED_RULE", "Don't invent arguments"])
def test_prompt_2_old_wording_absent(old):
    """Covers: AC-2 (wrong), PROMPT-2. Neither the constant's name nor the planner rule's opening is in the prompt."""
    assert old not in FLOW_ANSWER_PROMPT


def test_prompt_3_rule_string_not_in_prompt():
    """Covers: AC-2 (wrong), PROMPT-3. The spec 021 NO_INVENTED_RULE text is not in the prompt."""
    assert NO_INVENTED_RULE not in FLOW_ANSWER_PROMPT


def test_prompt_4_first_message_is_the_system_prompt(run_search_turn):
    """Covers: AC-3 (right), PROMPT-4. One stream call; first message SystemMessage(FLOW_ANSWER_PROMPT)."""
    r = run_search_turn()
    assert len(r.llm.stream_calls) == 1
    msgs = r.llm.stream_calls[0]
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == FLOW_ANSWER_PROMPT
    assert isinstance(msgs[-1], HumanMessage)


def test_prompt_4_no_documents_means_no_stream_call(run_search_turn):
    """Covers: AC-3 (wrong), PROMPT-4. A search that returns nothing gives no answer-model call."""
    r = run_search_turn(docs={})
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_prompt_4_system_prompt_appears_once(run_search_turn):
    """Covers: AC-3 (boundary), PROMPT-4. Only the first message is a SystemMessage with the prompt."""
    r = run_search_turn()
    system = [m for m in r.llm.stream_calls[0] if isinstance(m, SystemMessage)]
    assert [m.content for m in system].count(FLOW_ANSWER_PROMPT) == 1
