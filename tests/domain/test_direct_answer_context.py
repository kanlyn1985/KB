"""Unit tests for DirectAnswerContext — the input dataclass for build_direct_answer."""
from __future__ import annotations

import pytest

from enterprise_agent_kb.answer_policy import DirectAnswerContext


def _identity(value: str) -> str:
    return value


def test_context_creation() -> None:
    ctx = DirectAnswerContext(
        policy="definition",
        query="什么是 CC 电阻?",
        facts=[],
        evidence=[],
        wiki_pages=[],
        standard_normalizer=_identity,
        standard_extractor=_identity,
        truncate_fn=lambda s, n: s[:n],
    )
    assert ctx.policy == "definition"
    assert ctx.query == "什么是 CC 电阻?"


def test_context_is_frozen() -> None:
    ctx = DirectAnswerContext(
        policy="definition",
        query="q",
        facts=[],
        evidence=[],
        wiki_pages=[],
        standard_normalizer=_identity,
        standard_extractor=_identity,
        truncate_fn=lambda s, n: s,
    )
    with pytest.raises((AttributeError, Exception)):
        ctx.policy = "comparison"  # type: ignore[misc]


def test_context_callable_fields() -> None:
    """Normalizer/extractor/truncate are stored as callables; the policy
    module invokes them through ctx.X, not by importing answer_api helpers."""
    captured: list[tuple[str, str | int]] = []

    def normalizer(s: str) -> str:
        captured.append(("norm", s))
        return s.upper()

    def extractor(s: str) -> str:
        captured.append(("ext", s))
        return s.split("|")[0]

    def truncator(s: str, n: int) -> str:
        captured.append(("trunc", s))
        captured.append(("n", n))
        return s[:n]

    ctx = DirectAnswerContext(
        policy="standard_lookup",
        query="GB/T 1234",
        facts=[],
        evidence=[],
        wiki_pages=[],
        standard_normalizer=normalizer,
        standard_extractor=extractor,
        truncate_fn=truncator,
    )
    assert ctx.standard_normalizer("abc") == "ABC"
    assert ctx.standard_extractor("GB/T 1234|other") == "GB/T 1234"
    assert ctx.truncate_fn("hello world", 5) == "hello"


def test_context_equality() -> None:
    """DirectAnswerContext is a frozen dataclass, so two instances with
    the same fields compare equal (no need for them to be the same object)."""
    common = dict(
        policy="definition",
        query="q",
        facts=[],
        evidence=[],
        wiki_pages=[],
        standard_normalizer=_identity,
        standard_extractor=_identity,
        truncate_fn=_identity,
    )
    a = DirectAnswerContext(**common)
    b = DirectAnswerContext(**common)
    assert a == b
