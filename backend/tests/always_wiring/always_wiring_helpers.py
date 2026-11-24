"""Helpers for spec 045 (always items wiring): the 10 eval cases, the pure scorer (spec 4.6) and the eval log
writer and report (spec 4.7). Nothing here runs a model, reads data/ or needs the network.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime

from blc.tools.always_tools import run_always_tool

ALWAYS = "calculate_always_items"
FOOD = "calculate_food_item"
SEARCH = "search_documents"

AREAS = ("SCOPE", "ASK", "MIX")
AREA_SIZES = {"SCOPE": 4, "ASK": 3, "MIX": 3}
THRESHOLDS = {"SCOPE": 3, "ASK": 2, "MIX": 2}

H_ASK = [
    {"role": "user", "content": "What always items do I need?"},
    {"role": "assistant",
     "content": "Bus tubs: check\nTowels: check\nPlease tell me how many tables and drip trays there are?"},
]


def _res(status, counts, missing=()):
    return {"status": status, "counts": counts, "missing": tuple(missing)}


def _case(cid, area, question, tools, always=None, history=None, route="TOOL"):
    return {"id": cid, "area": area, "route": route, "question": question, "history": history,
            "tools": list(tools), "always": always}


_CASES = [
    _case("EVAL-1", "SCOPE", "How many black linens and purple napkins for 4 tables?", [ALWAYS],
          _res("ok", {"black linens": 9, "purple napkins": 8})),
    _case("EVAL-2", "SCOPE", "How many black napkins do I need for 3 drip trays?", [ALWAYS],
          _res("ok", {"black napkins": 3})),
    _case("EVAL-3", "SCOPE", "What always items do I pull for 5 tables and 2 drip trays?", [ALWAYS],
          _res("ok", {"black linens": 11, "black napkins": 2, "purple napkins": 10})),
    _case("EVAL-4", "SCOPE", "How many forks for 60 guests?", [FOOD]),
    _case("EVAL-5", "ASK", "How many purple napkins do I need?", [ALWAYS], _res("need_info", {}, ("tables",))),
    _case("EVAL-6", "ASK", "What are the always items?", [ALWAYS],
          _res("need_info", {}, ("tables", "drip trays"))),
    _case("EVAL-7", "ASK", "Always items for 4 tables?", [ALWAYS],
          _res("need_info", {"black linens": 9, "purple napkins": 8}, ("drip trays",))),
    _case("EVAL-8", "MIX", "6 tables and 2 drip trays", [ALWAYS],
          _res("ok", {"black linens": 13, "black napkins": 2, "purple napkins": 12}), history=H_ASK),
    _case("EVAL-9", "MIX", "We have 50 guests and 3 tables. How many purple napkins?", [ALWAYS],
          _res("ok", {"black linens": 7, "purple napkins": 6})),
    _case("EVAL-10", "MIX",
          "Special instructions: set up 2 6-ft tables by the bar, 1 drip tray. What goes in the Always box?",
          [ALWAYS], _res("ok", {"black linens": 5, "black napkins": 1, "purple napkins": 4})),
]

CASES = {c["id"]: c for c in _CASES}
CASE_IDS = [c["id"] for c in _CASES]


# --------------------------------------------------------------------------
# The scorer (spec 4.6): pure function of a case and the final Plan
# --------------------------------------------------------------------------

def _result_ok(expected, plan):
    calls = [c for c in plan.calls if c.name == ALWAYS]
    if not calls:
        return False
    result = run_always_tool(calls[0].args)
    if result.status != expected["status"] or result.counts != expected["counts"]:
        return False
    if expected["status"] == "need_info":
        text = result.text.casefold()
        return all(m.casefold() in text for m in expected["missing"])
    return True


def score_case(case, plan):
    """Set of failed checks: a subset of {"route", "tools", "result"}. Empty means pass."""
    failed = set()
    if plan.route != case["route"]:
        failed.add("route")
    names = Counter(c.name for c in plan.calls if c.name != SEARCH)
    if names != Counter(case["tools"]):
        failed.add("tools")
    if case["always"] is not None and not _result_ok(case["always"], plan):
        failed.add("result")
    return failed


# --------------------------------------------------------------------------
# The eval log (spec 4.7) and the report
# --------------------------------------------------------------------------

SUBSECTIONS = ("### Input", "### Planner", "### Tools", "### Retrieved", "### Answer", "### Verdict")
PREVIEW = 120


def _yn(flag):
    return "yes" if flag else "no"


def _plan_lines(label, plan):
    out = [f"- {label}: route {plan.route}"]
    for c in plan.calls:
        out.append(f"  - call: {c.name} {c.args}")
    return out


def _history_lines(history):
    if not history:
        return ["- history: none"]
    return ["- history:"] + [f"  - {h['role']}: {h['content']}" for h in history]


def _source(chunk):
    meta = getattr(chunk, "metadata", None) or {}
    return meta.get("source") or "unknown"


def _header(case):
    return [f"## {case['id']}", ""]


def section_lines(case, outcome, failed, first, total):
    out = _header(case)
    out += ["### Input", f"- id: {case['id']}", f"- area: {case['area']}", f"- question: {case['question']}"]
    out += _history_lines(case["history"]) + [""]
    out += ["### Planner"] + _plan_lines("first plan", outcome.first_plan)
    if outcome.rejected:
        out.append("- rejected:")
        out += [f"  - {r.name} {r.args} invented {r.invented}" for r in outcome.rejected]
    else:
        out.append("- rejected: none")
    out.append(f"- retried: {_yn(outcome.retried)}")
    out += _plan_lines("final plan", outcome.plan) + [""]
    out.append("### Tools")
    if not outcome.tools:
        out.append("none")
    for t in outcome.tools:
        out += [f"- name: {t.name}", f"  - arguments: {t.args}", f"  - status: {t.status}", f"  - text: {t.text}"]
    out += ["", "### Retrieved"]
    if not outcome.searches:
        out.append("none")
    for s in outcome.searches:
        out.append(f"- query: {s.query}")
        if not s.chunks:
            out.append("  - no chunks")
        for ch in s.chunks:
            out.append(f"  - {_source(ch)}: {ch.page_content[:PREVIEW].replace(chr(10), ' ')}")
    out += ["", "### Answer", outcome.reply, "", f"- answered_by_model: {_yn(outcome.answered_by_model)}",
            f"- time to first piece: {'none' if first is None else f'{first:.2f}s'}",
            f"- total time: {total:.2f}s", ""]
    verdict = "pass" if not failed else "fail"
    out += ["### Verdict", f"- {verdict}: failed checks {', '.join(sorted(failed)) or '-'}", ""]
    return out


def run_case(case, run_turn):
    """Run, score, format and report-line one case inside one error handler. A case that raises while it
    runs or while its section is built is recorded as an error and counts as failed."""
    r = {"case": case, "outcome": None, "failed": None, "error": None, "first": None, "total": 0.0,
         "section": [], "line": ""}
    first, start = [], time.perf_counter()

    def on_token(piece):
        if not first:
            first.append(time.perf_counter() - start)

    try:
        outcome = run_turn(case, on_token)
        failed = score_case(case, outcome.plan)
        total = time.perf_counter() - start
        section = section_lines(case, outcome, failed, first[0] if first else None, total)
        line = (f"{case['id']}: {'pass' if not failed else 'fail'} failed={','.join(sorted(failed)) or '-'} "
                f"route={outcome.plan.route}")
        r.update(outcome=outcome, failed=failed, first=first[0] if first else None, total=total,
                 section=section, line=line)
    except Exception as exc:  # recorded; the run goes on
        msg = " ".join(f"{type(exc).__name__}: {exc}".split())
        r.update(error=msg, failed=None, total=time.perf_counter() - start,
                 section=_header(case) + [f"- Error: {msg}", ""],
                 line=f"{case['id']}: fail (error: {msg})")
    return r


def build_report(results, log_path=None):
    passed = Counter()
    sizes = Counter()
    for r in results:
        area = r["case"]["area"]
        sizes[area] += 1
        if r["error"] is None and not r["failed"]:
            passed[area] += 1
    lines = [r["line"] for r in results] + [""]
    for area in AREAS:
        if sizes[area]:
            lines.append(f"{area}: {passed[area]} of {sizes[area]} passed")
    if log_path is not None:
        lines.append(f"log: {log_path}")
    return "\n".join(lines)


def write_log(results, report, log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"always_wiring_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Always items wiring eval", ""]
    for r in results:
        lines += r["section"]
    lines += ["## Report", "", report, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
