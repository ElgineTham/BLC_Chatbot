"""Shared fixtures for the Docker spec (035) tests. Helpers live in docker_helpers.py."""
import sys
import uuid
from pathlib import Path

import pytest

# pytest runs with --import-mode=importlib, so this folder is not on sys.path
# by itself; add it (as the other suites do) so `docker_helpers` can be imported.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # backend/
for _p in (str(HERE), str(ROOT / "scripts"), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from docker_helpers import (  # noqa: E402
    ADD_HOST,
    DOCKERFILE,
    REPO_ROOT,
    TEST_TAG,
    docker_ready,
    free_port,
    ollama_ready,
    run_cmd,
)


@pytest.fixture(scope="session")
def docker_available():
    if not docker_ready():
        pytest.skip("docker CLI missing or daemon not running")


@pytest.fixture(scope="session")
def ollama_available():
    if not ollama_ready():
        pytest.skip("host Ollama is not answering on localhost:11434")


@pytest.fixture
def repo_chroma():
    if not (REPO_ROOT / ".chroma").is_dir():
        pytest.skip("repo .chroma/ is missing")
    if not (REPO_ROOT / "data").is_dir():
        pytest.skip("repo data/ is missing")


@pytest.fixture(scope="session")
def image(docker_available):
    """Build the image once per session under a test-only tag; remove afterwards."""
    result = run_cmd(["docker", "build", "-f", DOCKERFILE, "-t", TEST_TAG, "."], timeout=1800)
    if result.returncode != 0:
        pytest.fail("docker build failed:\n" + result.stdout[-2000:] + result.stderr[-2000:])
    yield TEST_TAG
    run_cmd(["docker", "rmi", "-f", TEST_TAG], timeout=120)


@pytest.fixture
def containers():
    """Factory for detached containers; all are force-removed at teardown."""
    names = []

    def start(tag, port=None, mounts=(), env=None, command=()):
        name = f"blc-test-035-{uuid.uuid4().hex[:8]}"
        args = ["docker", "run", "-d", "--name", name, *ADD_HOST]
        if port is not None:
            args += ["-p", f"{port}:8000"]
        for src, dst in mounts:
            args += ["-v", f"{src}:{dst}"]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        args.append(tag)
        args += list(command)
        names.append(name)
        result = run_cmd(args, timeout=120)
        assert result.returncode == 0, result.stderr
        return name

    yield start
    for n in names:
        run_cmd(["docker", "rm", "-f", n], timeout=60)


@pytest.fixture
def web_container(image, containers, repo_chroma):
    """Factory: start the default command with repo data/.chroma mounted; returns (name, port)."""

    def start(env=None):
        port = free_port()
        mounts = [
            (str(REPO_ROOT / "data"), "/app/data"),
            (str(REPO_ROOT / ".chroma"), "/app/.chroma"),
        ]
        return containers(image, port=port, mounts=mounts, env=env), port

    return start
