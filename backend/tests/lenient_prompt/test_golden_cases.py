"""Spec 038, section 6.2 (EVAL): the golden file side of EVAL-1 to EVAL-3 (AC-5) and AC-6 limits. Unit; reads the file only.

The judged runs (EVAL-4, AC-5, AC-6 against a real model) are done by the existing graded food-answer eval
in backend/tests/food_answers/, which reads every case from the same golden file.
"""
import pytest

NEW_IDS = ("creamer-hot-tea", "bagels-bring-what", "conv-creamer-followup")


def _by_id(golden):
    return {c["id"]: c for c in golden}


@pytest.mark.parametrize("case_id", NEW_IDS)
def test_new_cases_exist_and_must_pass(golden, case_id):
    """Covers: AC-5 (right), EVAL-1, EVAL-2, EVAL-3. Each new case is in the file with must_pass true."""
    case = _by_id(golden).get(case_id)
    assert case is not None, case_id
    assert case["must_pass"] is True


def test_total_turns_within_spec_027_limit(golden):
    """Covers: AC-5 (boundary), spec 027 AC-1. Total turns stay between 20 and 40."""
    assert 20 <= sum(len(c["turns"]) for c in golden) <= 40


def test_ids_stay_unique(golden):
    """Covers: AC-5 (wrong). No duplicate case ids after the additions."""
    ids = [c["id"] for c in golden]
    assert len(ids) == len(set(ids))


def test_eval_1_creamer_hot_tea(golden):
    """Covers: AC-5 (right), EVAL-1. One turn, the exact question, reference requires No and forbids Yes."""
    turns = _by_id(golden)["creamer-hot-tea"]["turns"]
    assert len(turns) == 1
    assert turns[0]["question"] == "Do we need to bring creamer for hot tea?"
    ref = turns[0]["reference"]
    assert ref.startswith("Required:")
    low = ref.lower()
    assert "no" in low and "coffee" in low and "decaf" in low
    assert "must not" in low


def test_eval_2_bagels_bring_what(golden):
    """Covers: AC-5 (right), EVAL-2. One turn; reference requires bagels with location and cream cheese with
    location; forbids leaving out the bagels or adding plant-based herb cream cheese."""
    turns = _by_id(golden)["bagels-bring-what"]["turns"]
    assert len(turns) == 1
    assert turns[0]["question"] == "What do we need to bring for bagels?"
    ref = turns[0]["reference"]
    assert ref.startswith("Required:")
    low = ref.lower()
    for part in ("bagels", "metal rack", "service room", "manager", "cream cheese", "service cooler"):
        assert part in low, part
    assert "must not" in low and "plant-based" in low and "herb" in low


def test_eval_3_conversation_follow_up(golden):
    """Covers: AC-5 (right), EVAL-3. Two turns in order; turn 1 requires yes, turn 2 requires no (coffee or decaf)."""
    turns = _by_id(golden)["conv-creamer-followup"]["turns"]
    assert len(turns) == 2
    assert turns[0]["question"] == "Do we need creamer for coffee?"
    assert turns[1]["question"] == "What about hot tea?"
    assert turns[0]["reference"].startswith("Required:")
    assert "yes" in turns[0]["reference"].lower()
    assert turns[1]["reference"].startswith("Required:")
    low = turns[1]["reference"].lower()
    assert "no" in low and "coffee" in low and "decaf" in low


@pytest.mark.parametrize("case_id", ["abstain-cupcakes", "abstain-oat-milk"])
def test_abstain_cases_still_present(golden, case_id):
    """Covers: AC-6 (right). The two abstain cases remain in the file with a Required reference."""
    case = _by_id(golden).get(case_id)
    assert case is not None, case_id
    assert case["turns"][0]["reference"].startswith("Required:")
