"""Spec 019, AC-5 (eval log): run spec 018's 30 cases end to end and write a markdown log.

Marked eval. Skips (does not fail) when Ollama is not running or the Chroma store is missing or empty.
The real model is warmed up once. Answer quality is not checked: the test passes when the log was
written with all 30 sections. The log goes to logs/flow_answers_<YYYY-MM-DD_HHMMSS>.md (only under logs/).
"""
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from blc.flow import run_planned_turn

pytestmark = pytest.mark.eval

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
FIELDS = ("Question:", "History:", "Route:", "Planned calls:", "Searches:", "Tool results:",
          "Reply:", "Answered by model:", "Time to first piece:", "Total time:")


def _run_case(llm, store, case):
    """One run_planned_turn call; returns a dict with the outcome or the error, plus timings."""
    first = []
    start = time.perf_counter()

    def on_token(piece):
        if not first:
            first.append(time.perf_counter() - start)

    try:
        outcome = run_planned_turn(llm, store, case["question"], case["history"], on_token=on_token)
        error = None
    except Exception as exc:  # a failing case is recorded; the run goes on
        outcome, error = None, f"{type(exc).__name__}: {exc}"
    return {"case": case, "outcome": outcome, "error": error,
            "first": first[0] if first else None, "total": time.perf_counter() - start}


def _fmt_secs(v):
    return "n/a" if v is None else f"{v:.2f}s"


def _section(r):
    case, o = r["case"], r["outcome"]
    lines = [f"## {case['id']}", "", f"- Question: {case['question']}"]
    if case["history"]:
        lines.append("- History:")
        lines += [f"  - {h['role']}: {h['content']}" for h in case["history"]]
    else:
        lines.append("- History: none")
    if r["error"]:
        lines += [f"- Error: {r['error']}", f"- Total time: {_fmt_secs(r['total'])}", ""]
        return lines
    lines.append(f"- Route: {o.plan.route}")
    lines.append("- Planned calls:")
    lines += [f"  - {c.name} {c.args}" for c in o.plan.calls]
    lines.append("- Searches:")
    for s in o.searches:
        sources = ", ".join(d.metadata.get("source", "") for d in s.chunks) or "(none)"
        lines.append(f"  - {s.query!r} -> {sources}")
    lines.append("- Tool results:")
    lines += [f"  - {t.name} {t.args} status={t.status}: {t.text}" for t in o.tools]
    lines += ["- Reply:", "", o.reply, "",
              f"- Answered by model: {o.answered_by_model}",
              f"- Time to first piece: {_fmt_secs(r['first'])}",
              f"- Total time: {_fmt_secs(r['total'])}", ""]
    return lines


def _write_log(results):
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"flow_answers_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Planned flow answers", ""]
    for r in results:
        lines += _section(r)
    ok = [r for r in results if r["outcome"] is not None]
    firsts = [r["first"] for r in ok if r["first"] is not None]
    totals = [r["total"] for r in ok]
    avg = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    answered = sum(1 for r in ok if r["outcome"].answered_by_model)
    lines += ["## Summary", "",
              f"- Average time to first piece: {_fmt_secs(avg(firsts))}",
              f"- Average total time: {_fmt_secs(avg(totals))}",
              f"- Cases answered by the model: {answered} of {len(results)}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def eval_run(real_llm, real_store, eval_cases):
    results = [_run_case(real_llm, real_store, c) for c in eval_cases]
    path = _write_log(results)
    print(f"\nFlow answers log: {path}")
    return {"results": results, "path": path, "text": path.read_text(encoding="utf-8")}


def test_log_written_under_logs_with_a_timestamped_name(eval_run):
    """Covers: AC-5 (right), EC-16, NFR-3. The log exists at logs/flow_answers_<YYYY-MM-DD_HHMMSS>.md."""
    path = eval_run["path"]
    assert path.exists()
    assert path.parent == LOG_DIR
    assert re.fullmatch(r"flow_answers_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_has_30_case_sections_with_all_fields(eval_run, eval_cases):
    """Covers: AC-5 (right), EC-16. One section per case id, each with the fields of 4.5
    (or an Error line when the case raised)."""
    text = eval_run["text"]
    headings = re.findall(r"^## ((?:T|D|M)\d+)$", text, flags=re.M)
    assert headings == [c["id"] for c in eval_cases]
    parts = re.split(r"^## (?:T|D|M)\d+$", text, flags=re.M)[1:]
    assert len(parts) == 30
    for case, part in zip(eval_cases, parts):
        assert case["question"] in part
        if "- Error:" in part:
            continue
        for field in FIELDS:
            assert field in part, (case["id"], field)


def test_log_ends_with_averages_and_answered_count(eval_run):
    """Covers: AC-5 (right), EC-16. The summary has both averages and the number answered by the model."""
    tail = eval_run["text"].split("## Summary")[-1]
    assert "Average time to first piece" in tail
    assert "Average total time" in tail
    assert re.search(r"answered by the model: \d+ of 30", tail)


def test_first_piece_comes_before_the_end_for_model_answers(eval_run):
    """Covers: AC-5 (boundary), NFR-5. For cases the model answered, time to first piece <= total time,
    and for at least one it is strictly less (the answer streams)."""
    answered = [r for r in eval_run["results"]
                if r["outcome"] is not None and r["outcome"].answered_by_model]
    if not answered:
        pytest.skip("No case was answered by the model.")
    assert all(r["first"] is not None and r["first"] <= r["total"] for r in answered)
    assert any(r["first"] < r["total"] for r in answered)


def test_every_case_ran_or_recorded_its_error(eval_run, eval_cases):
    """Covers: AC-5 (boundary), EC-16. All 30 cases ended with an outcome or a recorded error."""
    results = eval_run["results"]
    assert [r["case"]["id"] for r in results] == [c["id"] for c in eval_cases]
    assert all((r["outcome"] is None) != (r["error"] is None) for r in results)
