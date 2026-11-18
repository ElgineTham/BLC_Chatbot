"""Tests for spec 032 section 6.2 (PAGE): page, logo, manifest, icons."""
from urllib.parse import urljoin

import pytest

from web import LOGO_URL, MANIFEST_URL

from web_helpers import LOGO_FILE


def test_page1_index_html(fake, client):
    """Covers: AC-1 (right), PAGE-1. GET / is 200 HTML referencing LOGO_URL and MANIFEST_URL; no answer call."""
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert LOGO_URL in r.text
    assert MANIFEST_URL in r.text
    assert fake.calls == []


def test_constants_values():
    """Covers: AC-1/AC-3/AC-4 (boundary). URL constants have the documented values."""
    assert LOGO_URL == "/assets/blc_logo.png"
    assert MANIFEST_URL == "/manifest.webmanifest"


def test_page2_logo_bytes(fake, client):
    """Covers: AC-3 (right), PAGE-2. Logo is 200 image/png with the same bytes as the spec asset."""
    r = client.get(LOGO_URL)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == LOGO_FILE.read_bytes()
    assert fake.calls == []


def test_unknown_asset_is_404(client):
    """Covers: AC-3 (wrong). A missing asset is not served as 200."""
    assert client.get("/assets/does_not_exist.png").status_code == 404


def test_page3_manifest_fields(client):
    """Covers: AC-4 (right), PAGE-3. Manifest has the required fields and 192/512 PNG icons."""
    r = client.get(MANIFEST_URL)
    assert r.status_code == 200
    m = r.json()
    assert m["name"] == "Bay Laurel Catering Assistant"
    assert m["short_name"] == "Laurel"
    assert m["start_url"] == "/"
    assert m["display"] == "standalone"
    assert m["theme_color"]
    assert m["background_color"]
    sizes = [i.get("sizes") for i in m["icons"]]
    assert "192x192" in sizes
    assert "512x512" in sizes


@pytest.mark.parametrize("size", ["192x192", "512x512"])
def test_page3_icon_is_png(client, size):
    """Covers: AC-4 (right), PAGE-3. The 192 and 512 icons are PNGs (fetchable, image/png, PNG signature)."""
    m = client.get(MANIFEST_URL).json()
    icons = [i for i in m["icons"] if i.get("sizes") == size]
    assert icons
    src = urljoin("http://testserver" + MANIFEST_URL, icons[0]["src"])
    r = client.get(src.replace("http://testserver", ""))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_page4_every_icon_src_fetchable(fake, client):
    """Covers: AC-4 (right), PAGE-4. Every manifest icon src returns 200 with an image content type."""
    m = client.get(MANIFEST_URL).json()
    assert m["icons"]
    for icon in m["icons"]:
        url = urljoin("http://testserver" + MANIFEST_URL, icon["src"])
        r = client.get(url.replace("http://testserver", ""))
        assert r.status_code == 200, icon["src"]
        assert r.headers["content-type"].startswith("image/"), icon["src"]
        assert len(r.content) > 0
    assert fake.calls == []
