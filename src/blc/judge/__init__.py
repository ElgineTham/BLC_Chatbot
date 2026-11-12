"""LLM judge that grades answers against a reference (spec 004)."""

from __future__ import annotations

from blc.judge.grader import JUDGE_MODEL, judge_answer
from blc.judge.verdict import JudgeError, Verdict

__all__ = ["JUDGE_MODEL", "JudgeError", "Verdict", "judge_answer"]
