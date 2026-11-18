"""Spec 017 AC-3c (revision 3): labelled parts in the final message of BOTH turns, and the ANSWER_PROMPT line.

Unit only: PartResults are built by hand, no model, no Chroma, nothing under data/ (NFR-2).
The last message of build_final_messages(...) is the user message; the first is the system message.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

import chat
from blc.router import RoutedPart

PART_INSTRUCTION = (
    "When the question is split into labelled parts, answer each part, in order: "
    "(documents) parts only from the documents, (tool) parts only from their result."
)
ANCHOR = "Answer every part of the user's question."
QUESTION = "Where are the syrups kept; which cambros hold 12 gallons of iced water?"
DOC_TEXT = "Syrups are above the lemons inside the beverage cooler."
DOCS = [Document(page_content=DOC_TEXT, metadata={"source": "data/supplies/syrups.md"})]
P_DOCS = "Where are the syrups kept"
P_TOOL = "which cambros hold 12 gallons of iced water?"
R_TOOL = "Iced water: 12 gal."


def docs_part(text=P_DOCS):
    return chat.PartResult(RoutedPart("DOCS", text), (), None)


def tool_part(text=P_TOOL, result=R_TOOL):
    return chat.PartResult(RoutedPart("TOOL", text, "calculate_bev_item"), (), result)


def user_message(results, question=QUESTION, docs=DOCS):
    messages = chat.build_final_messages([], docs, question, results)
    return str(messages[-1].content)


def lines_of(text):
    return [line.strip() for line in text.splitlines()]


def test_part_instruction_constant_matches_contract():
    """Covers: AC-3c (right), EC-23. PART_INSTRUCTION is exactly the contract's sentence."""
    assert chat.PART_INSTRUCTION == PART_INSTRUCTION


def test_ec19_both_turn_lists_labelled_parts():
    """Covers: AC-3c (right), EC-19. Parts: header, Part 1 (documents) line, Part 2 (tool) line, then Result: R."""
    text = user_message([docs_part(), tool_part()])
    lines = lines_of(text)
    assert "Parts:" in lines
    assert f"Part 1 (documents): {P_DOCS}" in lines
    assert f"Part 2 (tool): {P_TOOL}" in lines
    assert f"Result: {R_TOOL}" in lines
    assert lines.index(f"Part 2 (tool): {P_TOOL}") < lines.index(f"Result: {R_TOOL}")
    assert lines.index(f"Part 1 (documents): {P_DOCS}") < lines.index(f"Part 2 (tool): {P_TOOL}")


def test_ec19_result_directly_follows_its_tool_part():
    """Covers: AC-3c (right), EC-19. The Result line belongs to the tool part: it comes right after it, not after the documents part."""
    lines = lines_of(user_message([docs_part(), tool_part()]))
    i = lines.index(f"Part 2 (tool): {P_TOOL}")
    assert lines[i + 1] == f"Result: {R_TOOL}"


def test_ec19_section_order_and_no_old_tool_results_section():
    """Covers: AC-3c (right, wrong), EC-19. Order Question:, Parts:, Documents:, Answer:; no 'Tool results:' section."""
    text = user_message([docs_part(), tool_part()])
    assert "Tool results:" not in text
    positions = [text.index("Question:"), text.index("Parts:"), text.index("Documents:"), text.rindex("Answer:")]
    assert positions == sorted(positions) and len(set(positions)) == 4
    assert text.rstrip().endswith("Answer:")


def test_ec19_question_and_chunks_are_present():
    """Covers: AC-3c (right), EC-19. The question appears after 'Question:' and the retrieved chunk text appears under Documents:."""
    text = user_message([docs_part(), tool_part()])
    assert QUESTION in text[text.index("Question:"):text.index("Parts:")]
    assert DOC_TEXT in text[text.index("Documents:"):]


def test_final_messages_keep_system_prompt_first():
    """Covers: AC-3c (right). The first message is the system message holding ANSWER_PROMPT; the user message is last."""
    messages = chat.build_final_messages([], DOCS, QUESTION, [docs_part(), tool_part()])
    assert chat.ANSWER_PROMPT in str(messages[0].content)
    assert len(messages) >= 2


def test_ec20_order_follows_the_router_tool_first():
    """Covers: AC-3c (right), EC-20. TOOL then DOCS gives Part 1 (tool) with its result, then Part 2 (documents)."""
    lines = lines_of(user_message([tool_part(), docs_part()]))
    assert lines.index(f"Part 1 (tool): {P_TOOL}") < lines.index(f"Part 2 (documents): {P_DOCS}")
    assert f"Result: {R_TOOL}" in lines
    assert lines.index(f"Result: {R_TOOL}") < lines.index(f"Part 2 (documents): {P_DOCS}")


def test_ec20_three_parts_each_with_own_result():
    """Covers: AC-3c (right, boundary), EC-20. DOCS, TOOL, TOOL give parts 1 to 3, each tool part followed by its own result."""
    results = [docs_part("doc q"), tool_part("tool q one", "RESULT-ONE"), tool_part("tool q two", "RESULT-TWO")]
    lines = lines_of(user_message(results))
    order = ["Part 1 (documents): doc q", "Part 2 (tool): tool q one", "Result: RESULT-ONE",
             "Part 3 (tool): tool q two", "Result: RESULT-TWO"]
    idx = [lines.index(item) for item in order]
    assert idx == sorted(idx)
    assert lines[idx[1] + 1] == "Result: RESULT-ONE"
    assert lines[idx[3] + 1] == "Result: RESULT-TWO"


def test_ec21_tool_part_without_result_is_labelled_documents():
    """Covers: AC-3c (wrong), EC-21. A TOOL part whose tool_text is None (fell back) is labelled (documents), next to a TOOL part with a result."""
    fell_back = chat.PartResult(RoutedPart("TOOL", "fallen back part", "calculate_bev_item"), (), None)
    lines = lines_of(user_message([fell_back, tool_part()]))
    assert "Part 1 (documents): fallen back part" in lines
    assert f"Part 2 (tool): {P_TOOL}" in lines
    assert not any(line.startswith("Part 1 (tool)") for line in lines)
    assert "Tool results:" not in "\n".join(lines)


def test_ec22_tool_only_message_keeps_old_layout():
    """Covers: AC-3c (right), EC-22. A TOOL-only set keeps 'Tool results:' with Question:/Result: blocks and has no Parts:."""
    text = user_message([tool_part()], docs=[])
    assert "Tool results:" in text
    assert "Result: " + R_TOOL in text
    assert "Question:" in text
    assert "Parts:" not in text
    assert "(tool)" not in text and "(documents)" not in text


def test_ec22_docs_only_message_keeps_old_layout():
    """Covers: AC-3c (right), EC-22. A DOCS-only set has Documents: and no Parts:, no Tool results:."""
    text = user_message([docs_part(QUESTION)])
    assert "Documents:" in text and DOC_TEXT in text
    assert "Parts:" not in text
    assert "Tool results:" not in text
    assert "(documents)" not in text


def test_extra_all_fallen_back_tool_parts_are_not_a_mixed_turn():
    """Covers: AC-3c (boundary), EC-21 (extra). Only parts without a tool_text (no part with a result): the message has no Parts: section (§4.6 'at least one with and one without')."""
    fell_back = chat.PartResult(RoutedPart("TOOL", "fallen back part", "calculate_bev_item"), (), None)
    text = user_message([fell_back])
    assert "Parts:" not in text
    assert "Tool results:" not in text


def test_ec23_answer_prompt_has_part_instruction_once_after_anchor():
    """Covers: AC-3c (right), EC-23. ANSWER_PROMPT contains PART_INSTRUCTION exactly once, directly after the anchor line."""
    prompt = chat.ANSWER_PROMPT
    assert prompt.count(PART_INSTRUCTION) == 1
    lines = lines_of(prompt)
    assert lines[lines.index(ANCHOR) + 1] == PART_INSTRUCTION


def test_ec23_answer_prompt_keeps_earlier_lines():
    """Covers: AC-3c (boundary), EC-23. Removing the one new line leaves the anchor and the other prompt lines in place (the prompt is not reduced to the new line)."""
    prompt = chat.ANSWER_PROMPT
    rest = [line for line in lines_of(prompt) if line and line != PART_INSTRUCTION]
    assert ANCHOR in rest
    assert len(rest) >= 2


@pytest.mark.parametrize("results", [[docs_part(), tool_part()], [tool_part(), docs_part()]])
def test_nfr5_final_message_is_deterministic(results):
    """Covers: AC-3c (boundary), NFR-5 (extra). The same inputs always give the same user message."""
    assert user_message(results) == user_message(results)
