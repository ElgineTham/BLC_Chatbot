"""Spec 009 AC-2 (run_tool_step applies the check) and AC-3 (temperature).

Unit: scripted fake model, tool from make_bev_tool on the spec 005 Appendix A catalog
(through the bev_spy fixture, which records invocations). No Ollama, no network, nothing under data/.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage

from blc.router import RoutedPart
from blc.tool_step import REJECTED_PREFIX
from blc.tools.bev_tools import BEV_TOOL_NAME
from chat import CHAT_TEMPERATURE, MAX_TOOL_ROUNDS, TOOL_LIMIT_REPLY, run_tool_step

QUESTION = "How many cambros for 7 gallons of lemonade?"
GOOD = {"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}
BAD = {"item": "cambros", "drinks": ["lemonade"], "gallons": [7], "guests": 40}  # 40 is invented


def _tool_messages(messages):
    return [m for m in messages if isinstance(m, ToolMessage)]


def test_temperature_is_zero():
    """Covers: AC-3 (right), EC-13. CHAT_TEMPERATURE is 0."""
    assert CHAT_TEMPERATURE == 0
    assert CHAT_TEMPERATURE != 0.1


def test_refused_then_good_call(bev_tool, bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-9. Invented guests refused, retry without them runs once."""
    tool, calls = bev_spy
    bound = make_bound([ai([tc(BEV_TOOL_NAME, dict(BAD), "c1")]), ai([tc(BEV_TOOL_NAME, dict(GOOD), "c2")])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert len(calls) == 1 and calls[0] == GOOD
    assert len(out.records) == 2
    assert out.records[0].name == BEV_TOOL_NAME
    assert out.records[0].args == BAD
    assert out.records[0].result.startswith(REJECTED_PREFIX)
    assert "guests" in out.records[0].result and "40" in out.records[0].result
    assert not out.records[1].result.startswith(REJECTED_PREFIX)
    assert out.tool_text == out.records[1].result == bev_tool.invoke(GOOD)
    assert len(bound.invocations) == 2
    msgs = _tool_messages(bound.invocations[1])
    assert any(m.content == out.records[0].result and m.tool_call_id == "c1" for m in msgs)


def test_check_does_not_set_retried(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-9. A refused call does not change retried."""
    tool, _ = bev_spy
    bound = make_bound([ai([tc(BEV_TOOL_NAME, dict(BAD))]), ai([tc(BEV_TOOL_NAME, dict(GOOD))])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))
    assert out.retried is False


def test_refused_forever_hits_limit(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (wrong), EC-10. Every call refused: limit reply after MAX_TOOL_ROUNDS, tool never run."""
    tool, calls = bev_spy
    bound = make_bound([ai([tc(BEV_TOOL_NAME, dict(BAD))])], repeat_last=True)
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert out.tool_text == TOOL_LIMIT_REPLY
    assert calls == []
    assert len(bound.invocations) == MAX_TOOL_ROUNDS
    assert len(out.records) == MAX_TOOL_ROUNDS
    assert all(r.result.startswith(REJECTED_PREFIX) for r in out.records)


def test_good_call_runs_as_before(bev_tool, bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-11. Correct arguments are not refused."""
    tool, calls = bev_spy
    bound = make_bound([ai([tc(BEV_TOOL_NAME, dict(GOOD))])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert calls == [GOOD]
    assert len(out.records) == 1
    assert out.records[0].args == GOOD
    assert out.records[0].result == bev_tool.invoke(GOOD)
    assert out.tool_text == out.records[0].result
    assert len(bound.invocations) == 1
    assert out.retried is False


def test_no_numbers_call_not_refused(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-11 (boundary). A call with no guests/gallons and no number in the question runs."""
    tool, calls = bev_spy
    args = {"item": "supplies", "drinks": ["coffee"]}
    bound = make_bound([ai([tc(BEV_TOOL_NAME, args)])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", "Do I need sugar for coffee?"))
    assert calls == [args]
    assert len(out.records) == 1 and not out.records[0].result.startswith(REJECTED_PREFIX)


def test_refused_and_good_in_same_round(bev_tool, bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right/wrong), EC-12. Good call runs, refused does not, round counts as failed."""
    tool, calls = bev_spy
    bound = make_bound([
        ai([tc(BEV_TOOL_NAME, dict(BAD), "bad"), tc(BEV_TOOL_NAME, dict(GOOD), "good")]),
        ai([tc(BEV_TOOL_NAME, dict(GOOD), "good2")]),
    ])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert len(bound.invocations) == 2, "a round with a refused call must be asked again"
    assert calls == [GOOD, GOOD]  # one run per round; the refused call never ran
    assert [r.args for r in out.records] == [BAD, GOOD, GOOD]
    assert out.records[0].result.startswith(REJECTED_PREFIX)
    assert not out.records[1].result.startswith(REJECTED_PREFIX)
    assert out.tool_text == out.records[2].result
    by_id = {m.tool_call_id: m.content for m in _tool_messages(bound.invocations[1])}
    assert by_id["bad"] == out.records[0].result
    assert by_id["good"] == out.records[1].result


def test_rule_b_refusal_in_tool_step(bev_tool, bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (wrong/right), EC-9 (item rule). supplies for an 'everything' question is refused, then fixed."""
    tool, calls = bev_spy
    q = "What do I need to bring for decaf for 85 guests?"
    wrong = {"item": "supplies", "drinks": ["decaf"], "guests": 85}
    right = {"item": "everything", "drinks": ["decaf"], "guests": 85}
    bound = make_bound([ai([tc(BEV_TOOL_NAME, wrong)]), ai([tc(BEV_TOOL_NAME, right)])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", q))

    assert calls == [right]
    assert out.records[0].result.startswith(REJECTED_PREFIX)
    assert "everything" in out.records[0].result.lower()
    assert out.tool_text == bev_tool.invoke(right)


def test_check_uses_part_text(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right/wrong), EC-9 (boundary). The check compares with part.text: the same args pass for one question and not another."""
    tool, calls = bev_spy
    args = {"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}
    ok = run_tool_step(make_bound([ai([tc(BEV_TOOL_NAME, dict(args))])]), (tool,),
                       RoutedPart("TOOL", "Seven gallons of lemonade, which containers?"))
    assert len(calls) == 1 and not ok.records[0].result.startswith(REJECTED_PREFIX)

    bound = make_bound([ai([tc(BEV_TOOL_NAME, dict(args))])], repeat_last=True)
    bad = run_tool_step(bound, (tool,), RoutedPart("TOOL", "Which containers for lemonade?"))
    assert len(calls) == 1, "tool must not run when 7 is not in the question"
    assert bad.tool_text == TOOL_LIMIT_REPLY


def _ran(spy_calls, make_bound, ai, tc, tool, question, args):
    bound = make_bound([ai([tc(BEV_TOOL_NAME, args)])], repeat_last=True)
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", question))
    return out, bound


def test_whole_match_gallons_17_vs_7(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (wrong/right), EC-14. '17 gallons': gallons [7] refused, [17] runs."""
    tool, calls = bev_spy
    q = "Which cambros for 17 gallons of decaf?"
    bad, _ = _ran(calls, make_bound, ai, tc, tool, q, {"item": "cambros", "drinks": ["decaf"], "gallons": [7]})
    assert calls == [] and bad.tool_text == TOOL_LIMIT_REPLY
    good, _ = _ran(calls, make_bound, ai, tc, tool, q, {"item": "cambros", "drinks": ["decaf"], "gallons": [17]})
    assert len(calls) == 1 and not good.records[0].result.startswith(REJECTED_PREFIX)


def test_whole_match_guests(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right/wrong), EC-14. 'often 10 guests' accepts 10; '150 guests' refuses 50; 'a 50-guest event' accepts 50."""
    tool, calls = bev_spy
    args = {"item": "cups", "drinks": ["coffee"]}
    _ran(calls, make_bound, ai, tc, tool, "Cups for often 10 guests of coffee?", {**args, "guests": 10})
    assert len(calls) == 1
    out, _ = _ran(calls, make_bound, ai, tc, tool, "Cups for 150 guests of coffee?", {**args, "guests": 50})
    assert len(calls) == 1 and out.tool_text == TOOL_LIMIT_REPLY
    _ran(calls, make_bound, ai, tc, tool, "Cups for a 50-guest event of coffee?", {**args, "guests": 50})
    assert len(calls) == 2


def test_whole_match_words(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right/wrong), EC-14. 'seventeen' does not allow 7; 'twenty five' allows 25."""
    tool, calls = bev_spy
    args = {"item": "cambros", "drinks": ["decaf"]}
    out, _ = _ran(calls, make_bound, ai, tc, tool, "Which cambros for seventeen gallons of decaf?",
                  {**args, "gallons": [7]})
    assert calls == [] and out.tool_text == TOOL_LIMIT_REPLY
    _ran(calls, make_bound, ai, tc, tool, "Which cambros for twenty five gallons of decaf?",
         {**args, "gallons": [25]})
    assert len(calls) == 1


def test_boundary_good_call_after_max_minus_one_refusals(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-15 (boundary). MAX_TOOL_ROUNDS-1 refused rounds then a good call: tool runs once."""
    tool, calls = bev_spy
    script = [ai([tc(BEV_TOOL_NAME, dict(BAD), f"b{i}")]) for i in range(MAX_TOOL_ROUNDS - 1)]
    script.append(ai([tc(BEV_TOOL_NAME, dict(GOOD), "g")]))
    bound = make_bound(script)
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert calls == [GOOD]
    assert out.tool_text != TOOL_LIMIT_REPLY
    assert len(out.records) == MAX_TOOL_ROUNDS
    assert all(r.result.startswith(REJECTED_PREFIX) for r in out.records[:-1])
    assert not out.records[-1].result.startswith(REJECTED_PREFIX)
    assert out.tool_text == out.records[-1].result
    assert len(bound.invocations) == MAX_TOOL_ROUNDS


def test_boundary_max_rounds_of_refusals_is_limit(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (wrong), EC-15 (boundary). MAX_TOOL_ROUNDS refused rounds: limit reply, tool never ran."""
    tool, calls = bev_spy
    script = [ai([tc(BEV_TOOL_NAME, dict(BAD), f"b{i}")]) for i in range(MAX_TOOL_ROUNDS)]
    bound = make_bound(script)
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))
    assert calls == []
    assert out.tool_text == TOOL_LIMIT_REPLY
    assert len(out.records) == MAX_TOOL_ROUNDS


def test_record_and_message_order_follows_calls(bev_spy, make_bound, ai, tc):
    """Covers: AC-2 (right), section 3.2 order (revision 1). Records and tool messages follow the model's call order."""
    tool, calls = bev_spy
    bound = make_bound([
        ai([tc(BEV_TOOL_NAME, dict(GOOD), "first"), tc(BEV_TOOL_NAME, dict(BAD), "second"),
            tc(BEV_TOOL_NAME, dict(GOOD), "third")]),
        ai([tc(BEV_TOOL_NAME, dict(GOOD), "next")]),
    ])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", QUESTION))

    assert [r.args for r in out.records[:3]] == [GOOD, BAD, GOOD]
    assert not out.records[0].result.startswith(REJECTED_PREFIX)
    assert out.records[1].result.startswith(REJECTED_PREFIX)
    assert not out.records[2].result.startswith(REJECTED_PREFIX)
    msgs = _tool_messages(bound.invocations[1])
    assert [m.tool_call_id for m in msgs] == ["first", "second", "third"]
    assert [m.content for m in msgs] == [r.result for r in out.records[:3]]


def test_other_tool_names_not_checked(other_tool, make_bound, ai, tc):
    """Covers: AC-2 (right), EC-11 (boundary). Calls to other tool names are not checked."""
    tool, calls = other_tool
    bound = make_bound([ai([tc("other_tool", {"guests": 50})])])
    out = run_tool_step(bound, (tool,), RoutedPart("TOOL", "How many cups?"))
    assert calls == [{"guests": 50}]
    assert len(out.records) == 1
    assert out.records[0].result == "other-result"
    assert out.tool_text == "other-result"
