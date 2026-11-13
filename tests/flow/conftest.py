"""Shared setup for spec 011 (flow trace and stage eval). Written from the spec only.

Unit tests (AC-1 to AC-3): no Ollama, no network, no Chroma store, nothing read under data/.
Helpers are exposed as fixtures so test files never import this module.

Fixtures (unit):
- catalog / bev_tool    the spec 005 Appendix A catalog (written to tmp_path) and make_bev_tool(catalog)
- Scripted              scripted fake chat model (plain invoke list + bound invoke list)
- FakeStore, Doc        fake store with similarity_search(query, k=...) and a Document builder
- NoCallStore, NoCallLLM  objects that fail the test on any use
- ai, tc                build scripted AIMessages and tool-call dicts
- full_trace            a TurnTrace holding every stage (for the formatters)

Eval-only (AC-5): E1 to E21 cases, parametrisation, the real store/model (session scoped), and
the stage-check helpers.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

PKG = "Coffee, decaf, tea, iced water & juice"
ANY = "*"


# --------------------------------------------------------------------------
# Appendix A catalog (copy of spec 005 Appendix A, as in tests/router/conftest.py)
# --------------------------------------------------------------------------

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
def catalog(tmp_path):
    from blc.pull_sheet import load_catalog

    for rel, data in (("menu/beverages.json", _menu()), ("rules/beverages.json", _rules())):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalog(tmp_path)


@pytest.fixture
def bev_tool(catalog):
    from blc.tools.bev_tools import make_bev_tool

    return make_bev_tool(catalog)


# --------------------------------------------------------------------------
# Scripted fake chat model (spec 006 section 3.2), accepting the router's format= keyword
# --------------------------------------------------------------------------

def tc(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def ai(content="", calls=()):
    return AIMessage(content=content, tool_calls=list(calls))


class _Bound:
    def __init__(self, owner):
        self.owner = owner

    def invoke(self, messages, *args, **kwargs):
        o = self.owner
        o.bound_invocations.append(list(messages))
        if not o.bound_script:
            raise AssertionError("tool step asked the model more times than scripted")
        if o.repeat_last and len(o.bound_script) == 1:
            return o.bound_script[0]
        return o.bound_script.pop(0)


class Scripted:
    """llm.invoke(messages, **kw) pops `plain` replies (summary if any, router, final last); strings
    become AIMessages. llm.bind_tools(tools) returns an object whose invoke pops `bound` replies."""

    def __init__(self, plain, bound=(), repeat_last=False):
        self.plain_script = list(plain)
        self.bound_script = list(bound)
        self.repeat_last = repeat_last
        self.plain_invocations = []
        self.bound_invocations = []
        self.bind_calls = []

    def invoke(self, messages, *args, **kwargs):
        self.plain_invocations.append(list(messages))
        if not self.plain_script:
            raise AssertionError("llm.invoke was called more times than scripted")
        reply = self.plain_script.pop(0)
        return AIMessage(content=reply) if isinstance(reply, str) else reply

    def bind_tools(self, tools, *args, **kwargs):
        self.bind_calls.append(list(tools))
        return _Bound(self)


class FakeStore:
    """similarity_search(query, k=...) -> the fixed docs. Records (query, k)."""

    def __init__(self, docs=()):
        self.docs = list(docs)
        self.calls = []

    def similarity_search(self, query, k=4, *args, **kwargs):
        self.calls.append((query, k))
        return list(self.docs)


class NoCallStore:
    def __getattr__(self, name):
        raise AssertionError(f"store.{name} must not be touched")


class NoCallLLM:
    def __getattr__(self, name):
        raise AssertionError(f"llm.{name} must not be touched")


def doc(text, source="data/supplies/coffee.md"):
    return Document(page_content=text, metadata={"source": source} if source is not None else {})


@pytest.fixture(name="Scripted")
def _scripted_fixture():
    return Scripted


@pytest.fixture(name="FakeStore")
def _fake_store_fixture():
    return FakeStore


@pytest.fixture(name="NoCallStore")
def _no_call_store_fixture():
    return NoCallStore


@pytest.fixture(name="NoCallLLM")
def _no_call_llm_fixture():
    return NoCallLLM


@pytest.fixture(name="doc")
def _doc_fixture():
    return doc


@pytest.fixture(name="ai")
def _ai_fixture():
    return ai


@pytest.fixture(name="tc")
def _tc_fixture():
    return tc


@pytest.fixture
def full_trace():
    """A TurnTrace with every stage set: BOTH route, two chunks, one tool stage with a refused call
    and a run call, and a reply."""
    from blc.router import RouteDecision, RoutedPart
    from blc.trace import RetrievalStage, RetrievedChunk, ToolCallLog, ToolStage, TurnTrace

    return TurnTrace(
        question="Where are lemons kept? How many cups?",
        history=(
            {"role": "user", "content": "hist-one"},
            {"role": "assistant", "content": "hist-two"},
            {"role": "user", "content": "hist-three"},
        ),
        retrieval=RetrievalStage(
            "Where are lemons kept? How many cups?", 3,
            (RetrievedChunk(1, "data/supplies/lemon.md", "zzchunkone lemons are by the sink"),
             RetrievedChunk(2, "data/supplies/coffee.md", "zzchunktwo coffee is in the beverage room")),
        ),
        route=RouteDecision(
            (RoutedPart("DOCS", "Where are lemons kept?"), RoutedPart("TOOL", "How many cups?")),
            "BOTH", False,
        ),
        tools=(
            ToolStage(
                "How many cups?",
                (ToolCallLog("calculate_bev_item", {"item": "cups", "guests": 50},
                             "invalid (check): REFUSEDREASON", True),
                 ToolCallLog("calculate_bev_item", {"item": "cups", "drinks": ["lemonade"]},
                             "RESULTOKTEXT", False)),
                "RESULTOKTEXT", False,
            ),
        ),
        reply="The final reply zzreply.",
    )


# --------------------------------------------------------------------------
# Eval cases (spec 011 section 4.6). Expectation keys:
#   id, history, question, kind, sources, must (words in retrieved text), tool (dict or None)
#   tool: item, status, drinks (None = not checked | list of alternatives, each a list of
#         (display name, amount|ANY, from_guests|ANY); [] = "no drinks"), guests (int | None),
#         no_amount (question has no number), names_only (names that must appear in BevResult.text)
# --------------------------------------------------------------------------

H15 = [
    {"role": "user", "content": "How many cambros do I need for coffee and lemonade?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]


def _tool(item, status="ok", drinks=None, guests=None, **extra):
    spec = {"item": item, "status": status, "drinks": drinks, "guests": guests}
    spec.update(extra)
    return spec


def _case(cid, question, kind, sources=(), must=(), tool=None, history=()):
    return {"id": cid, "history": list(history), "question": question, "kind": kind,
            "sources": list(sources), "must": list(must), "tool": tool}


PACKAGE_DRINKS = [("Coffee", 3, True), ("Decaf", 3, True), ("Hot water", 3, True),
                  ("Iced water", 3, True), ("Orange juice", 3, True)]

CASES = [
    _case("E1", "Where is the coffee?", "DOCS", ["data/supplies/coffee.md"], ["coffee machine", "beverage room"]),
    # spec 016 revision 1: now a TOOL case (scale_recipe); sources and must are kept but only used for DOCS/BOTH
    _case("E2", "How do I make 5 gallons of lemonade?", "TOOL", ["data/recipes/lemonade.md"], ["35 oz"],
          tool={"name": "scale_recipe", "recipe": "Lemonade", "gallons": 5, "status": "ok", "guests": None}),
    _case("E3", "What syrup flavors do we have?", "DOCS", ["data/supplies/syrups.md"], ["Mango", "Strawberry", "Peach"]),
    _case("E4", "If there are no lemons by the sink, where else can I look?", "DOCS",
          ["data/supplies/lemon.md"], ["cooler", "dish room"]),
    _case("E5", "What concentrate flavors do we carry?", "DOCS", ["data/supplies/concentrates.md"],
          ["Pomegranate", "Lemonade", "Orange"]),
    _case("E6", "What's in the coffee, decaf, tea, iced water & juice package?", "DOCS",
          ["data/pull_sheet/menu/beverages.md"], ["orange juice"]),
    _case("E7", "Where is the flour?", "DOCS"),
    _case("E8", "How many cambros do I need to bring for 7 gallons of lemonade?", "TOOL",
          tool=_tool("cambros", drinks=[[("Lemonade", 7, ANY)]])),
    _case("E9", "How many cambros for lemonade for 70 guests?", "TOOL",
          tool=_tool("cambros", drinks=[[("Lemonade", 3, True)]], guests=70)),
    _case("E10", "We have the coffee, decaf, tea, iced water & juice package for 70 guests. How many cambros?",
          "TOOL", tool=_tool("cambros", drinks=[PACKAGE_DRINKS], guests=70)),
    _case("E11", "What do I need to bring for coffee for 50 guests?", "TOOL",
          tool=_tool("everything", drinks=[[("Coffee", 2, True)]], guests=50)),
    _case("E12", "Do I need sugar for coffee?", "TOOL",
          tool=_tool("supplies", no_amount=True, names_only=["Coffee"])),
    _case("E13", "How many gallons do I make for 25 people?", "TOOL",
          tool=_tool("gallons", drinks=[[]], guests=25)),
    _case("E14", "Brewed hot cider for 100 people, what goes on the pull sheet?", "TOOL",
          tool=_tool("everything", drinks=[[("Brewed hot cider", 4, True)]], guests=100)),
    _case("E15", "5 gallons each.", "TOOL", history=H15,
          tool=_tool("cambros", drinks=[[("Coffee", 5, ANY), ("Lemonade", 5, ANY)]])),
    _case("E16", "I need 5 gallons of coffee and lemonade. How many cambros?", "TOOL",
          tool=_tool("cambros", drinks=[[("Coffee", 5, ANY), ("Lemonade", 5, ANY)]])),
    _case("E17", "How many cups do I need for coffee?", "TOOL",
          tool=_tool("cups", status="need_info", no_amount=True)),
    _case("E18", "How many cambros for 4 gallons of hot chocolate?", "TOOL",
          tool=_tool("cambros", status="not_on_menu")),
    _case("E19", "Where is the coffee, and how many gallons of coffee do I need for 75 people?", "BOTH",
          ["data/supplies/coffee.md"], ["coffee machine", "beverage room"],
          tool=_tool("gallons", drinks=[[("Coffee", 3, True)], []], guests=75)),
    _case("E20", "Where are the lemons, and do I need lemons for iced tea?", "BOTH",
          ["data/supplies/lemon.md"], ["sink"],
          tool=_tool("supplies", no_amount=True, names_only=["Iced tea"])),
    _case("E21", "What syrup flavors do we have, and how many cups do I need for 45 guests?", "BOTH",
          ["data/supplies/syrups.md"], ["Mango", "Strawberry", "Peach"],
          tool=_tool("cups", guests=45)),
]


def pytest_generate_tests(metafunc):
    """Parametrise the eval fixtures: case (all), docs_case (stage 3), tool_case (stage 4), both_case (stage 5)."""
    pools = {
        "case": CASES,
        "docs_case": [c for c in CASES if c["kind"] in ("DOCS", "BOTH") and c["sources"]],
        "tool_case": [c for c in CASES if c["kind"] in ("TOOL", "BOTH")],
        "both_case": [c for c in CASES if c["kind"] == "BOTH"],
    }
    for name, pool in pools.items():
        if name in metafunc.fixturenames:
            metafunc.parametrize(name, pool, ids=[c["id"] for c in pool])


# --------------------------------------------------------------------------
# Eval environment: skip, do not fail, when Ollama or the Chroma store is missing (AC-5)
# --------------------------------------------------------------------------

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


def _installed_models():
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return {m.get("name", "") for m in data.get("models", [])}


def _chroma_exists(chat):
    raw = getattr(chat, "CHROMA_DIR", None)
    if raw is None:
        return True  # cannot tell; let build_store decide
    path = Path(str(raw))
    candidates = [path] if path.is_absolute() else [Path.cwd() / path, ROOT / path]
    return any(p.exists() for p in candidates)


@pytest.fixture(scope="session")
def flow_env():
    """The real store and the real chat model, built once per run (NFR-3)."""
    import chat

    names = _installed_models()
    if names is None:
        pytest.skip("Ollama is not running; start it to run the flow eval.")
    if chat.CHAT_MODEL not in names and f"{chat.CHAT_MODEL}:latest" not in names:
        pytest.skip(f"Model {chat.CHAT_MODEL} is not installed in Ollama.")
    if not _chroma_exists(chat):
        pytest.skip("The Chroma store does not exist; run scripts/ingest.py first.")
    from langchain_ollama import ChatOllama

    store = chat.build_store()
    llm = ChatOllama(model=chat.CHAT_MODEL, temperature=chat.CHAT_TEMPERATURE)
    return SimpleNamespace(store=store, llm=llm, traces={})


@pytest.fixture
def get_trace(flow_env):
    """get_trace(case) -> the case's TurnTrace; run_turn(generate=False) runs once per case."""
    import chat

    def _get(case):
        if case["id"] not in flow_env.traces:
            flow_env.traces[case["id"]] = chat.run_turn(
                flow_env.store, flow_env.llm, list(case["history"]), case["question"], generate=False)
        return flow_env.traces[case["id"]]

    return _get


# --------------------------------------------------------------------------
# Stage-check helpers (section 4.5)
# --------------------------------------------------------------------------

def _not_given(value):
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


def _guests_given(args):
    raw = args.get("guests")
    if raw is None:
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return raw
    return None if value == 0 else value


def _amount_equal(got, expected):
    try:
        return got is not None and abs(float(got) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _drinks_match(got, expected):
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


def _call_errors(spec, call):
    """Errors for one call that was not refused: name, item, status, drinks, guests, no invented amounts."""
    from blc.tools.bev_tools import BEV_TOOL_NAME, run_bev_tool

    errors = []
    if spec.get("name") == "scale_recipe":
        from blc.tools.recipe_tools import run_recipe_tool

        if call.name != "scale_recipe":
            errors.append(f"call to {call.name!r}, expected 'scale_recipe'")
        try:
            res = run_recipe_tool(call.args)
        except Exception as exc:
            return errors + [f"run_recipe_tool raised {exc!r}"]
        if res.status != spec["status"]:
            errors.append(f"status {res.status!r} != {spec['status']!r}")
        elif res.recipe != spec["recipe"] or not _amount_equal(res.gallons, spec["gallons"]):
            errors.append(f"recipe/gallons {res.recipe!r}/{res.gallons!r} != {spec['recipe']!r}/{spec['gallons']!r}")
        if _guests_given(call.args) != spec["guests"]:
            errors.append(f"guests {_guests_given(call.args)!r} != {spec['guests']!r}")
        return errors
    if call.name != BEV_TOOL_NAME:
        errors.append(f"call to {call.name!r}, expected {BEV_TOOL_NAME!r}")
    if call.args.get("item") != spec["item"]:
        errors.append(f"item {call.args.get('item')!r} != {spec['item']!r}")
    try:
        result = run_bev_tool(call.args)
    except Exception as exc:  # the calculator should never raise
        return errors + [f"run_bev_tool raised {exc!r}"]
    if result.status != spec["status"]:
        errors.append(f"status {result.status!r} != {spec['status']!r}")
    elif result.status == "ok":
        drinks = list(result.drinks)
        if spec["drinks"] is not None and not any(_drinks_match(drinks, alt) for alt in spec["drinks"]):
            shown = [(d.drink, d.amount, d.from_guests) for d in drinks]
            errors.append(f"drinks {shown} match none of {spec['drinks']}")
        text = str(getattr(result, "text", "")).lower()
        for name in spec.get("names_only", ()):
            if name.lower() not in text:
                errors.append(f"drink {name!r} not found in result text")
    given = _guests_given(call.args)
    if given != spec["guests"]:
        errors.append(f"guests {given!r} != {spec['guests']!r}")
    if spec.get("no_amount"):
        for key in ("guests", "gallons"):
            if not _not_given(call.args.get(key)):
                errors.append(f"invented amount: {key}={call.args.get(key)!r}, the question has no number")
    return errors


def _stage3_errors(case, trace):
    if trace.retrieval is None:
        return ["trace.retrieval is None"]
    chunks = trace.retrieval.chunks
    sources = {c.source for c in chunks}
    text = " ".join(c.text for c in chunks).lower()
    errors = [f"expected source {s!r} not retrieved (got {sorted(sources)})"
              for s in case["sources"] if s not in sources]
    errors += [f"word {w!r} not in the retrieved text" for w in case["must"] if w.lower() not in text]
    return errors


def _stage4_errors(case, trace):
    import chat

    if len(trace.tools) != 1:
        return [f"expected exactly one ToolStage, got {len(trace.tools)}"]
    stage = trace.tools[0]
    if stage.tool_text is None:
        return ["tool_text is None (the part fell back to docs)"]
    if stage.tool_text == chat.TOOL_LIMIT_REPLY:
        return ["tool_text is TOOL_LIMIT_REPLY (the round limit was hit)"]
    errors = []
    for call in stage.calls:
        if call.refused:
            continue
        errors += _call_errors(case["tool"], call)
    return errors


@pytest.fixture
def stage_checks():
    return SimpleNamespace(stage3=_stage3_errors, stage4=_stage4_errors)
