"""AC-10: tool choice eval with the real model and the real store (cases T1 to T23).

Marked eval; skips (does not fail) when Ollama is not running or the knowledge files are not in
the store (NFR-4). Read only: nothing is written to .chroma/ or data/.

Tool column rules (spec section 6), checked exactly as written:
- none: no tool call.
- item: at least one call, every call is calculate_bev_item with that item, and run_bev_tool on the
  call's args gives the listed status (default ok), resolved drinks, amounts, from_guests and guests.
- none_or_item: no call, or calls matching the item whose result status is the listed one.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

pytestmark = pytest.mark.eval

ANY = "*"
HOT_DRINKS = {"Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider"}


def _guests_given(args):
    """Return the guests value the call gave as an int, or None when not given (missing, null, 0)."""
    raw = args.get("guests")
    if raw is None:
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return raw
    return None if value == 0 else value


def _drinks_match(got, expected):
    """got: list of DrinkAmount; expected: [(name, amount|ANY, from_guests|ANY)]."""
    by_name = {d.drink: d for d in got}
    if set(by_name) != {name for name, _, _ in expected} or len(by_name) != len(got):
        return False
    for name, amount, from_guests in expected:
        d = by_name[name]
        if amount != ANY and d.amount != Fraction(amount):
            return False
        if from_guests != ANY and d.from_guests != from_guests:
            return False
    return True


def _check_item_call(case, call, run_bev_tool, bev_name):
    if call.name != bev_name:
        return [f"call to {call.name!r}, expected {bev_name!r}"]
    errors = []
    args = call.args
    if args.get("item") != case["item"]:
        errors.append(f"item {args.get('item')!r} != {case['item']!r}")
    result = run_bev_tool(args)

    if case["kind"] == "none_or_item":
        if result.status != case["status"]:
            errors.append(f"status {result.status!r} != {case['status']!r}")
        return errors

    if result.status != case.get("status", "ok"):
        return errors + [f"status {result.status!r} != 'ok' (args {args})"]

    if case.get("drinks_hot_only"):
        if any(d.drink not in HOT_DRINKS for d in result.drinks):
            errors.append(f"drinks {[d.drink for d in result.drinks]} are not all hot drinks")
    elif "drinks_any_of" in case:
        if not any(_drinks_match(result.drinks, opt) for opt in case["drinks_any_of"]):
            errors.append(f"drinks {result.drinks} match none of {case['drinks_any_of']}")
    elif not _drinks_match(result.drinks, case["drinks"]):
        errors.append(f"drinks {result.drinks} do not match {case['drinks']}")

    expected_guests = case["guests"]
    given = _guests_given(args)
    if expected_guests is None:
        if given is not None:
            errors.append(f"guests {given!r} given, expected no guests")
    elif expected_guests != ANY and given != expected_guests:
        errors.append(f"guests {given!r} != {expected_guests}")
    return errors


def test_tool_choice(store, chat_llm, eval_case):
    """Covers: AC-10 (right/wrong per case), NFR-4 (skip). The real model's tool calls match the Tool column for every case T1 to T23."""
    from blc.tools.bev_tools import BEV_TOOL_NAME, run_bev_tool
    from chat import answer_with_tools, retrieve

    case = eval_case
    question = case["question"]
    docs = retrieve(store, question)
    out = answer_with_tools(chat_llm, case["history"], docs, question)
    calls = out.tool_calls
    names = [(c.name, c.args) for c in calls]

    if case["kind"] == "none":
        assert not calls, f"{case['id']}: expected no tool call, got {names}"
        return

    if case["kind"] == "none_or_item" and not calls:
        return

    assert calls, f"{case['id']}: expected a call to {BEV_TOOL_NAME}, got none. Reply: {out.reply!r}"
    errors = []
    for call in calls:
        errors += _check_item_call(case, call, run_bev_tool, BEV_TOOL_NAME)
    assert not errors, f"{case['id']}: {errors}. Calls: {names}. Reply: {out.reply!r}"
