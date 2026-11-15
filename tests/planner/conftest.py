"""Shared fixtures and helpers for the planner tests (spec 018, revision 2).

Unit tests: no Ollama, no Chroma, no network, nothing read under data/.

Exposes (as fixtures, so no test imports from conftest):
- make_llm      build a scripted fake chat model from a reply
- mk            reply builders (mk.ai, mk.raw)
- score         the pure scorer of spec 4.3: score(case, plan) -> set of failed checks
- cases         the 30 eval cases by id
- ollama_available / planner_llm   (eval only) skip when Ollama is not running
"""
import re
import urllib.request
from collections import Counter
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

LOC = ("where", "locat", "kept", "stor", "find", "plac")


# --------------------------------------------------------------------------
# Scripted fake model
# --------------------------------------------------------------------------

class FakeBound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        if self.parent.raises is not None:
            raise self.parent.raises
        return self.parent.reply


class FakeLLM:
    def __init__(self, reply=None, raises=None):
        self.reply = reply
        self.raises = raises
        self.bind_calls = []
        self.invoke_calls = []

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(tools)
        return FakeBound(self)

    def invoke(self, *args, **kwargs):  # the unbound model must not be invoked
        raise AssertionError("invoke called on the unbound model")


def tc(name, args, idx=1):
    return {"name": name, "args": args, "id": f"call_{idx}"}


def ai(*calls, content=""):
    """AIMessage with the given (name, args) tool calls."""
    return AIMessage(
        content=content,
        tool_calls=[tc(n, a, i) for i, (n, a) in enumerate(calls, 1)],
    )


def raw_reply(*calls, content=""):
    """Reply object that skips AIMessage validation (e.g. args=None)."""
    return SimpleNamespace(
        content=content,
        tool_calls=[tc(n, a, i) for i, (n, a) in enumerate(calls, 1)],
    )


@pytest.fixture(scope="session")
def mk():
    """Reply builders: mk.ai(...) is an AIMessage, mk.raw(...) skips validation."""
    return SimpleNamespace(ai=ai, raw=raw_reply)


@pytest.fixture
def make_llm():
    def _make(reply=None, raises=None):
        return FakeLLM(reply, raises)
    return _make


# --------------------------------------------------------------------------
# Eval cases (spec section 6)
# --------------------------------------------------------------------------

def bev(item, drinks=(), gallons=(), guests=None):
    """Expected calculate_bev_item call; gallons pair with drinks by position."""
    return {"name": BEV, "item": item, "drinks": list(drinks),
            "gallons": list(gallons), "guests": guests}


def rec(recipe, gallons=None, guests=None):
    """Expected scale_recipe call; gallons is a single number or None."""
    return {"name": REC, "recipe": recipe, "gallons": gallons, "guests": guests}


def _case(cid, route, question, tools=(), keep=(), drop=(), history=None):
    return {"id": cid, "route": route, "question": question, "history": history,
            "tools": list(tools), "keep": [tuple(k) for k in keep], "drop": list(drop)}


_ASK = "How many gallons of each drink, or how many guests?"
_HIST_CIDER = [
    {"role": "user", "content": "How many cambros do I need for brewed hot cider?"},
    {"role": "assistant", "content": _ASK},
]
_HIST_EACH = [
    {"role": "user", "content": "How many cambros for coffee and decaf?"},
    {"role": "assistant", "content": _ASK},
]
_HIST_THREE = [
    {"role": "user", "content": "How many cambros for coffee, iced water, and hot water?"},
    {"role": "assistant", "content": _ASK},
]
_HIST_SYRUP = [
    {"role": "user", "content": "Where are the syrups?"},
    {"role": "assistant", "content": "Above the lemons in the beverage cooler, near the sink by the coffee machine (data/supplies/syrups.md)."},
]
_HIST_LEMON = [
    {"role": "user", "content": "How do I make 2 gallons of lemonade?"},
    {"role": "assistant", "content": "Use 14 oz of lemon concentrate and fill with water to 2 gallons."},
]

_CASES = [
    _case("T1", "TOOL", "How many cambros do I need for 7 gallons of peach tea and 3 gallons of hot water?",
          [bev("cambros", ["peach tea", "hot water"], [7, 3])]),
    _case("T2", "TOOL", "How many gallons of coffee should I make for 160 guests?",
          [bev("gallons", ["coffee"], [], 160)]),
    _case("T3", "TOOL", "How many cups for 45 guests?", [bev("cups", [], [], 45)]),
    _case("T4", "TOOL", "What goes on the pull sheet for 6 gallons of orange juice?",
          [bev("everything", ["orange juice"], [6])]),
    _case("T5", "TOOL", "How many cups for iced tea and lemonade for 90 guests?",
          [bev("cups", ["iced tea", "lemonade"], [], 90)]),
    _case("T6", "TOOL", "How do I make lemonade?", [rec("lemonade")]),
    _case("T7", "TOOL", "How do I make lemonade for 60 guests?", [rec("lemonade", None, 60)]),
    _case("T8", "TOOL", "How do I make 4 gallons of lemonade and how many cambros do I need for it?",
          [rec("lemonade", 4), bev("cambros", ["lemonade"], [4])]),
    _case("T9", "TOOL", "For 75 guests.",
          [bev("cambros", ["brewed hot cider"], [], 75)], history=_HIST_CIDER),
    _case("T10", "TOOL", "5 gallons each.",
          [bev("cambros", ["coffee", "decaf"], [5, 5])], history=_HIST_EACH),

    _case("D1", "DOCS", "What supplies do I need for coffee and hot water?",
          keep=[("coffee",), ("hot water",), ("suppl", "bring", "need")]),
    _case("D2", "DOCS", "Should I bring lemons for the iced tea?",
          keep=[("lemon",), ("iced tea",)]),
    _case("D3", "DOCS", "Where do the 5 gallon cambros go?",
          keep=[("cambro",), ("5",), LOC + ("go",)]),
    _case("D4", "DOCS", "Is lemonade served in a cambro?",
          keep=[("lemonade",), ("cambro",), ("serv",)]),
    _case("D5", "DOCS", "What flavors of syrup do we have?", keep=[("syrup",), ("flavor",)]),
    _case("D6", "DOCS", "Never mind that. What do I need to bring for them?",
          keep=[("coffee",), ("iced water",), ("hot water",), ("bring", "need", "suppl")],
          history=_HIST_THREE),
    _case("D7", "DOCS", "What's in the coffee, decaf, tea, iced water & juice package?",
          keep=[("package",)]),
    _case("D8", "DOCS", "How do I pull stock of concentrates?",
          keep=[("concentrate",), ("pull", "stock")]),
    _case("D9", "DOCS", "When do we bring hot cups?",
          keep=[("hot cup",), ("when", "bring", "rule")]),
    _case("D10", "DOCS", "What if there are none there?",
          keep=[("syrup",), ("backup", "none", "else", "other", "empty", "out of", "no syrup",
                                "not found", "not there")],
          history=_HIST_SYRUP),

    _case("M1", "BOTH", "Where are the cambros kept and how many do I need for 6 gallons of iced tea?",
          [bev("cambros", ["iced tea"], [6])], [("cambro",), LOC], ["6"]),
    _case("M2", "BOTH", "How many cups for coffee for 80 guests, and where are the hot cups stored?",
          [bev("cups", ["coffee"], [], 80)], [("hot cup",), LOC], ["80"]),
    _case("M3", "BOTH", "Where is the lemon concentrate, and how much do I need for 3 gallons of lemonade?",
          [rec("lemonade", 3)], [("concentrate",), LOC], ["3"]),
    _case("M4", "BOTH", "How many cambros for 4 gallons of decaf, and where is the oatmilk?",
          [bev("cambros", ["decaf"], [4])], [("oatmilk", "oat milk"), LOC], ["4"]),
    _case("M5", "BOTH", "How many cambros to bring for 3 gallons of coffee and what stuffs do I need to bring",
          [bev("cambros", ["coffee"], [3])],
          [("coffee",), ("bring", "stuff", "need", "suppl")], ["3"]),
    _case("M6", "BOTH", "What flavors of concentrate do we have, and how do I make 5 gallons of lemonade?",
          [rec("lemonade", 5)], [("concentrate",), ("flavor",)], ["5"]),
    _case("M7", "BOTH", "Is iced tea served in a cambro, and how many gallons of iced tea do I make for 120 guests?",
          [bev("gallons", ["iced tea"], [], 120)], [("iced tea",), ("cambro",)], ["120"]),
    _case("M8", "BOTH", "How many cups for peach tea for 40 guests, and do we bring lemons for it?",
          [bev("cups", ["peach tea"], [], 40)], [("lemon",), ("peach tea",)], ["40"]),
    _case("M9", "BOTH", "Where do the 5 gallon cambros go, and how many cambros do I need for 12 gallons of orange juice?",
          [bev("cambros", ["orange juice"], [12])],
          [("cambro",), ("5",), LOC + ("go",)], ["12"]),
    _case("M10", "BOTH", "Where is the concentrate kept, and how much do I need for 6 gallons instead?",
          [rec("lemonade", 6)], [("concentrate",), LOC], ["6"], history=_HIST_LEMON),
]


@pytest.fixture(scope="session")
def cases():
    return {c["id"]: c for c in _CASES}


# --------------------------------------------------------------------------
# The scorer (spec 4.3): pure function of a case and a Plan
# --------------------------------------------------------------------------

def _num(v):
    """Number by value; numeric strings count; booleans never. Raises ValueError otherwise."""
    if isinstance(v, bool):
        raise ValueError(v)
    if isinstance(v, (int, float, str)):
        return float(v)
    raise ValueError(v)


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _norm_name(s):
    return str(s).strip().casefold()


def _pairs(drinks, gallons):
    """Multiset of (drink, gallons), or None on a mismatch (bad number or bad count)."""
    try:
        g = [_num(x) for x in _as_list(gallons)]
    except (TypeError, ValueError):
        return None
    if not g:
        return Counter((d, None) for d in drinks)
    if len(g) == 1:
        if not drinks:
            return Counter([(None, g[0])])
        return Counter((d, g[0]) for d in drinks)
    if len(g) != len(drinks):
        return None
    return Counter(zip(drinks, g))


def _single(v):
    """Recipe gallons: a number, None, or a bad marker."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        if len(v) == 0:
            return None
        if len(v) != 1:
            return ("bad", "list")
        v = v[0]
    try:
        return _num(v)
    except (TypeError, ValueError):
        return ("bad", str(v))


def _guests(v):
    if v is None:
        return None
    try:
        return _num(v)
    except (TypeError, ValueError):
        return ("bad", str(v))


def _match(exp, act):
    if exp["name"] != act.name:
        return False
    a = act.args if isinstance(act.args, dict) else {}
    if exp["name"] == BEV:
        if a.get("item") != exp["item"]:
            return False
        drinks = [_norm_name(d) for d in _as_list(a.get("drinks"))]
        edrinks = [_norm_name(d) for d in exp["drinks"]]
        if Counter(drinks) != Counter(edrinks):
            return False
        pa = _pairs(drinks, a.get("gallons"))
        pe = _pairs(edrinks, exp["gallons"])
        if pa is None or pa != pe:
            return False
    else:
        r = a.get("recipe")
        if not isinstance(r, str) or _norm_name(r) != _norm_name(exp["recipe"]):
            return False
        if _single(a.get("gallons")) != _single(exp["gallons"]):
            return False
    return _guests(a.get("guests")) == _guests(exp["guests"])


def _multiset_match(expected, actual):
    """Each expected call matches exactly one actual call; no extras (backtracking)."""
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
    for group in case["keep"]:
        if not any(t in joined for t in group):
            return False
    for term in case["drop"]:
        pat = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
        if any(pat.search(q) for q in queries):
            return False
    return True


def score_case(case, plan):
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


@pytest.fixture(scope="session")
def score():
    return score_case


# --------------------------------------------------------------------------
# Eval environment (NFR-3: skip, do not fail)
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
        pytest.skip("Ollama is not running; start it to run the planner eval.")
    return True


@pytest.fixture(scope="session")
def planner_llm(ollama_available):
    """The real chat model (spec 4.3), warmed up with one call."""
    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL, CHAT_TEMPERATURE
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE)
    llm.invoke("Reply with one word: ready")
    return llm
