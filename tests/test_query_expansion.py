from __future__ import annotations

from enterprise_agent_kb import query_expansion


def test_generated_requirement_query_uses_rule_expansion(monkeypatch) -> None:
    query_expansion.expand_query.cache_clear()

    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM should not be called for explicit requirement queries")

    monkeypatch.setattr(query_expansion, "_call_astron_text", fail_llm)

    expansion = query_expansion.expand_query("UDS on IP services overview有哪些要求？")

    assert expansion.used_llm is False
    assert expansion.intent_candidates == ["requirement_lookup", "constraint_lookup"]
    assert expansion.possible_answer_shape == "requirement_set"
    assert "UDS on IP services overview" in expansion.expanded_terms


def test_generated_requirement_query_does_not_promote_lowercase_word_as_hard_anchor(monkeypatch) -> None:
    query_expansion.expand_query.cache_clear()
    monkeypatch.setattr(
        query_expansion,
        "_call_astron_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    expansion = query_expansion.expand_query("Periodic data response message有哪些要求？")

    assert expansion.preserved_anchors == []
    assert expansion.expanded_terms[:2] == ["Periodic data response message", "要求"]
