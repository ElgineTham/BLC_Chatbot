"""Shared setup for spec 016 (connect the recipe tool; tool-calling eval). Written from the spec only.

Unit tests (AC-1 to AC-3): no Ollama, no Chroma, no network, nothing read under data/ (NFR-2). The beverage
catalog (spec 005 Appendix A) and the recipe test book (spec 015 Appendix A + B) are written to tmp_path.
Helpers are exposed as fixtures so test files never import this module.

Fixtures:
- catalog, bev_tool       the Appendix A catalog and make_bev_tool(catalog)
- book, recipe_tool       the recipe test book (Appendix A + B) and make_recipe_tool(book)
- Scripted, FakeStore     scripted fake chat model (plain invoke list + bound invoke list); fake store
- ai, tc, text_of         build scripted AIMessages and tool-call dicts; join message contents
- docs, doc_mark          a one-document list for the fake store and the marker text inside it
- run_flow                chat.run_turn on a fake store with the given tools patched into chat.CHAT_TOOLS
- b_cases, r_cases        the eval cases B1-B20 and R1-R20 (section 6)
- score_case, Score       the scorer of section 4.2: a pure function on a TurnTrace and a case (NFR-6)
- tool_env                (eval only) the real store and model, warmed up; skips when unavailable (NFR-3)
"""

from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

BEV = "calculate_bev_item"
RECIPE = "scale_recipe"
PKG = "Coffee, decaf, tea, iced water & juice"
ANY = "*"          # "not compared"
HOT_ONLY = "HOT"   # "no drinks, or only hot drinks (any amount)"
HOT_DRINKS = {"Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider"}


# --------------------------------------------------------------------------
# Beverage catalog: copy of spec 005 Appendix A
# --------------------------------------------------------------------------

def _menu():
    return {
        "items": {
            "Coffee": {"unit": "gallon", "also_written_as": ["Fresh-brewed coffee"], "tags": ["HOT", "COFFEE"]},
            "Decaf": {"unit": "gallon", "also_written_as": ["Fresh-brewed decaffeinated coffee"], "tags": ["HOT", "COFFEE"]},
            "Hot water": {
                "unit": "gallon",
                "also_written_as": ["Hot water with an assortment of black, green, and herbal tea bags"],
                "tags": ["HOT", "HOT-WATER"],
            },
            "Brewed hot cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Ginger Honeycrisp apple cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Iced water": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Iced tea": {"unit": "gallon", "also_written_as": ["Iced tea with lemon wedges"], "tags": ["COLD", "ICED-TEA"]},
            "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
            "Lemonade": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Peach tea": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []},
        },
        "packages": {
            PKG: {"includes": ["Coffee", "Decaf", "Hot water", "Iced water"], "placeholders": {"JUICE": "Orange juice"}}
        },
    }


def _rules():
    return {
        "cambros": [
            {"supply": "5 gal cambro", "gallons": 5},
            {"supply": "2 gal cambro", "gallons": 2},
            {"supply": "1 gal cambro", "gallons": 1},
        ],
        "supplies": [
            {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
            {"supply": "cold-cups", "qty": 1, "per": "guest+extra", "when_tagged": "COLD"},
            {"supply": "Cocktail napkins", "tick": True},
            {"supply": "Creamer", "tick": True, "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemon tongs", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "HOT-WATER"},
            {"supply": "Tea packets", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "ICED-TEA"},
        ],
        "extras": [
            {"guests_up_to": 20, "extra": 10},
            {"guests_up_to": 50, "extra": 20},
            {"guests_up_to": 100, "extra": 50},
            {"guests_up_to": None, "extra": 100},
        ],
    }


@pytest.fixture
def catalog(tmp_path):
    from blc.pull_sheet import load_catalog

    for rel, data in (("menu/beverages.json", _menu()), ("rules/beverages.json", _rules())):
        path = tmp_path / "pull_sheet" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalog(tmp_path / "pull_sheet")


@pytest.fixture
def bev_tool(catalog):
    from blc.tools.bev_tools import make_bev_tool

    return make_bev_tool(catalog)


# --------------------------------------------------------------------------
# Recipe test book: spec 015 Appendix A + B
# --------------------------------------------------------------------------

def _recipes():
    return {
        "recipes": {
            "Lemonade": {
                "also_written_as": ["Fresh lemonade"],
                "yield_gallons": 1,
                "ingredients": [{"name": "Lemon concentrate", "amount": 7, "unit": "oz"}, {"name": "Water", "fill": True}],
                "steps": [
                    "Pour the lemon concentrate into a clean container that holds the whole batch.",
                    "Add water until the total volume reaches the batch size.",
                    "Stir well until fully mixed.",
                    "Taste and adjust if needed before service.",
                ],
            },
            "Fruit punch": {
                "also_written_as": ["Punch"],
                "yield_gallons": 2,
                "ingredients": [
                    {"name": "Orange concentrate", "amount": 10, "unit": "oz"},
                    {"name": "Simple syrup", "amount": 3, "unit": "oz"},
                    {"name": "Water", "fill": True},
                ],
                "steps": [
                    "Pour the orange concentrate and simple syrup into a clean container.",
                    "Add water up to the batch size and stir.",
                ],
            },
        }
    }


@pytest.fixture
def book(tmp_path):
    from blc.tools.recipe_tools import load_recipe_book

    path = tmp_path / "recipes" / "recipes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_recipes()), encoding="utf-8")
    return load_recipe_book(path)


@pytest.fixture
def recipe_tool(book):
    from blc.tools.recipe_tools import make_recipe_tool

    return make_recipe_tool(book)


# --------------------------------------------------------------------------
# Scripted fake chat model (spec 006 section 3.2: plain invoke list + bind_tools -> bound invoke list)
# --------------------------------------------------------------------------

def tc(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def ai(content="", calls=()):
    return AIMessage(content=content, tool_calls=list(calls))


def text_of(messages):
    return "\n".join(str(getattr(m, "content", "")) for m in messages)


class _Bound:
    def __init__(self, owner, tools):
        self.owner = owner
        self.tools = tools

    def invoke(self, messages, *args, **kwargs):
        o = self.owner
        o.bound_invocations.append(list(messages))
        o.bound_owner_tools.append([t.name for t in self.tools])
        if not o.bound_script:
            raise AssertionError("tool step asked the model more times than scripted")
        if o.repeat_last and len(o.bound_script) == 1:
            return o.bound_script[0]
        return o.bound_script.pop(0)


class Scripted:
    """llm.invoke(messages) pops `plain` replies (router first when needed, final last); strings become AIMessages.
    llm.bind_tools(tools) returns an object whose invoke pops `bound` replies (tool steps).
    With repeat_last=True the last bound reply is returned forever (for the round limit).
    Records: plain_invocations, bound_invocations (message-list snapshots), bind_calls (tool lists),
    bound_owner_tools (the tool names each bound invoke was bound with)."""

    def __init__(self, plain, bound=(), repeat_last=False):
        self.plain_script = list(plain)
        self.bound_script = list(bound)
        self.repeat_last = repeat_last
        self.plain_invocations = []
        self.bound_invocations = []
        self.bound_owner_tools = []
        self.bind_calls = []

    def invoke(self, messages, *args, **kwargs):
        self.plain_invocations.append(list(messages))
        if not self.plain_script:
            raise AssertionError("llm.invoke was called more times than scripted")
        reply = self.plain_script.pop(0)
        return AIMessage(content=reply) if isinstance(reply, str) else reply

    def bind_tools(self, tools, *args, **kwargs):
        tools = list(tools)
        self.bind_calls.append(tools)
        return _Bound(self, tools)


class FakeStore:
    """similarity_search(query, k=...) -> the fixed docs. Records (query, k)."""

    def __init__(self, docs=()):
        self.docs = list(docs)
        self.calls = []

    def similarity_search(self, query, k=4, *args, **kwargs):
        self.calls.append((query, k))
        return list(self.docs)


DOC_MARK = "Concentrates are kept in the dry store zzdocmarker."


@pytest.fixture(name="Scripted")
def _scripted_fixture():
    return Scripted


@pytest.fixture(name="FakeStore")
def _fake_store_fixture():
    return FakeStore


@pytest.fixture(name="ai")
def _ai_fixture():
    return ai


@pytest.fixture(name="tc")
def _tc_fixture():
    return tc


@pytest.fixture(name="text_of")
def _text_of_fixture():
    return text_of


@pytest.fixture
def doc_mark():
    return DOC_MARK


@pytest.fixture
def docs():
    return [Document(page_content=DOC_MARK, metadata={"source": "data/supplies/concentrates.md"})]


@pytest.fixture
def run_flow(monkeypatch, docs):
    """run_flow(llm, question, tools, history=None, generate=False) -> TurnTrace.
    Patches chat.CHAT_TOOLS to `tools` and runs the real chat.run_turn on a FakeStore(docs)."""
    import chat

    def _run(llm, question, tools, history=None, generate=False):
        monkeypatch.setattr(chat, "CHAT_TOOLS", tuple(tools), raising=False)
        return chat.run_turn(FakeStore(docs), llm, [] if history is None else history, question, generate=generate)

    return _run


# --------------------------------------------------------------------------
# Eval cases (section 6). An expected call is a dict:
#   tool, and for calculate_bev_item:
#     item, status (default ok), drinks [(display name, amount|ANY, from_guests|ANY)] (exact set),
#     drinks_any_of [list | HOT_ONLY, ...], not_on_menu (lower case name), guests (int | None | ANY),
#     no_gallons (args give no gallons), args_mention [lower case words in the call's drinks]
#   for scale_recipe:
#     status (default ok), recipe (display name), gallons, from_guests (default False),
#     guests (int | ANY, default ANY), recipe_as_given (lower case name, for no_recipe)
# --------------------------------------------------------------------------

def _bev(item, drinks=(), guests=None, **extra):
    call = {"tool": BEV, "item": item, "guests": guests}
    if drinks != ANY:
        call["drinks"] = list(drinks)
    call.update(extra)
    return call


def _rec(gallons, from_guests=False, guests=ANY, **extra):
    call = {"tool": RECIPE, "status": "ok", "recipe": "Lemonade", "gallons": Fraction(str(gallons)),
            "from_guests": from_guests, "guests": guests}
    call.update(extra)
    return call


def _case(cid, question, calls, history=()):
    return {"id": cid, "question": question, "history": list(history), "calls": list(calls)}


H_B20 = [
    {"role": "user", "content": "How many cambros do I need for decaf and iced tea?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]
H_R16 = [
    {"role": "user", "content": "How do I make lemonade?"},
    {"role": "assistant", "content": "Pour 7 oz of lemon concentrate into a clean 1-gallon container, add water to 1 gallon and stir."},
]
H_R17 = [
    {"role": "user", "content": "How much lemon concentrate do I need for 4 gallons of lemonade?"},
    {"role": "assistant", "content": "28 oz of lemon concentrate."},
]
_PKG5 = [(d, 5, True) for d in ("Coffee", "Decaf", "Hot water", "Iced water", "Orange juice")]

B_CASES = [
    _case("B1", "How many cambros for 8 gallons of peach tea?", [_bev("cambros", [("Peach tea", 8, False)])]),
    _case("B2", "Which cambros should hold 4 gallons of decaf?", [_bev("cambros", [("Decaf", 4, False)])]),
    _case("B3", "How many cambros for 6 gallons of coffee and 2 gallons of hot water?",
          [_bev("cambros", [("Coffee", 6, False), ("Hot water", 2, False)])]),
    _case("B4", "I have 3 gallons each of iced tea and lemonade, how many cambros?",
          [_bev("cambros", [("Iced tea", 3, False), ("Lemonade", 3, False)])]),
    _case("B5", "How many cambros for brewed hot cider for 60 guests?",
          [_bev("cambros", [("Brewed hot cider", 2, True)], 60)]),
    _case("B6", "What containers do I need for eleven gallons of orange juice?",
          [_bev("cambros", [("Orange juice", 11, False)])]),
    _case("B7", "How many gallons of iced tea for 110 guests?",
          [_bev("gallons", ANY, 110, drinks_any_of=[[("Iced tea", 4, True)], []])]),
    _case("B8", "How many gallons should we make for 65 people?", [_bev("gallons", [], 65)]),
    _case("B9", "How many cups for iced water and orange juice for 45 guests?",
          [_bev("cups", [("Iced water", ANY, ANY), ("Orange juice", ANY, ANY)], 45)]),
    _case("B10", "How many hot cups for 90 guests?", [_bev("cups", ANY, 90, drinks_any_of=[[], HOT_ONLY])]),
    _case("B11", "Cups for the ginger honeycrisp apple cider, 35 guests?",
          [_bev("cups", [("Ginger Honeycrisp apple cider", ANY, ANY)], 35)]),
    _case("B12", "Do I need stir sticks for decaf?",
          [_bev("supplies", ANY, None, drink_arg="decaf", result_has="Stir sticks")]),
    _case("B13", "Should I bring tea packets for hot water?",
          [_bev("supplies", ANY, None, drink_arg="hot water", result_has="Tea packets")]),
    _case("B14", "Do we need lemons for the iced tea for 80 guests?",
          [_bev("supplies", [("Iced tea", 3, True)], 80)]),
    _case("B15", "What do I need to bring for peach tea for 30 guests?",
          [_bev("everything", [("Peach tea", 1, True)], 30)]),
    _case("B16", "What goes on the pull sheet for 5 gallons of decaf?", [_bev("everything", [("Decaf", 5, False)])]),
    _case("B17", "The coffee, decaf, tea, iced water & juice package for 120 guests, what do I bring?",
          [_bev("everything", _PKG5, 120)]),
    _case("B18", "How many cambros for 3 gallons of hot chocolate?",
          [_bev("cambros", ANY, None, status="not_on_menu", not_on_menu="hot chocolate")]),
    _case("B19", "How many cambros for the coffee?",
          [_bev("cambros", ANY, None, status="need_info", args_mention=["coffee"], no_gallons=True)]),
    _case("B20", "45 guests.", [_bev("cambros", [("Decaf", 2, True), ("Iced tea", 2, True)], 45)], H_B20),
]

R_CASES = [
    _case("R1", "How much lemon concentrate for 3 gallons of lemonade?", [_rec(3)]),
    _case("R2", "How many oz of concentrate do I need for 10 gallons of lemonade?", [_rec(10)]),
    _case("R3", "How do I make 5 gallons of lemonade?", [_rec(5)]),
    _case("R4", "How do I make lemonade for 60 guests?", [_rec(2, True, 60)]),
    _case("R5", "How much concentrate for lemonade for 150 guests?", [_rec(6, True, 150)]),
    _case("R6", "How many ounces of lemon concentrate go into 1.5 gallons of lemonade?", [_rec("1.5")]),
    _case("R7", "What's the lemonade recipe for 4 gallons?", [_rec(4)]),
    _case("R8", "How do we make twelve gallons of lemonade?", [_rec(12)]),
    _case("R9", "Ingredients for 7 gallons of fresh lemonade?", [_rec(7)]),
    _case("R10", "How can I make lemonade for 35 people?", [_rec(1, True, 35)]),
    _case("R11", "How much concentrate do I need to make 2.5 gallons of lemonade?", [_rec("2.5")]),
    _case("R12", "Lemonade for 200 guests, how much concentrate?", [_rec(8, True, 200)]),
    _case("R13", "How many oz of concentrate for a 20 gallon batch of lemonade?", [_rec(20)]),
    _case("R14", "Recipe for 8 gallons of lemonade please", [_rec(8)]),
    _case("R15", "How do I make 3 gallons of iced tea?",
          [{"tool": RECIPE, "status": "no_recipe", "recipe_as_given": "iced tea", "guests": ANY}]),
    _case("R16", "And for 7 gallons?", [_rec(7)], H_R16),
    _case("R17", "What about 9 gallons?", [_rec(9)], H_R17),
    _case("R18", "Where are the concentrates kept, and how many ounces of lemon concentrate go into 6 gallons of lemonade?",
          [_rec(6)]),
    _case("R19", "How much lemon concentrate for 4 gallons of lemonade; which cambros hold 4 gallons of lemonade?",
          [_rec(4), _bev("cambros", [("Lemonade", 4, False)])]),
    _case("R20", "How do I make 6 gallons of lemonade for 140 guests?", [_rec(6, False)]),
]


@pytest.fixture
def b_cases():
    return list(B_CASES)


@pytest.fixture
def r_cases():
    return list(R_CASES)


# --------------------------------------------------------------------------
# The scorer (section 4.2): a pure function on a TurnTrace and a case (NFR-6)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Score:
    passed: bool
    stage: str | None     # failures: "router", "no call", "arguments"; a pass after a bad first call: "corrected"; else None
    detail: str           # the problems found ("" on a clean pass)
    first_call: bool      # every part's first call was itself accepted and right


def _is_bad(call):
    """A call the scorer does not accept: refused, or its result starts with invalid or error."""
    result = str(call.result).strip().lower()
    return bool(call.refused) or result.startswith("invalid") or result.startswith("error")


def _unwrap(raw):
    if isinstance(raw, (list, tuple)):
        return raw[0] if len(raw) == 1 else (None if len(raw) == 0 else raw)
    return raw


def _number(args, key):
    """The value a call gave for guests/gallons as an int/float, or None when not given (missing, null, 0, [])."""
    raw = _unwrap(args.get(key))
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return raw
    if value == 0:
        return None
    return int(value) if value == int(value) else value


def _recipe_name(args):
    for key in ("recipe", "drink", "drinks", "name"):
        raw = _unwrap(args.get(key))
        if isinstance(raw, str) and raw.strip():
            return raw.strip().casefold()
    return None


def _drinks_match(got, expected):
    by_name = {d.drink: d for d in got}
    if len(by_name) != len(got) or set(by_name) != {n for n, _, _ in expected}:
        return False
    for name, amount, from_guests in expected:
        d = by_name[name]
        if amount != ANY and d.amount != Fraction(amount):
            return False
        if from_guests != ANY and d.from_guests != from_guests:
            return False
    return True


def _drinks_option_ok(got, option):
    if option == HOT_ONLY:
        return all(d.drink in HOT_DRINKS for d in got)
    return _drinks_match(got, option)


def _check_bev(exp, args, run_bev):
    problems = []
    result = run_bev(args)
    if str(args.get("item", "")).strip().casefold() != exp["item"]:
        problems.append(f"item {args.get('item')!r} != {exp['item']!r}")
    status = exp.get("status", "ok")
    if result.status != status:
        problems.append(f"status {result.status!r} != {status!r}")
    elif status == "ok":
        if "drinks_any_of" in exp:
            if not any(_drinks_option_ok(result.drinks, o) for o in exp["drinks_any_of"]):
                problems.append(f"drinks {result.drinks} match none of {exp['drinks_any_of']}")
        elif "drinks" in exp and not _drinks_match(result.drinks, exp["drinks"]):
            problems.append(f"drinks {result.drinks} != {exp['drinks']}")
    if "not_on_menu" in exp and exp["not_on_menu"] not in {str(n).strip().casefold() for n in result.not_on_menu}:
        problems.append(f"not_on_menu {result.not_on_menu} lacks {exp['not_on_menu']!r}")
    if "drink_arg" in exp:
        # B12, B13 (section 4.2): no amount and no guests gives no resolved drinks, so check the call's own
        # `drinks` argument: it holds exactly that drink's name (stripped, ignoring case).
        raw = args.get("drinks")
        names = [raw] if isinstance(raw, str) else list(raw or [])
        names = [str(n).strip().casefold() for n in names]
        if names != [exp["drink_arg"]]:
            problems.append(f"drinks argument {raw!r} != [{exp['drink_arg']!r}]")
    if "result_has" in exp and exp["result_has"].casefold() not in str(getattr(result, "text", "")).casefold():
        problems.append(f"result text lacks {exp['result_has']!r}")
    for word in exp.get("args_mention", ()):
        if word not in str(args.get("drinks", "")).casefold():
            problems.append(f"drinks {args.get('drinks')!r} do not mention {word!r}")
    if exp.get("no_gallons") and _number(args, "gallons") is not None:
        problems.append(f"gallons {args.get('gallons')!r} given, expected none")
    if exp["guests"] != ANY and _number(args, "guests") != exp["guests"]:
        problems.append(f"guests {_number(args, 'guests')!r} != {exp['guests']!r}")
    return problems


def _check_recipe(exp, args, run_recipe):
    problems = []
    result = run_recipe(args)
    status = exp.get("status", "ok")
    if result.status != status:
        return [f"status {result.status!r} != {status!r}"]
    if status == "ok":
        if result.recipe != exp["recipe"]:
            problems.append(f"recipe {result.recipe!r} != {exp['recipe']!r}")
        if result.gallons != exp["gallons"]:
            problems.append(f"gallons {result.gallons!r} != {exp['gallons']!r}")
        if result.from_guests != exp.get("from_guests", False):
            problems.append(f"from_guests {result.from_guests!r} != {exp.get('from_guests', False)!r}")
    if "recipe_as_given" in exp and _recipe_name(args) != exp["recipe_as_given"]:
        problems.append(f"recipe given {_recipe_name(args)!r} != {exp['recipe_as_given']!r}")
    if exp.get("guests", ANY) != ANY and _number(args, "guests") != exp["guests"]:
        problems.append(f"guests {_number(args, 'guests')!r} != {exp['guests']!r}")
    return problems


def _check_call(exp, args, run_bev, run_recipe):
    return _check_bev(exp, args, run_bev) if exp["tool"] == BEV else _check_recipe(exp, args, run_recipe)


def score_case(trace, case, run_bev, run_recipe):
    """Section 4.2. Pure: reads the trace and the case; run_bev / run_recipe run the calculators on a call's args."""
    expected = case["calls"]
    parts = [] if trace.route is None else [p for p in trace.route.parts if p.route == "TOOL"]
    if [p.tool for p in parts] != [e["tool"] for e in expected]:
        return Score(False, "router", f"TOOL parts {[p.tool for p in parts]} != {[e['tool'] for e in expected]}", False)
    stages = list(trace.tools)
    corrected, first_ok = False, True
    for i, (part, exp) in enumerate(zip(parts, expected)):
        calls = list(stages[i].calls) if i < len(stages) else []
        if not calls or any(c.name != part.tool for c in calls):
            return Score(False, "no call", f"part {i + 1}: calls {[c.name for c in calls]}", False)
        accepted = [c for c in calls if not _is_bad(c)]
        if not accepted:
            return Score(False, "arguments", f"part {i + 1}: every call was refused or invalid", False)
        problems = _check_call(exp, accepted[-1].args, run_bev, run_recipe)
        if problems:
            return Score(False, "arguments", f"part {i + 1}: " + "; ".join(problems), False)
        if _is_bad(calls[0]):
            corrected = True
        if _is_bad(calls[0]) or _check_call(exp, calls[0].args, run_bev, run_recipe):
            first_ok = False
    return Score(True, "corrected" if corrected else None, "", first_ok)


@pytest.fixture(name="score_case")
def _score_case_fixture():
    return score_case


# --------------------------------------------------------------------------
# Eval environment (NFR-3: skip, do not fail; warm the model up with one call)
# --------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def tool_env():
    """The real store and model, built once. Skips when Ollama is not running, the store is empty or
    missing, or data/recipes/recipes.json is missing. Reads only; nothing is written to data/ or .chroma/."""
    if not _ollama_running():
        pytest.skip("Ollama is not running; start it to run the tool-calling eval.")
    import chat
    from blc.tools.recipe_tools import RECIPES_FILE
    from langchain_ollama import ChatOllama

    if not Path(RECIPES_FILE).exists():
        pytest.skip(f"{RECIPES_FILE} is missing; the recipe tool has no recipes.")
    if not Path(chat.CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {chat.CHROMA_DIR}. Run scripts/ingest.py.")
    store = chat.build_store()
    if not (store.get(include=["metadatas"]).get("ids") or []):
        pytest.skip("The Chroma store is empty. Run scripts/ingest.py.")
    llm = ChatOllama(model=chat.CHAT_MODEL, temperature=0, keep_alive=chat.CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")  # warm-up: loads the model
    return SimpleNamespace(store=store, llm=llm, chat=chat, results=None)
