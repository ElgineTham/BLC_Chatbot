"""Spec 020, AC-3 (mixed-question eval): X1 to X5 (plus spec 018's T5 in the log) through
run_planned_turn (which runs spec 018's plan_question), with the real models and data.

Marked eval. Skips (does not fail) when Ollama is not running or the Chroma store is missing or empty.
Report only, no threshold: one line per case and the count passed out of 5 are printed, and the log
logs/mixed_answers_<YYYY-MM-DD_HHMMSS>.md (spec 019 section 4.5's format) is written for the user to read.
The test passes when the log is complete: 6 sections (X1 to X5 and T5). Writes only under logs/.
"""
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from blc.flow import run_planned_turn

pytestmark = pytest.mark.eval

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
FIELDS = ("Question:", "History:", "Route:", "Planned calls:", "Searches:", "Tool results:",
          "Reply:", "Answered by model:", "Time to first piece:", "Total time:")
SECTION_IDS = ["X1", "X2", "X3", "X4", "X5", "T5"]


def _run_case(llm, store, case):
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


def _section(r, failed):
    case, o = r["case"], r["outcome"]
    lines = [f"## {case['id']}", "", f"- Question: {case['question']}", "- History: none"]
    if r["error"]:
        lines += [f"- Error: {r['error']}", f"- Total time: {_fmt_secs(r['total'])}", ""]
        return lines
    lines.append(f"- Route: {o.plan.route}")
    lines.append("- Planned calls:")
    lines += [f"  - {c.name} {c.args}" for c in o.plan.calls]
    if failed is not None:
        lines.append(f"- Planned calls check: {'pass' if not failed else 'fail (' + ', '.join(failed) + ')'}")
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


def _write_log(results, verdicts):
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"mixed_answers_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Mixed questions", ""]
    for r in results:
        lines += _section(r, verdicts.get(r["case"]["id"]))
    ok = [r for r in results if r["outcome"] is not None]
    firsts = [r["first"] for r in ok if r["first"] is not None]
    totals = [r["total"] for r in ok]
    avg = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    answered = sum(1 for r in ok if r["outcome"].answered_by_model)
    passed = sum(1 for v in verdicts.values() if v == [])
    lines += ["## Summary", "",
              f"- Average time to first piece: {_fmt_secs(avg(firsts))}",
              f"- Average total time: {_fmt_secs(avg(totals))}",
              f"- Cases answered by the model: {answered} of {len(results)}",
              f"- Planned calls passed: {passed} of 5", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def mixed_run(real_llm, real_store, mixed_cases, t5_case, score_case):
    results = [_run_case(real_llm, real_store, c) for c in mixed_cases + [t5_case]]
    verdicts = {}
    for r in results:
        case = r["case"]
        if case["expected"] is None:
            continue
        verdicts[case["id"]] = (["error"] if r["outcome"] is None
                                else score_case(r["outcome"].plan, case["expected"]))
    for r in results:
        cid = r["case"]["id"]
        if cid in verdicts:
            failed = verdicts[cid]
            calls = [] if r["outcome"] is None else [f"{c.name} {c.args}" for c in r["outcome"].plan.calls]
            print(f"{cid}: {'pass' if not failed else 'fail'} failed={','.join(failed) or '-'} "
                  f"calls={calls}")
    passed = sum(1 for v in verdicts.values() if v == [])
    print(f"Mixed questions passed: {passed} of 5")
    path = _write_log(results, verdicts)
    print(f"Mixed answers log: {path}")
    return {"results": results, "verdicts": verdicts, "path": path,
            "text": path.read_text(encoding="utf-8")}


def test_log_written_under_logs_with_a_timestamped_name(mixed_run):
    """Covers: AC-3 (right), NFR-3. The log is logs/mixed_answers_<YYYY-MM-DD_HHMMSS>.md."""
    path = mixed_run["path"]
    assert path.exists()
    assert path.parent == LOG_DIR
    assert re.fullmatch(r"mixed_answers_\d{4}-\d{2}-\d{2}_\d{6}\.md", path.name)


def test_log_has_six_sections_in_order(mixed_run, mixed_cases, t5_case):
    """Covers: AC-3 (right). Sections X1 to X5 then T5, each with its question and the fields of 019 section 4.5
    (or an Error line when the case raised)."""
    text = mixed_run["text"]
    headings = re.findall(r"^## ((?:X|T)\d+)$", text, flags=re.M)
    assert headings == SECTION_IDS
    parts = re.split(r"^## (?:X|T)\d+$", text, flags=re.M)[1:]
    assert len(parts) == 6
    for case, part in zip(mixed_cases + [t5_case], parts):
        assert case["question"] in part
        if "- Error:" in part:
            continue
        for field in FIELDS:
            assert field in part, (case["id"], field)


def test_log_ends_with_averages_and_answered_count(mixed_run):
    """Covers: AC-3 (right). The summary has both averages and the number answered by the model."""
    tail = mixed_run["text"].split("## Summary")[-1]
    assert "Average time to first piece" in tail
    assert "Average total time" in tail
    assert re.search(r"answered by the model: \d+ of 6", tail)


def test_every_case_ran_or_recorded_its_error(mixed_run):
    """Covers: AC-3 (boundary). All 6 cases ended with an outcome or a recorded error; the 5 scored cases
    have a verdict (no threshold on it)."""
    results = mixed_run["results"]
    assert [r["case"]["id"] for r in results] == SECTION_IDS
    assert all((r["outcome"] is None) != (r["error"] is None) for r in results)
    assert sorted(mixed_run["verdicts"]) == ["X1", "X2", "X3", "X4", "X5"]
