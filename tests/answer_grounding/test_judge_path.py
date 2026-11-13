"""Spec 017 AC-3a: `judge_answer(..., path=...)` with a scripted fake model that records the prompt
(section 3.3, EC-14 to EC-17, NFR-6). Unit; no Ollama, no network."""

from __future__ import annotations

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from blc.judge import JUDGE_PATHS, Verdict, judge_answer

Q = "How many gallons of coffee for QQQ-100 guests?"
REF = "Required: REFERENCE-MARKER four gallons."
ANS = "ANSWER-MARKER about four gallons."
PATHS = ("TOOL", "DOCS", "BOTH")


class RecordingChat(BaseChatModel):
    """Fake chat model: returns a fixed reply and records every message list it receives."""

    reply: str = "PASS"
    calls: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def received_text(self) -> str:
        return "\n".join(f"{type(m).__name__}:{m.content}" for call in self.calls for m in call)


def prompt_for(*args, reply="PASS", **kwargs):
    llm = RecordingChat(reply=reply)
    judge_answer(*args, llm=llm, **kwargs)
    assert llm.calls, "the judge made no model call"
    return llm.received_text()


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def strip_final_punct(text: str) -> str:
    return text.rstrip(" .?!;:,")


# ---- the constant ----------------------------------------------------------------

def test_judge_paths_constant():
    """Covers: AC-3a (right). JUDGE_PATHS is exactly ("TOOL", "DOCS", "BOTH")."""
    assert JUDGE_PATHS == ("TOOL", "DOCS", "BOTH")


# ---- EC-14: path=None is today's behaviour -----------------------------------------

def test_omitted_path_and_none_send_identical_prompts():
    """Covers: AC-3a (right), EC-14. judge_answer(q, r, a, llm) and path=None send the same prompt, byte for byte."""
    assert prompt_for(Q, REF, ANS) == prompt_for(Q, REF, ANS, path=None)


def test_path_none_prompt_is_stable_across_calls():
    """Covers: AC-3a (boundary), EC-14. The path=None prompt is deterministic."""
    assert prompt_for(Q, REF, ANS, path=None) == prompt_for(Q, REF, ANS, path=None)


def test_path_none_returns_a_verdict_and_reaches_the_model():
    """Covers: AC-3a (right), EC-14. With path=None the question, reference and answer still reach the model and a Verdict comes back."""
    llm = RecordingChat(reply="PASS")
    verdict = judge_answer(Q, REF, ANS, llm=llm, path=None)
    text = llm.received_text()
    assert isinstance(verdict, Verdict) and verdict.passed is True
    assert Q in text and REF in text and ANS in text


# ---- EC-15: each path changes the prompt ----------------------------------------------

@pytest.mark.parametrize("path", PATHS)
def test_each_path_prompt_differs_from_path_none(path):
    """Covers: AC-3a (right), EC-15. The prompt for TOOL, DOCS and BOTH each differs from the path=None prompt."""
    assert prompt_for(Q, REF, ANS, path=path) != prompt_for(Q, REF, ANS, path=None)


def test_path_prompts_differ_from_each_other():
    """Covers: AC-3a (right), EC-15. The three path prompts are pairwise different."""
    prompts = {p: prompt_for(Q, REF, ANS, path=p) for p in PATHS}
    assert len(set(prompts.values())) == 3


RULES = {
    "TOOL": ('STRICT: the answer may say only what is in "Required:" and "May also:". Any other fact FAILS, even if it '
             "is true: a location, a rule, a reason, an explanation, another item or another amount. Asking the user a "
             "question or offering help is not a fact."),
    "DOCS": "Correct extra details and explanations PASS. Naming something only to rule it out PASSES.",
    "BOTH": ("The answer has a calculator part (amounts, counts, cambros, cups, supplies, recipe) and a documents part "
             '(locations, names, meanings, how-to). Calculator part, STRICT: it may say only what is in "Required:" and '
             '"May also:"; any other calculator fact FAILS, even if true. Documents part: correct extra details PASS.'),
}


def template(path, question, reference, answer):
    return (f"{RULES[path]}\n\nReply with PASS or FAIL first, then a short reason.\n\n"
            f"QUESTION:\n{question.strip()}\n\nREFERENCE:\n{reference.strip()}\n\nANSWER:\n{answer.strip()}")


def prompt_content(*args, **kwargs):
    llm = RecordingChat(reply="PASS")
    judge_answer(*args, llm=llm, **kwargs)
    return "\n".join(str(m.content) for m in llm.calls[0])


@pytest.mark.parametrize("path", PATHS)
def test_path_prompt_equals_the_template(path):
    """Covers: AC-3a (right), EC-15 (revision 2). With a path the prompt is exactly the section 4.4 template: that path's
    rule, the reply line, then the stripped question, reference and answer (compared with whitespace collapsed)."""
    got = prompt_content(Q, REF, ANS, path=path)
    assert norm(got) == norm(template(path, Q, REF, ANS))


@pytest.mark.parametrize("path", PATHS)
def test_path_prompt_uses_stripped_inputs(path):
    """Covers: AC-3a (boundary), EC-15. Padding around the inputs is stripped before they go into the template."""
    got = prompt_content("  " + Q + "\n", "\n" + REF + "  ", "\t" + ANS + "\n\n", path=path)
    assert norm(got) == norm(template(path, Q, REF, ANS))


@pytest.mark.parametrize("path", PATHS)
def test_path_prompt_has_no_spec_004_rules(path):
    """Covers: AC-3a (wrong), EC-15, NFR-6. None of spec 004's rule lines or examples are in a path prompt
    (and the path=None prompt does still contain them)."""
    marker = "hedging between values fails"
    assert marker not in norm(prompt_content(Q, REF, ANS, path=path))
    assert marker in norm(prompt_content(Q, REF, ANS))


@pytest.mark.parametrize("path", PATHS)
def test_inputs_reach_the_model_on_every_path(path):
    """Covers: AC-3a (right). The question, reference and answer appear in the prompt for each path."""
    text = prompt_for(Q, REF, ANS, path=path)
    assert Q in text and REF in text and ANS in text


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("reply, passed", [("PASS", True), ("FAIL: extra fact", False), ("fail", False), ("**PASS**", True)])
def test_verdict_follows_the_models_reply_on_every_path(path, reply, passed):
    """Covers: AC-3a (right/wrong). With a path, the reply is parsed as in spec 004: the verdict follows PASS or FAIL."""
    verdict = judge_answer(Q, REF, ANS, llm=RecordingChat(reply=reply), path=path)
    assert verdict.passed is passed
    assert isinstance(verdict.reason, str)


@pytest.mark.parametrize("path", PATHS)
def test_unreadable_reply_raises_on_every_path(path):
    """Covers: AC-3a (wrong). Spec 004's errors still apply with a path: a reply that does not start with PASS or FAIL raises."""
    from blc.judge import JudgeError

    with pytest.raises(JudgeError):
        judge_answer(Q, REF, ANS, llm=RecordingChat(reply="Maybe"), path=path)


# ---- EC-16: invalid paths and blank inputs ---------------------------------------------

@pytest.mark.parametrize("bad", ["tool", "docs", "Both", "X", "", " ", "TOOL ", "ALL", "tool,docs"])
def test_invalid_path_raises_value_error_without_model_call(bad):
    """Covers: AC-3a (wrong), EC-16. A path not in JUDGE_PATHS (wrong case, unknown, empty) raises ValueError before any model call."""
    llm = RecordingChat(reply="PASS")
    with pytest.raises(ValueError):
        judge_answer(Q, REF, ANS, llm=llm, path=bad)
    assert llm.calls == []


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("blank", ["", " ", "\n", "\t \n"])
def test_blank_answer_with_valid_path_fails_without_model_call(path, blank):
    """Covers: AC-3a (wrong/boundary), EC-16. A blank answer with a valid path gives passed=False and makes no model call."""
    llm = RecordingChat(reply="PASS")
    verdict = judge_answer(Q, REF, blank, llm=llm, path=path)
    assert verdict.passed is False
    assert llm.calls == []


@pytest.mark.parametrize("path", PATHS)
def test_blank_question_or_reference_still_raises_with_a_path(path):
    """Covers: AC-3a (wrong), EC-16. Spec 004's errors still apply: a blank question or reference raises ValueError."""
    llm = RecordingChat(reply="PASS")
    with pytest.raises(ValueError):
        judge_answer(" ", REF, ANS, llm=llm, path=path)
    with pytest.raises(ValueError):
        judge_answer(Q, "", ANS, llm=llm, path=path)
    assert llm.calls == []


def test_blank_answer_with_path_does_not_need_ollama():
    """Covers: AC-3a (boundary), EC-16, NFR-2. Blank answer + path with llm=None returns passed=False without any model."""
    assert judge_answer(Q, REF, "", path="TOOL").passed is False


def test_invalid_path_with_llm_none_raises_before_building_a_model():
    """Covers: AC-3a (wrong), EC-16, NFR-2. A bad path raises ValueError even with llm=None (no Ollama needed)."""
    with pytest.raises(ValueError):
        judge_answer(Q, REF, ANS, path="nope")


# ---- EC-17 / NFR-6: no calibration answer or eval question in the prompt -------------

@pytest.mark.parametrize("path", PATHS)
def test_prompt_contains_no_long_j_answer(path, j_cases):
    """Covers: AC-3a (wrong), EC-17, NFR-6. No J1-J10 answer of 6 or more words appears in the path's prompt (casefolded, whitespace collapsed, final punctuation dropped)."""
    prompt = norm(prompt_for("Q?", "Required: x.", "y.", path=path))
    checked, leaked = 0, []
    for c in j_cases:
        if len(c["answer"].split()) < 6:
            continue
        checked += 1
        if norm(c["answer"]) in prompt or norm(strip_final_punct(c["answer"])) in prompt:
            leaked.append(c["id"])
    assert checked >= 5
    assert not leaked, f"J answers found in the {path} prompt: {leaked}"


@pytest.mark.parametrize("path", PATHS)
def test_prompt_contains_no_eval_question(path, cases, j_cases):
    """Covers: AC-3a (wrong), EC-17, NFR-6. No A, D or M question (and no J question) appears in the path's prompt."""
    prompt = norm(prompt_for("Q?", "Required: x.", "y.", path=path))
    leaked = [c["id"] for c in list(cases) + list(j_cases) if norm(strip_final_punct(c["question"])) in prompt]
    assert not leaked, f"Questions found in the {path} prompt: {leaked}"


def test_leak_check_would_detect_an_embedded_answer(j_cases):
    """Covers: AC-3a (boundary), EC-17. Sanity: the normalisation used above detects a J answer if it were embedded (guards against a vacuous check)."""
    j10 = next(c for c in j_cases if c["id"] == "J10")
    embedded = norm("prefix   " + j10["answer"].upper() + "\n suffix")
    assert norm(j10["answer"]) in embedded


def test_case_data_has_10_calibration_cases(j_cases):
    """Covers: AC-3b (boundary). The calibration data holds J1 to J10 exactly, with TOOL, DOCS and BOTH all represented."""
    assert [c["id"] for c in j_cases] == [f"J{i}" for i in range(1, 11)]
    assert {c["path"] for c in j_cases} == set(PATHS)
