"""Helpers for spec 030 (food tool wiring): the 25 eval cases, the pure scorer (spec 4.2) and the eval
log writer and report (spec 4.3). Nothing here runs a model, reads data/ or needs the network.

Imported by conftest.py (which exposes everything as fixtures) and by the test modules that need
plain data (the case list).
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import datetime

FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
SEARCH = "search_documents"

LOC = ("where", "locat", "kept", "stor", "find", "plac")
AREAS = ("CALL", "ARGS", "ANSWER", "FT", "FD")
AREA_SIZES = {"CALL": 6, "ARGS": 6, "ANSWER": 1, "FT": 6, "FD": 6}
THRESHOLD = 5

COUNT_ITEMS = ("spoons", "forks", "knives", "small plates", "large plates")
NAPKIN_ITEMS = ("cocktail napkins", "dinner napkins")


# --------------------------------------------------------------------------
# Histories (spec 6)
# --------------------------------------------------------------------------

def _h(*pairs):
    out = []
    for user, assistant in pairs:
        out += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    return out


H_FORKS = _h(("How many forks do I need for 70 guests?", "Forks: 120 (70 guests + 50 extra)"))
H_LARGE = _h(("How many large plates for 50 guests?", "Large plates: 70 (50 guests + 20 extra)"))
H_NAPKIN = _h(("Do I need dinner napkins for a lunch?", "Dinner napkins for lunch: yes"))
H_MUFFIN = _h(("We have 60 guests at the lunch. Where are the muffins kept?",
               "The breakfast muffins are on the metal rack in the service room, near the manager's table."))
H_BAGEL = _h(("Where are the bagels kept?",
              "Assorted bagels are on the metal rack in the service room, near the manager's table."))
H_YOGURT = _h(("How many small plates for 80 guests?", "Small plates: 130 (80 guests + 50 extra)"),
              ("Where is the Greek yogurt kept?", "Greek yogurt is in the service cooler."))


# --------------------------------------------------------------------------
# The 25 eval cases (spec 6)
# --------------------------------------------------------------------------

def cnt(item, guests):
    return {"name": FOOD, "item": item, "guests": guests, "meal": None, "names_only": False}


def nap(item, meal):
    return {"name": FOOD, "item": item, "guests": None, "meal": meal, "names_only": False}


def names_only(name):
    return {"name": name, "item": None, "guests": None, "meal": None, "names_only": True}


def _case(cid, area, route, question, tools=(), keep=(), history=None):
    return {"id": cid, "area": area, "route": route, "question": question, "history": history,
            "tools": list(tools), "keep": [tuple(k) for k in keep]}


_CASES = [
    _case("CALL-1", "CALL", "TOOL", "How many forks do we need for 90 guests?", [names_only(FOOD)]),
    _case("CALL-2", "CALL", "TOOL", "Will we need dinner napkins for the dinner service?", [names_only(FOOD)]),
    _case("CALL-3", "CALL", "TOOL", "How many small plates for 45 people?", [names_only(FOOD)]),
    _case("CALL-4", "CALL", "TOOL", "Should I put out cocktail napkins for breakfast?", [names_only(FOOD)]),
    _case("CALL-5", "CALL", "TOOL", "How many cups do I need for 70 guests?", [names_only(BEV)]),
    _case("CALL-6", "CALL", "DOCS", "Do I need napkins for the iced tea?"),
    _case("ARGS-1", "ARGS", "TOOL", "How many spoons do I need for 45 guests?", [cnt("spoons", 45)]),
    _case("ARGS-2", "ARGS", "TOOL", "How many large plates for 120 people?", [cnt("large plates", 120)]),
    _case("ARGS-3", "ARGS", "TOOL", "How many knives and forks for 60 guests?",
          [cnt("knives", 60), cnt("forks", 60)]),
    _case("ARGS-4", "ARGS", "TOOL", "Do I need dinner napkins for a lunch for 80 guests?",
          [nap("dinner napkins", "lunch")]),
    _case("ARGS-5", "ARGS", "TOOL", "Do we put out cocktail napkins at a reception?",
          [nap("cocktail napkins", "reception")]),
    _case("ARGS-6", "ARGS", "TOOL", "How many small plates for fifty guests?", [cnt("small plates", 50)]),
    _case("ANSWER-7", "ANSWER", "TOOL", "How many forks do I need for 70 guests?", [cnt("forks", 70)]),
    _case("FT-1", "FT", "TOOL", "What about knives?", [cnt("knives", 70)], history=H_FORKS),
    _case("FT-2", "FT", "TOOL", "How many if it's 100 guests instead?", [cnt("forks", 100)], history=H_FORKS),
    _case("FT-3", "FT", "TOOL", "And small plates?", [cnt("small plates", 50)], history=H_LARGE),
    _case("FT-4", "FT", "TOOL", "What about cocktail napkins?", [nap("cocktail napkins", "lunch")],
          history=H_NAPKIN),
    _case("FT-5", "FT", "TOOL", "And for a reception?", [nap("dinner napkins", "reception")], history=H_NAPKIN),
    _case("FT-6", "FT", "TOOL", "How many forks do I need?", [cnt("forks", 60)], history=H_MUFFIN),
    _case("FD-1", "FD", "DOCS", "Where are the croissants kept?", keep=[("croissant",), LOC], history=H_FORKS),
    _case("FD-2", "FD", "DOCS", "Where is the cream cheese kept?", keep=[("cream cheese",), LOC], history=H_LARGE),
    _case("FD-3", "FD", "DOCS", "Where is the Greek yogurt?", keep=[("yogurt",), LOC], history=H_NAPKIN),
    _case("FD-4", "FD", "DOCS", "What comes with the croissants?", keep=[("croissant",)], history=H_FORKS),
    _case("FD-5", "FD", "DOCS", "And what comes with them?", keep=[("bagel", "cream cheese")], history=H_BAGEL),
    _case("FD-6", "FD", "DOCS", "And the vegan one?", keep=[("vegan",)], history=H_YOGURT),
]

CASES = {c["id"]: c for c in _CASES}
CASE_IDS = [c["id"] for c in _CASES]


# --------------------------------------------------------------------------
# The scorer (spec 4.2): pure function of a case and the final Plan
# --------------------------------------------------------------------------

def num(v):
    """A number by value: ints and floats; numeric strings count; booleans never. None otherwise."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _singular(word):
    if word == "knives":
        return "knife"
    return word[:-1] if word.endswith("s") else word


def canon_item(v):
    """Strip, casefold, '_' and '-' as a space, collapse spaces, singular (last word)."""
    if not isinstance(v, str):
        return None
    words = re.sub(r"[_\-\s]+", " ", v.strip().casefold()).strip().split(" ")
    if not words or words == [""]:
        return None
    words[-1] = _singular(words[-1])
    return " ".join(words)


_NAPKIN_CANON = {canon_item(x) for x in NAPKIN_ITEMS}


def _norm_meal(v):
    return v.strip().casefold() if isinstance(v, str) else None


def _args(call):
    return call.args if isinstance(call.args, dict) else {}


def _match(exp, act):
    if exp["name"] != act.name:
        return False
    if exp["names_only"]:
        return True
    a = _args(act)
    item = canon_item(a.get("item"))
    if item is None or item != canon_item(exp["item"]):
        return False
    if canon_item(exp["item"]) in _NAPKIN_CANON:
        return _norm_meal(a.get("meal")) is not None and _norm_meal(a.get("meal")) == _norm_meal(exp["meal"])
    g = num(a.get("guests"))
    return g is not None and g == num(exp["guests"])


def _multiset_match(expected, actual):
    if len(expected) != len(actual):
        return False
    if not expected:
        return True
    first, rest = expected[0], expected[1:]
    for i, a in enumerate(actual):
        if _match(first, a) and _multiset_match(rest, actual[:i] + actual[i + 1:]):
            return True
    return False


def _search_ok(case, search_calls):
    if case["route"] == "TOOL":
        return not search_calls
    if not search_calls:
        return False
    queries = [c.args.get("query") for c in search_calls
               if isinstance(c.args, dict) and isinstance(c.args.get("query"), str)]
    joined = " ".join(queries).casefold()
    return all(any(t in joined for t in group) for group in case["keep"])


def score_case(case, plan):
    """Set of failed checks: a subset of {"route", "tools", "search"}. Empty means pass."""
    failed = set()
    if plan.route != case["route"]:
        failed.add("route")
    tool_calls = [c for c in plan.calls if c.name != SEARCH]
    search_calls = [c for c in plan.calls if c.name == SEARCH]
    if not _multiset_match(case["tools"], tool_calls):
        failed.add("tools")
    if not _search_ok(case, search_calls):
        failed.add("search")
    return failed


# --------------------------------------------------------------------------
# The eval log (spec 4.3) and the report
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
    route_ok = Counter(r["case"]["area"] for r in results
                       if r["outcome"] is not None and r["outcome"].plan.route == r["case"]["route"])
    lines = [r["line"] for r in results] + [""]
    for area in AREAS:
        if sizes[area]:
            lines.append(f"{area}: {passed[area]} of {sizes[area]} passed")
    for area in AREAS:
        if sizes[area]:
            lines.append(f"{area}: route accuracy {route_ok[area]} of {sizes[area]}")
    firsts = [r["first"] for r in results if r["first"] is not None]
    totals = [r["total"] for r in results]
    if firsts:
        lines.append(f"average time to first piece: {sum(firsts) / len(firsts):.2f}s")
    if totals:
        lines.append(f"average total time: {sum(totals) / len(totals):.2f}s")
    if log_path is not None:
        lines.append(f"log: {log_path}")
    return "\n".join(lines)


def write_log(results, report, log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"food_wiring_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Food tool wiring eval", ""]
    for r in results:
        lines += r["section"]
    lines += ["## Report", "", report, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
