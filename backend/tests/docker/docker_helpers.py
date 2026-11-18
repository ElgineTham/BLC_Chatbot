"""Plain helpers and constants for the Docker spec (035) tests."""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = "docker/Dockerfile"
COMPOSE_FILE = "docker/compose.yaml"
TEST_TAG = "blc-chatbot-test-035:latest"
DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434"
HOST_OLLAMA_URL = "http://localhost:11434"
ERROR_MESSAGE = "Sorry, something went wrong on my end. Please try again."
ADD_HOST = ["--add-host", "host.docker.internal:host-gateway"]


def run_cmd(args, timeout=300, env=None, cwd=REPO_ROOT):
    """Run a command, capture text output."""
    return subprocess.run(
        args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout
    )


def docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return run_cmd(["docker", "info"], timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(HOST_OLLAMA_URL, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_get(url, timeout=5):
    """Return (status, body_text); (None, '') when not reachable."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception:
        return None, ""


def post_chat(port, question, timeout=180):
    """POST /api/chat; return (status, list of parsed NDJSON lines)."""
    req = urllib.request.Request(
        f"http://localhost:{port}/api/chat",
        data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8")
        return r.status, [json.loads(x) for x in body.split("\n") if x.strip()]


def wait_for_health(port, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        status, body = http_get(f"http://localhost:{port}/api/health")
        if status == 200:
            return status, body
        time.sleep(1)
    return None, ""


def compose_config(extra_env=None, remove_env=("OLLAMA_HOST",)):
    """Return parsed `docker compose config --format json` output."""
    env = dict(os.environ)
    for k in remove_env:
        env.pop(k, None)
    env.update(extra_env or {})
    result = run_cmd(
        ["docker", "compose", "-f", COMPOSE_FILE, "config", "--format", "json"],
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
