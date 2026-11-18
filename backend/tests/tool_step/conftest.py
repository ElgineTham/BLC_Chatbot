"""Shared setup for spec 008 (tool-step eval). Written from the spec only.

Everything here is eval-only: real Ollama, real model, real menu and rules under data/pull_sheet/.
Nothing is written to .chroma/ or data/ and .chroma/ is never read (EC-2).

Case expectation keys (spec section 4.2):
  id, question
  item:    the expected args["item"]
  status:  expected run_bev_tool status (default "ok")
  drinks:  None -> not checked; else a list of alternatives, each alternative being a list of
           (display name, amount or ANY, from_guests True/False/ANY). An empty alternative []
           means "no drinks". Any one alternative matching is enough.
  hot_only / cold_only: alternative to "no drinks": a subset of the hot (cold) drinks is fine too.
  guests:  int (must be the number given) | None ("no guests": missing, null or 0)
  no_amount:  True for questions containing no number (S3, S6, S16, S19, S25): the call must pass
           neither guests nor gallons (missing, null, 0 or empty list), revision 1 / EC-8.
  names_only: list of display names (S16, S19, S25): BevResult.drinks is empty for these, so each
           name must appear in BevResult.text, ignoring case (revision 1 / EC-9).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ANY = "*"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

HOT_DRINKS = {"Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider"}
COLD_DRINKS = {"Iced water", "Iced tea", "Orange juice", "Lemonade", "Peach tea"}

PACKAGE_DRINKS = [
    ("Coffee", 3, True), ("Decaf", 3, True), ("Hot water", 3, True),
    ("Iced water", 3, True), ("Orange juice", 3, True),
]


def _case(cid, question, item, drinks, guests, status="ok", **extra):
    case = {"id": cid, "question": question, "item": item, "status": status,
            "drinks": drinks, "guests": guests}
    case.update(extra)
    return case


CASES = [
    _case("S1", "How many cambros do I need to bring for 7 gallons of lemonade?",
          "cambros", [[("Lemonade", 7, ANY)]], None),
    _case("S2", "How many gallons of coffee do I need for 75 people?",
          "gallons", [[("Coffee", 3, True)], []], 75),
    _case("S3", "How many cambros do I need for coffee and lemonade?",
          "cambros", None, None, status="need_info", no_amount=True),
    _case("S4", "How many cambros for 5 gallons of coffee and 5 gallons of lemonade?",
          "cambros", [[("Coffee", 5, ANY), ("Lemonade", 5, ANY)]], None),
    _case("S5", "I need 5 gallons of coffee and lemonade. How many cambros?",
          "cambros", [[("Coffee", 5, ANY), ("Lemonade", 5, ANY)]], None),
    _case("S6", "How many cups do I need for coffee?",
          "cups", None, None, status="need_info", no_amount=True),
    _case("S7", "5 gallons of coffee and 3 gallons of lemonade, how many cambros?",
          "cambros", [[("Coffee", 5, ANY), ("Lemonade", 3, ANY)]], None),
    _case("S8", "Coffee and lemonade for 70 guests, how many cups?",
          "cups", [[("Coffee", ANY, ANY), ("Lemonade", ANY, ANY)]], 70),
    _case("S9", "How many cambros for lemonade for 70 guests?",
          "cambros", [[("Lemonade", 3, True)]], 70),
    _case("S10", "How many cambros for 4 gallons of hot chocolate?",
          "cambros", None, None, status="not_on_menu"),
    _case("S11", "How many cambros for 7 gallons of fresh-brewed coffee?",
          "cambros", [[("Coffee", 7, ANY)]], None),
    _case("S12", "We have the coffee, decaf, tea, iced water & juice package for 70 guests. "
                 "How many cambros?",
          "cambros", [PACKAGE_DRINKS], 70),
    _case("S13", "What do I put 7 gallons of lemonade in?",
          "cambros", [[("Lemonade", 7, ANY)]], None),
    _case("S14", "Seven gallons of lemonade, which containers do I bring?",
          "cambros", [[("Lemonade", 7, ANY)]], None),
    _case("S15", "What do I need to bring for coffee for 50 guests?",
          "everything", [[("Coffee", 2, True)]], 50),
    _case("S16", "Do I need sugar for coffee?",
          "supplies", None, None, no_amount=True, names_only=["Coffee"]),
    _case("S17", "How many gallons do I make for 25 people?",
          "gallons", [[]], 25),
    _case("S18", "How many hot cups do I need for 40 guests?",
          "cups", [[]], 40, only=HOT_DRINKS),
    _case("S19", "How many napkins should I grab for the iced tea station?",
          "supplies", None, None, no_amount=True, names_only=["Iced tea"]),
    _case("S20", "Which jugs do I fill with 9 gallons of iced water?",
          "cambros", [[("Iced water", 9, ANY)]], None),
    _case("S21", "Brewed hot cider for 100 people, what goes on the pull sheet?",
          "everything", [[("Brewed hot cider", 4, True)]], 100),
    _case("S22", "Do I bring lemon tongs for hot water for 30 guests?",
          "supplies", [[("Hot water", 1, True)]], 30),
    _case("S23", "What should I pack for orange juice for 40 guests?",
          "everything", [[("Orange juice", 2, True)]], 40),
    _case("S24", "How many cold cups for 55 guests?",
          "cups", [[]], 55, only=COLD_DRINKS),
    _case("S25", "Do I need creamer for decaf?",
          "supplies", None, None, no_amount=True, names_only=["Decaf"]),
    _case("S26", "How many cambros do I need for 3 gallons of peach tea and 6 gallons of orange juice?",
          "cambros", [[("Peach tea", 3, ANY), ("Orange juice", 6, ANY)]], None),
    _case("S27", "How many gallons of lemonade do I make for 90 people?",
          "gallons", [[("Lemonade", 4, True)], []], 90),
    _case("S28", "How many cups for 20 guests of coffee?",
          "cups", [[("Coffee", ANY, ANY)]], 20),
]


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        metafunc.parametrize("case", CASES, ids=[c["id"] for c in CASES])


def _installed_models():
    """Return the set of installed model names, or None if Ollama is not reachable."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return {m.get("name", "") for m in data.get("models", [])}


@pytest.fixture(scope="session")
def chat_model_name():
    """EC-1: skip when Ollama is not running or CHAT_MODEL is not installed."""
    from chat import CHAT_MODEL

    names = _installed_models()
    if names is None:
        pytest.skip("Ollama is not running; start it to run the tool-step eval.")
    if CHAT_MODEL not in names and f"{CHAT_MODEL}:latest" not in names:
        pytest.skip(f"Model {CHAT_MODEL} is not installed in Ollama.")
    return CHAT_MODEL


@pytest.fixture(scope="session")
def bound_model(chat_model_name):
    """The real model with only the real beverage tool bound (spec section 3)."""
    from blc.tools.bev_tools import BEV_TOOL
    from chat import CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=chat_model_name, temperature=CHAT_TEMPERATURE)
    return llm.bind_tools([BEV_TOOL])


# --------------------------------------------------------------------------
# Checking helpers, exposed as fixtures so test files never import this module.
# --------------------------------------------------------------------------

def guests_given(args):
    """The call's guests as an int, or None when missing, null or 0. Unreadable values are returned raw."""
    raw = args.get("guests")
    if raw is None:
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return raw
    return None if value == 0 else value


def not_given(value):
    """True for missing, null, 0, empty string or empty list/dict (an amount that was not given)."""
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict, str)):
        if len(value) == 0:
            return True
        if isinstance(value, str):
            try:
                return float(value) == 0
            except ValueError:
                return False
        return False
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _amount_equal(got, expected):
    if got is None:
        return False
    try:
        return abs(float(got) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def drinks_match(got, expected):
    """got: BevResult.drinks; expected: [(name, amount|ANY, from_guests|ANY)], same names, any order."""
    by_name = {d.drink: d for d in got}
    if len(by_name) != len(got) or set(by_name) != {n for n, _, _ in expected}:
        return False
    for name, amount, from_guests in expected:
        d = by_name[name]
        if amount != ANY and not _amount_equal(d.amount, amount):
            return False
        if from_guests != ANY and d.from_guests != from_guests:
            return False
    return True


def drinks_ok(case, got):
    """Check 4 drinks part. `only`: no drinks, or every drink in the allowed set."""
    only = case.get("only")
    if only is not None:
        return all(d.drink in only for d in got)
    return any(drinks_match(got, alt) for alt in case["drinks"])


@pytest.fixture
def check_call():
    """check_call(case, call) -> (errors, status, drink names) for one call (checks 2 to 4)."""
    from blc.tools.bev_tools import BEV_TOOL_NAME, run_bev_tool

    def _check(case, call):
        errors = []
        if call.name != BEV_TOOL_NAME:
            errors.append(f"check 2 (right tool): call to {call.name!r}, expected {BEV_TOOL_NAME!r}")
        if call.args.get("item") != case["item"]:
            errors.append(f"check 3 (right item): item {call.args.get('item')!r} != {case['item']!r}")
        try:
            result = run_bev_tool(call.args)
        except Exception as exc:  # the calculator should never raise; report it as a failure
            errors.append(f"check 4 (right result): run_bev_tool raised {exc!r}")
            return errors, "raised", []
        drinks = list(result.drinks)
        if result.status != case["status"]:
            errors.append(f"check 4 (right result): status {result.status!r} != {case['status']!r}")
        elif result.status == "ok" and case["drinks"] is not None and not drinks_ok(case, drinks):
            errors.append(f"check 4 (right result): drinks {_show(drinks)} do not match "
                          f"{'only ' + str(sorted(case['only'])) if case.get('only') is not None else case['drinks']}")
        if result.status == "ok" and case["status"] == "ok" and case.get("names_only"):
            text = str(getattr(result, "text", "")).lower()
            for name in case["names_only"]:
                if name.lower() not in text:
                    errors.append(f"check 4 (right result): drink {name!r} not found in result text")
        given = guests_given(call.args)
        if given != case["guests"]:
            errors.append(f"check 4 (right result): guests {given!r} != {case['guests']!r}")
        if case.get("no_amount"):
            for key in ("guests", "gallons"):
                if not not_given(call.args.get(key)):
                    errors.append(f"no invented amounts: call passed {key}={call.args.get(key)!r} "
                                  f"but the question has no number")
        return errors, result.status, drinks

    return _check


def _show(drinks):
    return [(d.drink, d.amount, d.from_guests) for d in drinks]


@pytest.fixture
def describe_drinks():
    return _show


# --------------------------------------------------------------------------
# Spec 009 unit-test setup (AC-1 to AC-3): no Ollama, no network, nothing read under data/.
# The catalog is the spec 005 Appendix A catalog, written to tmp_path.
# --------------------------------------------------------------------------

PKG = "Coffee, decaf, tea, iced water & juice"


def _menu():
    def hot(tags, also=()):
        return {"unit": "gallon", "also_written_as": list(also), "tags": tags}

    return {
        "items": {
            "Coffee": hot(["HOT", "COFFEE"], ["Fresh-brewed coffee"]),
            "Decaf": hot(["HOT", "COFFEE"], ["Fresh-brewed decaffeinated coffee"]),
            "Hot water": hot(["HOT", "HOT-WATER"],
                             ["Hot water with an assortment of black, green, and herbal tea bags"]),
            "Brewed hot cider": hot(["HOT", "CIDER"]),
            "Ginger Honeycrisp apple cider": hot(["HOT", "CIDER"]),
            "Iced water": hot(["COLD"]),
            "Iced tea": hot(["COLD", "ICED-TEA"], ["Iced tea with lemon wedges"]),
            "Orange juice": hot(["COLD", "JUICE"]),
            "Lemonade": hot(["COLD"]),
            "Peach tea": hot(["COLD"]),
            "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []},
        },
        "packages": {
            PKG: {"includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
                  "placeholders": {"JUICE": "Orange juice"}}
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
def bev_tool(tmp_path):
    """make_bev_tool(Appendix A catalog)."""
    from blc.pull_sheet import load_catalog
    from blc.tools.bev_tools import make_bev_tool

    for rel, data in (("menu/beverages.json", _menu()), ("rules/beverages.json", _rules())):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return make_bev_tool(load_catalog(tmp_path))


@pytest.fixture
def bev_spy(bev_tool):
    """(tool, calls): a tool named BEV_TOOL_NAME that records each invocation and delegates to bev_tool."""
    from blc.tools.bev_tools import BEV_TOOL_NAME
    from langchain_core.tools import StructuredTool

    calls = []

    def _fn(**kwargs):
        args = {k: v for k, v in kwargs.items() if v is not None}
        calls.append(args)
        return bev_tool.invoke(args)

    tool = StructuredTool.from_function(
        func=_fn, name=BEV_TOOL_NAME, description=bev_tool.description,
        args_schema=bev_tool.args_schema,
    )
    return tool, calls


@pytest.fixture
def other_tool():
    """(tool, calls): a tool with another name; it takes a guests argument."""
    from langchain_core.tools import StructuredTool

    calls = []

    def _fn(guests: int = 0) -> str:
        calls.append({"guests": guests})
        return "other-result"

    tool = StructuredTool.from_function(func=_fn, name="other_tool", description="fake tool for tests")
    return tool, calls


def tc(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def ai(calls=()):
    from langchain_core.messages import AIMessage

    return AIMessage(content="", tool_calls=list(calls))


class ScriptedBound:
    """Stands in for llm.bind_tools(...). invoke pops scripted AIMessages; with repeat_last the last
    reply is returned forever. `invocations` holds a snapshot of the message list of each invoke."""

    def __init__(self, script, repeat_last=False):
        self.script = list(script)
        self.repeat_last = repeat_last
        self.invocations = []

    def invoke(self, messages, *args, **kwargs):
        self.invocations.append(list(messages))
        if not self.script:
            raise AssertionError("tool step asked the model more times than scripted")
        if self.repeat_last and len(self.script) == 1:
            return self.script[0]
        return self.script.pop(0)


@pytest.fixture
def make_bound():
    return ScriptedBound


@pytest.fixture(name="tc")
def _tc_fixture():
    return tc


@pytest.fixture(name="ai")
def _ai_fixture():
    return ai
