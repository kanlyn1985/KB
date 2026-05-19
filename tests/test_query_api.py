from __future__ import annotations

from enterprise_agent_kb.query_api import _is_hard_anchor_term


def test_hard_anchor_term_does_not_promote_lowercase_requirement_words() -> None:
    assert _is_hard_anchor_term("UDS") is True
    assert _is_hard_anchor_term("CP") is True
    assert _is_hard_anchor_term("requirement") is False
    assert _is_hard_anchor_term("shall") is False
