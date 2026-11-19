"""Spec 018, AC-1 to AC-5: constants, model use, route from calls, fallback and cleaning, errors.

Unit tests: scripted fake model, no Ollama, no network, nothing read under data/.
"""
import dataclasses
import re

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from blc.planner import (
    PLAN_ROUTES,
    PLANNER_BEV_TOOL,
    PLANNER_PROMPT,
    PLANNER_TOOLS,
    SEARCH_TOOL,
    SEARCH_TOOL_NAME,
    Plan,
    PlannedCall,
    plan_question,
)
from blc.tools.recipe_tools import RECIPE_TOOL

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


def _texts(llm):
    return [str(m.content) for m in llm.invoke_calls[0]]


# --------------------------------------------------------------------------
# AC-1 constants (EC-1, EC-2)
# --------------------------------------------------------------------------

def test_search_tool_shape():
    """Covers: AC-1 (right), EC-1. Name, description, one required string argument 'query'."""
    assert SEARCH_TOOL_NAME == "search_documents"
    assert SEARCH_TOOL.name == "search_documents"
    assert SEARCH_TOOL.description.strip()
    params = convert_to_openai_tool(SEARCH_TOOL)["function"]["parameters"]
    assert set(params["properties"]) == {"query"}
    assert params["properties"]["query"]["type"] == "string"
    assert params["required"] == ["query"]


def test_search_tool_placeholder_returns_empty_string():
    """Covers: AC-1 (right), EC-1. Retrieval is a later spec: invoke returns ''."""
    assert SEARCH_TOOL.invoke({"query": "x"}) == ""


def test_planner_tools_identity_and_order():
    """Covers: AC-1 (right), EC-1; spec 030 AC-1. PLANNER_TOOLS is (SEARCH_TOOL, PLANNER_BEV_TOOL, RECIPE_TOOL,
    <food tool>) by identity for the first three, the food tool (FOOD_TOOL_NAME) last."""
    from blc.tools.food_tools import FOOD_TOOL_NAME

    assert isinstance(PLANNER_TOOLS, tuple)
    assert len(PLANNER_TOOLS) == 5
    assert PLANNER_TOOLS[0] is SEARCH_TOOL
    assert PLANNER_TOOLS[1] is PLANNER_BEV_TOOL
    assert PLANNER_TOOLS[2] is RECIPE_TOOL
    assert PLANNER_TOOLS[3].name == FOOD_TOOL_NAME == "calculate_food_item"
    assert PLANNER_TOOLS[4].name == "calculate_serving_utensils"  # spec 043 AC-1


# --------------------------------------------------------------------------
# AC-1 PLANNER_BEV_TOOL (EC-1b)
# --------------------------------------------------------------------------

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
    raise AssertionError(f"no enum found for item: {item}")


def _all_description_text(tool):
    parts = [tool.description]
    for prop in _params(tool)["properties"].values():
        parts.append(prop.get("description", ""))
    return "\n".join(parts)


def test_planner_bev_tool_name():
    """Covers: AC-1 (right), EC-1b. PLANNER_BEV_TOOL is named calculate_bev_item (the real tool object is gone, spec 041)."""
    assert PLANNER_BEV_TOOL.name == "calculate_bev_item"


def test_planner_bev_tool_schema_properties():
    """Covers: AC-1 (right), EC-1b. Exactly item, drinks, gallons, guests; item required."""
    params = _params(PLANNER_BEV_TOOL)
    assert set(params["properties"]) == {"item", "drinks", "gallons", "guests"}
    assert "item" in params["required"]


def test_planner_bev_tool_item_enum_exact():
    """Covers: AC-1 (right), EC-1b. item enum is exactly gallons, cambros, cups, everything (no supplies)."""
    enum = _item_enum(PLANNER_BEV_TOOL)
    assert list(enum) == ["gallons", "cambros", "cups", "everything"]
    assert "supplies" not in enum


def test_planner_bev_tool_descriptions_not_supply_job():
    """Covers: AC-1 (wrong), EC-1b. Descriptions never present 'whether to bring' / 'what to bring' as this tool's job."""
    text = _all_description_text(PLANNER_BEV_TOOL).casefold()
    assert "whether to bring" not in text
    assert "what to bring" not in text


def test_planner_bev_tool_no_supplies_item_in_example_call():
    """Covers: AC-1 (wrong), EC-1b. No example call in the descriptions uses item 'supplies'."""
    text = _all_description_text(PLANNER_BEV_TOOL)
    assert not re.search(r"""item["']?\s*[:=]\s*["']?supplies""", text, re.IGNORECASE)


def test_planner_bev_tool_descriptions_explain_items_and_recipe_job():
    """Covers: AC-1 (right), EC-1b. Descriptions mention each item and that ingredient amounts are scale_recipe's job."""
    text = _all_description_text(PLANNER_BEV_TOOL)
    folded = text.casefold()
    for word in ("gallons", "cambros", "cups", "everything"):
        assert word in folded
    assert "scale_recipe" in text


def test_planner_bev_tool_descriptions_hold_no_eval_question(cases):
    """Covers: NFR-4 (wrong). No eval question appears word for word in the planner bev tool's descriptions."""
    folded = _all_description_text(PLANNER_BEV_TOOL).casefold()
    for c in cases.values():
        assert c["question"].casefold() not in folded, c["id"]


def test_plan_routes_constant():
    """Covers: AC-1 (right), EC-1. PLAN_ROUTES == ('TOOL', 'DOCS', 'BOTH')."""
    assert PLAN_ROUTES == ("TOOL", "DOCS", "BOTH")


def test_prompt_names_three_tools():
    """Covers: AC-1 (right), EC-2. The prompt contains all three tool names."""
    for name in (SEARCH, BEV, REC):
        assert name in PLANNER_PROMPT


PROMPT_EXAMPLES = [
    # TOOL
    "How many cups do I need for 70 guests?",
    "How much lemon concentrate for 8 gallons of lemonade?",
    # DOCS
    "Where are the lemons kept?",
    "Should I bring creamer for decaf?",
    # BOTH
    "How many cambros for 4 gallons of coffee and what to bring?",
    "Where is the orange juice concentrate, and how much do I need for 8 gallons of orange juice?",
]


@pytest.mark.parametrize("example", PROMPT_EXAMPLES)
def test_prompt_contains_each_example_verbatim(example):
    """Covers: AC-1 (right), EC-2. Each of the six example questions appears verbatim."""
    assert example in PLANNER_PROMPT


@pytest.mark.parametrize("query", ["what to bring for coffee", "where is the orange juice concentrate"])
def test_prompt_contains_example_queries(query):
    """Covers: AC-1 (right), EC-2. The BOTH example search queries appear in the prompt."""
    assert query in PLANNER_PROMPT


def test_prompt_examples_in_order_tool_docs_both():
    """Covers: AC-1 (boundary), EC-2. TOOL examples come before DOCS examples, before BOTH examples."""
    pos = [PLANNER_PROMPT.index(e) for e in PROMPT_EXAMPLES]
    assert max(pos[:2]) < min(pos[2:4])
    assert max(pos[2:4]) < min(pos[4:])


def test_prompt_states_how_much_rule():
    """Covers: AC-1 (right), EC-2. The prompt carries the 'how much' rule: scale_recipe for ingredient amounts, 'everything' for the pull sheet."""
    folded = PLANNER_PROMPT.casefold()
    # the rule: "how much ... for N gallons" asks for ingredient amounts -> scale_recipe
    assert re.search(r"how much.{0,200}?ingredient", folded, re.DOTALL)
    assert "scale_recipe" in folded
    # item gallons answers only "how many gallons to make"
    assert "how many gallons" in folded
    # "what goes on the pull sheet" with an amount is item everything
    assert re.search(r"pull sheet.{0,200}everything|everything.{0,200}pull sheet", folded, re.DOTALL)


def test_bound_tools_use_planner_bev_tool(make_llm, mk):
    """Covers: AC-1 (right), AC-2 (right), EC-3. The model is given PLANNER_BEV_TOOL."""
    llm = make_llm(mk.ai((SEARCH, {"query": "x"})))
    plan_question(llm, "Where is the coffee?")
    bound = llm.bind_calls[0]
    assert any(t is PLANNER_BEV_TOOL for t in bound)


def test_prompt_is_nonempty_string():
    """Covers: AC-1 (wrong), EC-2. The prompt is a real, non-blank string."""
    assert isinstance(PLANNER_PROMPT, str) and PLANNER_PROMPT.strip()


# --------------------------------------------------------------------------
# AC-2 model use (EC-3, EC-4, stripped question of EC-7)
# --------------------------------------------------------------------------

def test_model_use_and_docs_plan(make_llm, mk):
    """Covers: AC-2 (right), AC-3 (right), EC-3, NFR-6. One bind_tools, one invoke, message layout, DOCS plan."""
    llm = make_llm(mk.ai((SEARCH, {"query": "where is the coffee"})))
    plan = plan_question(llm, "Where is the coffee?")
    assert len(llm.bind_calls) == 1
    assert llm.bind_calls[0] == list(PLANNER_TOOLS)
    assert len(llm.invoke_calls) == 1
    msgs = llm.invoke_calls[0]
    assert isinstance(msgs, list)
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == PLANNER_PROMPT
    assert isinstance(msgs[-1], HumanMessage) and "Where is the coffee?" in msgs[-1].content
    assert plan == Plan("DOCS", (PlannedCall("search_documents", {"query": "where is the coffee"}),), False)


def test_question_is_stripped_in_human_message(make_llm, mk):
    """Covers: AC-2 (boundary), EC-7. The last message is a HumanMessage whose content contains the stripped question."""
    llm = make_llm(mk.ai((SEARCH, {"query": "q"})))
    plan_question(llm, "  \n Where is the coffee?\t ")
    last = llm.invoke_calls[0][-1]
    assert isinstance(last, HumanMessage)
    assert "Where is the coffee?" in last.content


def test_history_contents_appear_verbatim(make_llm, mk):
    """Covers: AC-2 (right), EC-4. Every history content and the question appear in the messages."""
    history = [
        {"role": "user", "content": "How many cambros for coffee and decaf?"},
        {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
    ]
    llm = make_llm(mk.ai((BEV, {"item": "cambros", "drinks": ["coffee", "decaf"], "gallons": [5, 5]})))
    plan_question(llm, "5 gallons each.", history)
    joined = "\n".join(_texts(llm))
    for h in history:
        assert h["content"] in joined
    assert "5 gallons each." in joined
    assert isinstance(llm.invoke_calls[0][-1], HumanMessage)
    assert "5 gallons each." in llm.invoke_calls[0][-1].content


def test_summary_history_item_appears(make_llm, mk):
    """Covers: AC-2 (right), EC-4. A 'summary' item's content appears too."""
    history = [
        {"role": "summary", "content": "The user is planning a wedding for 200 guests."},
        {"role": "user", "content": "Where is the coffee?"},
    ]
    llm = make_llm(mk.ai((SEARCH, {"query": "coffee"})))
    plan_question(llm, "And the decaf?", history)
    joined = "\n".join(_texts(llm))
    assert "The user is planning a wedding for 200 guests." in joined
    assert "Where is the coffee?" in joined


@pytest.mark.parametrize("history", [None, []])
def test_no_history_works(make_llm, mk, history):
    """Covers: AC-2 (boundary), EC-4. history=None and history=[] both work and the question is sent."""
    llm = make_llm(mk.ai((SEARCH, {"query": "coffee"})))
    plan = plan_question(llm, "Where is the coffee?", history)
    assert plan.route == "DOCS"
    assert "Where is the coffee?" in llm.invoke_calls[0][-1].content


def test_history_not_mutated(make_llm, mk):
    """Covers: AC-2 (boundary), extra. The caller's history list is left unchanged."""
    history = [{"role": "user", "content": "hi"}]
    snapshot = [dict(h) for h in history]
    plan_question(make_llm(mk.ai((SEARCH, {"query": "x"}))), "Where?", history)
    assert history == snapshot


def test_text_content_is_ignored(make_llm, mk):
    """Covers: AC-2 (right), extra. Text next to tool calls does not change the plan."""
    llm = make_llm(mk.ai((SEARCH, {"query": "coffee"}), content="I will use BOTH tools."))
    plan = plan_question(llm, "Where is the coffee?")
    assert plan.route == "DOCS" and plan.fallback is False


# --------------------------------------------------------------------------
# AC-3 route from calls (EC-5, EC-6)
# --------------------------------------------------------------------------

def test_tool_only_route(make_llm, mk):
    """Covers: AC-3 (right), EC-5. Two tool calls give TOOL, in order, args unchanged."""
    a = {"item": "cambros", "drinks": ["peach tea"], "gallons": [7]}
    b = {"recipe": "lemonade", "gallons": 4}
    plan = plan_question(make_llm(mk.ai((BEV, a), (REC, b))), "q")
    assert plan.route == "TOOL"
    assert plan.fallback is False
    assert plan.calls == (PlannedCall(BEV, a), PlannedCall(REC, b))


def test_both_route_search_first(make_llm, mk):
    """Covers: AC-3 (right), EC-6. Search then tool gives BOTH in order."""
    s = {"query": "where are the cambros kept"}
    t = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}
    plan = plan_question(make_llm(mk.ai((SEARCH, s), (BEV, t))), "q")
    assert plan.route == "BOTH" and plan.fallback is False
    assert plan.calls == (PlannedCall(SEARCH, s), PlannedCall(BEV, t))


def test_both_route_tool_first(make_llm, mk):
    """Covers: AC-3 (right), EC-6. Tool then search also gives BOTH, order kept."""
    s = {"query": "where are the cambros kept"}
    t = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}
    plan = plan_question(make_llm(mk.ai((BEV, t), (SEARCH, s))), "q")
    assert plan.route == "BOTH"
    assert plan.calls == (PlannedCall(BEV, t), PlannedCall(SEARCH, s))


def test_recipe_with_search_is_both(make_llm, mk):
    """Covers: AC-3 (right), extra. scale_recipe counts as a tool call for BOTH."""
    plan = plan_question(
        make_llm(mk.ai((SEARCH, {"query": "concentrate"}), (REC, {"recipe": "lemonade"}))), "q")
    assert plan.route == "BOTH"


def test_single_tool_call_is_tool(make_llm, mk):
    """Covers: AC-3 (boundary), extra. One tool call alone gives TOOL, not fallback."""
    plan = plan_question(make_llm(mk.ai((REC, {"recipe": "lemonade"}))), "q")
    assert plan.route == "TOOL" and plan.fallback is False and len(plan.calls) == 1


# --------------------------------------------------------------------------
# AC-4 fallback and cleaning (EC-7 to EC-11)
# --------------------------------------------------------------------------

def test_no_calls_falls_back(make_llm, mk):
    """Covers: AC-4 (wrong), EC-7. A text-only reply gives the DOCS fallback with the stripped question."""
    llm = make_llm(mk.ai(content="The coffee is under the machine."))
    plan = plan_question(llm, "  Where is the coffee?  ")
    assert plan == Plan("DOCS", (PlannedCall("search_documents", {"query": "Where is the coffee?"}),), True)


def test_unknown_only_falls_back(make_llm, mk):
    """Covers: AC-4 (wrong), EC-8. Only an unknown tool name gives the fallback."""
    plan = plan_question(make_llm(mk.ai(("make_coffee", {"x": 1}))), "Where is the coffee?")
    assert plan == Plan("DOCS", (PlannedCall("search_documents", {"query": "Where is the coffee?"}),), True)


def test_unknown_call_dropped_others_kept(make_llm, mk):
    """Covers: AC-4 (right), EC-8. An unknown call is dropped; the bev call stays; TOOL, no fallback."""
    args = {"item": "cups", "guests": 45}
    plan = plan_question(make_llm(mk.ai(("make_coffee", {"x": 1}), (BEV, args))), "How many cups for 45 guests?")
    assert plan.route == "TOOL"
    assert plan.fallback is False
    assert plan.calls == (PlannedCall(BEV, args),)


def test_unknown_call_dropped_in_between(make_llm, mk):
    """Covers: AC-4 (boundary), EC-8. Unknown calls between valid ones are dropped, order of the rest kept."""
    s = {"query": "coffee"}
    t = {"recipe": "lemonade"}
    plan = plan_question(make_llm(mk.ai((SEARCH, s), ("nope", {}), (REC, t))), "q")
    assert plan.route == "BOTH"
    assert plan.calls == (PlannedCall(SEARCH, s), PlannedCall(REC, t))


@pytest.mark.parametrize("bad_args", [
    {},
    {"query": ""},
    {"query": "   "},
    {"query": 5},
    {"query": "", "k": 3},
])
def test_bad_search_query_replaced(make_llm, mk, bad_args):
    """Covers: AC-4 (wrong), EC-9. A missing/blank/non-string query becomes the stripped question; other keys dropped."""
    plan = plan_question(make_llm(mk.ai((SEARCH, bad_args))), "  Where is the coffee? ")
    assert plan == Plan("DOCS", (PlannedCall(SEARCH, {"query": "Where is the coffee?"}),), False)


def test_good_search_query_extra_keys_dropped(make_llm, mk):
    """Covers: AC-4 (right), EC-9. A valid query is kept as sent; other keys are dropped, no fallback."""
    plan = plan_question(make_llm(mk.ai((SEARCH, {"query": "coffee", "k": 3}))), "Where is the coffee?")
    assert plan.calls == (PlannedCall(SEARCH, {"query": "coffee"}),)
    assert plan.calls[0].args == {"query": "coffee"}
    assert plan.fallback is False


def test_good_search_query_outer_spaces_kept_as_sent(make_llm, mk):
    """Covers: AC-4 (boundary), EC-9. A valid non-blank query with outer spaces is kept exactly as sent."""
    plan = plan_question(make_llm(mk.ai((SEARCH, {"query": "  where is the coffee  "}))), "Where is the coffee?")
    assert plan.calls == (PlannedCall(SEARCH, {"query": "  where is the coffee  "}),)
    assert plan.fallback is False


def test_non_dict_args_become_empty(make_llm, mk):
    """Covers: AC-4 (wrong), EC-9. calculate_bev_item with args None gets {}."""
    plan = plan_question(make_llm(mk.raw((BEV, None))), "q")
    assert plan.route == "TOOL"
    assert plan.calls == (PlannedCall(BEV, {}),)


def test_non_dict_search_args_use_question(make_llm, mk):
    """Covers: AC-4 (wrong), EC-9. A search call whose args is not a dict gets the stripped question as query."""
    plan = plan_question(make_llm(mk.raw((SEARCH, None))), " Where is the coffee? ")
    assert plan.calls == (PlannedCall(SEARCH, {"query": "Where is the coffee?"}),)
    assert plan.fallback is False


def test_rejectable_tool_args_kept_exactly(make_llm, mk):
    """Covers: AC-4 (boundary), EC-10. Args the tools would reject are kept unchanged."""
    args = {"item": "supplies", "drinks": ["coffee"], "guests": 0, "gallons": []}
    plan = plan_question(make_llm(mk.ai((BEV, args))), "q")
    assert plan.calls == (PlannedCall(BEV, args),)
    assert plan.calls[0].args["guests"] == 0
    assert plan.calls[0].args["gallons"] == []


def test_duplicate_searches_kept(make_llm, mk):
    """Covers: AC-4 (boundary), EC-11. Two identical searches are both kept; route DOCS."""
    s = {"query": "where is the coffee"}
    plan = plan_question(make_llm(mk.ai((SEARCH, s), (SEARCH, s))), "q")
    assert plan.route == "DOCS"
    assert plan.calls == (PlannedCall(SEARCH, s), PlannedCall(SEARCH, s))


def test_plan_is_frozen(make_llm, mk):
    """Covers: AC-4 (right), extra. Plan and PlannedCall are frozen dataclasses."""
    plan = plan_question(make_llm(mk.ai((SEARCH, {"query": "coffee"}))), "q")
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.route = "TOOL"
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.calls[0].name = "x"


def test_calls_never_empty(make_llm, mk):
    """Covers: AC-4 (boundary), extra. Even with an empty reply the plan has at least one call."""
    plan = plan_question(make_llm(mk.ai()), "Where is the coffee?")
    assert len(plan.calls) >= 1 and plan.fallback is True


# --------------------------------------------------------------------------
# AC-5 errors (EC-12, EC-13)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_empty_question_rejected_before_model(make_llm, mk, question):
    """Covers: AC-5 (wrong), EC-12 (boundary). Empty/whitespace question raises ValueError; model untouched."""
    llm = make_llm(mk.ai((SEARCH, {"query": "x"})))
    with pytest.raises(ValueError):
        plan_question(llm, question)
    assert llm.bind_calls == []
    assert llm.invoke_calls == []


def test_model_error_propagates(make_llm):
    """Covers: AC-5 (wrong), EC-13. A RuntimeError from invoke propagates unchanged."""
    llm = make_llm(raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        plan_question(llm, "Where is the coffee?")


def test_one_character_question_accepted(make_llm, mk):
    """Covers: AC-5 (boundary), extra. The shortest non-blank question is accepted."""
    plan = plan_question(make_llm(mk.ai((SEARCH, {"query": "x"}))), "?")
    assert plan.route == "DOCS"
