"""GOLD-1 to GOLD-5 (AC-1): validity of evals/answers/food_answers.jsonl. Unit; reads the file only."""

from __future__ import annotations

import json

import pytest

from food_answer_helpers import GOLDEN_PATH, load_golden

BUG_IDS = (
    "croissant-extras",
    "croissant-preserves",
    "conv-croissant-pushback",
    "croissant-extras-we",
    "conv-croissant-bring-yesno",
)


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return load_golden()


def _turns(cases):
    return [(c["id"], n, t) for c in cases for n, t in enumerate(c["turns"], start=1)]


def test_file_exists_and_lines_are_json_objects():
    """Covers: AC-1 (right). Every non-blank line is a JSON object with the contract keys."""
    assert GOLDEN_PATH.exists()
    lines = [ln for ln in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "golden file is empty"
    for ln in lines:
        obj = json.loads(ln)
        assert isinstance(obj, dict)
        assert {"id", "turns", "must_pass"} <= set(obj)


def test_total_turns_in_range(cases):
    """Covers: GOLD-1, AC-1 (boundary). Between 20 and 40 turns in total."""
    total = sum(len(c["turns"]) for c in cases)
    assert 20 <= total <= 40, f"{total} turns in total"


def test_ids_unique_and_non_empty(cases):
    """Covers: GOLD-1, AC-1 (wrong). Ids are non-empty strings and unique."""
    ids = [c["id"] for c in cases]
    assert all(isinstance(i, str) and i.strip() for i in ids)
    assert len(ids) == len(set(ids)), f"duplicate ids: {sorted({i for i in ids if ids.count(i) > 1})}"


def test_every_case_has_a_turn(cases):
    """Covers: AC-1 (boundary). Every case has at least one turn."""
    empty = [c["id"] for c in cases if not isinstance(c["turns"], list) or len(c["turns"]) < 1]
    assert not empty, f"cases with no turns: {empty}"


def test_questions_non_blank(cases):
    """Covers: GOLD-2, AC-1 (wrong). Every question is a non-blank string."""
    bad = [(i, n) for i, n, t in _turns(cases)
           if not isinstance(t.get("question"), str) or not t["question"].strip()]
    assert not bad, f"blank questions at (case, turn): {bad}"


def test_references_non_blank_and_start_with_required(cases):
    """Covers: GOLD-2, AC-1 (wrong). Every reference is non-blank and starts with 'Required:'."""
    bad = [(i, n) for i, n, t in _turns(cases)
           if not isinstance(t.get("reference"), str)
           or not t["reference"].strip()
           or not t["reference"].startswith("Required:")]
    assert not bad, f"references not starting with 'Required:' at (case, turn): {bad}"


def test_at_least_four_conversations(cases):
    """Covers: GOLD-3, AC-1 (boundary). At least 4 cases have two or more turns."""
    multi = [c["id"] for c in cases if len(c["turns"]) >= 2]
    assert len(multi) >= 4, f"only {len(multi)} multi-turn cases: {multi}"


def test_bug_cases_present_and_must_pass(cases):
    """Covers: GOLD-4, AC-1 (right/wrong). The five bug cases exist and have must_pass true."""
    by_id = {c["id"]: c for c in cases}
    missing = [i for i in BUG_IDS if i not in by_id]
    assert not missing, f"missing bug cases: {missing}"
    not_must = [i for i in BUG_IDS if by_id[i]["must_pass"] is not True]
    assert not not_must, f"bug cases without must_pass true: {not_must}"


def test_new_bug_case_shapes(cases):
    """Covers: GOLD-4, CONV-5, ANS-20 (right). croissant-extras-we has one turn; conv-croissant-bring-yesno has two."""
    by_id = {c["id"]: c for c in cases}
    assert len(by_id["croissant-extras-we"]["turns"]) == 1
    assert len(by_id["conv-croissant-bring-yesno"]["turns"]) == 2
    assert len(by_id["conv-croissant-pushback"]["turns"]) == 5


def test_must_pass_is_bool(cases):
    """Covers: GOLD-5, AC-1 (wrong). must_pass of every case is a real bool (not 0/1 or a string)."""
    bad = [c["id"] for c in cases if not isinstance(c["must_pass"], bool)]
    assert not bad, f"must_pass not a bool in: {bad}"


def test_calibration_references_exist_and_gate_has_both_verdicts():
    """Covers: AC-2 (boundary), unit. The six calibration cases build from golden references and expect both verdicts."""
    from food_answer_helpers import cal_cases

    cc = cal_cases()
    assert len(cc) == 6
    assert {c["expected"] for c in cc} == {True, False}
    assert all(c["reference"].startswith("Required:") for c in cc)
