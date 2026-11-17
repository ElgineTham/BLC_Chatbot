"""Shared fixtures for the food answer-quality eval (spec 027).

Read only: nothing is written to .chroma/, data/ or evals/. Eval fixtures skip (never fail)
when Ollama, a model or the ingested food.md is missing (AC-7). The judge gate (AC-2) makes the
graded fixture fail, naming the failed calibration ids, instead of grading.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import food_answer_helpers as fah  # noqa: E402


def pytest_generate_tests(metafunc):
    if "cal_case" in metafunc.fixturenames:
        cases = fah.cal_cases()
        metafunc.parametrize("cal_case", cases, ids=[c["id"] for c in cases])
    if "case_id" in metafunc.fixturenames:
        ids = fah.golden_ids()
        metafunc.parametrize("case_id", ids, ids=ids)


@pytest.fixture(scope="session")
def ollama_models():
    models = fah.installed_models()
    if models is None:
        pytest.skip("Ollama is not running; start it to run the food answer eval.")
    return models


@pytest.fixture(scope="session")
def models_ready(ollama_models):
    from blc.judge import JUDGE_MODEL
    from chat import CHAT_MODEL

    for wanted in (CHAT_MODEL, JUDGE_MODEL):
        if not fah.has_model(ollama_models, wanted):
            pytest.skip(f"Ollama model {wanted!r} is not available; run: ollama pull {wanted}")
    return True


@pytest.fixture(scope="session")
def store(models_ready):
    """The real store (read only); skips if food.md has not been ingested."""
    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run scripts/ingest.py first.")
    chroma = build_store()
    data = chroma.get(include=["metadatas"])
    sources = {(m or {}).get("source", "") for m in (data.get("metadatas") or [])}
    if not any(s.endswith(fah.FOOD_SOURCE) for s in sources):
        pytest.skip(
            f"No documents with source {fah.FOOD_SOURCE} in the store: run scripts/ingest.py first."
        )
    return chroma


@pytest.fixture(scope="session")
def chat_llm(models_ready):
    from chat import CHAT_MODEL, CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    return ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE)


@pytest.fixture(scope="session")
def calibration_results(models_ready):
    """Map calibration id -> Verdict, or the exception raised while judging."""
    from blc.judge import judge_answer

    results = {}
    for case in fah.cal_cases():
        try:
            results[case["id"]] = judge_answer(case["question"], case["reference"], case["answer"])
        except Exception as exc:  # reported by the tests
            results[case["id"]] = exc
    return results


@pytest.fixture(scope="session")
def graded(calibration_results, store, chat_llm) -> dict[str, list]:
    """Run every golden case through the real flow and judge each turn.

    Fails (naming the failed calibration ids) instead of grading when the judge gate fails.
    Each case starts with an empty history; turn n uses the history returned by turn n-1.
    """
    failed = fah.failed_calibration_ids(calibration_results)
    if failed:
        pytest.fail(
            "Judge failed calibration, answers not graded. Failed calibration ids: "
            + ", ".join(failed),
            pytrace=False,
        )
    from blc.flow import run_planned_turn
    from blc.judge import judge_answer

    out: dict[str, list] = {}
    for case in fah.load_golden():
        history: list[dict[str, str]] = []
        rows: list = []
        for n, turn in enumerate(case["turns"], start=1):
            outcome = run_planned_turn(chat_llm, store, turn["question"], history)
            history = outcome.history
            verdict = judge_answer(turn["question"], turn["reference"], outcome.reply)
            rows.append(
                fah.TurnResult(
                    case_id=case["id"],
                    turn=n,
                    question=turn["question"],
                    reply=outcome.reply,
                    passed=bool(verdict.passed),
                    reason=verdict.reason,
                    must_pass=bool(case["must_pass"]),
                )
            )
        out[case["id"]] = rows
    return out
