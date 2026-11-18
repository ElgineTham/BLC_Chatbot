"""Spec 035 section 6.1: the image and running containers (integration)."""
import json
import tempfile
import time
from pathlib import Path

import pytest

from docker_helpers import (
    DEFAULT_OLLAMA_HOST,
    ERROR_MESSAGE,
    http_get,
    post_chat,
    run_cmd,
    wait_for_health,
)

pytestmark = pytest.mark.integration


def test_build_succeeds(image):
    """Covers: AC-1 (right), DOCKER-1. Building the image from repo root exits 0 (fixture fails otherwise)."""
    result = run_cmd(["docker", "image", "inspect", image], timeout=60)
    assert result.returncode == 0


def test_image_contents(image):
    """Covers: AC-2 (right), DOCKER-2. Excluded names absent; data absent/empty; required files present."""
    code = (
        "import os, json;"
        "r={'top': os.listdir('/app'),"
        "'data': os.listdir('/app/data') if os.path.isdir('/app/data') else [],"
        "'req': {p: os.path.exists(p) for p in ["
        "'/app/backend/scripts/web.py','/app/frontend/index.html',"
        "'/app/pyproject.toml','/app/poetry.lock']}};"
        "print(json.dumps(r))"
    )
    result = run_cmd(["docker", "run", "--rm", image, "python", "-c", code], timeout=120)
    assert result.returncode == 0, result.stderr
    info = json.loads(result.stdout.strip().splitlines()[-1])
    for name in [".git", ".venv", ".chroma", ".env", ".models", "logs", ".pytest_cache"]:
        assert name not in info["top"], f"{name} must not be in the image"
    assert info["data"] == []
    assert all(info["req"].values()), info["req"]


def test_no_command_no_mounts_exits_1(image):
    """Covers: AC-3 (wrong), DOCKER-3. No store mounted: exit 1 and output mentions Chroma/ingest."""
    result = run_cmd(["docker", "run", "--rm", image], timeout=120)
    assert result.returncode == 1
    out = (result.stdout + result.stderr).lower()
    assert "chroma" in out or "ingest" in out


def test_health_and_page(web_container):
    """Covers: AC-4 (right), DOCKER-4. Health 200 ok within 60 s; GET / returns HTML."""
    _, port = web_container()
    status, body = wait_for_health(port, 60)
    assert status == 200
    assert json.loads(body) == {"status": "ok"}
    status, page = http_get(f"http://localhost:{port}/")
    assert status == 200
    assert "<html" in page.lower()


def test_chat_streams_tokens_and_done(web_container, ollama_available):
    """Covers: AC-5 (right), DOCKER-5. Tokens then done with non-empty reply."""
    _, port = web_container(env={"OLLAMA_HOST": DEFAULT_OLLAMA_HOST})
    assert wait_for_health(port, 60)[0] == 200
    status, lines = post_chat(port, "Where is the coffee kept?")
    assert status == 200
    assert any(l["type"] == "token" for l in lines)
    done = lines[-1]
    assert done["type"] == "done"
    assert done["reply"].strip()


def test_chat_with_dead_ollama_returns_error_line(web_container):
    """Covers: AC-6 (wrong), DOCKER-6. Unreachable Ollama: 200, error line, health still 200."""
    _, port = web_container(env={"OLLAMA_HOST": "http://host.docker.internal:9"})
    assert wait_for_health(port, 60)[0] == 200
    status, lines = post_chat(port, "Where is the coffee kept?")
    assert status == 200
    errors = [l for l in lines if l["type"] == "error"]
    assert errors
    assert errors[0]["message"] == ERROR_MESSAGE
    status, body = http_get(f"http://localhost:{port}/api/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_docker_stop_is_clean(web_container):
    """Covers: AC-7 (boundary), DOCKER-7. docker stop returns within 10 s and exit code is not 137."""
    name, port = web_container()
    assert wait_for_health(port, 60)[0] == 200
    start = time.time()
    result = run_cmd(["docker", "stop", name], timeout=60)
    elapsed = time.time() - start
    assert result.returncode == 0
    assert elapsed < 10
    inspect = run_cmd(
        ["docker", "inspect", "-f", "{{.State.ExitCode}}", name], timeout=30
    )
    assert inspect.stdout.strip() != "137"


def test_ingest_in_container(image, ollama_available):
    """Covers: AC-8 (right), DOCKER-8. Ingest of one md file exits 0 and fills the empty .chroma folder."""
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        chroma = Path(tmp) / "chroma"
        data.mkdir()
        chroma.mkdir()
        (data / "coffee.md").write_text(
            "# Coffee\n\nThe coffee urn is kept in the back kitchen.\n", encoding="utf-8"
        )
        assert list(chroma.iterdir()) == []
        result = run_cmd(
            [
                "docker", "run", "--rm",
                "--add-host", "host.docker.internal:host-gateway",
                "-e", f"OLLAMA_HOST={DEFAULT_OLLAMA_HOST}",
                "-v", f"{data}:/app/data",
                "-v", f"{chroma}:/app/.chroma",
                image, "python", "backend/scripts/ingest.py",
            ],
            timeout=600,
        )
        assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
        assert list(chroma.iterdir()) != []


def test_command_replaces_default_command(image):
    """Covers: AC-8 (boundary), spec 3 contract. A command given to docker run replaces the default (runs, then exits) instead of serving."""
    result = run_cmd(
        ["docker", "run", "--rm", image, "python", "-c", "print('ran')"], timeout=120
    )
    assert result.returncode == 0
    assert "ran" in result.stdout


def test_python_imports(image):
    """Covers: AC-9 (right), DOCKER-9. Runtime packages import."""
    result = run_cmd(
        ["docker", "run", "--rm", image, "python", "-c",
         "import fastapi, uvicorn, chromadb, langchain_ollama"],
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_voice_package_absent(image):
    """Covers: AC-9 (wrong), DOCKER-9. sounddevice is not installed."""
    result = run_cmd(
        ["docker", "run", "--rm", image, "python", "-c", "import sounddevice"],
        timeout=120,
    )
    assert result.returncode != 0
