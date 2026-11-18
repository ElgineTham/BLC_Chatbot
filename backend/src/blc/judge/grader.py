"""Grade a chatbot answer against a reference answer with an LLM."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from blc.judge.prompt import JUDGE_PATHS, build_prompt
from blc.judge.verdict import Verdict, parse_verdict, reply_text

JUDGE_MODEL = "qwen2.5:7b"
EMPTY_ANSWER_REASON = "The answer is empty."


def _default_llm() -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(model=JUDGE_MODEL, temperature=0)


def judge_answer(
    question: str,
    reference: str,
    answer: str,
    llm: BaseChatModel | None = None,
    path: str | None = None,
) -> Verdict:
    """Grade `answer` to `question` against `reference`.

    `path` (TOOL, DOCS or BOTH) tells the judge which answer path it grades
    (spec 017). Raises ValueError for a blank question or reference or a path
    not in JUDGE_PATHS, JudgeError for an unreadable reply. A blank answer fails without calling the model.
    """
    if path is not None and path not in JUDGE_PATHS:
        raise ValueError(f"path must be one of {JUDGE_PATHS}, got {path!r}")
    if not question.strip():
        raise ValueError("question must not be empty")
    if not reference.strip():
        raise ValueError("reference must not be empty")
    if not answer.strip():
        return Verdict(False, EMPTY_ANSWER_REASON)
    model = llm if llm is not None else _default_llm()
    reply = model.invoke(build_prompt(question, reference, answer, path))
    return parse_verdict(reply_text(reply.content))
