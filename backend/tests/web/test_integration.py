"""Integration test for spec 032 (AC-10 / API-13): real Gemini (spec 037) and .chroma/."""
import pytest
from fastapi.testclient import TestClient

from web import build_answerer, create_app

from web_helpers import REPO_ROOT, parse_lines

@pytest.mark.integration
def test_api13_real_answerer_with_follow_up():
    """Covers: AC-10 (right), API-13. Real flow streams tokens then done; joined tokens == reply; follow-up works."""
    import os

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set")
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is not set (Claude chat model, spec 039)")
    if not (REPO_ROOT / ".chroma").exists():
        pytest.skip(".chroma/ is missing")

    from chat import CHAT_TEMPERATURE, build_chat_model, build_domain_store

    llm = build_chat_model(temperature=CHAT_TEMPERATURE)
    store = build_domain_store()
    client = TestClient(create_app(build_answerer(llm, store)))

    r = client.post("/api/chat", json={"question": "Where is the coffee kept?"})
    assert r.status_code == 200
    lines = parse_lines(r)
    tokens = [l["text"] for l in lines if l["type"] == "token"]
    assert len(tokens) >= 1
    done = lines[-1]
    assert done["type"] == "done"
    assert done["reply"]
    assert "".join(tokens) == done["reply"]

    r2 = client.post(
        "/api/chat", json={"question": "And the tea?", "history": done["history"]}
    )
    assert r2.status_code == 200
    assert parse_lines(r2)[-1]["type"] == "done"
