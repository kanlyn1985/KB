"""Tests for the unified response format.

Verifies that both ontology and legacy answers are normalized
into a single ``UnifiedResponse`` shape.
"""
from __future__ import annotations

from kb1_ontology.unified_response import (
    TypedAnswer,
    SourceSnippet,
    UnifiedResponse,
    from_combined_answer,
    from_legacy_answer,
)


class TestTypedAnswer:
    def test_typed_answer_creation(self) -> None:
        ta = TypedAnswer(value="50.0 ms", type="typed_value")
        assert ta.value == "50.0 ms"
        assert ta.type == "typed_value"


class TestSourceSnippet:
    def test_source_snippet_creation(self) -> None:
        s = SourceSnippet(text="snippet", doc_id="DOC-001", page_no=5)
        assert s.text == "snippet"
        assert s.doc_id == "DOC-001"
        assert s.page_no == 5


class TestUnifiedResponse:
    def test_unified_response_defaults(self) -> None:
        r = UnifiedResponse(query="test")
        assert r.query == "test"
        assert r.category == "free_form"
        assert r.ontology_answer is None
        assert r.legacy_answer == ""
        assert r.sources == []
        assert r.confidence is None
        assert r.explanation == ""
        assert r.warnings == []

    def test_to_dict(self) -> None:
        r = UnifiedResponse(
            query="test",
            category="parameter",
            ontology_answer=TypedAnswer(value="50 ms", type="typed_value"),
            legacy_answer="legacy text",
            sources=[SourceSnippet(text="s1", doc_id="DOC-1")],
            confidence=0.95,
        )
        d = r.to_dict()
        assert d["query"] == "test"
        assert d["category"] == "parameter"
        assert d["ontology_answer"]["value"] == "50 ms"
        assert d["ontology_answer"]["type"] == "typed_value"
        assert d["legacy_answer"] == "legacy text"
        assert len(d["sources"]) == 1
        assert d["sources"][0]["text"] == "s1"
        assert d["confidence"] == 0.95


class TestFromLegacyAnswer:
    def test_from_legacy_answer(self) -> None:
        legacy = {
            "direct_answer": "answer text",
            "answer_mode": "parameter",
            "confidence_score": {"score": 0.95},
            "supporting_evidence": [
                {
                    "snippet": "evidence 1",
                    "doc_id": "DOC-001",
                    "page_no": 3,
                    "confidence": 0.9,
                }
            ],
            "warnings": ["warning 1"],
        }
        r = from_legacy_answer("query text", legacy)
        assert r.query == "query text"
        assert r.legacy_answer == "answer text"
        assert r.category == "parameter"
        assert r.confidence == 0.95
        assert len(r.sources) == 1
        assert r.sources[0].text == "evidence 1"
        assert r.warnings == ["warning 1"]

    def test_from_legacy_answer_no_evidence(self) -> None:
        legacy = {
            "direct_answer": "answer",
            "confidence_score": 0.8,
        }
        r = from_legacy_answer("q", legacy)
        assert r.legacy_answer == "answer"
        assert r.confidence == 0.8
        assert r.sources == []


class TestFromCombinedAnswer:
    def test_from_combined_answer_with_ontology(self) -> None:
        # Mock CombinedAnswer-like object
        class MockCA:
            query = "test"
            category = "parameter"
            ontology_answer = "50 ms"
            ontology_exactness = "typed_value"
            legacy_answer = None
            legacy_excerpt = ""

        r = from_combined_answer(MockCA())
        assert r.query == "test"
        assert r.category == "parameter"
        assert r.ontology_answer is not None
        assert r.ontology_answer.value == "50 ms"
        assert r.ontology_answer.type == "typed_value"

    def test_from_combined_answer_no_ontology(self) -> None:
        class MockCA:
            query = "test"
            category = "free_form"
            ontology_answer = None
            ontology_exactness = "not_attempted"
            legacy_answer = None
            legacy_excerpt = ""

        r = from_combined_answer(MockCA())
        assert r.ontology_answer is None
        assert r.legacy_answer == ""
