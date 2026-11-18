"""Tests for spec 032 section 6.1 (API): POST /api/chat, stream, validation, health."""
import json

import pytest

from web import ERROR_MESSAGE, MAX_QUESTION_CHARS

from web_helpers import FakeAnswerer, parse_lines, post_raw


# ---------- valid requests / stream (AC-6) ----------

def test_api1_stripped_question_and_token_order(fake, client):
    """Covers: AC-6 (right), API-1. Stripped question, [] history, 3 tokens in order, then done."""
    r = client.post("/api/chat", json={"question": "  Where is the coffee?  "})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert fake.calls == [("Where is the coffee?", [])]
    lines = parse_lines(r)
    assert lines[:3] == [
        {"type": "token", "text": "The "},
        {"type": "token", "text": "coffee"},
        {"type": "token", "text": " is here."},
    ]
    assert len(lines) == 4
    assert lines[3] == {"type": "done", "reply": "The coffee is here.", "history": fake.history}


def test_api2_history_passed_unchanged(make_client):
    """Covers: AC-6 (right), API-2. History passed exactly as sent; done.history is the fake's."""
    sent = [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "In the pantry."},
    ]
    returned = sent + [
        {"role": "user", "content": "And the tea?"},
        {"role": "assistant", "content": "Next to it."},
    ]
    fake = FakeAnswerer(pieces=["Next to it."], reply="Next to it.", history=returned)
    r = make_client(fake).post("/api/chat", json={"question": "And the tea?", "history": sent})
    assert r.status_code == 200
    assert fake.calls == [("And the tea?", sent)]
    done = parse_lines(r)[-1]
    assert done["type"] == "done"
    assert done["history"] == returned


def test_api3_summary_role_accepted(make_client):
    """Covers: AC-5 (right), AC-6 (right), API-3. A summary item is accepted and passed unchanged."""
    sent = [{"role": "summary", "content": "Earlier we talked about coffee."}]
    fake = FakeAnswerer(pieces=["ok"], reply="ok")
    r = make_client(fake).post("/api/chat", json={"question": "hi", "history": sent})
    assert r.status_code == 200
    assert fake.calls == [("hi", sent)]


def test_api4_non_ascii_emoji_newline_round_trip(make_client):
    """Covers: AC-6 (boundary), API-4. Non-ASCII, emoji and newlines inside a piece round-trip exactly."""
    pieces = ["café ☕", "line1\nline2", "🙂 \n\n", "日本語"]
    fake = FakeAnswerer(pieces=pieces, reply="".join(pieces))
    r = make_client(fake).post("/api/chat", json={"question": "hi"})
    lines = parse_lines(r)
    assert [l["text"] for l in lines if l["type"] == "token"] == pieces
    assert len(lines) == len(pieces) + 1
    assert lines[-1]["type"] == "done"
    assert lines[-1]["reply"] == "".join(pieces)


def test_answer_called_exactly_once(fake, client):
    """Covers: AC-6 (right). answer is called once per valid request."""
    client.post("/api/chat", json={"question": "hi"})
    assert len(fake.calls) == 1


def test_history_omitted_defaults_to_empty_list(fake, client):
    """Covers: AC-6 (boundary). Omitted history is passed as an empty list."""
    client.post("/api/chat", json={"question": "hi"})
    assert fake.calls[0][1] == []


def test_explicit_empty_history_accepted(fake, client):
    """Covers: AC-6 (boundary). history [] is valid."""
    r = client.post("/api/chat", json={"question": "hi", "history": []})
    assert r.status_code == 200
    assert fake.calls[0][1] == []


def test_done_carries_answerer_reply_not_joined_tokens(make_client):
    """Covers: AC-6 (right). done.reply is ChatTurn.reply even if it differs from the tokens."""
    fake = FakeAnswerer(pieces=["a", "b"], reply="FINAL")
    lines = parse_lines(make_client(fake).post("/api/chat", json={"question": "hi"}))
    assert lines[-1]["reply"] == "FINAL"


def test_inner_whitespace_of_question_preserved(make_client):
    """Covers: AC-6 (boundary). Only the ends are stripped; inner newlines/spaces remain."""
    fake = FakeAnswerer()
    make_client(fake).post("/api/chat", json={"question": "\n a  b\nc \t"})
    assert fake.calls[0][0] == "a  b\nc"


# ---------- no tokens (AC-7) ----------

def test_api5_no_tokens_exactly_one_done(make_client):
    """Covers: AC-7 (boundary), API-5. Zero on_token calls still yields exactly one done line."""
    fake = FakeAnswerer(pieces=[], reply="direct")
    lines = parse_lines(make_client(fake).post("/api/chat", json={"question": "hi"}))
    assert len(lines) == 1
    assert lines[0]["type"] == "done"
    assert lines[0]["reply"] == "direct"


# ---------- errors (AC-8) ----------

def test_api6_error_after_token_hides_exception(make_client):
    """Covers: AC-8 (wrong), API-6. Token then one error line; exception text absent; app keeps serving."""
    boom = FakeAnswerer(pieces=["Hi"], raises=RuntimeError("db password 123"))
    client = make_client(boom)
    r = client.post("/api/chat", json={"question": "hi"})
    assert "db password 123" not in r.text
    lines = parse_lines(r)
    assert lines == [
        {"type": "token", "text": "Hi"},
        {"type": "error", "message": ERROR_MESSAGE},
    ]
    assert not any(l["type"] == "done" for l in lines)
    # next request works on the same app
    boom.raises = None
    boom.pieces = ["ok"]
    r2 = client.post("/api/chat", json={"question": "again"})
    assert r2.status_code == 200
    assert parse_lines(r2)[-1]["type"] == "done"


def test_error_before_any_token_single_error_line(make_client):
    """Covers: AC-8 (boundary). Raising with no tokens gives exactly one error line."""
    fake = FakeAnswerer(raises=ValueError("secret detail"))
    r = make_client(fake).post("/api/chat", json={"question": "hi"})
    assert parse_lines(r) == [{"type": "error", "message": ERROR_MESSAGE}]
    assert "secret detail" not in r.text


# ---------- state (AC-9) ----------

def test_api11_no_state_between_requests(make_client):
    """Covers: AC-9 (right), API-11. Second call with [] gets [] even after a first call with history."""
    h1 = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    fake = FakeAnswerer(pieces=["x"], reply="x")
    client = make_client(fake)
    client.post("/api/chat", json={"question": "one", "history": h1})
    client.post("/api/chat", json={"question": "two", "history": []})
    assert fake.calls[0][1] == h1
    assert fake.calls[1][1] == []


def test_no_state_when_history_omitted(make_client):
    """Covers: AC-9 (boundary). Omitted history on the second request is [] not the earlier history."""
    h1 = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    fake = FakeAnswerer()
    client = make_client(fake)
    client.post("/api/chat", json={"question": "one", "history": h1})
    client.post("/api/chat", json={"question": "two"})
    assert fake.calls[1][1] == []


# ---------- validation (AC-5) ----------

@pytest.mark.parametrize("body", [
    {"question": ""},
    {"question": "   "},
    {"question": "\n\t "},
    {},
    {"history": []},
    {"question": 42},
    {"question": None},
    {"question": ["hi"]},
])
def test_api7_bad_question_rejected(fake, client, body):
    """Covers: AC-5 (wrong), API-7. Blank/missing/non-string question gives 400 JSON error; answer not called."""
    r = client.post("/api/chat", json=body)
    assert r.status_code == 400
    assert isinstance(r.json()["error"], str) and r.json()["error"]
    assert fake.calls == []


def test_api8_question_at_max_accepted(fake, client):
    """Covers: AC-5 (boundary), API-8. Exactly MAX_QUESTION_CHARS chars is accepted."""
    q = "a" * MAX_QUESTION_CHARS
    r = client.post("/api/chat", json={"question": q})
    assert r.status_code == 200
    assert fake.calls[0][0] == q


def test_api8_question_over_max_rejected(fake, client):
    """Covers: AC-5 (boundary/wrong), API-8. One char more than the max gives 400."""
    r = client.post("/api/chat", json={"question": "a" * (MAX_QUESTION_CHARS + 1)})
    assert r.status_code == 400
    assert r.json()["error"]
    assert fake.calls == []


def test_max_length_measured_after_stripping(fake, client):
    """Covers: AC-5 (boundary). Padding whitespace around a max-length question does not count."""
    q = "a" * MAX_QUESTION_CHARS
    r = client.post("/api/chat", json={"question": "   " + q + "  \n"})
    assert r.status_code == 200
    assert fake.calls[0][0] == q


def test_max_question_chars_is_2000():
    """Covers: AC-5 (boundary). The documented limit is 2000."""
    assert MAX_QUESTION_CHARS == 2000


@pytest.mark.parametrize("history", [
    "oops",
    42,
    {"role": "user", "content": "x"},
    None,
    [{"role": "user"}],
    [{"content": "x"}],
    [{"role": "system", "content": "x"}],
    [{"role": "user", "content": 5}],
    [{"role": 1, "content": "x"}],
    ["just a string"],
    [None],
    [["user", "x"]],
    [{"role": "user", "content": "ok"}, {"role": "bogus", "content": "x"}],
])
def test_api9_bad_history_rejected(fake, client, history):
    """Covers: AC-5 (wrong), API-9. Malformed history gives 400 JSON error; answer not called."""
    r = client.post("/api/chat", json={"question": "hi", "history": history})
    assert r.status_code == 400
    assert isinstance(r.json()["error"], str) and r.json()["error"]
    assert fake.calls == []


@pytest.mark.parametrize("role", ["user", "assistant", "summary"])
def test_each_allowed_role_accepted(fake, client, role):
    """Covers: AC-5 (right). Every role in ALLOWED_ROLES is accepted."""
    r = client.post("/api/chat", json={
        "question": "hi", "history": [{"role": role, "content": "x"}],
    })
    assert r.status_code == 200


def test_empty_content_string_is_a_string(fake, client):
    """Covers: AC-5 (boundary). content is only required to be a string; empty string is accepted."""
    r = client.post("/api/chat", json={
        "question": "hi", "history": [{"role": "user", "content": ""}],
    })
    assert r.status_code == 200


@pytest.mark.parametrize("body", [b"not json", b"{bad", b"", b"{\"question\": "])
def test_api10_non_json_body_rejected(fake, client, body):
    """Covers: AC-5 (wrong), API-10. A body that is not JSON gives 400 JSON error; answer not called."""
    r = post_raw(client, body)
    assert r.status_code == 400
    assert r.json()["error"]
    assert fake.calls == []


@pytest.mark.parametrize("body", [b"[]", b'"x"', b"42", b"null", b"true", b'["question", "hi"]'])
def test_api10_json_not_an_object_rejected(fake, client, body):
    """Covers: AC-5 (wrong), API-10. Valid JSON that is not an object gives 400 JSON error; answer not called."""
    r = post_raw(client, body)
    assert r.status_code == 400
    assert isinstance(r.json()["error"], str) and r.json()["error"]
    assert fake.calls == []


def test_api10_null_history_rejected(fake, client):
    """Covers: AC-5 (wrong), API-10. history null is present but not a list: 400; answer not called."""
    r = client.post("/api/chat", json={"question": "hi", "history": None})
    assert r.status_code == 400
    assert isinstance(r.json()["error"], str) and r.json()["error"]
    assert fake.calls == []


# ---------- health (AC-2) ----------

def test_api12_health(fake, client):
    """Covers: AC-2 (right), API-12. Health returns 200 {"status": "ok"}; answer not called."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert fake.calls == []


def test_chat_rejects_get(client):
    """Covers: AC-5 (wrong). GET on /api/chat is not a successful chat (non-2xx)."""
    assert client.get("/api/chat").status_code >= 400
