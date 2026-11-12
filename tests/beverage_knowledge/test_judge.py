"""AC-1: judge mechanics with a fake chat model (unit; no Ollama, no network)."""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from blc.judge import JudgeError, Verdict, judge_answer

Q = "How many gallons of coffee for QQQ-100 guests?"
REF = "REFERENCE-MARKER four gallons exactly."
ANS = "ANSWER-MARKER about four gallons."


class RecordingChat(BaseChatModel):
    """Fake chat model that returns a fixed reply and records what it received."""

    reply: str = "PASS"
    calls: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.reply))]
        )

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def received_text(self) -> str:
        return "\n".join(str(m.content) for call in self.calls for m in call)


def run(reply: str):
    llm = RecordingChat(reply=reply)
    return judge_answer(Q, REF, ANS, llm=llm), llm


# ---- reply table (EC-6) ---------------------------------------------------

@pytest.mark.parametrize(
    "reply",
    [
        "PASS",
        "pass\nMatches the reference.",
        "**PASS**",
        "Pass",
        "  PASS  ",
        "PASS.",
        "PASS: matches",
        "## PASS",
        "- pass",
        "**Pass**: all facts match",
    ],
)
def test_pass_replies_give_passed_true(reply):
    """Covers: AC-1 (right), EC-6 (right). PASS-first replies parse as passed=True."""
    verdict, _ = run(reply)
    assert isinstance(verdict, Verdict)
    assert verdict.passed is True


@pytest.mark.parametrize(
    "reply",
    [
        "FAIL: says two 5 gal cambros",
        "**FAIL** - wrong count",
        "fail",
        "FAIL",
        "FAIL\nWrong number.",
        "  fail.  ",
        "### Fail: missing fact",
    ],
)
def test_fail_replies_give_passed_false(reply):
    """Covers: AC-1 (right), EC-6 (right). FAIL-first replies parse as passed=False."""
    verdict, _ = run(reply)
    assert isinstance(verdict, Verdict)
    assert verdict.passed is False


@pytest.mark.parametrize(
    "reply",
    [
        "I think it passes",
        "",
        "PASSED",
        "   ",
        "\n\n",
        "The answer is PASS",
        "Maybe",
        "FAILED",
        "PASSING",
        "FAILURE: wrong",
    ],
)
def test_unreadable_replies_raise_judge_error(reply):
    """Covers: AC-1 (wrong), EC-6 (wrong/boundary). Replies whose first word is not exactly PASS/FAIL raise JudgeError."""
    with pytest.raises(JudgeError):
        run(reply)


def test_reason_is_a_string():
    """Covers: AC-1 (right). Verdict.reason is always a str (may be empty)."""
    for reply in ("PASS", "FAIL: because"):
        verdict, _ = run(reply)
        assert isinstance(verdict.reason, str)


def test_verdict_is_frozen():
    """Covers: AC-1 (wrong). Verdict is a frozen dataclass; assignment is rejected."""
    verdict, _ = run("PASS")
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.passed = False  # type: ignore[misc]


def test_judge_error_is_an_exception():
    """Covers: AC-1 (right). JudgeError is an Exception subclass."""
    assert issubclass(JudgeError, Exception)


# ---- inputs reach the model ----------------------------------------------

def test_question_reference_and_answer_reach_the_model():
    """Covers: AC-1 (right). Each of question, reference and answer appears in the text the model receives."""
    _, llm = run("PASS")
    assert len(llm.calls) >= 1
    text = llm.received_text()
    assert Q in text
    assert REF in text
    assert ANS in text


def test_model_is_called_for_nonblank_answer():
    """Covers: AC-1 (right). A normal answer causes the model to be consulted."""
    _, llm = run("PASS")
    assert llm.calls


# ---- no calibration answers or eval questions in the prompt (AC-6) --------

def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _strip_final_punct(text: str) -> str:
    return text.rstrip(" .?!;:,")


def _prompt_text() -> str:
    llm = RecordingChat(reply="PASS")
    judge_answer("Q?", "Required: x.", "y.", llm=llm)
    assert llm.calls
    return _norm(llm.received_text())


def test_prompt_contains_no_long_calibration_answer(all_calibration_cases):
    """Covers: AC-6 (wrong), NFR-8 (wrong). No calibration answer of 6+ words appears in the judge prompt."""
    prompt = _prompt_text()
    checked = 0
    leaked = []
    for case in all_calibration_cases:
        if len(case["answer"].split()) < 6:
            continue
        checked += 1
        ans = _norm(case["answer"])
        if ans in prompt or _norm(_strip_final_punct(case["answer"])) in prompt:
            leaked.append(case["id"])
    assert checked > 0
    assert not leaked, f"Calibration answers found in judge prompt: {leaked}"


def test_prompt_contains_no_eval_question(all_generation_cases):
    """Covers: AC-6 (wrong), NFR-8 (wrong). No A, S or X eval question appears in the judge prompt."""
    prompt = _prompt_text()
    leaked = [
        c["id"]
        for c in all_generation_cases
        if _norm(_strip_final_punct(c["question"])) in prompt
    ]
    assert not leaked, f"Eval questions found in judge prompt: {leaked}"


def test_prompt_check_detects_a_leak(all_calibration_cases):
    """Covers: AC-6 (boundary). Sanity: the normalisation used above would detect a calibration answer if it were embedded (guards against a vacuous check)."""
    case = next(c for c in all_calibration_cases if c["id"] == "C27")
    embedded = _norm("prefix   " + case["answer"].upper() + "\n suffix")
    assert _norm(case["answer"]) in embedded


def test_prompt_is_at_most_3000_characters():
    """Covers: AC-7 (right). The text the model receives for the minimal call (all messages joined) is at most 3,000 characters."""
    llm = RecordingChat(reply="PASS")
    judge_answer("Q?", "Required: x.", "y.", llm=llm)
    assert llm.calls
    joined = "\n".join(str(m.content) for call in llm.calls for m in call)
    assert len(joined) <= 3000, f"prompt is {len(joined)} characters"


def test_prompt_size_counts_every_call():
    """Covers: AC-7 (boundary). If the judge makes more than one model call, each call's text stays within the limit."""
    llm = RecordingChat(reply="PASS")
    judge_answer("Q?", "Required: x.", "y.", llm=llm)
    for call in llm.calls:
        assert len("\n".join(str(m.content) for m in call)) <= 3000


def test_prompt_is_not_empty_beyond_inputs():
    """Covers: AC-7 (boundary). The prompt holds real instructions, not just the inputs (guards against a vacuous size check)."""
    llm = RecordingChat(reply="PASS")
    judge_answer("Q?", "Required: x.", "y.", llm=llm)
    assert len(llm.received_text()) > 200


def test_judge_model_is_14b():
    """Covers: AC-8 (right). JUDGE_MODEL is qwen2.5:14b."""
    import blc.judge as judge_pkg

    assert judge_pkg.JUDGE_MODEL == "qwen2.5:14b"


def test_judge_model_differs_from_chat_model():
    """Covers: AC-8 (wrong). The judge is not the 7B chat model it grades."""
    import blc.judge as judge_pkg

    assert judge_pkg.JUDGE_MODEL != "qwen2.5:7b"


def test_calibration_case_data_has_35_cases(all_calibration_cases):
    """Covers: AC-2 (boundary), AC-6 (boundary). The case data holds C1 to C35 so AC-6 checks all of them."""
    assert [c["id"] for c in all_calibration_cases] == [f"C{i}" for i in range(1, 36)]


# ---- blank inputs (EC-5) --------------------------------------------------

@pytest.mark.parametrize("blank", ["", " ", "   ", "\n", "\t \n"])
def test_blank_answer_fails_without_calling_model(blank):
    """Covers: AC-1 (wrong), EC-5 (wrong/boundary). Empty or whitespace answer gives passed=False and never calls the model."""
    llm = RecordingChat(reply="PASS")
    verdict = judge_answer(Q, REF, blank, llm=llm)
    assert verdict.passed is False
    assert llm.calls == []


def test_blank_answer_without_llm_does_not_need_ollama():
    """Covers: EC-5 (boundary), NFR-2 (right). Blank answer with llm=None returns passed=False with no model/network use."""
    assert judge_answer(Q, REF, "").passed is False


@pytest.mark.parametrize("blank", ["", " ", "\n", "\t  "])
def test_blank_question_raises_value_error(blank):
    """Covers: AC-1 (wrong), EC-5 (wrong). Blank question raises ValueError."""
    llm = RecordingChat(reply="PASS")
    with pytest.raises(ValueError):
        judge_answer(blank, REF, ANS, llm=llm)
    assert llm.calls == []


@pytest.mark.parametrize("blank", ["", " ", "\n", "\t  "])
def test_blank_reference_raises_value_error(blank):
    """Covers: AC-1 (wrong), EC-5 (wrong). Blank reference raises ValueError."""
    llm = RecordingChat(reply="PASS")
    with pytest.raises(ValueError):
        judge_answer(Q, blank, ANS, llm=llm)
    assert llm.calls == []


def test_single_character_inputs_are_not_blank():
    """Covers: AC-1 (boundary). One-character question, reference and answer are valid and reach the model."""
    llm = RecordingChat(reply="PASS")
    verdict = judge_answer("q", "r", "a", llm=llm)
    assert verdict.passed is True
    assert llm.calls


def test_verdict_follows_reply_not_answer_text():
    """Covers: AC-1 (wrong). The verdict comes from the model's reply: the same inputs give opposite verdicts for PASS vs FAIL replies."""
    passed, _ = run("PASS")
    failed, _ = run("FAIL")
    assert passed.passed is True and failed.passed is False
