"""Spec 035 section 6.2: compose.yaml via `docker compose config --format json` (integration)."""
import os

import pytest

from docker_helpers import DEFAULT_OLLAMA_HOST, REPO_ROOT, compose_config

pytestmark = pytest.mark.integration


def _real(p):
    return os.path.realpath(str(p))


def test_single_service_build_and_port(docker_available):
    """Covers: AC-10 (right), COMPOSE-1. Only `web`; context is repo root; 8000 -> 8000."""
    cfg = compose_config()
    assert set(cfg["services"]) == {"web"}
    web = cfg["services"]["web"]
    build = web["build"]
    context = build["context"] if isinstance(build, dict) else build
    assert _real(context) == _real(REPO_ROOT)
    assert isinstance(build, dict)
    assert build["dockerfile"].replace("\\", "/").endswith("docker/Dockerfile")
    ports = web["ports"]
    assert len(ports) == 1
    assert int(ports[0]["published"]) == 8000
    assert int(ports[0]["target"]) == 8000


def test_no_extra_services_or_ports(docker_available):
    """Covers: AC-10 (wrong). No second service (e.g. an ollama container) and no other published port."""
    cfg = compose_config()
    assert "ollama" not in cfg["services"]
    published = {int(p["published"]) for p in cfg["services"]["web"]["ports"]}
    assert published == {8000}


def test_bind_mounts(docker_available):
    """Covers: AC-10 (right), COMPOSE-2. data and .chroma bind-mounted to /app."""
    cfg = compose_config()
    mounts = {
        v["target"]: _real(v["source"])
        for v in cfg["services"]["web"]["volumes"]
        if v.get("type") == "bind"
    }
    assert mounts.get("/app/data") == _real(REPO_ROOT / "data")
    assert mounts.get("/app/.chroma") == _real(REPO_ROOT / ".chroma")


def test_only_the_two_mounts(docker_available):
    """Covers: AC-10 (boundary). Exactly two volumes; nothing else (e.g. no source-code mount)."""
    cfg = compose_config()
    targets = sorted(v["target"] for v in cfg["services"]["web"]["volumes"])
    assert targets == ["/app/.chroma", "/app/data"]


def test_ollama_host_default(docker_available):
    """Covers: AC-11 (right), COMPOSE-3. Without shell OLLAMA_HOST the default host URL is used."""
    cfg = compose_config()
    assert cfg["services"]["web"]["environment"]["OLLAMA_HOST"] == DEFAULT_OLLAMA_HOST


def test_ollama_host_override(docker_available):
    """Covers: AC-11 (right), COMPOSE-4. Shell OLLAMA_HOST wins over the default."""
    cfg = compose_config(extra_env={"OLLAMA_HOST": "http://example:1234"})
    env = cfg["services"]["web"]["environment"]
    assert env["OLLAMA_HOST"] == "http://example:1234"
    assert env["OLLAMA_HOST"] != DEFAULT_OLLAMA_HOST
