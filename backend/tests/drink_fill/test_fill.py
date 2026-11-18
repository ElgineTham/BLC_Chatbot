"""Spec 022, AC-3 (fill_missing_drinks): EC-11 to EC-21 and the §4.2 rules. Unit tests, N = menu_names(Appendix A)."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from blc.flow import FROM_HISTORY, FROM_QUESTION, FilledDrinks, fill_missing_drinks

Q_DECAF = "How many cups to bring for decaf, 40 guests"
CUPS40 = {"item": "cups", "guests": 40}


def hist(*pairs):
    return [{"role": r, "content": c} for r, c in pairs]


def test_constants_and_dataclass():
    """Covers: AC-3 (right). FROM_QUESTION/FROM_HISTORY values; FilledDrinks is frozen with the three fields."""
    assert FROM_QUESTION == "question"
    assert FROM_HISTORY == "history"
    f = FilledDrinks(0, ("Decaf",), "question")
    assert (f.call_index, f.drinks, f.source) == (0, ("Decaf",), "question")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.call_index = 1  # type: ignore[misc]


# ---------------------------------------------------------------- EC-11, EC-12

def test_ec11_fills_from_question(names, P):
    """Covers: AC-3 (right), EC-11. The drink-less bev call gets the drinks; route and fallback are unchanged."""
    plan = P.plan("TOOL", P.bev(dict(CUPS40)))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert P.only_bev(new).args == {"item": "cups", "guests": 40, "drinks": ["Decaf"]}
    assert filled == FilledDrinks(0, ("Decaf",), "question")
    assert new.route == "TOOL" and new.fallback is False
    assert len(new.calls) == 1 and new.calls[0].name == "calculate_bev_item"


def test_ec11_input_plan_is_not_changed(names, P):
    """Covers: AC-3 (right), EC-11. The input plan, including its args dict, is untouched."""
    plan = P.plan("TOOL", P.bev(dict(CUPS40)))
    before = copy.deepcopy(plan)
    fill_missing_drinks(plan, Q_DECAF, None, names)
    assert plan == before
    assert "drinks" not in plan.calls[0].args


@pytest.mark.parametrize("empty", [[], None, "  ", ""], ids=["list", "none", "blank-string", "empty-string"])
def test_ec12_empty_drinks_are_filled(names, P, empty):
    """Covers: AC-3 (right + boundary), EC-12. drinks [], None, '  ' or '' count as no drinks."""
    plan = P.plan("TOOL", P.bev({**CUPS40, "drinks": empty}))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert P.only_bev(new).args == {"item": "cups", "guests": 40, "drinks": ["Decaf"]}
    assert filled == FilledDrinks(0, ("Decaf",), "question")


def test_other_args_are_kept(names, P):
    """Covers: AC-3 (right), §4.2 step 3. Every other argument stays as it was."""
    args = {"item": "everything", "guests": 55, "gallons": [2]}
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev(dict(args))), "pull sheet for decaf", None, names)
    assert P.only_bev(new).args == {**args, "drinks": ["Decaf"]}
    assert filled is not None


def test_several_drinks_in_text_order(names, P):
    """Covers: AC-3 (right), §4.2 step 3. drinks is a list of display names in order of appearance."""
    q = "Cups needed for orange juice and decaf, 140 guests?"
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 140})), q, None, names)
    assert P.only_bev(new).args["drinks"] == ["Orange juice", "Decaf"]
    assert isinstance(P.only_bev(new).args["drinks"], list)
    assert filled == FilledDrinks(0, ("Orange juice", "Decaf"), "question")


# ---------------------------------------------------------------- EC-13

def test_ec13_call_with_drinks_is_never_changed(names, P):
    """Covers: AC-3 (wrong), EC-13. A call that has drinks is left alone even if the question names another drink."""
    plan = P.plan("TOOL", P.bev({**CUPS40, "drinks": ["coffee"]}))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert new == plan and filled is None
    assert P.only_bev(new).args["drinks"] == ["coffee"]


def test_ec13_string_drinks_with_text_is_left_alone(names, P):
    """Covers: AC-3 (wrong), EC-13. A non-empty drinks string counts as having drinks."""
    plan = P.plan("TOOL", P.bev({**CUPS40, "drinks": "lemonade"}))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert new == plan and filled is None


# ---------------------------------------------------------------- EC-14, EC-15

def test_ec14_two_bev_calls_are_never_changed(names, P):
    """Covers: AC-3 (wrong), EC-14. Two bev calls, one without drinks: unchanged and None."""
    q = "How many cups and gallons of decaf do I need for 40 guests?"
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 40}),
                  P.bev({"item": "gallons", "drinks": ["decaf"], "guests": 40}))
    new, filled = fill_missing_drinks(plan, q, None, names)
    assert new == plan and filled is None


def test_ec14_two_drinkless_bev_calls_unchanged(names, P):
    """Covers: AC-3 (wrong), EC-14. Two bev calls, both without drinks: still unchanged."""
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 40}), P.bev({"item": "gallons", "guests": 40}))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert new == plan and filled is None


@pytest.mark.parametrize("kind", ["search", "recipe", "empty"])
def test_ec15_no_bev_call(names, P, kind):
    """Covers: AC-3 (wrong), EC-15. Search only, scale_recipe only, or no calls: unchanged and None."""
    if kind == "search":
        plan = P.plan("DOCS", P.search("decaf location"))
    elif kind == "recipe":
        plan = P.plan("TOOL", P.rec({"recipe": "lemonade", "guests": 40}))
    else:
        plan = P.plan("DOCS")
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert new == plan and filled is None


def test_recipe_call_is_never_filled_alongside_a_bev_call(names, P):
    """Covers: AC-3 (boundary), §4.2 step 1. A scale_recipe call does not count as a bev call and is not changed."""
    rec = {"recipe": "lemonade", "guests": 40}
    plan = P.plan("TOOL", P.rec(dict(rec)), P.bev(dict(CUPS40)))
    new, filled = fill_missing_drinks(plan, Q_DECAF, None, names)
    assert new.calls[0] == plan.calls[0] and "drinks" not in new.calls[0].args
    assert P.only_bev(new).args["drinks"] == ["Decaf"]
    assert filled == FilledDrinks(1, ("Decaf",), "question")


# ---------------------------------------------------------------- EC-16

def test_ec16_both_route_fills_the_bev_call_by_index(names, P):
    """Covers: AC-3 (right), EC-16. The bev call (index 1) gets Hot water; the search call and route are unchanged."""
    q = "Do we bring lemons for hot water, and how many cups for hot water for 35 guests?"
    search = P.search("lemons for hot water")
    plan = P.plan("BOTH", search, P.bev({"item": "cups", "guests": 35}))
    new, filled = fill_missing_drinks(plan, q, None, names)
    assert new.calls[0] == search
    assert new.calls[1].args == {"item": "cups", "guests": 35, "drinks": ["Hot water"]}
    assert filled.call_index == 1
    assert filled == FilledDrinks(1, ("Hot water",), "question")
    assert new.route == "BOTH"


# ---------------------------------------------------------------- EC-17 to EC-21

def test_ec17_fills_from_most_recent_user_message_naming_a_drink(names, P):
    """Covers: AC-3 (right), EC-17. Question '50' names nothing; the latest user message naming a drink is used."""
    h = hist(("user", "How many cups to bring for decaf, 40 guests"), ("assistant", "Hot cups: 60 for 40 guests."),
             ("user", "How many cups to bring for 2 gallons of decaf"), ("assistant", "How many guests?"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert P.only_bev(new).args == {"item": "cups", "guests": 50, "drinks": ["Decaf"]}
    assert filled == FilledDrinks(0, ("Decaf",), "history")


def test_ec18_most_recent_user_message_wins(names, P):
    """Covers: AC-3 (right), EC-18. 'actually decaf' (later) beats 'cups for coffee'."""
    h = hist(("user", "cups for coffee"), ("assistant", "How many guests?"),
             ("user", "actually decaf"), ("assistant", "How many guests?"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert P.only_bev(new).args["drinks"] == ["Decaf"]
    assert filled.source == "history"


def test_ec18_latest_user_message_without_a_drink_is_skipped(names, P):
    """Covers: AC-3 (boundary), EC-18. A later user message that names no drink is skipped, not a stop."""
    h = hist(("user", "cups for lemonade"), ("assistant", "How many guests?"), ("user", "hmm, 50 maybe"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert P.only_bev(new).args["drinks"] == ["Lemonade"]
    assert filled == FilledDrinks(0, ("Lemonade",), "history")


def test_ec18_all_drinks_of_that_one_message(names, P):
    """Covers: AC-3 (boundary), EC-18. The drinks come from one message only, all of its drinks, not mixed."""
    h = hist(("user", "cups for peach tea"), ("assistant", "How many guests?"),
             ("user", "coffee and lemonade please"), ("assistant", "How many guests?"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert P.only_bev(new).args["drinks"] == ["Coffee", "Lemonade"]


def test_ec19_assistant_text_is_not_searched(names, P):
    """Covers: AC-3 (wrong), EC-19. Only the assistant's reply names Coffee: unchanged and None."""
    h = hist(("user", "How many guests do we have?"), ("assistant", "Coffee for 40 guests."))
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 50}))
    new, filled = fill_missing_drinks(plan, "50", h, names)
    assert new == plan and filled is None


def test_ec19_summary_item_is_not_searched(names, P):
    """Covers: AC-3 (wrong), EC-19. A summary item naming a drink is not searched."""
    h = [{"role": "summary", "content": "The user asked about cups for decaf."}]
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 50}))
    new, filled = fill_missing_drinks(plan, "50", h, names)
    assert new == plan and filled is None


def test_ec19_assistant_after_user_without_drink_does_not_help(names, P):
    """Covers: AC-3 (wrong), EC-19. The assistant naming a drink between user messages is skipped; an older user drink is used."""
    h = hist(("user", "cups for lemonade"), ("assistant", "Decaf? How many guests?"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert P.only_bev(new).args["drinks"] == ["Lemonade"]


def test_ec20_question_beats_history(names, P):
    """Covers: AC-3 (right), EC-20. The question names Iced tea; the history names Decaf: Iced tea, source question."""
    h = hist(("user", "cups for decaf"), ("assistant", "How many guests?"))
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})),
                                      "make that iced tea, 50 guests", h, names)
    assert P.only_bev(new).args["drinks"] == ["Iced tea"]
    assert filled == FilledDrinks(0, ("Iced tea",), "question")


@pytest.mark.parametrize("history", [None, []], ids=["none", "empty"])
def test_ec21_no_drink_anywhere(names, P, history):
    """Covers: AC-3 (wrong + boundary), EC-21. Nothing named in question or history (None behaves as [])."""
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 45}))
    new, filled = fill_missing_drinks(plan, "How many cups for 45 guests?", history, names)
    assert new == plan and filled is None


def test_ec21_history_with_no_drinks(names, P):
    """Covers: AC-3 (wrong), EC-21. A history that names no drink leaves the plan unchanged."""
    h = hist(("user", "hello there"), ("assistant", "Hi!"))
    plan = P.plan("TOOL", P.bev({"item": "cups", "guests": 45}))
    new, filled = fill_missing_drinks(plan, "How many cups for 45 guests?", h, names)
    assert new == plan and filled is None


def test_history_none_behaves_like_empty_when_question_names_drink(names, P):
    """Covers: AC-3 (boundary), EC-21. history=None with a drink in the question still fills."""
    new, filled = fill_missing_drinks(P.plan("TOOL", P.bev(dict(CUPS40))), Q_DECAF, None, names)
    assert filled is not None


def test_history_input_is_not_changed(names, P):
    """Covers: AC-3 (right), §4.2 'never changes the input'. The history list is untouched."""
    h = hist(("user", "cups for decaf"), ("assistant", "How many guests?"))
    snap = copy.deepcopy(h)
    fill_missing_drinks(P.plan("TOOL", P.bev({"item": "cups", "guests": 50})), "50", h, names)
    assert h == snap
