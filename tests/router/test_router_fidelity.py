"""AC-2 (spec 010): check_fidelity (section 4.1, EC-2 to EC-8). Pure unit tests, no model."""

from __future__ import annotations

import pytest

from blc.router import FIDELITY_PREFIX, RoutedPart, check_fidelity

ONE_TURN = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]
EACH_HISTORY = [
    {"role": "user", "content": "How many cambros for orange juice and iced tea?"},
    {"role": "assistant", "content": "How many gallons of each?"},
]

Q_DECAF = "I need 9 gallons of decaf and hot water, how many containers?"
Q_PACKAGE = "The decaf, tea, iced water package is ordered for 110 guests, how many cups?"
Q_BOTH = "Where is the creamer kept, and do I bring sugar for hot water for 35 guests?"
Q_PEACH = "Peach tea for 80 people, what should I pack?"
Q_PKG70 = "We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros?"


def T(text):
    return RoutedPart("TOOL", text)


def D(text):
    return RoutedPart("DOCS", text)


def check(question, history, *parts):
    return check_fidelity(question, history, tuple(parts))


def assert_reason(result):
    assert isinstance(result, str)
    assert result.startswith(FIDELITY_PREFIX)
    assert "\n" not in result and "\r" not in result


# ---------------------------------------------------------------- constant

def test_prefix_value():
    """Covers: AC-2 (right), EC-8. FIDELITY_PREFIX is 'invalid (rewrite): '."""
    assert FIDELITY_PREFIX == "invalid (rewrite): "


# ---------------------------------------------------------------- EC-2: the section 4.1 table

def test_row1_whole_question_no_history_is_faithful():
    """Covers: AC-2 (right), EC-2. A single part that is the whole question passes with no history."""
    assert check(Q_DECAF, [], T(Q_DECAF)) is None


def test_row2_split_per_drink_no_history_fails():
    """Covers: AC-2 (wrong), EC-2. Two rewritten parts fail rule V; the reason holds the first part that is not in the question."""
    first = "How many containers for 9 gallons of decaf?"
    r = check(Q_DECAF, [], T(first), T("How many containers for 9 gallons of hot water?"))
    assert_reason(r)
    assert first.casefold() in r.casefold()


def test_row3_dropped_package_no_history_fails():
    """Covers: AC-2 (wrong), EC-2. A part that drops the package text fails; the reason holds the part's text."""
    part = "How many cups for 110 guests?"
    r = check(Q_PACKAGE, [], T(part))
    assert_reason(r)
    assert part.casefold() in r.casefold()


def test_row4_docs_and_tool_cut_from_the_question_pass():
    """Covers: AC-2 (right), EC-2. Parts cut from the question between separate questions pass."""
    assert check(Q_BOTH, [], D("Where is the creamer kept?"), T("do I bring sugar for hot water for 35 guests?")) is None


def test_row5_rewritten_gallons_no_history_fails():
    """Covers: AC-2 (wrong), EC-2. 'How many gallons of peach tea for 80 people?' is not inside the question."""
    part = "How many gallons of peach tea for 80 people?"
    r = check(Q_PEACH, [], T(part))
    assert_reason(r)
    assert part.casefold() in r.casefold()


def test_row6_dropped_item_with_history_fails_and_names_pack():
    """Covers: AC-2 (wrong), EC-2. With history, the rewrite drops the item 'pack'; the reason names it."""
    r = check(Q_PEACH, ONE_TURN, T("How many gallons of peach tea for 80 people?"))
    assert_reason(r)
    assert "pack" in r.casefold()


def test_row7_each_followup_rewrite_is_faithful():
    """Covers: AC-2 (right), EC-2. '6 each.' rewritten with both drinks and '6' passes."""
    part = "How many cambros for 6 gallons of orange juice and 6 gallons of iced tea?"
    assert check("6 each.", EACH_HISTORY, T(part)) is None


def test_row8_lost_number_fails_and_names_six():
    """Covers: AC-2 (wrong), EC-2. The rewrite loses '6'; the reason names it."""
    r = check("6 each.", EACH_HISTORY, T("How many cambros for 4 gallons of orange juice?"))
    assert_reason(r)
    assert "6" in r


def test_row9_spelled_number_equals_digit_with_history():
    """Covers: AC-2 (right), EC-2, EC-6. 'Seven' in the question equals 7 in the part; gallons and containers are kept."""
    assert check("Seven gallons of decaf, which containers?", ONE_TURN, T("Which containers hold 7 gallons of decaf?")) is None


# ---------------------------------------------------------------- EC-3: rule V comparison

def test_ec3_case_spaces_and_end_punctuation_are_ignored():
    """Covers: AC-2 (right), EC-3. A part without the final '?' and in lower case is inside the question."""
    q = "Where is the tea? How many cups for 45 guests?"
    assert check(q, [], T("how many cups for 45 guests")) is None
    assert check(q, [], T("HOW MANY CUPS FOR 45 GUESTS?")) is None


def test_ec3_extra_spaces_in_the_part_are_ignored():
    """Covers: AC-2 (right), EC-3. Runs of spaces in the part do not matter."""
    q = "Where is the tea? How many cups for 45 guests?"
    assert check(q, [], T("  how   many  cups   for 45   guests  ")) is None


def test_ec3_punctuation_at_the_start_and_end_is_ignored():
    """Covers: AC-2 (boundary), EC-3. Leading and trailing punctuation on the part is ignored."""
    q = "Where is the tea? How many cups for 45 guests?"
    assert check(q, [], T("...How many cups for 45 guests?!")) is None
    assert check(q, [], D('"Where is the tea"')) is None


def test_ec3_package_text_copied_exactly_is_inside():
    """Covers: AC-2 (right), EC-3. The package text with its commas and '&' is inside the question when copied exactly."""
    assert check(Q_PKG70, [], T("the coffee, decaf, tea, iced water & juice package for 70 guests")) is None
    assert check(Q_PKG70, [], T(Q_PKG70)) is None


def test_ec3_inner_punctuation_must_match():
    """Covers: AC-2 (wrong), EC-3. Dropping the commas inside the text makes the part not inside the question."""
    r = check(Q_PKG70, [], T("the coffee decaf tea iced water & juice package for 70 guests"))
    assert_reason(r)


def test_ec3_and_for_ampersand_fails():
    """Covers: AC-2 (wrong), EC-3. Writing 'and' for '&' is a change."""
    assert_reason(check(Q_PKG70, [], T("the coffee, decaf, tea, iced water and juice package for 70 guests")))


def test_ec3_part_longer_than_question_fails():
    """Covers: AC-2 (wrong), EC-3 (extra). A part with extra words is not inside the question."""
    assert_reason(check("How many cups?", [], T("How many cups? Please answer.")))


def test_ec3_second_bad_part_is_also_caught():
    """Covers: AC-2 (wrong), EC-3 (extra). The first part is fine; the second is not inside the question; the reason holds the bad one."""
    bad = "do I bring sugar for 35 guests"
    r = check(Q_BOTH, [], D("Where is the creamer kept?"), T(bad))
    assert_reason(r)
    assert bad.casefold() in r.casefold()


# ---------------------------------------------------------------- EC-4: no history, rewrite fails

def test_ec4_rewrite_keeping_everything_still_fails_without_history():
    """Covers: AC-2 (wrong), EC-4. With no history the rewrite fails even if every number, drink and item is kept."""
    r = check(Q_DECAF, [], T("How many containers for 9 gallons of decaf and hot water?"))
    assert_reason(r)


def test_ec4_same_rewrite_passes_with_history():
    """Covers: AC-2 (right), EC-4, EC-5. The same rewrite passes once there is history (rule P)."""
    assert check(Q_DECAF, ONE_TURN, T("How many containers for 9 gallons of decaf and hot water?")) is None


# ---------------------------------------------------------------- EC-5: rule P

Q_P = "I need 9 gallons of decaf, how many containers?"


def test_ec5_rewrite_keeping_all_passes():
    """Covers: AC-2 (right), EC-5. Number, drink and item all kept."""
    assert check(Q_P, ONE_TURN, T("Which containers for 9 gallons of decaf?")) is None


def test_ec5_losing_a_number_fails():
    """Covers: AC-2 (wrong), EC-5. Losing '9' fails and the reason names it."""
    r = check(Q_P, ONE_TURN, T("How many containers for gallons of decaf?"))
    assert_reason(r)
    assert "9" in r


def test_ec5_losing_a_drink_fails():
    """Covers: AC-2 (wrong), EC-5. Losing 'decaf' fails and the reason names it."""
    r = check(Q_P, ONE_TURN, T("How many containers for 9 gallons?"))
    assert_reason(r)
    assert "decaf" in r.casefold()


def test_ec5_changing_a_drink_fails():
    """Covers: AC-2 (wrong), EC-5. Swapping decaf for lemonade loses decaf."""
    assert_reason(check(Q_P, ONE_TURN, T("How many containers for 9 gallons of lemonade?")))


def test_ec5_losing_an_item_fails():
    """Covers: AC-2 (wrong), EC-5. Losing 'containers' fails and the reason names it."""
    r = check(Q_P, ONE_TURN, T("How many cups for 9 gallons of decaf?"))
    assert_reason(r)
    assert "containers" in r.casefold()


def test_ec5_adding_item_from_history_passes():
    """Covers: AC-2 (right), EC-5. Parts may add an item (cambros from the history)."""
    assert check("5 gallons each.", EACH_HISTORY, T("How many cambros for 5 gallons of coffee and 5 gallons of lemonade?")) is None


def test_ec5_adding_drinks_from_history_passes():
    """Covers: AC-2 (right), EC-5. Parts may add drinks that were only in the history."""
    assert check("5 each.", EACH_HISTORY, T("How many cups for 5 gallons of orange juice and 5 gallons of iced tea?")) is None


def test_ec5_lost_items_and_numbers_are_all_listed():
    """Covers: AC-2 (wrong), EC-5. Every lost number, drink and item word appears in the reason."""
    q = "Bring 12 cups of lemonade and sugar for 40 guests"
    r = check(q, ONE_TURN, T("Tell me about the event."))
    assert_reason(r)
    low = r.casefold()
    for needle in ("12", "40", "lemonade", "cups", "sugar"):
        assert needle in low, needle


def test_ec5_rule_p_looks_at_all_parts_together():
    """Covers: AC-2 (right), EC-5. A number in one part and a drink in another still count as kept."""
    q = "Where is the lemonade kept, and how many cups for 45 guests?"
    assert check(q, ONE_TURN, D("Where is the lemonade kept?"), T("How many cups are needed for 45 people?")) is None


def test_ec5_no_numbers_drinks_or_items_in_question_passes_any_rewrite():
    """Covers: AC-2 (boundary), EC-5. Nothing to lose: with history any parts pass."""
    assert check("original user question quokka", ONE_TURN, T("anything at all")) is None


def test_ec5_item_dropped_even_if_other_items_added():
    """Covers: AC-2 (wrong), EC-5. Adding 'gallons' does not make up for losing 'pack'."""
    assert_reason(check(Q_PEACH, ONE_TURN, T("How many gallons of peach tea for 80 people?")))


def test_ec5_history_empty_list_is_no_history():
    """Covers: AC-2 (wrong), EC-4, EC-5. An empty history list means rule V only."""
    assert_reason(check(Q_P, [], T("Which containers for 9 gallons of decaf?")))


# ---------------------------------------------------------------- EC-6: numbers by value

def test_ec6_spelled_question_digit_part():
    """Covers: AC-2 (right), EC-6. 'Seven' in Q and 7 in the part match."""
    assert check("Seven cups of tea please", ONE_TURN, T("How many cups of tea for 7 guests?")) is None


def test_ec6_digit_question_spelled_part():
    """Covers: AC-2 (right), EC-6. 7 in Q and 'seven' in the part match."""
    assert check("7 cups of tea please", ONE_TURN, T("How many cups of tea for seven guests?")) is None


def test_ec6_comma_number_equals_plain_number_both_ways():
    """Covers: AC-2 (right), EC-6. 1,000 and 1000 match each other."""
    assert check("Do I need 1,000 cups?", ONE_TURN, T("How many cups for 1000 guests?")) is None
    assert check("Do I need 1000 cups?", ONE_TURN, T("How many cups for 1,000 guests?")) is None


def test_ec6_five_is_not_matched_by_fifty():
    """Covers: AC-2 (wrong), EC-6. 5 in Q is not matched by 50 in the part."""
    assert_reason(check("I need 5 cups of tea", ONE_TURN, T("How many cups of tea for 50 guests?")))


def test_ec6_fifty_is_not_matched_by_five():
    """Covers: AC-2 (wrong), EC-6. 50 in Q is not matched by 5 in the part."""
    assert_reason(check("I need 50 cups of tea", ONE_TURN, T("How many cups of tea for 5 guests?")))


def test_ec6_decimal_by_value():
    """Covers: AC-2 (right), EC-6. A decimal in Q is kept when the part has it; losing it fails."""
    assert check("2.5 gallons of lemonade, which cambros?", ONE_TURN, T("Which cambros for 2.5 gallons of lemonade?")) is None
    assert_reason(check("2.5 gallons of lemonade, which cambros?", ONE_TURN, T("Which cambros for 5 gallons of lemonade?")))


def test_ec6_spelled_number_losing_fails():
    """Covers: AC-2 (wrong), EC-6. 'twelve' in Q lost in the part fails."""
    assert_reason(check("twelve gallons of coffee, which cambros?", ONE_TURN, T("Which cambros for 7 gallons of coffee?")))


def test_ec6_one_hundred_spelled_matches_100():
    """Covers: AC-2 (boundary), EC-6. 'one hundred' equals 100."""
    assert check("one hundred cups of coffee", ONE_TURN, T("How many cups of coffee for 100 guests?")) is None


# ---------------------------------------------------------------- EC-7: never raises

@pytest.mark.parametrize("question", ["", " ", "\n"])
def test_ec7_blank_question_does_not_raise(question):
    """Covers: AC-2 (boundary), EC-7. A blank question never raises; result is None or a reason."""
    for history in ([], ONE_TURN):
        r = check_fidelity(question, history, (T("x"),))
        assert r is None or (isinstance(r, str) and r.startswith(FIDELITY_PREFIX))


def test_ec7_empty_parts_does_not_raise():
    """Covers: AC-2 (boundary), EC-7. Empty parts never raise."""
    for history in ([], ONE_TURN):
        r = check_fidelity(Q_DECAF, history, ())
        assert r is None or (isinstance(r, str) and r.startswith(FIDELITY_PREFIX))


@pytest.mark.parametrize(
    "history",
    [[{}], [{"role": "user"}], [{"content": "x"}], [{"role": "bot", "content": ""}], [{"role": 1, "content": 2}]],
)
def test_ec7_odd_history_items_do_not_raise(history):
    """Covers: AC-2 (boundary), EC-7. Odd history items still count as 'history not empty' and never raise."""
    r = check_fidelity(Q_DECAF, history, (T("How many containers for 9 gallons of decaf and hot water?"),))
    assert r is None or (isinstance(r, str) and r.startswith(FIDELITY_PREFIX))


def test_ec7_very_long_question_does_not_raise_and_whole_copy_passes():
    """Covers: AC-2 (boundary), EC-7. A very long question works; copying it whole is faithful."""
    q = ("Where is the tea kept? " * 5000) + "How many cups for 45 guests?"
    assert check_fidelity(q, [], (T(q),)) is None
    r = check_fidelity(q, [], (T("something else"),))
    assert_reason(r)


def test_ec7_prints_nothing_and_keeps_inputs(capsys):
    """Covers: AC-2 (boundary), EC-7. No output; history and parts unchanged."""
    history = [dict(m) for m in ONE_TURN]
    parts = (T("rewritten"),)
    check_fidelity(Q_DECAF, history, parts)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == ONE_TURN
    assert parts == (T("rewritten"),)


# ---------------------------------------------------------------- EC-8: reason shape

@pytest.mark.parametrize(
    "question, history, parts",
    [
        (Q_DECAF, [], (T("How many containers for 9 gallons of decaf?"),)),
        (Q_PEACH, ONE_TURN, (T("How many gallons of peach tea for 80 people?"),)),
        ("6 each.", EACH_HISTORY, (T("How many cambros for 4 gallons of orange juice?"),)),
        ("Where is the tea?\nHow many cups for 45 guests?", [], (T("rewritten text"),)),
        ("Where is the tea?\nHow many cups for 45 guests?", ONE_TURN, (T("rewritten text"),)),
    ],
)
def test_ec8_reason_is_one_line_with_prefix(question, history, parts):
    """Covers: AC-2 (right), EC-8. Every reason starts with FIDELITY_PREFIX and has no newline."""
    assert_reason(check_fidelity(question, history, parts))


def test_ec8_reason_tells_the_model_to_copy_the_users_words():
    """Covers: AC-2 (right), EC-8. The reason tells the model to copy the user's own words."""
    r = check(Q_DECAF, [], T("How many containers for 9 gallons of decaf?"))
    assert "copy" in r.casefold()


def test_ec8_none_is_returned_not_empty_string():
    """Covers: AC-2 (boundary), EC-8. A faithful result is None, not an empty string."""
    assert check(Q_DECAF, [], T(Q_DECAF)) is None
