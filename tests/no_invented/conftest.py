"""Shared fakes, the 30 golden cases and the scorer for spec 021 (no invented numbers).

Unit tests: no Ollama, no Chroma, no network, nothing read under data/ (NFR-3).
Exposed as fixtures (so no test imports from conftest):
- mk, doc, make_store      reply builders, Document builder, fake store class
- make_runner              fake tool runner that records its calls
- make_llm                 scripted fake model; one planner reply per planner call; a third call raises
- text_of                  join the text of a list of messages
- run                      run one planned turn with scripted plans
- golden_cases             the 30 cases of spec 021 section 6
- scorer                   the pure scorer of section 4.4 (namespace of functions; num accepts Fraction)
- mkout / mkres            hand-made TurnOutcome stand-ins and fake tool results (scorer tests)
- ollama_available / real_store / real_llm   (eval only) skip when Ollama or the store is missing
"""
import itertools
import numbers
import re
import urllib.request
from fractions import Fraction
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


# --------------------------------------------------------------------------
# Scripted fakes
# --------------------------------------------------------------------------

class FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        n = len(self.parent.invoke_calls)
        if n > len(self.parent.plan_replies):
            raise AssertionError(f"planner called {n} times; only {len(self.parent.plan_replies)} scripted")
        return self.parent.plan_replies[n - 1]


class FakeLLM:
    """plan_replies: one reply per planner call, in order. A call past the script raises."""

    def __init__(self, plan_replies=(), pieces=("Answer.",)):
        self.plan_replies = list(plan_replies)
        self.pieces = list(pieces)
        self.bind_calls = []
        self.invoke_calls = []      # messages of each planner call
        self.stream_calls = []      # messages of each answer call

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        return (AIMessageChunk(content=p) for p in self.pieces)


class FakeStore:
    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        return list(self.results.get(query, []))


class FakeRunner:
    def __init__(self, status="ok", text=""):
        self.status = status
        self.text = text
        self.calls = []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(args)
        return ToolOutput(self.status, self.text)


def ai(*calls, content=""):
    return AIMessage(content=content,
                     tool_calls=[{"name": n, "args": a, "id": f"call_{i}"} for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture(scope="session")
def mk():
    return SimpleNamespace(ai=ai)


@pytest.fixture(scope="session")
def doc():
    return lambda text, source: Document(page_content=text, metadata={"source": source})


@pytest.fixture(scope="session")
def make_runner():
    return FakeRunner


@pytest.fixture(scope="session")
def make_llm():
    return FakeLLM


@pytest.fixture(scope="session")
def make_store():
    return FakeStore


@pytest.fixture(scope="session")
def text_of():
    return lambda messages: "\n".join(str(m.content) for m in messages)


@pytest.fixture
def run():
    """run(question, plans, history=None, docs=None, runners=None, pieces=...) -> namespace.

    plans: a list with one entry per scripted planner reply; each entry is a list of (name, args)."""

    def _run(question, plans, history=None, docs=None, runners=None, pieces=("Answer.",)):
        from blc.flow import run_planned_turn

        llm = FakeLLM([ai(*p) for p in plans], pieces)
        store = FakeStore(docs)
        if runners is None:
            runners = {BEV: FakeRunner("ok", "BEV TEXT"), REC: FakeRunner("ok", "RECIPE TEXT")}
        outcome = run_planned_turn(llm, store, question, history, tool_runners=runners)
        return SimpleNamespace(outcome=outcome, llm=llm, store=store, runners=runners)

    return _run


# --------------------------------------------------------------------------
# The 30 golden cases (section 6)
# --------------------------------------------------------------------------

def _b(item, drinks=None, gallons=None, guests=None):
    return {"name": BEV, "item": item, "drinks": drinks or [], "gallons": gallons or [], "guests": guests}


def _r(recipe, gallons=None, guests=None):
    return {"name": REC, "recipe": recipe, "gallons": gallons, "guests": guests}


def _h(user, assistant):
    return [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]


def _case(cid, path, question, history=None, gold=(), drinks=None, lines=None, mode=None,
          rec=None, docs=()):
    """gold: list of alternatives, each a list of gold calls. drinks: {name: gallons}.
    lines: [(supply, qty)]. mode: exact / include / none. rec: (gallons, oz). docs: accepted sources."""
    return {"id": cid, "path": path, "question": question, "history": history, "gold": [list(g) for g in gold],
            "drinks": drinks or {}, "lines": lines or [], "mode": mode, "rec": rec, "docs": list(docs)}


_S, _M, _R = "data/supplies/", "data/pull_sheet/menu/beverages.md", "data/pull_sheet/rules/beverages.md"
_CAM5, _CAM2, _CAM1 = "5 gal cambro", "2 gal cambro", "1 gal cambro"

_CASES = [
    _case("G1", "TOOL", "How many cambros for brewed hot cider for 85 guests?",
          gold=[[_b("cambros", ["brewed hot cider"], guests=85)]], drinks={"Brewed hot cider": 3},
          lines=[(_CAM5, 1)], mode="exact"),
    _case("G2", "TOOL", "Cups needed for orange juice and decaf, 140 guests?",
          gold=[[_b("cups", ["orange juice", "decaf"], guests=140)]], drinks={"Orange juice": 6, "Decaf": 6},
          lines=[("hot-cups", 240), ("cold-cups", 240)], mode="exact"),
    _case("G3", "TOOL", "How many gallons of iced water for 210 guests?",
          gold=[[_b("gallons", ["iced water"], guests=210)]], drinks={"Iced water": 8}, mode="none"),
    _case("G4", "TOOL", "Which cambros hold 9 gallons of iced tea?",
          gold=[[_b("cambros", ["iced tea"], gallons=[9])]], drinks={"Iced tea": 9},
          lines=[(_CAM5, 2)], mode="exact"),
    _case("G5", "TOOL", "How do I make lemonade for 45 people?",
          gold=[[_r("lemonade", guests=45)]], rec=(2, 14)),
    _case("G6", "TOOL", "How much lemon concentrate for 2.5 gallons of lemonade?",
          gold=[[_r("lemonade", gallons=2.5)]], rec=(2.5, 17.5)),
    _case("G7", "TOOL", "How many cambros for twenty-five guests of hot water?",
          gold=[[_b("cambros", ["hot water"], guests=25)]], drinks={"Hot water": 1},
          lines=[(_CAM1, 1)], mode="exact"),
    _case("G8", "TOOL", "What goes on the pull sheet for decaf for 55 guests?",
          gold=[[_b("everything", ["decaf"], guests=55)]], drinks={"Decaf": 2},
          lines=[(_CAM2, 1), ("hot-cups", 105), ("Stir sticks", 1), ("Sugar", 1)], mode="include"),
    _case("G9", "TOOL", "How many cambros for that?",
          history=_h("How many gallons of coffee for 100 guests?", "Coffee: 4 gallons for 100 guests."),
          gold=[[_b("cambros", ["coffee"], gallons=[4])], [_b("cambros", ["coffee"], guests=100)],
                [_b("cambros", ["coffee"], gallons=[4], guests=100)]],
          drinks={"Coffee": 4}, lines=[(_CAM5, 1)], mode="exact"),
    _case("G10", "TOOL", "65 guests.", history=_h("How many cups for peach tea?", "How many guests?"),
          gold=[[_b("cups", ["peach tea"], guests=65)]], drinks={"Peach tea": 3},
          lines=[("cold-cups", 115)], mode="exact"),
    _case("L1", "DOCS", "If the coffee shelf is empty, where do I get more coffee supplies?", docs=[_S + "coffee.md"]),
    _case("L2", "DOCS", "What flavors of concentrate are on the blue racks?", docs=[_S + "concentrates.md"]),
    _case("L3", "DOCS", "Do we bring stir sticks for iced tea?", docs=[_R]),
    _case("L4", "DOCS", "How do I pull stock of syrups?", docs=[_S + "syrups.md"]),
    _case("L5", "DOCS", "What's the rule for cold cups when lemonade is ordered?", docs=[_R]),
    _case("L6", "DOCS", "Is orange juice part of the beverage package?", docs=[_M]),
    _case("L7", "DOCS", "Where are the backup lemons?", docs=[_S + "lemon.md"]),
    _case("L8", "DOCS", "Is peach tea a hot or a cold drink?", docs=[_M]),
    _case("L9", "DOCS", "Does oatmilk go in a cambro?", docs=[_M]),
    _case("L10", "DOCS", "And the concentrates?",
          history=_h("Where are the syrups kept?", "Above the lemons in the beverage cooler."),
          docs=[_S + "concentrates.md"]),
    _case("B1", "BOTH", "Where are the backup coffee supplies, and how many cambros of coffee for 80 guests?",
          gold=[[_b("cambros", ["coffee"], guests=80)]], drinks={"Coffee": 3}, lines=[(_CAM5, 1)], mode="exact",
          docs=[_S + "coffee.md"]),
    _case("B2", "BOTH", "How many cups for decaf for 150 guests, and what does decaf mean on a BEO?",
          gold=[[_b("cups", ["decaf"], guests=150)]], drinks={"Decaf": 6}, lines=[("hot-cups", 250)], mode="exact",
          docs=[_M]),
    _case("B3", "BOTH", "Where is the lemon concentrate kept, and how do I make lemonade for 90 guests?",
          gold=[[_r("lemonade", guests=90)]], rec=(4, 28), docs=[_S + "concentrates.md"]),
    _case("B4", "BOTH", "How many gallons of peach tea for 70 guests, and what flavors of syrup do we have?",
          gold=[[_b("gallons", ["peach tea"], guests=70)]], drinks={"Peach tea": 3}, mode="none",
          docs=[_S + "syrups.md"]),
    _case("B5", "BOTH", "How many cambros for 11 gallons of orange juice, and what sizes of cambros do we have?",
          gold=[[_b("cambros", ["orange juice"], gallons=[11])]], drinks={"Orange juice": 11},
          lines=[(_CAM5, 2), (_CAM1, 1)], mode="exact", docs=[_R]),
    _case("B6", "BOTH", "Do we bring lemons for hot water, and how many cups for hot water for 35 guests?",
          gold=[[_b("cups", ["hot water"], guests=35)]], drinks={"Hot water": 1}, lines=[("hot-cups", 55)],
          mode="exact", docs=[_R, _S + "lemon.md"]),
    _case("B7", "BOTH", "How much concentrate for 4 gallons of lemonade, and how do I pull stock of concentrates?",
          gold=[[_r("lemonade", gallons=4)]], rec=(4, 28), docs=[_S + "concentrates.md"]),
    _case("B8", "BOTH", "What goes on the pull sheet for 120 guests of iced water, and is iced water a hot or cold drink?",
          gold=[[_b("everything", ["iced water"], guests=120)]], drinks={"Iced water": 5},
          lines=[(_CAM5, 1), ("cold-cups", 220)], mode="include", docs=[_M]),
    _case("B9", "BOTH", "Which cambros for that, and what's in the beverage package?",
          history=_h("How many gallons of decaf for 60 guests?", "Decaf: 2 gallons for 60 guests."),
          gold=[[_b("cambros", ["decaf"], gallons=[2])], [_b("cambros", ["decaf"], guests=60)],
                [_b("cambros", ["decaf"], gallons=[2], guests=60)]],
          drinks={"Decaf": 2}, lines=[(_CAM2, 1)], mode="exact", docs=[_M]),
    _case("B10", "BOTH", "Where are the lemons, and how many gallons of coffee for forty guests?",
          gold=[[_b("gallons", ["coffee"], guests=40)]], drinks={"Coffee": 2}, mode="none",
          docs=[_S + "lemon.md"]),
]


@pytest.fixture(scope="session")
def golden_cases():
    return list(_CASES)


# --------------------------------------------------------------------------
# The scorer (section 4.4): pure, runs no model
# --------------------------------------------------------------------------

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def num(v):
    """A number as a Fraction; None for bools and anything that is not a number."""
    if isinstance(v, bool):
        return None
    if isinstance(v, numbers.Real):     # int, float, Fraction, Decimal-like reals (the real tools return Fraction)
        try:
            return Fraction(v)
        except (ValueError, OverflowError, TypeError):   # nan, inf
            return None
    if isinstance(v, str):
        try:
            return Fraction(v.strip().replace(",", ""))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def allowed_numbers(question, history=None):
    text = (question or "").strip() + "\n" + "\n".join(h["content"] for h in (history or []))
    found = {Fraction(1)}
    for m in re.finditer(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", text):
        found.add(Fraction(m.group().replace(",", "")))
    words = re.findall(r"[a-z]+", text.lower())
    i = 0
    while i < len(words):
        w = words[i]
        if w in _TENS:
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if _UNITS.get(nxt, 99) in range(1, 10):
                found.add(Fraction(_TENS[w] + _UNITS[nxt]))
                i += 2
                continue
            found.add(Fraction(_TENS[w]))
        elif w in _UNITS:
            if w == "one" and words[i + 1: i + 2] == ["hundred"]:
                found.add(Fraction(100))
                i += 2
                continue
            found.add(Fraction(_UNITS[w]))
        i += 1
    return found


def _drinks(args):
    d = args.get("drinks")
    if d is None:
        return set()
    if isinstance(d, str):
        d = [d]
    return {str(x).strip().casefold() for x in d}


def _gallon_list(args):
    g = args.get("gallons")
    if g is None:
        return []
    return [num(x) for x in (g if isinstance(g, list) else [g])]


def _one_gallon(args):
    g = _gallon_list(args)
    return g[0] if len(g) == 1 else (None if not g else tuple(g))


def diff_fields(gold, run_call):
    """Fields on which a run call differs from a gold call (empty list = match)."""
    if gold["name"] != run_call["name"]:
        return ["name"]
    a = run_call["args"]
    out = []
    if gold["name"] == BEV:
        if gold["item"] != a.get("item"):
            out.append("item")
        if _drinks(gold) != _drinks(a):
            out.append("drinks")
        if (num(gold["guests"]) if gold["guests"] is not None else None) != num(a.get("guests")):
            out.append("guests")
        if _gallon_list(gold) != _gallon_list(a):
            out.append("gallons")
    else:
        if str(gold["recipe"]).strip().casefold() != str(a.get("recipe", "")).strip().casefold():
            out.append("recipe")
        if (num(gold["guests"]) if gold["guests"] is not None else None) != num(a.get("guests")):
            out.append("guests")
        if _one_gallon(gold) != _one_gallon(a):
            out.append("gallons")
    return out


def _matches(golds, runs):
    if len(golds) != len(runs):
        return False
    return any(all(not diff_fields(g, r) for g, r in zip(golds, perm)) for perm in itertools.permutations(runs))


def score_part1(case, outcome):
    runs = [{"name": t.name, "args": t.args} for t in outcome.tools]
    if not case["gold"]:
        return not runs
    return any(_matches(alt, runs) for alt in case["gold"])


def invented_in_run(case, outcome):
    ok = allowed_numbers(case["question"], case["history"])
    bad = []
    for t in outcome.tools:
        for key in ("guests", "gallons"):
            v = t.args.get(key)
            for x in (v if isinstance(v, list) else [v]):
                n = num(x)
                if n is not None and n not in ok:
                    bad.append((t.name, key, x))
    return bad


def score_part2(case, outcome):
    return not invented_in_run(case, outcome)


def _line_key(pair):
    return (pair[0], pair[1] is None, pair[1] if pair[1] is not None else Fraction(0))


def _bev_facts_ok(case, args, res):
    if res.status != "ok":
        return False
    for name, gal in case["drinks"].items():
        if not any(d.drink.casefold() == name.casefold() and num(d.amount) == num(gal) for d in res.drinks):
            return False
    got = sorted(((l.supply, num(l.quantity)) for l in res.lines), key=_line_key)   # quantity may be None (tick items)
    want = sorted(((s, num(q)) for s, q in case["lines"]), key=_line_key)
    item = args.get("item")
    if item in ("cambros", "cups"):
        return got == want
    if item == "everything":
        return all(w in got for w in want)
    if item == "gallons":
        return got == []
    return False


def _rec_facts_ok(case, res):
    if res.status != "ok" or case["rec"] is None:
        return False
    gal, oz = case["rec"]
    amounts = [i.amount for i in res.ingredients if i.name == "Lemon concentrate"]
    return num(res.gallons) == num(gal) and len(amounts) == 1 and num(amounts[0]) == num(oz)


def score_part3(case, outcome, tool_result):
    ok = True
    if case["path"] in ("TOOL", "BOTH"):
        if not outcome.tools:
            return False
        for t in outcome.tools:
            res = tool_result(t.name, t.args)
            if t.name == BEV:
                ok = ok and _bev_facts_ok(case, t.args, res)
            else:
                ok = ok and _rec_facts_ok(case, res)
    if case["path"] in ("DOCS", "BOTH"):
        sources = {d.metadata.get("source") for s in outcome.searches for d in s.chunks}
        ok = ok and bool(outcome.searches) and any(d in sources for d in case["docs"])
    return ok


def score_case(case, outcome, tool_result):
    p1, p2, p3 = score_part1(case, outcome), score_part2(case, outcome), score_part3(case, outcome, tool_result)
    route = outcome.plan.route == case["path"]
    no_search = not (case["path"] == "TOOL" and outcome.searches)
    return {"route": route, "no_search": no_search, "part1": p1, "part2": p2, "part3": p3,
            "passed": route and no_search and p1 and p2 and p3,
            "first_invented": bool(outcome.rejected), "retried": bool(outcome.retried)}


@pytest.fixture(scope="session")
def scorer():
    return SimpleNamespace(score=score_case, part1=score_part1, part2=score_part2, part3=score_part3,
                           allowed=allowed_numbers, invented=invented_in_run, diff=diff_fields,
                           num=num)


# --------------------------------------------------------------------------
# Hand-made outcomes and tool results for the scorer tests
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mkout():
    def _out(route="TOOL", tools=(), searches=(), rejected=(), retried=False):
        return SimpleNamespace(
            plan=SimpleNamespace(route=route),
            tools=tuple(SimpleNamespace(name=n, args=a, status="ok", text="") for n, a in tools),
            searches=tuple(SimpleNamespace(query=q, chunks=tuple(
                Document(page_content="x", metadata={"source": s}) for s in srcs)) for q, srcs in searches),
            rejected=tuple(rejected), retried=retried)
    return _out


@pytest.fixture(scope="session")
def mkres():
    def bev(drinks, lines=(), status="ok"):
        return SimpleNamespace(status=status, drinks=[SimpleNamespace(drink=d, amount=a) for d, a in drinks],
                               lines=[SimpleNamespace(supply=s, quantity=q) for s, q in lines])

    def rec(gallons, oz, status="ok"):
        return SimpleNamespace(status=status, gallons=gallons, ingredients=[
            SimpleNamespace(name="Lemon concentrate", amount=oz, unit="oz"),
            SimpleNamespace(name="Water", amount=gallons, unit="gallon")])

    return SimpleNamespace(bev=bev, rec=rec)


# --------------------------------------------------------------------------
# Golden eval log writer and report (section 4.4, revisions 1 and 2). No model; every case is isolated.
# --------------------------------------------------------------------------

import time                                    # noqa: E402
from collections import Counter                # noqa: E402
from datetime import datetime                  # noqa: E402

_SUBSECTIONS = ("### Question", "### Plan", "### Part 1, gold call", "### Part 2, invented numbers",
                "### Part 3, required outcome", "### Answer", "### Verdict")


def _yn(ok):
    return "pass" if ok else "fail"


def fmt_num(v):
    """A shown amount: None is 'bring' (a tick item); any number by value (Fraction(35, 2) -> 17.5)."""
    if v is None:
        return "bring"
    n = num(v)
    return str(v) if n is None else f"{float(n):g}"


def _fmt_lines(pairs):
    return "[" + ", ".join(f"({s}: {fmt_num(q)})" for s, q in pairs) + "]"


def _fact(label, required, actual, ok):
    return f"  - {label}: required {required}, actual {actual}: {_yn(ok)}"


def tool_facts(case, t, tool_result):
    """Part 3 lines for one tool call: each required fact next to the actual value, with pass or fail."""
    try:
        res = tool_result(t.name, t.args)
    except Exception as exc:  # the tool itself failed: record it, the run goes on
        return [f"- {t.name} {t.args}", f"  - tool re-run raised {type(exc).__name__}: {exc}: fail"]
    out = [f"- {t.name} {t.args}", _fact("status", "ok", res.status, res.status == "ok")]
    if t.name == BEV:
        for name, gal in case["drinks"].items():
            got = next((d.amount for d in res.drinks if d.drink.casefold() == name.casefold()), "missing")
            out.append(_fact(f"drink {name} gallons", fmt_num(gal), fmt_num(got),
                             got != "missing" and num(got) is not None and num(got) == num(gal)))
        item = t.args.get("item")
        actual = sorted(((l.supply, num(l.quantity)) for l in res.lines), key=_line_key)
        want = sorted(((s, num(q)) for s, q in case["lines"]), key=_line_key)
        shown_actual = _fmt_lines([(l.supply, l.quantity) for l in res.lines])
        if item in ("cambros", "cups"):
            out.append(_fact("lines (exact match)", _fmt_lines(want), shown_actual, actual == want))
        elif item == "everything":
            out.append(_fact("lines (subset match)", _fmt_lines(want), shown_actual, all(w in actual for w in want)))
        else:
            out.append(_fact("lines (must be empty)", "[]", shown_actual, actual == []))
    elif case["rec"] is not None:
        gal, oz = case["rec"]
        amounts = [i.amount for i in res.ingredients if i.name == "Lemon concentrate"]
        out.append(_fact("recipe gallons", fmt_num(gal), fmt_num(res.gallons),
                         num(res.gallons) is not None and num(res.gallons) == num(gal)))
        out.append(_fact("lemon concentrate oz", fmt_num(oz), [fmt_num(a) for a in amounts],
                         len(amounts) == 1 and num(amounts[0]) is not None and num(amounts[0]) == num(oz)))
    return out


def _calls(plan):
    return [f"{c.name} {c.args}" for c in plan.calls]


def _header(case):
    hist = "none" if not case["history"] else "; ".join(f"{h['role']}: {h['content']}" for h in case["history"])
    return [f"## {case['id']}", "", "### Question", f"- id: {case['id']}", f"- path: {case['path']}",
            f"- question: {case['question']}", f"- history: {hist}", ""]


def section_lines(scorer, case, o, s, tool_result, first, total):
    out = _header(case)
    out += ["### Plan", f"- first plan: {o.first_plan.route} {_calls(o.first_plan)}",
            f"- rejected: {[(c.name, c.invented) for c in o.rejected] or 'none'}",
            f"- retried: {'yes' if o.retried else 'no'}",
            f"- final plan: {o.plan.route} {_calls(o.plan)}", ""]
    runs = [{"name": t.name, "args": t.args} for t in o.tools]
    out += ["### Part 1, gold call", f"- gold (any of): {case['gold'] or 'none (DOCS: no tool result allowed)'}",
            f"- run calls: {runs}", f"- result: {_yn(s['part1'])}"]
    if not s["part1"] and case["gold"]:
        if len(case["gold"][0]) != len(runs):
            out.append("- differing: extra or missing call")
        else:
            out.append("- differing fields vs first alternative: "
                       f"{[scorer.diff(g, rc) for g, rc in zip(case['gold'][0], runs)]}")
    out.append("")
    out += ["### Part 2, invented numbers",
            f"- allowed numbers: {sorted(float(n) for n in scorer.allowed(case['question'], case['history']))}"]
    for t in o.tools:
        for k in ("guests", "gallons"):
            if k in t.args:
                out.append(f"- {t.name} {k}={t.args[k]}")
    out += [f"- invented in the run: {scorer.invented(case, o) or 'none'}", f"- result: {_yn(s['part2'])}",
            f"- first plan invented: {[(c.name, c.invented) for c in o.rejected] or 'none'}", ""]
    out += ["### Part 3, required outcome"]
    for t in o.tools:
        out += tool_facts(case, t, tool_result)
    for sr in o.searches:
        out.append(f"- search {sr.query!r}: {[d.metadata.get('source') for d in sr.chunks]}")
    out += [f"- required document(s): {case['docs'] or 'none'}", f"- result: {_yn(s['part3'])}", ""]
    out += ["### Answer", o.reply, "", f"- time to first piece: {first if first is None else round(first, 2)}",
            f"- total time: {total:.2f}s", ""]
    failed = [p for p in ("route", "no_search", "part1", "part2", "part3") if not s[p]]
    out += ["### Verdict", f"- {_yn(s['passed'])}" + (f" (failed: {', '.join(failed)})" if failed else ""), ""]
    return out


def report_line_and_stats(case, o, s):
    line = (f"{case['id']}: {_yn(s['passed'])} route={o.plan.route} part1={_yn(s['part1'])} "
            f"part2={_yn(s['part2'])} part3={_yn(s['part3'])} retried={'yes' if s['retried'] else 'no'}")
    planned = [pc for pc in o.plan.calls if pc.name != "search_documents"]
    dropped = bool(s["retried"] and any(t.args != pc.args for t, pc in zip(o.tools, planned)))
    return line, {"passed": bool(s["passed"]), "part1": bool(s["part1"]), "part2": bool(s["part2"]),
                  "part3": bool(s["part3"]), "first_invented": bool(s["first_invented"]),
                  "retried": bool(s["retried"]), "dropped": dropped}


def run_case(scorer, case, run_turn, tool_result):
    """Run, score, format and report-line one case entirely inside one error handler: a case whose run, scoring
    or formatting raises is recorded as an error (message in its section and report line) and counts as failed."""
    r = {"case": case, "outcome": None, "score": None, "error": None, "first": None, "total": 0.0,
         "section": "", "line": "", "stats": None}
    first, start = [], time.perf_counter()

    def on_token(piece):
        if not first:
            first.append(time.perf_counter() - start)

    try:
        outcome = run_turn(case, on_token)
        score = scorer.score(case, outcome, tool_result)
        total = time.perf_counter() - start
        section = section_lines(scorer, case, outcome, score, tool_result, first[0] if first else None, total)
        line, stats = report_line_and_stats(case, outcome, score)
        r.update(outcome=outcome, score=score, first=first[0] if first else None, total=total,
                 section=section, line=line, stats=stats)
    except Exception as exc:  # recorded; the run goes on
        msg = " ".join(f"{type(exc).__name__}: {exc}".split())
        r.update(outcome=None, score=None, error=msg, total=time.perf_counter() - start, stats=None,
                 section=_header(case) + [f"- Error: {msg}", ""], line=f"{case['id']}: fail (error: {msg})")
    return r


def build_report(results):
    paths, parts, totals = Counter(), {}, Counter()
    lines = [r["line"] for r in results]
    for r in results:
        st, path = r["stats"], r["case"]["path"]
        if st is None:
            continue
        paths[path] += st["passed"]
        for p in ("part1", "part2", "part3"):
            parts.setdefault(path, Counter())[p] += st[p]
        for k in ("first_invented", "retried", "dropped"):
            totals[k] += st[k]
    lines.append("")
    for path in ("TOOL", "DOCS", "BOTH"):
        lines.append(f"{path}: {paths[path]} of 10 passed; parts " +
                     ", ".join(f"{p}={parts.get(path, Counter())[p]}" for p in ("part1", "part2", "part3")))
    lines += [f"First plans that invented a number: {totals['first_invented']}",
              f"Cases that retried: {totals['retried']}",
              f"Cases that still dropped a value after the retry: {totals['dropped']}"]
    return "\n".join(lines)


def write_log(results, report, log_dir):
    log_dir.mkdir(exist_ok=True)
    path = log_dir / f"golden_calls_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    lines = ["# Golden calls", ""]
    for r in results:
        lines += r["section"]
    lines += ["## Totals", "", report, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def golden_log():
    return SimpleNamespace(run_case=run_case, report=build_report, write_log=write_log, tool_facts=tool_facts,
                           SUBSECTIONS=_SUBSECTIONS)


# --------------------------------------------------------------------------
# Eval environment (NFR-4: skip, do not fail)
# --------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama_available():
    if not _ollama_running():
        pytest.skip("Ollama is not running; start it to run the golden eval.")
    return True


@pytest.fixture(scope="session")
def real_store(ollama_available):
    from pathlib import Path

    import chat

    if not Path(chat.CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py.")
    store = chat.build_store()
    if not store.get(limit=1).get("ids"):
        pytest.skip("Chroma store is empty. Run scripts/ingest.py.")
    return store


@pytest.fixture(scope="session")
def real_llm(ollama_available):
    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL, CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")
    return llm
