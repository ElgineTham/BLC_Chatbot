"""Spec 033 section 6.2 PATHS: path constants still point at the repo root."""
import pytest
from fastapi.testclient import TestClient


def _same(actual, expected):
    return actual.resolve() == expected.resolve()


# ---------------------------------------------------------------- PATHS-1


def test_chat_root_is_repo_root(repo_root):
    """Covers: PATHS-1, AC-3 (right). chat.ROOT is the folder holding pyproject.toml."""
    import chat

    assert _same(chat.ROOT, repo_root)


def test_ingest_root_is_repo_root(repo_root):
    """Covers: PATHS-1, AC-3 (right). ingest.ROOT is the folder holding pyproject.toml."""
    import ingest

    assert _same(ingest.ROOT, repo_root)


def test_roots_are_not_backend(repo_root):
    """Covers: PATHS-1, AC-3 (wrong). Neither ROOT stops at backend/."""
    import chat
    import ingest

    backend = (repo_root / "backend").resolve()
    assert chat.ROOT.resolve() != backend
    assert ingest.ROOT.resolve() != backend


# ---------------------------------------------------------------- PATHS-2


def test_chat_chroma_dir(repo_root):
    """Covers: PATHS-2, AC-3 (right). chat.CHROMA_DIR is REPO_ROOT/.chroma."""
    import chat

    assert _same(chat.CHROMA_DIR, repo_root / ".chroma")


def test_ingest_chroma_dir(repo_root):
    """Covers: PATHS-2, AC-3 (right). ingest.CHROMA_DIR is REPO_ROOT/.chroma."""
    import ingest

    assert _same(ingest.CHROMA_DIR, repo_root / ".chroma")


def test_ingest_data_dir(repo_root):
    """Covers: PATHS-2, AC-3 (right). ingest.DATA_DIR is REPO_ROOT/data."""
    import ingest

    assert _same(ingest.DATA_DIR, repo_root / "data")


def test_chroma_and_data_not_under_backend(repo_root):
    """Covers: PATHS-2, AC-3 (wrong). No store or data path points inside backend/."""
    import chat
    import ingest

    backend = (repo_root / "backend").resolve()
    for p in (chat.CHROMA_DIR, ingest.CHROMA_DIR, ingest.DATA_DIR):
        assert backend not in p.resolve().parents, p


def test_data_dir_exists_when_chroma_expected(repo_root):
    """Covers: PATHS-2, AC-3 (boundary). The data folder that DATA_DIR names exists at the root (the move did not strand it)."""
    import ingest

    assert ingest.DATA_DIR.resolve().is_dir()


# ---------------------------------------------------------------- PATHS-3


def test_recipes_file(repo_root):
    """Covers: PATHS-3, AC-3 (right). RECIPES_FILE is REPO_ROOT/data/recipes/recipes.json."""
    from blc.tools.recipe_tools import RECIPES_FILE

    assert _same(RECIPES_FILE, repo_root / "data" / "recipes" / "recipes.json")


def test_default_rules_dir(repo_root):
    """Covers: PATHS-3, AC-3 (right). DEFAULT_RULES_DIR is REPO_ROOT/data/pull_sheet."""
    from blc.tools.bev_tools.catalog import DEFAULT_RULES_DIR

    assert _same(DEFAULT_RULES_DIR, repo_root / "data" / "pull_sheet")


def test_food_rules_file(repo_root):
    """Covers: PATHS-3, AC-3 (right). FOOD_RULES_FILE is REPO_ROOT/data/pull_sheet/rules/food.json."""
    from blc.tools.food_tools import FOOD_RULES_FILE

    assert _same(FOOD_RULES_FILE, repo_root / "data" / "pull_sheet" / "rules" / "food.json")


def test_tool_paths_not_under_backend(repo_root):
    """Covers: PATHS-3, AC-3 (wrong). None of the three tool paths points inside backend/."""
    from blc.tools.bev_tools.catalog import DEFAULT_RULES_DIR
    from blc.tools.food_tools import FOOD_RULES_FILE
    from blc.tools.recipe_tools import RECIPES_FILE

    backend = (repo_root / "backend").resolve()
    for p in (RECIPES_FILE, DEFAULT_RULES_DIR, FOOD_RULES_FILE):
        assert backend not in p.resolve().parents, p


def test_pull_sheet_root_is_repo_root(repo_root):
    """Covers: PATHS-3, AC-3 (boundary). pull_sheet.ROOT (used for its default rules path) is still the repo root."""
    import pull_sheet

    assert _same(pull_sheet.ROOT, repo_root)


# ---------------------------------------------------------------- PATHS-4


def _unused_answerer(question, history, on_token):
    raise AssertionError("serving the page must not call the answerer")


@pytest.fixture
def page_client():
    from web import create_app

    return TestClient(create_app(_unused_answerer))


def test_page_is_frontend_index(repo_root, page_client):
    """Covers: PATHS-4, AC-3 (right). GET / returns 200 with the bytes of REPO_ROOT/frontend/index.html."""
    r = page_client.get("/")
    assert r.status_code == 200
    assert r.content == (repo_root / "frontend" / "index.html").read_bytes()


def test_logo_is_frontend_asset(repo_root, page_client):
    """Covers: PATHS-4, AC-3 (right). GET /assets/blc_logo.png returns 200 with the bytes of the frontend file."""
    r = page_client.get("/assets/blc_logo.png")
    assert r.status_code == 200
    assert r.content == (repo_root / "frontend" / "assets" / "blc_logo.png").read_bytes()


def test_missing_asset_is_not_found(page_client):
    """Covers: PATHS-4, AC-3 (wrong). An asset that is not in frontend/assets/ is a 404."""
    assert page_client.get("/assets/does_not_exist_033.png").status_code == 404


# ---------------------------------------------------------------- PATHS-5


@pytest.mark.integration
def test_real_store_returns_data_sources(repo_root):
    """Covers: PATHS-5, AC-4 (right). The existing .chroma/ returns >=1 chunk for a coffee question and every
    source starts with data/ (repo-root relative)."""
    import os

    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        pytest.skip("GOOGLE_API_KEY is not set (spec 037: embeddings run on Gemini)")
    if not (repo_root / ".chroma").exists():
        pytest.skip(".chroma/ is missing")

    from chat import build_domain_store, retrieve

    store = build_domain_store()
    docs = retrieve(store, "Where is the coffee kept?")
    assert len(docs) >= 1
    sources = [d.metadata.get("source", "") for d in docs]
    assert all(s.startswith("data/") for s in sources), sources
