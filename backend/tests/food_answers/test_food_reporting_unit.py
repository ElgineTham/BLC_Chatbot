"""RATE-3, RATE-4, AC-2, AC-6 reporting helpers. Unit; no Ollama."""

from __future__ import annotations

from food_answer_helpers import TurnResult, cal_cases, describe, failed_calibration_ids


class _V:
    def __init__(self, passed):
        self.passed = passed


def test_failure_message_lists_all_fields():
    """Covers: RATE-3, AC-6 (right). The failure text has case id, turn, question, reply and judge reason."""
    text = describe([TurnResult("c-1", 3, "Q here?", "A reply", False, "because", True)])
    for piece in ("c-1", "3", "Q here?", "A reply", "because"):
        assert piece in text


def test_failure_message_lists_every_failing_turn():
    """Covers: RATE-3, AC-6 (boundary). Two failing turns both appear."""
    text = describe([
        TurnResult("a", 1, "Qa", "Ra", False, "ra", False),
        TurnResult("b", 2, "Qb", "Rb", False, "rb", True),
    ])
    assert "Qa" in text and "Qb" in text and "rb" in text


def test_gate_names_failed_calibration_ids():
    """Covers: RATE-4, AC-2 (wrong). A wrong verdict or a raised error is reported by calibration id."""
    results = {c["id"]: _V(c["expected"]) for c in cal_cases()}
    assert failed_calibration_ids(results) == []
    results["CAL-2"] = _V(True)
    results["CAL-5"] = RuntimeError("judge down")
    assert failed_calibration_ids(results) == ["CAL-2", "CAL-5"]
