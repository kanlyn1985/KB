"""Tests for Phase 5 judgement + ContextPack assembly."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock

import pytest

from kb_ontology.context import ContextPack, assemble_context_pack
from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.judgement import judge, judge_rules
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.pipeline import answer_query
from kb_ontology.query import QueryFrame, TargetEntityRef, execute_frame, query
from kb_ontology.storage import OntologyStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAINS_DIR = PROJECT_ROOT / "domains"


@pytest.fixture
def domain_pack():
    return load_domain_pack(DOMAINS_DIR / "obc_dcdc")


@pytest.fixture
def seeded_store(tmp_path, domain_pack):
    db = tmp_path / "j.db"
    with OntologyStore(db) as store:
        dcdc = store.find_or_create_entity("Product", "DC-DC转换器", domain_pack.domain_id)
        store.upsert_attribute(dcdc.id, "name", "DC-DC转换器", "string")
        store.upsert_attribute(
            dcdc.id, "description", "高压转低压的车载变换器", "string"
        )
        store.add_evidence("entity", dcdc.id, "DOC-1", "简介", "p1")

        ripple = store.find_or_create_entity("Parameter", "输出纹波", domain_pack.domain_id)
        store.upsert_attribute(ripple.id, "name", "输出纹波", "string")
        store.upsert_attribute(ripple.id, "value", 30, "number")
        store.upsert_attribute(ripple.id, "unit", "mVpp", "string")
        store.upsert_attribute(ripple.id, "operator", "<=", "string")
        store.add_evidence("entity", ripple.id, "DOC-1", "纹波<=30mVpp", "§3")
        store.upsert_relation(ripple.id, "part_of", dcdc.id)

        weak = store.find_or_create_entity("Parameter", "待机电流", domain_pack.domain_id)
        store.upsert_attribute(weak.id, "name", "待机电流", "string")
        # no value, no evidence

        yield store


class TestRuleJudgement:
    def test_sufficient_parameter_lookup(self, seeded_store, domain_pack):
        result = query(seeded_store, "输出纹波是多少？", domain_pack=domain_pack)
        j = judge_rules(result)
        assert j.status == "sufficient"
        assert j.score >= 0.75
        assert j.needs_semantic is False
        assert j.recommended_strategy == "answer_with_evidence"
        assert j.hit_count >= 1
        assert j.evidence_count >= 1

    def test_definition_sufficient(self, seeded_store, domain_pack):
        result = query(seeded_store, "什么是DC-DC转换器？", domain_pack=domain_pack)
        j = judge_rules(result)
        assert j.status in {"sufficient", "partial"}
        assert j.has_target
        assert j.hit_count >= 1

    def test_missing_entity_insufficient(self, seeded_store, domain_pack):
        result = query(
            seeded_store, "不存在参数QQQ是多少？", domain_pack=domain_pack
        )
        j = judge_rules(result)
        assert j.status in {"insufficient", "partial"}
        assert j.needs_semantic is True
        assert j.recommended_strategy in {
            "report_knowledge_gap",
            "refuse_insufficient",
            "clarify_ambiguity",
            "answer_with_caveat",
        }

    def test_weak_parameter_partial(self, seeded_store, domain_pack):
        # Entity exists but no value → missing parameter_value-ish
        weak = seeded_store.search_entities("待机电流")[0]
        frame = QueryFrame(
            original_query="待机电流是多少",
            intent="parameter_lookup",
            target_entities=[
                TargetEntityRef(
                    entity_id=weak.id,
                    canonical_name=weak.canonical_name,
                    role="primary",
                    confidence=1.0,
                )
            ],
        )
        result = execute_frame(seeded_store, frame)
        j = judge_rules(result)
        assert j.status in {"partial", "insufficient"}
        assert j.needs_semantic is True
        assert any(
            "parameter" in m or "value" in m for m in j.missing_requirements
        ) or j.evidence_count == 0

    def test_unknown_intent(self, seeded_store):
        frame = QueryFrame(original_query="???", intent="unknown")
        result = execute_frame(seeded_store, frame)
        j = judge_rules(result)
        assert j.status == "insufficient"
        assert "unknown_intent" in j.missing_requirements


class TestSemanticFallback:
    def test_no_llm_when_sufficient(self, seeded_store, domain_pack):
        result = query(seeded_store, "输出纹波是多少？", domain_pack=domain_pack)
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="x",
            api_format="openai",
        )

        def _boom(*args, **kwargs):
            raise AssertionError("should not call")

        # Patch on the class — LLMChatClient is a frozen dataclass.
        with mock.patch.object(LLMChatClient, "chat", side_effect=_boom):
            j = judge(result, client=client, use_llm=True)
        assert j.used_llm is False
        assert j.status == "sufficient"

    def test_llm_refines_when_partial(self, seeded_store, domain_pack, monkeypatch):
        result = query(
            seeded_store, "不存在参数QQQ是多少？", domain_pack=domain_pack
        )
        base = judge_rules(result)
        assert base.needs_semantic

        payload = {
            "id": "c1",
            "model": "grok-4.5",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "evidence_quality": "poor",
                                "knowledge_gaps": ["本体中无此参数"],
                                "recommended_strategy": "report_knowledge_gap",
                                "notes": ["未命中实体"],
                                "status_override": "insufficient",
                            }
                        ),
                    }
                }
            ],
            "usage": {},
        }

        def _open(*args, **kwargs):
            return io.BytesIO(json.dumps(payload).encode())

        monkeypatch.setattr("urllib.request.urlopen", _open)
        client = LLMChatClient(
            endpoint="https://api.cdn-krill-ai.com/v1",
            model="grok-4.5",
            api_key="x",
            api_format="openai",
        )
        j = judge(result, client=client, use_llm=True)
        assert j.used_llm is True
        assert j.recommended_strategy == "report_knowledge_gap"
        assert any("本体中无此参数" in g for g in j.knowledge_gaps)
        assert any("evidence_quality:poor" in n for n in j.semantic_notes)


class TestContextPack:
    def test_assemble(self, seeded_store, domain_pack):
        result = query(seeded_store, "输出纹波是多少？", domain_pack=domain_pack)
        j = judge_rules(result)
        pack = assemble_context_pack(result, j)
        assert isinstance(pack, ContextPack)
        assert pack.intent == "parameter_lookup"
        assert pack.hits
        assert pack.judgement is not None
        assert pack.judgement.status == "sufficient"
        assert pack.recommended_answer_strategy == "answer_with_evidence"
        d = pack.to_dict()
        assert d["evidence_sufficient"] is True
        assert d["hit_count"] >= 1

    def test_pipeline_answer_query(self, seeded_store, domain_pack):
        pack = answer_query(
            seeded_store,
            "什么是DC-DC转换器？",
            domain_pack=domain_pack,
        )
        assert pack.intent == "definition"
        assert pack.judgement is not None
        assert pack.judgement.status in {"sufficient", "partial"}
        assert pack.query_frame.original_query.startswith("什么是")
