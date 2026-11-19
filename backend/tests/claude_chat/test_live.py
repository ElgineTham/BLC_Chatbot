"""Spec 039 section 6.4 (LIVE-1 to LIVE-5): integration tests. Skipped when a needed key or the store is missing.

LIVE-6 (AC-12, food-answer and generation evals on Claude) is the existing eval suites, whose fixtures now skip
without ANTHROPIC_API_KEY (see test_migrate.py); no new test is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cc_helpers import make_store, parse_lines, seed_persisted

pytestmark = pytest.mark.integration


def _text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content)


# ---- LIVE-1 / AC-10

def test_chat_model_replies(live_anthropic_key):
    """Covers: AC-10 (right), LIVE-1. invoke('Reply with OK') returns non-empty text."""
    from blc.llm import build_chat_model

    out = build_chat_model().invoke("Reply with OK")
    assert _text(out.content).strip()


# ---- LIVE-1b / AC-1b

@pytest.mark.parametrize("temperature", [0.0, 0.1], ids=["default-zero", "point-one"])
def test_temperature_reaches_api_without_http_400(live_anthropic_key, temperature):
    """Covers: AC-1b (right), LIVE-1b. A real invoke succeeds for build_chat_model() and for
    build_chat_model(temperature=0.1): the API does not reject the temperature parameter (no HTTP 400)."""
    from blc.llm import build_chat_model

    model = build_chat_model() if temperature == 0.0 else build_chat_model(temperature=temperature)
    out = model.invoke("Reply with OK")
    assert _text(out.content).strip()


# ---- LIVE-3 / AC-10

@pytest.mark.parametrize(
    "question",
    ["How many cups do I need for 70 guests?", "Where is the coffee kept?"],
    ids=["tool", "docs"],
)
def test_planner_accepts_claude(live_anthropic_key, question):
    """Covers: AC-10 (right), LIVE-3. The planner returns a non-fallback plan on Claude (the bind_tools
    schemas are accepted). Which route is picked is not asserted."""
    from blc.llm import build_chat_model
    from blc.planner import plan_question

    plan = plan_question(build_chat_model(), question)
    assert plan.fallback is False
    assert plan.calls


# ---- LIVE-4 / AC-11

@pytest.mark.parametrize(
    "history",
    [
        [
            {"role": "assistant", "content": "Hi, how can I help?"},
            {"role": "user", "content": "I am setting up the coffee station."},
            {"role": "user", "content": "It is for a morning event."},
        ],
        [{"role": "assistant", "content": "Hi, how can I help?"}],
        [
            {"role": "user", "content": "I am setting up the coffee station."},
            {"role": "user", "content": "It is for a morning event."},
        ],
    ],
    ids=["assistant-first-and-two-users", "assistant-first", "two-users-in-a-row"],
)
def test_odd_history_still_answers(live_both_keys, history):
    """Covers: AC-11 (right), LIVE-4. A history starting with an assistant message, or ending in two
    consecutive user messages, still gets a non-empty answer (no Anthropic role-order error)."""
    from blc.flow import run_planned_turn
    from chat import CHAT_TEMPERATURE, CHROMA_DIR, build_chat_model, build_domain_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip("the Chroma store does not exist; run backend/scripts/ingest.py")
    store = build_domain_store()
    outcome = run_planned_turn(
        build_chat_model(temperature=CHAT_TEMPERATURE), store, "Where is the coffee kept?", history
    )
    assert outcome.reply.strip()


# ---- LIVE-5 / AC-13

def test_web_with_invalid_anthropic_key_streams_error_and_stays_healthy(monkeypatch, tmp_path):
    """Covers: AC-13 (wrong), LIVE-5. Real build_chat_model with ANTHROPIC_API_KEY=invalid, fake embeddings and a
    stamped temp store: POST /api/chat streams an error line with ERROR_MESSAGE, and /api/health is 200 after."""
    from fastapi.testclient import TestClient

    from blc.llm import EMBED_MODEL, build_chat_model
    from web import ERROR_MESSAGE, build_answerer, create_app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid")
    seed_persisted(tmp_path / "chroma", EMBED_MODEL)
    import ingest

    store = make_store(tmp_path / "chroma", collection=ingest.COLLECTION_NAME)
    client = TestClient(create_app(build_answerer(build_chat_model(), store)))

    r = client.post("/api/chat", json={"question": "Where is the coffee kept?"})
    assert r.status_code == 200
    errors = [ln for ln in parse_lines(r) if ln.get("type") == "error"]
    assert errors
    assert errors[0]["message"] == ERROR_MESSAGE
    health = client.get("/api/health")
    assert health.status_code == 200
