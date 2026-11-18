"""Spec 037 section 6.6 (LIVE-1 to LIVE-5): integration tests. Skipped without GOOGLE_API_KEY / Docker."""

from __future__ import annotations

import json
import math
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid

import pytest
from gm_helpers import ROOT, make_store, seed_persisted

pytestmark = pytest.mark.integration


def test_embeddings_have_768_unit_vectors(live_key):
    """Covers: AC-16 (right), LIVE-1. embed_query and embed_documents give length-768 vectors of norm 1."""
    from blc.llm import EMBED_DIM, build_embeddings

    emb = build_embeddings()
    vectors = [emb.embed_query("coffee")] + emb.embed_documents(["a", "b"])
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == EMBED_DIM == 768
        assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-3


def test_chat_model_replies(live_key):
    """Covers: AC-16 (right), LIVE-2. invoke('Reply with OK') returns non-empty text."""
    from blc.llm import build_chat_model

    out = build_chat_model().invoke("Reply with OK")
    text = out.content if isinstance(out.content, str) else json.dumps(out.content)
    assert text.strip()


def _real_markdown(n):
    files = sorted(p for p in (ROOT / "data").rglob("*.md") if p.stat().st_size > 200)
    if len(files) < n:
        pytest.skip("fewer than two real markdown files under data/")
    return files[:n]


def test_real_ingest_new_then_unchanged_and_search(live_key, tmp_path):
    """Covers: AC-17 (right), LIVE-3. Two real data files: new, then unchanged; store check passes;
    a phrase from one file finds a chunk of that file first."""
    from blc.llm import build_embeddings
    from ingest import check_store_model, ingest

    a, b = _real_markdown(2)
    data = tmp_path / "data"
    data.mkdir()
    (data / "one.md").write_bytes(a.read_bytes())
    (data / "two.md").write_bytes(b.read_bytes())
    store = make_store(tmp_path / "chroma", embeddings=build_embeddings(), collection="spec037_live")

    first = ingest(store, data)
    assert first.new == ("data/one.md", "data/two.md")
    second = ingest(store, data)
    assert second.unchanged == ("data/one.md", "data/two.md")
    assert second.new == () and second.updated == ()
    check_store_model(store)

    lines = [ln.strip() for ln in a.read_text(encoding="utf-8").splitlines() if len(ln.strip()) > 40]
    if not lines:
        pytest.skip("no long line to search for")
    hits = store.similarity_search(lines[0], k=1)
    assert hits[0].metadata["source"] == "data/one.md"


@pytest.mark.parametrize(
    "question,route",
    [("How many cups do I need for 70 guests?", "TOOL"), ("Where is the coffee kept?", "DOCS")],
)
def test_planner_accepts_gemini(live_key, question, route):
    """Covers: AC-18 (right), LIVE-4. The planner returns a plan that is not a fallback on Gemini (tool schemas
    accepted by bind_tools). Which route the model picks is not asserted (`route` is only the question's flavour)."""
    from blc.llm import build_chat_model
    from blc.planner import PLAN_ROUTES, plan_question

    plan = plan_question(build_chat_model(), question)
    assert plan.fallback is False
    assert plan.route in PLAN_ROUTES
    assert plan.calls


# ---- LIVE-5 (needs Docker)

TAG = "blc-chatbot-test-037:latest"


def _run(args, timeout=300):
    return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="module")
def image():
    if shutil.which("docker") is None or _run(["docker", "info"], 30).returncode != 0:
        pytest.skip("docker CLI missing or daemon not running")
    built = _run(["docker", "build", "-f", "docker/Dockerfile", "-t", TAG, "."], 1800)
    if built.returncode != 0:
        pytest.fail("docker build failed:\n" + built.stderr[-2000:])
    yield TAG
    _run(["docker", "rmi", "-f", TAG], 120)


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except Exception:
        return None


def test_container_with_invalid_key_streams_error_and_stays_healthy(image, tmp_path):
    """Covers: AC-19 (wrong), LIVE-5. GOOGLE_API_KEY=invalid and a stamped store: /api/chat streams an
    error line and /api/health still answers 200."""
    from blc.llm import EMBED_MODEL

    chroma = tmp_path / ".chroma"
    data = tmp_path / "data"
    data.mkdir()
    seed_persisted(chroma, EMBED_MODEL)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    name = f"blc-test-037-{uuid.uuid4().hex[:8]}"
    started = _run([
        "docker", "run", "-d", "--name", name, "-p", f"{port}:8000",
        "-v", f"{data}:/app/data", "-v", f"{chroma}:/app/.chroma",
        "-e", "GOOGLE_API_KEY=invalid", image,
    ], 120)
    assert started.returncode == 0, started.stderr
    try:
        deadline = time.time() + 60
        while time.time() < deadline and _get(f"http://localhost:{port}/api/health") != 200:
            time.sleep(1)
        assert _get(f"http://localhost:{port}/api/health") == 200
        req = urllib.request.Request(
            f"http://localhost:{port}/api/chat",
            data=json.dumps({"question": "Where is the coffee kept?"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            assert r.status == 200
            lines = [json.loads(x) for x in r.read().decode("utf-8").split("\n") if x.strip()]
        assert any(ln.get("type") == "error" for ln in lines)
        assert _get(f"http://localhost:{port}/api/health") == 200
    finally:
        _run(["docker", "rm", "-f", name], 60)
