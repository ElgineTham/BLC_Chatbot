"""Constants kept from spec 005 (AC-7 / AC-8).

Spec 006 replaced the chat-loop tests (spec 005 AC-7) and the safety-net tests (spec 005 AC-8)
with its own AC-2 tests in tests/router/test_answer_flow.py; they were removed from this file.
The safety net (TOOL_HINT_WORDS) no longer exists, so it is no longer asserted here.
"""

from __future__ import annotations

import chat
from blc.tools.bev_tools import BEV_TOOL


def test_constants_match_contract():
    """Covers: spec 005 AC-7 (right). Module constants that stay after spec 006."""
    assert chat.MAX_TOOL_ROUNDS == 3
    assert chat.TOOL_LIMIT_REPLY == "Sorry, I couldn't work that out. Please try rephrasing the question."
    assert chat.CHAT_TOOLS == (BEV_TOOL,)
