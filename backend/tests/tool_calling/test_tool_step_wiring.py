"""Spec 016 AC-2: the tool step runs the router's tool with that tool's prompt (EC-5 to EC-12).

Unit tests with the scripted fake model of conftest.py (Scripted) and chat.CHAT_TOOLS patched to the Appendix A
beverage tool and the spec 015 test-book recipe tool. No Ollama, no network, nothing read under data/ (NFR-2).
"""

from __future__ import annotations

import chat
from langchain_core.messages import HumanMessage, SystemMessage

from blc.tool_step import REJECTED_PREFIX
from blc.tools.bev_tools import BEV_TOOL, BEV_TOOL_NAME
from blc.tools.recipe_tools import RECIPE_TOOL, RECIPE_TOOL_NAME

Q_RECIPE4 = "How much lemon concentrate do I need for 4 gallons of lemonade?"
Q_CAMBROS10 = "How many cambros for 10 gallons of iced tea?"
Q_GUESTS90 = "How do I make lemonade for 90 guests?"
Q_BOTH = "How many cambros for 6 gallons of lemonade; how much concentrate for 6 gallons of lemonade?"
RECIPE_4 = {"recipe": "lemonade", "gallons": 4}
BEV_10 = {"item": "cambros", "drinks": ["iced tea"], "gallons": [10]}
BEV_6 = {"item": "cambros", "drinks": ["lemonade"], "gallons": [6]}
RECIPE_6 = {"recipe": "lemonade", "gallons": 6}


def names(tools):
    return [t.name for t in tools]


# ---------------------------------------------------------------- EC-5 a recipe part

def test_recipe_part_binds_only_the_recipe_tool_with_its_prompt(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), EC-5. One bind_tools call with exactly scale_recipe; messages are [SystemMessage(RECIPE_TOOL_PROMPT), HumanMessage(part text)]; one call with '28 oz' in its result."""
    llm = Scripted(["T"], bound=[ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)])])
    trace = run_flow(llm, Q_RECIPE4, [bev_tool, recipe_tool])
    assert len(llm.bind_calls) == 1
    assert names(llm.bind_calls[0]) == [RECIPE_TOOL_NAME]
    assert len(llm.bound_invocations) == 1
    first, second = llm.bound_invocations[0][:2]
    assert isinstance(first, SystemMessage) and first.content == chat.RECIPE_TOOL_PROMPT
    assert isinstance(second, HumanMessage) and second.content == Q_RECIPE4
    assert len(trace.tools) == 1 and len(trace.tools[0].calls) == 1
    call = trace.tools[0].calls[0]
    assert call.name == RECIPE_TOOL_NAME and call.refused is False
    assert "28 oz" in call.result
    assert trace.tools[0].tool_text is not None and "28 oz" in trace.tools[0].tool_text


def test_recipe_step_does_not_use_the_beverage_prompt(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (wrong), EC-5. The recipe step's system message is not the beverage prompt."""
    llm = Scripted(["T"], bound=[ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)])])
    run_flow(llm, Q_RECIPE4, [bev_tool, recipe_tool])
    assert llm.bound_invocations[0][0].content != chat.TOOL_PROMPT


# ---------------------------------------------------------------- EC-6 a beverage part

def test_beverage_part_binds_only_the_beverage_tool_with_its_prompt(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), EC-6. A cambros question: bind_tools with exactly the beverage tool; first message TOOL_PROMPT."""
    llm = Scripted(["T"], bound=[ai("", [tc(BEV_TOOL_NAME, BEV_10)])])
    trace = run_flow(llm, Q_CAMBROS10, [bev_tool, recipe_tool])
    assert len(llm.bind_calls) == 1 and names(llm.bind_calls[0]) == [BEV_TOOL_NAME]
    first, second = llm.bound_invocations[0][:2]
    assert isinstance(first, SystemMessage) and first.content == chat.TOOL_PROMPT
    assert isinstance(second, HumanMessage) and second.content == Q_CAMBROS10
    assert [c.name for c in trace.tools[0].calls] == [BEV_TOOL_NAME]


def test_chat_tools_order_does_not_decide_the_tool(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (boundary), EC-6, NFR-5. Extra: with CHAT_TOOLS in the other order the tool is still chosen by name."""
    llm = Scripted(["T"], bound=[ai("", [tc(BEV_TOOL_NAME, BEV_10)])])
    run_flow(llm, Q_CAMBROS10, [recipe_tool, bev_tool])
    assert names(llm.bind_calls[0]) == [BEV_TOOL_NAME]
    assert llm.bound_invocations[0][0].content == chat.TOOL_PROMPT


# ---------------------------------------------------------------- EC-7 two parts, two tools

def test_two_parts_use_their_own_tool_and_prompt_in_order(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), EC-7. 'TT' gives a calculate_bev_item part then a scale_recipe part; each step is bound with only its tool and prompt; two tool stages in order."""
    llm = Scripted(["TT"], bound=[ai("", [tc(BEV_TOOL_NAME, BEV_6)]), ai("", [tc(RECIPE_TOOL_NAME, RECIPE_6, "call_2")])])
    trace = run_flow(llm, Q_BOTH, [bev_tool, recipe_tool])
    assert [p.tool for p in trace.route.parts if p.route == "TOOL"] == [BEV_TOOL_NAME, RECIPE_TOOL_NAME]
    assert [names(b) for b in llm.bind_calls] == [[BEV_TOOL_NAME], [RECIPE_TOOL_NAME]]
    assert len(llm.bound_invocations) == 2
    assert llm.bound_invocations[0][0].content == chat.TOOL_PROMPT
    assert llm.bound_invocations[1][0].content == chat.RECIPE_TOOL_PROMPT
    assert "cambros" in str(llm.bound_invocations[0][1].content)
    assert "concentrate" in str(llm.bound_invocations[1][1].content)
    assert len(trace.tools) == 2
    assert [c.name for c in trace.tools[0].calls] == [BEV_TOOL_NAME]
    assert [c.name for c in trace.tools[1].calls] == [RECIPE_TOOL_NAME]
    assert "42 oz" in (trace.tools[1].tool_text or "")


def test_a_turn_without_a_tool_part_never_binds_tools(Scripted, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (wrong), section 4.1. A plain docs question with both tools in CHAT_TOOLS makes no bind_tools call."""
    llm = Scripted([])
    trace = run_flow(llm, "Where is the coffee?", [bev_tool, recipe_tool])
    assert llm.bind_calls == [] and llm.bound_invocations == []
    assert trace.tools == ()


# ---------------------------------------------------------------- EC-8 a call to the wrong tool

def test_call_to_the_other_tool_is_an_unknown_tool(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (wrong), EC-8. In a scale_recipe step a call to calculate_bev_item gets 'error: unknown tool calculate_bev_item' and nothing raises."""
    llm = Scripted(["T"], bound=[ai("", [tc(BEV_TOOL_NAME, BEV_10)])], repeat_last=True)
    trace = run_flow(llm, Q_RECIPE4, [bev_tool, recipe_tool])
    calls = trace.tools[0].calls
    assert len(calls) >= 1
    assert all(c.name == BEV_TOOL_NAME for c in calls)
    assert all(c.result == "error: unknown tool calculate_bev_item" for c in calls)


def test_beverage_step_call_to_recipe_tool_is_unknown(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (wrong), EC-8. Extra, the mirror: in a calculate_bev_item step a call to scale_recipe gets 'error: unknown tool scale_recipe'."""
    llm = Scripted(["T"], bound=[ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)])], repeat_last=True)
    trace = run_flow(llm, Q_CAMBROS10, [bev_tool, recipe_tool])
    calls = trace.tools[0].calls
    assert calls and all(c.result == "error: unknown tool scale_recipe" for c in calls)


# ---------------------------------------------------------------- EC-9 argument check for scale_recipe

def test_refused_recipe_call_is_recorded_and_the_model_asked_again(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right, wrong), EC-9. gallons 4 for a 90-guest question is refused (REJECTED_PREFIX, refused=True); the second call with guests 90 runs and gives the stage's tool_text."""
    llm = Scripted(
        ["T"],
        bound=[ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)]), ai("", [tc(RECIPE_TOOL_NAME, {"recipe": "lemonade", "guests": 90}, "call_2")])],
    )
    trace = run_flow(llm, Q_GUESTS90, [bev_tool, recipe_tool])
    calls = trace.tools[0].calls
    assert len(calls) == 2
    assert calls[0].refused is True and calls[0].result.startswith(REJECTED_PREFIX)
    assert "gallons" in calls[0].result
    assert calls[1].refused is False
    assert len(llm.bound_invocations) == 2
    text = trace.tools[0].tool_text
    assert text is not None and "28 oz" in text and "90 guests" in text


def test_recipe_guests_call_is_not_refused_by_the_everything_rule(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), EC-9, section 4.1. Extra: the flow checks with tool='scale_recipe', so guests 70 for a question with a pack-style wording is not refused by spec 009's 'everything' rule."""
    q = "What concentrate do I pack for lemonade for 70 guests?"
    llm = Scripted(["T"], bound=[ai("", [tc(RECIPE_TOOL_NAME, {"recipe": "lemonade", "guests": 70})])])
    trace = run_flow(llm, q, [bev_tool, recipe_tool])
    calls = trace.tools[0].calls
    assert len(calls) == 1 and calls[0].refused is False
    assert "21 oz" in (trace.tools[0].tool_text or "")


def test_always_refused_recipe_calls_stop_at_the_round_limit(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (boundary), EC-9. A model that keeps sending the refused call stops after at most MAX_TOOL_ROUNDS rounds, all calls refused, nothing raised."""
    llm = Scripted(["T"], bound=[ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)])], repeat_last=True)
    trace = run_flow(llm, Q_GUESTS90, [bev_tool, recipe_tool])
    calls = trace.tools[0].calls
    assert 1 <= len(calls) <= chat.MAX_TOOL_ROUNDS
    assert all(c.refused for c in calls)
    assert len(llm.bound_invocations) <= chat.MAX_TOOL_ROUNDS


def test_no_call_reminder_names_the_recipe_tool(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), section 4.1. A recipe step where the model makes no call: the model is asked again, the reminder (after the two prompt messages) names scale_recipe, not the beverage tool; retried is True."""
    llm = Scripted(["T"], bound=[ai("It is 28 oz."), ai("", [tc(RECIPE_TOOL_NAME, RECIPE_4)])])
    trace = run_flow(llm, Q_RECIPE4, [bev_tool, recipe_tool])
    assert len(llm.bound_invocations) == 2
    extra = llm.bound_invocations[1][2:]
    assert extra
    joined = "\n".join(str(m.content) for m in extra)
    assert RECIPE_TOOL_NAME in joined and BEV_TOOL_NAME not in joined
    assert trace.tools[0].retried is True


def test_no_call_reminder_names_the_beverage_tool(Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), section 4.1. The mirror for a beverage step: the reminder names calculate_bev_item, not scale_recipe."""
    llm = Scripted(["T"], bound=[ai("Two cambros."), ai("", [tc(BEV_TOOL_NAME, BEV_10)])])
    trace = run_flow(llm, Q_CAMBROS10, [bev_tool, recipe_tool])
    extra = llm.bound_invocations[1][2:]
    assert extra
    joined = "\n".join(str(m.content) for m in extra)
    assert BEV_TOOL_NAME in joined and RECIPE_TOOL_NAME not in joined
    assert trace.tools[0].retried is True


# ---------------------------------------------------------------- EC-10 tool not in CHAT_TOOLS

def test_part_for_a_tool_not_in_chat_tools_falls_back_to_docs(Scripted, run_flow, bev_tool, docs, doc_mark):
    """Covers: AC-2 (wrong), EC-10. CHAT_TOOLS holds only the beverage tool and the part is routed to scale_recipe: no bind_tools, no calls, tool_text None, and the final messages include the documents."""
    llm = Scripted(["T", "From the documents."])
    trace = run_flow(llm, Q_RECIPE4, [bev_tool], generate=True)
    assert [p.tool for p in trace.route.parts] == [RECIPE_TOOL_NAME]
    assert llm.bind_calls == [] and llm.bound_invocations == []
    assert len(trace.tools) == 1
    assert trace.tools[0].calls == () and trace.tools[0].tool_text is None
    final = "\n".join(str(m.content) for m in llm.plain_invocations[-1])
    assert doc_mark in final
    assert trace.reply == "From the documents."


def test_empty_chat_tools_makes_no_tool_step(Scripted, run_flow):
    """Covers: AC-2 (boundary), EC-10. Extra: with no tools at all, a routed TOOL part still makes no bind_tools call and falls back to docs."""
    llm = Scripted(["T"])
    trace = run_flow(llm, Q_RECIPE4, [])
    assert llm.bind_calls == []
    assert all(s.tool_text is None and s.calls == () for s in trace.tools)


# ---------------------------------------------------------------- EC-11 a part with no tool name

def test_tool_part_with_no_tool_name_runs_the_beverage_tool(monkeypatch, Scripted, ai, tc, run_flow, bev_tool, recipe_tool):
    """Covers: AC-2 (right), EC-11. A TOOL part with tool=None (route monkeypatched) runs calculate_bev_item with TOOL_PROMPT."""
    from blc.router import RouteDecision, RoutedPart

    q = "How many cambros for 10 gallons of iced tea?"
    decision = RouteDecision((RoutedPart("TOOL", q, None),), "TOOL", False)

    def fake_route(llm, history, question):
        return decision

    monkeypatch.setattr(chat, "route_fast", fake_route, raising=False)
    import blc.router as router_pkg

    monkeypatch.setattr(router_pkg, "route_fast", fake_route, raising=False)
    llm = Scripted([], bound=[ai("", [tc(BEV_TOOL_NAME, BEV_10)])])
    trace = run_flow(llm, q, [bev_tool, recipe_tool])
    assert len(llm.bind_calls) == 1 and names(llm.bind_calls[0]) == [BEV_TOOL_NAME]
    assert llm.bound_invocations[0][0].content == chat.TOOL_PROMPT
    assert [c.name for c in trace.tools[0].calls] == [BEV_TOOL_NAME]
    assert trace.tools[0].tool_text is not None


# ---------------------------------------------------------------- EC-12 the module's constants

def test_unpatched_chat_tools_hold_both_tools():
    """Covers: AC-2 (right), EC-12. chat.CHAT_TOOLS contains BEV_TOOL and RECIPE_TOOL."""
    assert any(t is BEV_TOOL for t in chat.CHAT_TOOLS)
    assert any(t is RECIPE_TOOL for t in chat.CHAT_TOOLS)
    assert sorted(names(chat.CHAT_TOOLS)) == sorted([BEV_TOOL_NAME, RECIPE_TOOL_NAME])


def test_tool_prompts_table():
    """Covers: AC-2 (right, wrong), EC-12. TOOL_PROMPTS has exactly the two keys and maps them to TOOL_PROMPT and RECIPE_TOOL_PROMPT."""
    assert set(chat.TOOL_PROMPTS) == {BEV_TOOL_NAME, RECIPE_TOOL_NAME}
    assert chat.TOOL_PROMPTS[BEV_TOOL_NAME] == chat.TOOL_PROMPT
    assert chat.TOOL_PROMPTS[RECIPE_TOOL_NAME] == chat.RECIPE_TOOL_PROMPT
    assert chat.TOOL_PROMPT != chat.RECIPE_TOOL_PROMPT


def test_recipe_tool_prompt_content():
    """Covers: AC-2 (right), EC-12, section 3.1. RECIPE_TOOL_PROMPT is a non-empty string that names scale_recipe, mentions gallons and guests, and holds at least two '{' (example argument dicts)."""
    p = chat.RECIPE_TOOL_PROMPT
    assert isinstance(p, str) and p.strip()
    assert RECIPE_TOOL_NAME in p
    assert p.count("{") >= 2
    low = p.casefold()
    assert "gallons" in low and "guests" in low


def test_tool_step_texts_hold_no_eval_question_word_for_word(b_cases, r_cases):
    """Covers: AC-2 (wrong), NFR-4 (extra, normally a manual review). Neither tool prompt, the classifier prompt nor a tool description contains a B or R question (25 characters or more) word for word."""
    from blc.router import classifier_prompt

    texts = [chat.TOOL_PROMPT, chat.RECIPE_TOOL_PROMPT, classifier_prompt(), BEV_TOOL.description, RECIPE_TOOL.description]
    haystack = "\n".join(texts).casefold()
    for case in list(b_cases) + list(r_cases):
        q = case["question"].casefold()
        if len(q) >= 25:
            assert q not in haystack, f"{case['id']} appears in a prompt or tool description"
