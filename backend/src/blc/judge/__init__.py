"""LLM judge that grades answers against a reference (spec 004)."""

from __future__ import annotations

from blc.judge.grader import JUDGE_MODEL, judge_answer
from blc.judge.grounding import ungrounded_numbers, unknown_sources
from blc.judge.prompt import JUDGE_PATHS
from blc.judge.verdict import JudgeError, Verdict

__all__ = [
    "JUDGE_MODEL",
    "JUDGE_PATHS",
    "JudgeError",
    "Verdict",
    "judge_answer",
    "ungrounded_numbers",
    "unknown_sources",
]
