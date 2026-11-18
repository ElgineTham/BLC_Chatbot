"""Spec 022 §4.4 helpers for the golden eval: the 'filled drinks' log line, the report additions and the
Conversation C1. New file (NFR-6): conftest.py is not grown. Pure formatting plus a runner that is given the
function that runs one turn; no model is imported here.

Importable by the test files of this directory as `golden_fill_helpers` (no __init__.py, pytest puts the
directory on sys.path).
"""
from __future__ import annotations

import re

BEV = "calculate_bev_item"
C1_QUESTIONS = (
    "How many cups to bring for decaf, 40 guests",
    "How many cups to bring for 2 gallons of decaf",
    "50",
)
C1_EXPECTED_LINES = {1: {"hot-cups": 60}, 3: {"hot-cups": 70}}


def filled_text(outcome) -> str:
    """'filled drinks: <drinks> from <source> (call <index>)' or 'filled drinks: none'."""
    f = getattr(outcome, "filled", None)
    if f is None:
        return "filled drinks: none"
    return f"filled drinks: {', '.join(f.drinks)} from {f.source} (call {f.call_index})"


def add_filled_line(section, outcome):
    """The case section with the filled line placed right after the '- final plan:' line of its Plan sub-section.
    A section with no such line (an error section) is returned unchanged."""
    out, done = [], False
    for line in section:
        out.append(line)
        if not done and line.startswith("- final plan:"):
            out.append(f"- {filled_text(outcome)}")
            done = True
    return out


def with_fill_info(result):
    """A copy of a run_case result with the filled line in its section and 'filled=yes|no' on its report line."""
    r = dict(result)
    o = r.get("outcome")
    if o is None:
        return r
    r["section"] = add_filled_line(r["section"], o)
    r["line"] = f"{r['line']} filled={'yes' if o.filled is not None else 'no'}"
    return r


def filled_total(results) -> int:
    return sum(1 for r in results if r.get("outcome") is not None and r["outcome"].filled is not None)


def _lines_of(res):
    return {l.supply: _as_number(l.quantity) for l in res.lines}


def _as_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def run_c1(run_turn, tool_result):
    """Run the three C1 turns in order, each with the previous outcome.history and the fill on.

    run_turn(question, history) -> TurnOutcome. tool_result(name, args) -> the real tool's result.
    Returns a list of dicts: turn, question, runs, all_decaf, filled, reply, tool_checks, error."""
    history, turns = None, []
    for i, q in enumerate(C1_QUESTIONS, 1):
        t = {"turn": i, "question": q, "runs": [], "all_decaf": False, "filled": "none", "reply": "",
             "tool_checks": [], "error": None}
        try:
            o = run_turn(q, history)
            history = o.history
            t["runs"] = [{"name": x.name, "args": x.args} for x in o.tools]
            bev = [x for x in o.tools if x.name == BEV]
            t["all_decaf"] = all(
                [str(d).strip().casefold() for d in _drinks(x.args)] == ["decaf"] for x in bev) if bev else False
            t["filled"] = filled_text(o).split(": ", 1)[1]
            t["reply"] = o.reply
            for x in bev:
                if x.args.get("item") == "cups" and i in C1_EXPECTED_LINES:
                    got = _lines_of(tool_result(x.name, x.args))
                    t["tool_checks"].append({"args": x.args, "lines": got,
                                             "ok": got == {k: float(v) for k, v in C1_EXPECTED_LINES[i].items()}})
        except Exception as exc:  # recorded; the run goes on
            t["error"] = " ".join(f"{type(exc).__name__}: {exc}".split())
        turns.append(t)
    return turns


def _drinks(args):
    d = args.get("drinks")
    if d is None:
        return []
    return [d] if isinstance(d, str) else list(d)


def c1_section(turns):
    out = ["## C1", ""]
    for t in turns:
        out += [f"### Turn {t['turn']}", f"- question: {t['question']}"]
        if t["error"]:
            out += [f"- Error: {t['error']}", ""]
            continue
        out += [f"- run calls: {t['runs']}", f"- every calculate_bev_item call names Decaf: "
                f"{'yes' if t['all_decaf'] else 'no'}", f"- filled drinks: {t['filled']}", f"- reply: {t['reply']}"]
        for c in t["tool_checks"]:
            out.append(f"- cups call {c['args']} result lines {c['lines']}: {'pass' if c['ok'] else 'fail'}")
        out.append("")
    return out


def c1_report_lines(turns):
    lines = []
    for t in turns:
        if t["error"]:
            lines.append(f"C1 turn {t['turn']}: error ({t['error']})")
            continue
        checks = ", ".join("pass" if c["ok"] else "fail" for c in t["tool_checks"]) or "n/a"
        lines.append(f"C1 turn {t['turn']}: all-decaf={'yes' if t['all_decaf'] else 'no'} "
                     f"filled={t['filled']} tool-lines={checks}")
    return lines


def c1_pseudo_result(turns):
    """A result-shaped entry so golden_log.write_log writes the C1 section after the 30 cases."""
    return {"case": {"id": "C1", "path": "C1"}, "outcome": None, "score": None, "error": None, "stats": None,
            "section": c1_section(turns), "line": ""}


WHOLE_INT = re.compile(r"\d+")
