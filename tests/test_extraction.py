"""Tests for the LLM extraction engine."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock
from urllib import error

import pytest

from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.extraction.extractor import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
    _parse_extraction_output,
    extract_document,
)
from kb_ontology.extraction.schema_prompt import build_schema_description
from kb_ontology.llm.llm_client import LLMChatClient, LLMClientError
from kb_ontology.storage import OntologyStore


# ── Paths and fixtures ──

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAINS_DIR = PROJECT_ROOT / "domains"


@pytest.fixture
def obc_domain_pack():
    return load_domain_pack(DOMAINS_DIR / "obc_dcdc")


@pytest.fixture
def llm_client():
    return LLMChatClient(
        endpoint="https://test-llm.example.com",
        model="test-model",
        api_key="test-key",
    )


def _fake_anthropic_response(content: str, model: str = "test-model") -> bytes:
    """Build a valid Anthropic-compatible JSON response body."""
    body = {
        "id": "msg_test_001",
        "model": model,
        "content": [{"type": "text", "text": content}],
        "usage": {"input_tokens": 100, "output_tokens": 200},
        "stop_reason": "end_turn",
    }
    return json.dumps(body).encode("utf-8")


def _patch_urlopen(content: bytes):
    """Return a mock that returns a BytesIO-wrapped response."""

    def _mock_open(*args, **kwargs):
        return io.BytesIO(content)

    return _mock_open


# ═══════════════════════════════════════════════════════════════════════
# Schema prompt builder tests
# ═══════════════════════════════════════════════════════════════════════


class TestSchemaPromptBuilder:
    def test_includes_domain_id(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        assert "obc_dcdc" in desc

    def test_includes_all_class_names(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        for cls in ("Product", "Subsystem", "Parameter", "Standard", "Method", "Requirement"):
            assert cls in desc

    def test_includes_attribute_templates(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        assert "value" in desc  # Parameter.value
        assert "number" in desc  # value type
        assert "必填" in desc or "选填" in desc  # required/optional markers

    def test_includes_identity_rules(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        assert "唯一性键" in desc
        assert "name + condition" in desc or "name" in desc

    def test_includes_relation_roles(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        assert "verified_by" in desc
        assert "part_of" in desc

    def test_includes_core_relations(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        assert "Core 通用关系" in desc
        assert "part_of" in desc
        assert "references" in desc

    def test_includes_enum_values(self, obc_domain_pack):
        desc = build_schema_description(obc_domain_pack)
        # Parameter.operator has enum values
        assert "<=" in desc or ">=" in desc


# ═══════════════════════════════════════════════════════════════════════
# Parse extraction output tests
# ═══════════════════════════════════════════════════════════════════════


class TestParseExtractionOutput:
    def test_parse_valid_output(self):
        llm_json = {
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "输出纹波",
                    "attributes": {"value": 30, "unit": "mVpp"},
                    "text_span": "纹波不大于30mVpp",
                    "confidence": 0.9,
                },
                {
                    "local_key": "e2",
                    "class": "Method",
                    "canonical_name": "示波器测量法",
                    "attributes": {"instrument": "示波器"},
                    "confidence": 0.85,
                },
            ],
            "relations": [
                {"source_key": "e1", "relation_type": "verified_by", "target_key": "e2", "confidence": 0.8}
            ],
        }
        result = _parse_extraction_output(llm_json)
        assert len(result.entities) == 2
        assert len(result.relations) == 1
        assert result.entities[0].local_key == "e1"
        assert result.entities[0].class_name == "Parameter"
        assert result.relations[0].source_key == "e1"
        assert result.relations[0].target_key == "e2"

    def test_parse_empty_output(self):
        result = _parse_extraction_output({"entities": [], "relations": []})
        assert len(result.entities) == 0
        assert len(result.relations) == 0

    def test_parse_missing_fields_skipped(self):
        llm_json = {
            "entities": [
                {"local_key": "e1"},  # missing class and name
                {"class": "Parameter"},  # missing local_key
                {"local_key": "e2", "class": "Parameter", "canonical_name": "纹波"},  # valid
            ],
            "relations": [],
        }
        result = _parse_extraction_output(llm_json)
        assert len(result.entities) == 1
        assert result.entities[0].local_key == "e2"

    def test_confidence_clamped(self):
        llm_json = {
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "test",
                    "confidence": 1.5,  # over max
                },
            ],
            "relations": [],
        }
        result = _parse_extraction_output(llm_json)
        assert result.entities[0].confidence == 1.0

    def test_confidence_invalid_fallback(self):
        llm_json = {
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "test",
                    "confidence": "invalid",
                },
            ],
            "relations": [],
        }
        result = _parse_extraction_output(llm_json)
        assert result.entities[0].confidence == 1.0

    def test_field_aliases(self):
        """LLM might use 'key'/'type'/'name' instead of 'local_key'/'class'/'canonical_name'."""
        llm_json = {
            "entities": [
                {
                    "key": "e1",
                    "type": "Parameter",
                    "name": "纹波",
                }
            ],
            "relations": [
                {"source": "e1", "type": "part_of", "target": "e2"}
            ],
        }
        result = _parse_extraction_output(llm_json)
        assert len(result.entities) == 1
        assert result.entities[0].local_key == "e1"
        assert result.entities[0].class_name == "Parameter"
        assert result.entities[0].canonical_name == "纹波"
        assert len(result.relations) == 1


# ═══════════════════════════════════════════════════════════════════════
# Full extraction pipeline tests
# ═══════════════════════════════════════════════════════════════════════


class TestExtractDocument:
    def test_successful_extraction(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Full extraction: LLM returns entities+relations → stored in OntologyStore."""
        llm_json = json.dumps({
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "输出纹波",
                    "attributes": {"value": 30, "unit": "mVpp", "operator": "<=", "condition": "额定负载"},
                    "text_span": "DCDC输出纹波在额定负载下应不大于30mVpp",
                    "location": "第1段",
                    "confidence": 0.9,
                },
                {
                    "local_key": "e2",
                    "class": "Method",
                    "canonical_name": "示波器测量法",
                    "attributes": {"instrument": "示波器"},
                    "text_span": "使用示波器测量",
                    "location": "第2段",
                    "confidence": 0.85,
                },
            ],
            "relations": [
                {"source_key": "e1", "relation_type": "verified_by", "target_key": "e2", "confidence": 0.8}
            ],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "DCDC输出纹波在额定负载下应不大于30mVpp，使用示波器测量。",
                document_id="DOC-001",
                domain_pack=obc_domain_pack,
                store=store,
                client=llm_client,
            )

            assert result.entity_count == 2
            assert result.relation_count == 1

            # Verify stored data
            stats = store.stats()
            assert stats["entities"] == 2
            assert stats["relations"] == 1
            assert stats["evidence"] >= 1

    def test_attributes_stored_with_correct_types(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Number attributes stored as float, string as string."""
        llm_json = json.dumps({
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "输出纹波",
                    "attributes": {"value": 30, "unit": "mVpp"},
                    "text_span": "30mVpp",
                    "confidence": 0.9,
                }
            ],
            "relations": [],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            extract_document(
                "test text",
                document_id="DOC-001",
                domain_pack=obc_domain_pack,
                store=store,
                client=llm_client,
            )
            entities = store.list_entities(class_name="Parameter")
            assert len(entities) == 1
            attrs = store.get_attributes(entities[0].id)
            attr_dict = {a.name: a for a in attrs}
            assert attr_dict["value"].value == 30.0
            assert attr_dict["value"].value_type == "number"
            assert attr_dict["unit"].value == "mVpp"

    def test_relation_local_key_resolved(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Relations reference entities by local_key, resolved to real entity_ids."""
        llm_json = json.dumps({
            "entities": [
                {"local_key": "e1", "class": "Parameter", "canonical_name": "纹波", "text_span": "x", "confidence": 0.9},
                {"local_key": "e2", "class": "Method", "canonical_name": "示波器法", "text_span": "y", "confidence": 0.9},
            ],
            "relations": [
                {"source_key": "e1", "relation_type": "verified_by", "target_key": "e2", "confidence": 0.8}
            ],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            extract_document(
                "test",
                document_id="DOC-001",
                domain_pack=obc_domain_pack,
                store=store,
                client=llm_client,
            )
            params = store.list_entities(class_name="Parameter")
            assert len(params) == 1
            rels = store.get_relations(params[0].id, "verified_by")
            assert len(rels) == 1
            target = store.get_entity(rels[0].target_id)
            assert target is not None
            assert target.canonical_name == "示波器法"

    def test_evidence_traceability(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Every extracted entity gets an evidence record."""
        llm_json = json.dumps({
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "纹波",
                    "text_span": "纹波原文",
                    "location": "第3段",
                    "confidence": 0.95,
                },
            ],
            "relations": [],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            extract_document(
                "test",
                document_id="DOC-001",
                domain_pack=obc_domain_pack,
                store=store,
                client=llm_client,
            )
            entities = store.list_entities(class_name="Parameter")
            assert len(entities) == 1
            evidence = store.get_evidence("entity", entities[0].id)
            assert len(evidence) >= 1
            assert evidence[0].document_id == "DOC-001"
            assert "纹波" in evidence[0].text_span

    def test_idempotent_extraction(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Extracting the same document twice should not duplicate entities."""
        llm_json = json.dumps({
            "entities": [
                {"local_key": "e1", "class": "Parameter", "canonical_name": "纹波", "confidence": 0.9},
            ],
            "relations": [],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            # First extraction
            extract_document("test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client)
            # Second extraction (same content)
            extract_document("test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client)

            # find_or_create should dedupe
            entities = store.list_entities(class_name="Parameter")
            assert len(entities) == 1

    def test_invalid_class_skipped(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Entities with classes not in domain pack are skipped."""
        llm_json = json.dumps({
            "entities": [
                {"local_key": "e1", "class": "NonExistentClass", "canonical_name": "x", "confidence": 0.9},
                {"local_key": "e2", "class": "Parameter", "canonical_name": "纹波", "confidence": 0.9},
            ],
            "relations": [],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            assert result.entity_count == 2  # parsed from LLM
            # But only 1 stored (the valid one)
            assert store.stats()["entities"] == 1

    def test_llm_failure_returns_empty(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """LLM call failure → empty result, no crash."""
        def _fail(*args, **kwargs):
            raise error.URLError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", _fail)

        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            assert result.entity_count == 0
            assert result.relation_count == 0

    def test_invalid_json_returns_empty(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Invalid JSON response → empty result, no crash."""
        resp_body = _fake_anthropic_response("not valid json {{{")
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            assert result.entity_count == 0

    def test_empty_text_returns_empty(self, tmp_path, llm_client, obc_domain_pack):
        """Empty text → empty result without calling LLM."""
        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            assert result.entity_count == 0

    def test_unresolved_relation_skipped(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Relations referencing non-existent local_keys are skipped."""
        llm_json = json.dumps({
            "entities": [
                {"local_key": "e1", "class": "Parameter", "canonical_name": "纹波", "confidence": 0.9},
            ],
            "relations": [
                {"source_key": "e1", "relation_type": "verified_by", "target_key": "e999", "confidence": 0.8}
            ],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            result = extract_document(
                "test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            # Entity stored, relation skipped (target e999 doesn't exist)
            assert store.stats()["entities"] == 1
            assert store.stats()["relations"] == 0

    def test_multi_identity_entity_condition_in_name(self, monkeypatch, tmp_path, llm_client, obc_domain_pack):
        """Parameter with condition gets condition folded into canonical_name for dedup."""
        llm_json = json.dumps({
            "entities": [
                {
                    "local_key": "e1",
                    "class": "Parameter",
                    "canonical_name": "输出纹波",
                    "attributes": {"value": 30, "condition": "额定负载"},
                    "confidence": 0.9,
                },
                {
                    "local_key": "e2",
                    "class": "Parameter",
                    "canonical_name": "输出纹波",
                    "attributes": {"value": 50, "condition": "空载"},
                    "confidence": 0.9,
                },
            ],
            "relations": [],
        })
        resp_body = _fake_anthropic_response(llm_json)
        monkeypatch.setattr("urllib.request.urlopen", _patch_urlopen(resp_body))

        with OntologyStore(tmp_path / "test.db") as store:
            extract_document(
                "test", document_id="DOC-001", domain_pack=obc_domain_pack, store=store, client=llm_client,
            )
            params = store.list_entities(class_name="Parameter")
            assert len(params) == 2  # different conditions → different entities
            names = {p.canonical_name for p in params}
            assert any("额定负载" in n for n in names)
            assert any("空载" in n for n in names)
