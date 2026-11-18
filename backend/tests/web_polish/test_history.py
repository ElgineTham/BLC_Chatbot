"""Tests for spec 034 section 6.1 (HIST): blc.history and the blc.web / chat import rule."""
import subprocess
import sys

import pytest

import blc.history
from blc.history import HISTORY_TOKEN_LIMIT, summarize_if_long
from polish_helpers import BACKEND_SRC, make_long_history


def test_hist1_short_history_unchanged(fake_model, short_history):
    """Covers: AC-1 (right), HIST-1. Short history is returned equal and the model is never called."""
    before = [dict(m) for m in short_history]
    out = summarize_if_long(fake_model, short_history)
    assert out == before
    assert fake_model.calls == []


def test_hist2_empty_history(fake_model):
    """Covers: AC-1 (boundary), HIST-2. Empty history -> [] with no model call."""
    assert summarize_if_long(fake_model, []) == []
    assert fake_model.calls == []


def test_hist3_long_history_summarized(fake_model):
    """Covers: AC-1 (right), HIST-3. Long history -> exactly one summary item; model called once."""
    out = summarize_if_long(fake_model, make_long_history(HISTORY_TOKEN_LIMIT))
    assert len(out) == 1
    assert out[0]["role"] == "summary"
    assert out[0]["content"] == "SUMMARY"
    assert len(fake_model.calls) == 1


def test_hist3_summary_uses_model_reply(fake_model):
    """Covers: AC-1 (right). The summary content is whatever the model replied."""
    fake_model.reply = "OTHER TEXT"
    out = summarize_if_long(fake_model, make_long_history(HISTORY_TOKEN_LIMIT))
    assert out == [{"role": "summary", "content": "OTHER TEXT"}]


def test_hist3_prints_nothing(fake_model, capsys):
    """Covers: AC-1 (right). summarize_if_long prints nothing, for long and short history."""
    summarize_if_long(fake_model, make_long_history(HISTORY_TOKEN_LIMIT))
    summarize_if_long(fake_model, [{"role": "user", "content": "hi"}])
    captured = capsys.readouterr()
    assert captured.out == ""


def test_hist6_exactly_at_limit_unchanged(fake_model):
    """Covers: AC-1 (boundary), HIST-6. 8000 chars = exactly the limit: unchanged, no model call."""
    assert HISTORY_TOKEN_LIMIT * 4 == 8000
    history = [{"role": "user", "content": "a" * 8000}]
    out = summarize_if_long(fake_model, history)
    assert out == [{"role": "user", "content": "a" * 8000}]
    assert fake_model.calls == []


def test_hist7_one_token_over_summarized(fake_model):
    """Covers: AC-1 (boundary), HIST-7. 8001 chars = one token over: one summary item, one model call."""
    out = summarize_if_long(fake_model, [{"role": "user", "content": "a" * 8001}])
    assert out == [{"role": "summary", "content": "SUMMARY"}]
    assert len(fake_model.calls) == 1


def test_hist4_limit_value():
    """Covers: AC-1 (boundary), HIST-4. The limit is 2000."""
    assert HISTORY_TOKEN_LIMIT == 2000
    assert blc.history.HISTORY_TOKEN_LIMIT == 2000


def test_hist4_chat_reexports():
    """Covers: AC-1 (right), HIST-4. chat re-exports the same function object and limit."""
    import chat

    assert chat.summarize_if_long is blc.history.summarize_if_long
    assert chat.HISTORY_TOKEN_LIMIT == blc.history.HISTORY_TOKEN_LIMIT == 2000


def test_hist5_web_does_not_import_chat(tmp_path):
    """Covers: AC-2 (right), HIST-5. With only backend/src on sys.path, import blc.web works
    and 'chat' is not in sys.modules."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import blc.web; print('chat' in sys.modules)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(BACKEND_SRC)],
        capture_output=True, text=True, cwd=str(tmp_path),
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"


def test_hist5_wrong_control_detects_chat_import(tmp_path):
    """Covers: AC-2 (wrong). Sanity check of the HIST-5 probe: if chat IS imported the probe prints True,
    so the 'False' above is meaningful."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); "
        "import blc.web, chat; print('chat' in sys.modules)"
    )
    scripts = str(BACKEND_SRC.parent / "scripts")
    proc = subprocess.run(
        [sys.executable, "-c", code, str(BACKEND_SRC), scripts],
        capture_output=True, text=True, cwd=str(tmp_path),
        env={"PATH": "/usr/bin:/bin"},
    )
    if proc.returncode != 0:
        pytest.skip("chat could not be imported in a bare interpreter")
    assert proc.stdout.strip() == "True"
