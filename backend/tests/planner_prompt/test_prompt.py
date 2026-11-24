"""Spec 046 section 6.1 PROMPT-1 to PROMPT-5 (AC-1, AC-2). Unit tests, no network."""
from __future__ import annotations

import pytest
from langchain_core.messages import SystemMessage

from blc.planner import PLANNER_PROMPT, plan_question

MUST_CONTAIN = [
    "Never ask the user anything yourself",
    "with or without numbers",
    "search_documents",
    "calculate_bev_item",
    "scale_recipe",
    "calculate_food_item",
    "calculate_serving_utensils",
    "calculate_always_items",
]

MUST_NOT_CONTAIN = [
    "not by the topic",
    "How many black linens do I need?",
    "Rule 1",
    "Rule 2",
    "Rule 3",
]

# The 11 example questions of Appendix A, in order.
EXAMPLES = [
    "How many cups do I need for 70 guests?",
    "How much lemon concentrate for 8 gallons of lemonade?",
    "How many knives for 35 guests?",
    "Are cocktail napkins needed at dinner?",
    "Which tongs for 7 dozen bagels?",
    "How many black napkins should I pull?",
    "What goes in the Always box for 7 drip trays?",
    "Where are the lemons kept?",
    "Should I bring creamer for decaf?",
    "How many cambros for 4 gallons of coffee and what to bring?",
    "Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?",
]


@pytest.mark.parametrize("needle", MUST_CONTAIN)
def test_prompt_contains_required_text(needle):
    """Covers: AC-1 (right), PROMPT-1. Each required phrase and tool name is present."""
    assert needle in PLANNER_PROMPT


@pytest.mark.parametrize("needle", MUST_NOT_CONTAIN)
def test_prompt_lacks_dropped_text(needle):
    """Covers: AC-1 (wrong), PROMPT-2. Each dropped phrase is absent (case-sensitive)."""
    assert needle not in PLANNER_PROMPT


def test_prompt_has_no_rule_n_wording_any_digit():
    """Covers: AC-1 (boundary), PROMPT-2. No 'Rule <digit>' wording at all, not only 1 to 3."""
    import re

    assert not re.search(r"Rule \d", PLANNER_PROMPT)


@pytest.mark.parametrize("example", EXAMPLES)
def test_each_example_question_appears_verbatim(example):
    """Covers: AC-1 (right), PROMPT-3. Each of the 11 Appendix A example questions appears word for word."""
    assert example in PLANNER_PROMPT


def test_example_questions_in_appendix_order():
    """Covers: AC-1 (boundary), PROMPT-3. First occurrences of the 11 examples strictly increase."""
    assert len(EXAMPLES) == 11
    positions = [PLANNER_PROMPT.index(e) for e in EXAMPLES]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_example_order_check_can_fail():
    """Covers: AC-1 (wrong), PROMPT-3. Swapping two examples breaks the increasing-position check, so the
    order test is meaningful (TOOL examples come before DOCS examples)."""
    swapped = list(EXAMPLES)
    swapped[0], swapped[7] = swapped[7], swapped[0]
    positions = [PLANNER_PROMPT.index(e) for e in swapped]
    assert positions != sorted(positions)


def test_plan_question_sends_prompt_as_first_system_message(make_llm):
    """Covers: AC-2 (right), PROMPT-4. The first message is a SystemMessage equal to PLANNER_PROMPT."""
    llm = make_llm()
    plan_question(llm, "Where is the coffee?")
    msgs = llm.invoke_calls[0]
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == PLANNER_PROMPT


def test_plan_question_prompt_unchanged_with_history(make_llm):
    """Covers: AC-2 (boundary), PROMPT-4. With chat history the system message is still the unmodified prompt."""
    llm = make_llm()
    history = [{"role": "user", "content": "Where is the coffee?"},
               {"role": "assistant", "content": "In the cooler."}]
    plan_question(llm, "And the decaf?", history)
    msgs = llm.invoke_calls[0]
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == PLANNER_PROMPT


def test_prompt_is_str_without_outer_whitespace():
    """Covers: AC-1 (boundary), PROMPT-5. A str that does not start or end with whitespace (no trailing newline)."""
    assert isinstance(PLANNER_PROMPT, str)
    assert PLANNER_PROMPT == PLANNER_PROMPT.strip()
    assert not PLANNER_PROMPT.endswith("\n")
    assert not PLANNER_PROMPT.startswith("\n")


def test_prompt_has_no_backslash_line_wrapping():
    """Covers: AC-1 (wrong), PROMPT-5 (spec 4.1). Long lines are single lines: no backslash-newline remnants."""
    assert "\\\n" not in PLANNER_PROMPT
    assert "\r" not in PLANNER_PROMPT
