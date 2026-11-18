"""Integration test for spec 032 (AC-10 / API-13): real Ollama and .chroma/."""
import httpx
import pytest
from fastapi.testclient import TestClient

from web import build_answerer, create_app

from web_helpers import REPO_ROOT, parse_lines

OLLAMA_URL = "http://localhost:11434"


def _ollama_up() -> bool:
    try:
        return httpx.get(OLLAMA_URL, timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.integration
def test_api13_real_answerer_with_follow_up():
    """Covers: AC-10 (right), API-13. Real flow streams tokens then done; joined tokens == reply; follow-up works."""
    if not _ollama_up():
        pytest.skip("Ollama is not running")
    if not (REPO_ROOT / ".chroma").exists():
        pytest.skip(".chroma/ is missing")
    from langchain_ollama import ChatOllama

    from chat import CHAT_KEEP_ALIVE, CHAT_MODEL, CHAT_TEMPERATURE, build_domain_store

    llm = ChatOllama(
        model=CHAT_MODEL, temperature=CHAT_TEMPERATURE, keep_alive=CHAT_KEEP_ALIVE
    )
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
