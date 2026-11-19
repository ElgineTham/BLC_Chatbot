"""Helpers for spec 043 (serving utensils wiring): the Appendix A test rules, the 12 eval cases (sections 6.1 to
6.3), the pure scorer (section 4.4) and the eval log writer and report (section 4.5).

Nothing here runs a model, reads data/ (unless a caller asks the scorer to use the real rules) or needs the
network. Imported by conftest.py and by the test modules that need plain data.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime

SERV = "calculate_serving_utensils"
FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

AREAS = ("CALL", "ARGS", "FOLLOW")
AREA_SIZES = {"CALL": 4, "ARGS": 4, "FOLLOW": 4}
THRESHOLD = 3

# Spec 042 Appendix A (test rules only; not real business rules).
APPENDIX_A = {
    "foods": {
        "butter croissants": {
            "unit": "dozen",
            "aliases": ["Butter croissants served with raspberry preserves"],
            "utensils": [{"utensil": "small tongs", "count": 2, "per": 2}],
        },
        "assorted bagels": {
            "unit": "dozen",
            "aliases": ["bagels", "Assorted bagels with cream cheese"],
            "utensils": [
                {"utensil": "small tongs", "count": 1, "per": None},
                {"utensil": "spreader/knives", "count": 1, "per": None},
            ],
        },
        "classic deli sandwiches": {
            "unit": "each",
            "aliases": ["deli sandwiches"],
            "utensils": [
                {"utensil": "large tongs", "count": 1, "per": None},
                {"utensil": "mayo/mustard", "count": 1, "per": 25},
            ],
        },
        "quinoa-chickpea tabbouleh salad": {
            "unit": "each",
            "aliases": ["tabbouleh salad"],
            "utensils": [
                {"utensil": "salad tongs", "count": 1, "per": 1},
                {"utensil": "dressing/sauce bowl", "count": 1, "per": 1},
            ],
        },
        "yogurt with toppings": {
            "unit": "each",
            "aliases": [],
            "utensils": [
                {"utensil": "honey bear", "count": 2, "per": None},
                {"utensil": "serving spoon", "count": 2, "per": None},
                {"utensil": "serving spoon", "count": 2, "per": None},
            ],
        },
        "trail mix": {"unit": "bags", "aliases": [], "utensils": []},
    }
}


# --------------------------------------------------------------------------
# Histories (spec 6)
# --------------------------------------------------------------------------

def _h(user, assistant):
    return [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]


H_MUFFIN = _h("What serving utensils do I need for 4 dozen muffins?",
              "Small tongs: 4. Counted for: breakfast muffins 4 dozen")
H_DELI = _h("Utensils for 50 classic deli sandwiches?",
            "Large tongs: 6. Mayo/mustard: 2. Counted for: classic deli sandwiches 50 each")
H_LUNCH = _h("We have 30 guests for lunch tomorrow.", "Got it, 30 guests for lunch.")


# --------------------------------------------------------------------------
# The 12 eval cases (spec 6.1 to 6.3)
# --------------------------------------------------------------------------

def _case(cid, area, route, question, tools=(), totals=None, keyword=None, history=None, ask_ok=False):
    """ask_ok (revision 4, FOLLOW-3 only): status need_info also passes the totals check (4.4 check 5)."""
    return {"id": cid, "area": area, "route": route, "question": question, "history": history,
            "tools": list(tools), "totals": totals, "keyword": keyword, "ask_ok": ask_ok}


_CASES = [
    _case("CALL-1", "CALL", "TOOL", "What serving utensils do I need for 4 dozen muffins?", [SERV]),
    _case("CALL-2", "CALL", "TOOL", "How many tongs should I pull for 3 large fruit trays?", [SERV],
          {"large tongs": 6}),
    _case("CALL-3", "CALL", "TOOL", "How many forks for 60 guests?", [FOOD]),
    _case("CALL-4", "CALL", "DOCS", "Where are the scones kept?", keyword="scone"),
    _case("ARGS-1", "ARGS", "TOOL",
          "What serving utensils for 2 dozen bagels and 50 classic deli sandwiches?", [SERV],
          {"small tongs": 2, "large tongs": 6, "spreader/knives": 2, "mayo/mustard": 2}),
    _case("ARGS-2", "ARGS", "TOOL",
          "We have a Cascade Breakfast for 70 guests: butter croissants, a freshly cut fruit platter and "
          "Greek yogurt with honey and granola. What serving utensils do I pull?", [SERV],
          {"small tongs": 6, "large tongs": 2, "spreader/knives": 2, "serving spoon": 1, "honey bear": 2}),
    _case("ARGS-3", "ARGS", "TOOL", "Serving utensils for 36 croissants?", [SERV],
          {"small tongs": 4, "spreader/knives": 2}),
    _case("ARGS-4", "ARGS", "TOOL",
          "What utensils do I need for scrambled eggs and roasted breakfast potatoes for 40 guests?", [SERV],
          {"serving spoon": 4}),
    _case("FOLLOW-1", "FOLLOW", "TOOL", "What about 6 dozen instead?", [SERV], {"small tongs": 6},
          history=H_MUFFIN),
    _case("FOLLOW-2", "FOLLOW", "TOOL", "And for 100 sandwiches?", [SERV],
          {"large tongs": 10, "mayo/mustard": 4}, history=H_DELI),
    _case("FOLLOW-3", "FOLLOW", "TOOL",
          "What serving utensils do I need for the classic deli sandwiches?", [SERV],
          {"large tongs": 4, "mayo/mustard": 2}, history=H_LUNCH, ask_ok=True),
    _case("FOLLOW-4", "FOLLOW", "DOCS", "Where are the muffins kept?", keyword="muffin", history=H_MUFFIN),
]

CASES = {c["id"]: c for c in _CASES}
CASE_IDS = [c["id"] for c in _CASES]


# --------------------------------------------------------------------------
# The scorer (spec 4.4): pure function of a case and the final Plan
# --------------------------------------------------------------------------

def _real_run_tool(args):
    from blc.tools.serv_tools import run_serv_tool

    return run_serv_tool(args)


def score_case(case, plan, run_tool=None):
    """Set of failed checks: a subset of {"route", "tools", "totals", "search"}. Empty means pass.

    run_tool(args) -> ServResult; default is run_serv_tool(args) with the real rules file."""
    run_tool = run_tool or _real_run_tool
    failed = set()
    if plan.route != case["route"]:
        failed.add("route")
    names = [c.name for c in plan.calls if c.name != SEARCH]
    if Counter(names) != Counter(case["tools"]):
        failed.add("tools")
    if case["totals"] is not None:
        serving = [c for c in plan.calls if c.name == SERV]
        ok = False
        if len(serving) == 1 and isinstance(serving[0].args, dict):
            result = run_tool(serving[0].args)
            ok = result.status == "ok" and result.utensils == case["totals"]
            if case.get("ask_ok") and result.status == "need_info":
                ok = True
        if not ok:
            failed.add("totals")
    if case["keyword"] is not None:
        queries = [c.args.get("query") for c in plan.calls
                   if c.name == SEARCH and isinstance(c.args, dict) and isinstance(c.args.get("query"), str)]
        if not any(case["keyword"].casefold() in q.casefold() for q in queries):
            failed.add("search")
    return failed


# --------------------------------------------------------------------------
# The eval log (spec 4.5) and the report
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


def run_case(case, run_turn, run_tool=None):
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
        failed = score_case(case, outcome.plan, run_tool)
        total = time.perf_counter() - start
        section = section_lines(case, outcome, failed, first[0] if first else None, total)
        line = (f"{case['id']}: {'pass' if not failed else 'fail'} failed={','.join(sorted(failed)) or '-'} "
                f"route={outcome.plan.route} time={total:.2f}s")
        r.update(outcome=outcome, failed=failed, first=first[0] if first else None, total=total,
                 section=section, line=line)
    except Exception as exc:  # recorded; the run goes on
        msg = " ".join(f"{type(exc).__name__}: {exc}".split())
        r.update(error=msg, failed=None, total=time.perf_counter() - start,
                 section=_header(case) + [f"- Error: {msg}", ""],
                 line=f"{case['id']}: fail (error: {msg})")
    return r


def build_report(results, log_path=None):
    passed, sizes = Counter(), Counter()
    for r in results:
        area = r["case"]["area"]
        sizes[area] += 1
        if r["error"] is None and not r["failed"]:
            passed[area] += 1
    lines = [r["line"] for r in results] + [""]
    for area in AREAS:
        if sizes[area]:
            lines.append(f"{area}: {passed[area]} of {sizes[area]} passed")
    totals = [r["total"] for r in results]
    if totals:
        lines.append(f"average total time: {sum(totals) / len(totals):.2f}s")
    if log_path is not None:
        lines.append(f"log: {log_path}")
    return "\n".join(lines)


def write_log(results, report, log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"serv_wiring_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Serving utensils wiring eval", ""]
    for r in results:
        lines += r["section"]
    lines += ["## Report", "", report, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
