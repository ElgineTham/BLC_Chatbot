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
    DOCKERFILE,
    EMBED_MODEL_NAME,
    REPO_ROOT,
    TEST_TAG,
    docker_ready,
    free_port,
    run_cmd,
)


@pytest.fixture(scope="session")
def docker_available():
    if not docker_ready():
        pytest.skip("docker CLI missing or daemon not running")


@pytest.fixture(scope="session")
def gemini_key():
    """Spec 037: a real Gemini key for tests that reach the model; skips when GOOGLE_API_KEY is unset."""
    import os

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        pytest.skip("GOOGLE_API_KEY is not set")
    return key


@pytest.fixture
def repo_chroma():
    if not (REPO_ROOT / ".chroma").is_dir():
        pytest.skip("repo .chroma/ is missing")
    if not (REPO_ROOT / "data").is_dir():
        pytest.skip("repo data/ is missing")


@pytest.fixture
def stamped_chroma(tmp_path):
    """A temp store stamped with the Gemini embedding model (fake 768-dim vectors), so the web container
    starts (spec 037 AC-11) without any model call. Returns (data_dir, chroma_dir)."""
    from langchain_chroma import Chroma
    from langchain_core.embeddings import DeterministicFakeEmbedding

    import ingest

    data = tmp_path / "data"
    chroma = tmp_path / ".chroma"
    data.mkdir()
    store = Chroma(
        collection_name=ingest.COLLECTION_NAME,
        embedding_function=DeterministicFakeEmbedding(size=768),
        persist_directory=str(chroma),
    )
    store.add_texts(
        ["The coffee urn is kept in the back kitchen."],
        metadatas=[{"source": "data/x.md", "category": "x", "domain": "x", "chunk_index": 0,
                    "embed_model": EMBED_MODEL_NAME}],
        ids=["seed-1"],
    )
    return data, chroma


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
        args = ["docker", "run", "-d", "--name", name]
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
def web_container(image, containers, stamped_chroma):
    """Factory: start the default command with a stamped temp store mounted; returns (name, port).
    GOOGLE_API_KEY defaults to 'invalid' (the web app only needs it to be non-blank to start)."""

    def start(env=None, real_store=False):
        port = free_port()
        if real_store:
            mounts = [
                (str(REPO_ROOT / "data"), "/app/data"),
                (str(REPO_ROOT / ".chroma"), "/app/.chroma"),
            ]
        else:
            data, chroma = stamped_chroma
            mounts = [(str(data), "/app/data"), (str(chroma), "/app/.chroma")]
        full_env = {"GOOGLE_API_KEY": "invalid", **(env or {})}
        return containers(image, port=port, mounts=mounts, env=full_env), port

    return start
