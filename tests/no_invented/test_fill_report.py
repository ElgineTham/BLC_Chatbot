"""Spec 022, AC-7 (report and log) without a model: the filled line, the report additions and Conversation C1.

Unit tests of golden_fill_helpers (tests/no_invented/golden_fill_helpers.py) with hand-made outcomes and the
golden_log fixture of conftest. C1's turn runner and the tool are faked.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import golden_fill_helpers as fh
from blc.flow import FilledDrinks


def outcome(filled=None, tools=(), history=None, reply="R"):
    t = tuple(SimpleNamespace(name=n, args=a, status="ok", text="") for n, a in tools)
    return SimpleNamespace(filled=filled, tools=t, history=history or [], reply=reply, plan=SimpleNamespace(route="TOOL"))


def test_filled_line_with_drinks():
    """Covers: AC-7 (right). 'filled drinks: <drinks> from <source> (call <index>)'."""
    o = outcome(FilledDrinks(1, ("Orange juice", "Decaf"), "history"))
    assert fh.filled_text(o) == "filled drinks: Orange juice, Decaf from history (call 1)"


def test_filled_line_none():
    """Covers: AC-7 (wrong). Nothing filled -> 'filled drinks: none'."""
    assert fh.filled_text(outcome()) == "filled drinks: none"


def test_filled_line_goes_after_the_final_plan():
    """Covers: AC-7 (right). The line sits in the Plan sub-section, directly after the final plan."""
    sec = ["## G1", "### Plan", "- first plan: x", "- final plan: y", "", "### Part 1, gold call"]
    out = fh.add_filled_line(sec, outcome(FilledDrinks(0, ("Decaf",), "question")))
    assert out.index("- filled drinks: Decaf from question (call 0)") == out.index("- final plan: y") + 1
    assert len(out) == len(sec) + 1


def test_error_section_is_left_alone():
    """Covers: AC-7 (boundary). A section with no Plan (an error section) gets no filled line."""
    sec = ["## G1", "- Error: boom", ""]
    assert fh.add_filled_line(sec, outcome()) == sec


def test_report_line_and_total_count_filled_cases():
    """Covers: AC-7 (right). Each report line says filled=yes/no and the total counts filled cases."""
    a = {"outcome": outcome(FilledDrinks(0, ("Decaf",), "question")), "section": ["- final plan: x"], "line": "G1: pass"}
    b = {"outcome": outcome(), "section": ["- final plan: x"], "line": "G2: pass"}
    c = {"outcome": None, "section": [], "line": "G3: fail (error: x)"}
    rs = [fh.with_fill_info(r) for r in (a, b, c)]
    assert rs[0]["line"].endswith("filled=yes") and rs[1]["line"].endswith("filled=no")
    assert rs[2]["line"] == "G3: fail (error: x)"
    assert fh.filled_total(rs) == 1


def _c1_runner(fills):
    state = {"n": 0}

    def run_turn(question, history):
        i = state["n"]
        state["n"] += 1
        drinks = fills[i]
        args = {"item": "cups", "guests": (40, None, 50)[i], "drinks": drinks}
        args = {k: v for k, v in args.items() if v is not None}
        f = FilledDrinks(0, tuple(drinks), "question") if i != 1 else None
        return outcome(f, tools=[("calculate_bev_item", args)], history=(history or []) + [
            {"role": "user", "content": question}, {"role": "assistant", "content": f"reply {i + 1}"}], reply=f"reply {i + 1}")

    return run_turn, state


def _tool(name, args):
    guests = args.get("guests")
    lines = [SimpleNamespace(supply="hot-cups", quantity={40: 60, 50: 70}.get(guests, 0))] if guests else []
    return SimpleNamespace(status="ok", lines=lines)


def test_c1_runs_three_turns_chaining_history():
    """Covers: AC-7 (right), C1. Three turns in order; each gets the previous turn's history."""
    seen = []
    run_turn, _ = _c1_runner([["Decaf"], ["Decaf"], ["decaf "]])

    def spy(q, h):
        seen.append((q, list(h or [])))
        return run_turn(q, h)

    turns = fh.run_c1(spy, _tool)
    assert [q for q, _ in seen] == list(fh.C1_QUESTIONS)
    assert seen[0][1] == [] and len(seen[1][1]) == 2 and len(seen[2][1]) == 4
    assert [t["all_decaf"] for t in turns] == [True, True, True]
    assert turns[0]["tool_checks"][0]["ok"] is True      # hot-cups 60 for 40 guests
    assert turns[2]["tool_checks"][0]["ok"] is True      # hot-cups 70 for 50 guests


def test_c1_flags_a_turn_that_lost_decaf():
    """Covers: AC-7 (wrong), C1. A run call naming another drink is reported as not all Decaf."""
    run_turn, _ = _c1_runner([["Decaf"], ["Coffee"], ["Decaf"]])
    turns = fh.run_c1(run_turn, _tool)
    assert [t["all_decaf"] for t in turns] == [True, False, True]


def test_c1_records_a_failing_turn_and_goes_on():
    """Covers: AC-7 (boundary), C1. A turn that raises is recorded with its error; later turns still run."""
    calls = []

    def run_turn(q, h):
        calls.append(q)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return outcome(history=[])

    turns = fh.run_c1(run_turn, _tool)
    assert len(calls) == 3
    assert "RuntimeError" in turns[0]["error"] and turns[1]["error"] is None


def test_c1_section_and_report_lines():
    """Covers: AC-7 (right), C1. A '## C1' section with three '### Turn n' sub-sections and one report line per turn."""
    run_turn, _ = _c1_runner([["Decaf"], ["Decaf"], ["Decaf"]])
    turns = fh.run_c1(run_turn, _tool)
    text = "\n".join(fh.c1_section(turns))
    assert text.startswith("## C1")
    assert re.findall(r"^### Turn (\d)$", text, flags=re.M) == ["1", "2", "3"]
    lines = fh.c1_report_lines(turns)
    assert len(lines) == 3 and all(l.startswith(f"C1 turn {i}") for i, l in enumerate(lines, 1))


def test_log_writer_places_c1_after_the_cases(golden_log, tmp_path):
    """Covers: AC-7 (right). write_log with the C1 pseudo-result writes '## C1' after the case sections and before Totals."""
    run_turn, _ = _c1_runner([["Decaf"], ["Decaf"], ["Decaf"]])
    turns = fh.run_c1(run_turn, _tool)
    cases = [{"case": {"id": "G1", "path": "TOOL"}, "section": ["## G1", "### Plan", ""], "line": "G1: pass", "stats": None}]
    path = golden_log.write_log(cases + [fh.c1_pseudo_result(turns)], "REPORT", tmp_path / "logs")
    text = path.read_text(encoding="utf-8")
    assert text.index("## G1") < text.index("## C1") < text.index("## Totals")
