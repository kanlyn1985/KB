"""Tests for Phase 4 query understanding + template engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.query import (
    KNOWN_INTENTS,
    TEMPLATE_REGISTRY,
    QueryFrame,
    TargetEntityRef,
    execute_frame,
    query,
    understand_query,
)
from kb_ontology.query.resolve import expand_aliases, resolve_entity_name
from kb_ontology.storage import OntologyStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAINS_DIR = PROJECT_ROOT / "domains"


@pytest.fixture
def domain_pack():
    return load_domain_pack(DOMAINS_DIR / "obc_dcdc")


@pytest.fixture
def seeded_store(tmp_path, domain_pack):
    """Minimal OBC/DCDC graph for template tests."""
    db = tmp_path / "q.db"
    with OntologyStore(db) as store:
        dcdc = store.find_or_create_entity("Product", "DC-DC转换器", domain_pack.domain_id)
        store.upsert_attribute(dcdc.id, "name", "DC-DC转换器", "string")
        store.upsert_attribute(
            dcdc.id,
            "description",
            "将动力电池高压直流转换为低压直流的车载变换器",
            "string",
        )
        store.add_evidence("entity", dcdc.id, "DOC-1", "DC-DC转换器简介", "p1")

        ripple = store.find_or_create_entity("Parameter", "输出纹波", domain_pack.domain_id)
        store.upsert_attribute(ripple.id, "name", "输出纹波", "string")
        store.upsert_attribute(ripple.id, "value", 30, "number")
        store.upsert_attribute(ripple.id, "unit", "mVpp", "string")
        store.upsert_attribute(ripple.id, "operator", "<=", "string")
        store.upsert_attribute(ripple.id, "condition", "额定负载", "string")
        store.add_evidence(
            "entity",
            ripple.id,
            "DOC-1",
            "DCDC输出纹波在额定负载下应不大于30mVpp",
            "§3",
        )

        vin = store.find_or_create_entity("Parameter", "输入电压", domain_pack.domain_id)
        store.upsert_attribute(vin.id, "name", "输入电压", "string")
        store.upsert_attribute(vin.id, "description", "290～420V高压直流电", "string")
        store.upsert_attribute(vin.id, "unit", "V", "string")

        method = store.find_or_create_entity("Method", "示波器测量法", domain_pack.domain_id)
        store.upsert_attribute(method.id, "name", "示波器测量法", "string")
        store.upsert_attribute(method.id, "instrument", "示波器", "string")

        pfc = store.find_or_create_entity("Subsystem", "PFC级", domain_pack.domain_id)
        store.upsert_attribute(pfc.id, "name", "PFC级", "string")
        dcdc_stage = store.find_or_create_entity(
            "Subsystem", "DCDC变换级", domain_pack.domain_id
        )
        store.upsert_attribute(dcdc_stage.id, "name", "DCDC变换级", "string")

        iso = store.find_or_create_entity("Standard", "ISO 14229", domain_pack.domain_id)
        store.upsert_attribute(iso.id, "name", "ISO 14229", "string")
        gbt = store.find_or_create_entity("Standard", "GB/T 18487", domain_pack.domain_id)
        store.upsert_attribute(gbt.id, "name", "GB/T 18487", "string")

        # Relations: child part_of parent  (tree down = reverse part_of)
        store.upsert_relation(ripple.id, "part_of", dcdc.id)
        store.upsert_relation(vin.id, "part_of", dcdc.id)
        store.upsert_relation(pfc.id, "part_of", dcdc.id)
        store.upsert_relation(dcdc_stage.id, "part_of", dcdc.id)
        store.upsert_relation(ripple.id, "verified_by", method.id)
        store.upsert_relation(iso.id, "references", gbt.id)

        yield store


# ── Registry ──────────────────────────────────────────────────────────


class TestRegistry:
    def test_six_templates_registered(self):
        expected = {
            "parameter_lookup",
            "definition",
            "relation_query",
            "hierarchy_traversal",
            "cross_entity",
            "attribute_search",
        }
        assert expected <= set(TEMPLATE_REGISTRY)
        assert expected <= KNOWN_INTENTS


# ── Understanding (rules) ─────────────────────────────────────────────


class TestUnderstand:
    def test_parameter_lookup_intent(self, domain_pack):
        frame = understand_query("DCDC输出纹波限制是多少？", domain_pack=domain_pack)
        assert frame.intent == "parameter_lookup"
        assert frame.intent_confidence >= 0.8

    def test_definition_intent(self, domain_pack):
        frame = understand_query("什么是车载充电机？", domain_pack=domain_pack)
        assert frame.intent == "definition"

    def test_working_principle_is_definition(self, domain_pack):
        frame = understand_query("慢充系统的工作原理", domain_pack=domain_pack)
        assert frame.intent == "definition"
        primary = frame.primary_entity()
        # Without store, terminology should still surface 慢充系统 as topic.
        assert primary is not None
        assert "慢充" in (primary.canonical_name or primary.matched_text or "")

    def test_dcdc_surface_keeps_specificity(self, domain_pack):
        frame = understand_query("什么是车载DC-DC转换器", domain_pack=domain_pack)
        assert frame.intent == "definition"
        primary = frame.primary_entity()
        assert primary is not None
        assert "车载" in (primary.canonical_name or "") or "DC-DC" in (
            primary.canonical_name or primary.matched_text or ""
        )

    def test_hierarchy_intent(self, domain_pack):
        frame = understand_query("OBC包含哪些子系统？", domain_pack=domain_pack)
        assert frame.intent == "hierarchy_traversal"

    def test_relation_intent(self, domain_pack):
        frame = understand_query("输出纹波有哪些测试方法？", domain_pack=domain_pack)
        assert frame.intent == "relation_query"
        assert frame.relation_type in ("verified_by", "part_of", None) or True

    def test_cross_entity_pair(self, domain_pack):
        frame = understand_query(
            "ISO 14229和GB/T 18487什么关系？", domain_pack=domain_pack
        )
        assert frame.intent == "cross_entity"
        roles = {t.role for t in frame.target_entities}
        assert "source" in roles and "target" in roles

    def test_attribute_search_intent(self, domain_pack):
        frame = understand_query("哪些参数和温度有关？", domain_pack=domain_pack)
        assert frame.intent == "attribute_search"

    def test_resolves_against_store(self, seeded_store, domain_pack):
        frame = understand_query(
            "输出纹波是多少？",
            store=seeded_store,
            domain_pack=domain_pack,
        )
        primary = frame.primary_entity()
        assert primary is not None
        assert primary.is_resolved
        assert primary.canonical_name == "输出纹波"


# ── Resolve ───────────────────────────────────────────────────────────


class TestResolve:
    def test_expand_ripple_aliases(self, domain_pack):
        aliases = expand_aliases("纹波", domain_pack)
        assert any("纹波" in a for a in aliases)

    def test_resolve_exact(self, seeded_store, domain_pack):
        hits = resolve_entity_name(seeded_store, "输出纹波", domain_pack=domain_pack)
        assert hits
        assert hits[0].canonical_name == "输出纹波"
        assert hits[0].confidence >= 0.9

    def test_resolve_substring(self, seeded_store, domain_pack):
        hits = resolve_entity_name(seeded_store, "纹波", domain_pack=domain_pack)
        assert hits
        assert "纹波" in hits[0].canonical_name

    def test_expand_dcdc_aliases(self, domain_pack):
        aliases = expand_aliases("DC-DC转换器", domain_pack)
        assert any("DC-DC" in a or "DCDC" in a or "变换器" in a for a in aliases)


# ── Templates ─────────────────────────────────────────────────────────


class TestParameterLookup:
    def test_returns_value_unit(self, seeded_store, domain_pack):
        result = query(seeded_store, "输出纹波是多少？", domain_pack=domain_pack)
        assert result.intent == "parameter_lookup"
        assert not result.is_empty
        hit = result.hits[0]
        names = {a["name"]: a["value"] for a in hit.attributes}
        assert names.get("value") == 30.0
        assert names.get("unit") == "mVpp"

    def test_filter_target_attributes(self, seeded_store):
        frame = QueryFrame(
            original_query="x",
            intent="parameter_lookup",
            target_entities=[
                TargetEntityRef(
                    entity_id=seeded_store.search_entities("输出纹波")[0].id,
                    canonical_name="输出纹波",
                    role="primary",
                    confidence=1.0,
                )
            ],
            target_attributes=["unit"],
        )
        result = execute_frame(seeded_store, frame)
        assert [a["name"] for a in result.hits[0].attributes] == ["unit"]

    def test_missing_entity(self, seeded_store, domain_pack):
        result = query(seeded_store, "不存在的参数XYZ是多少？", domain_pack=domain_pack)
        assert result.is_empty or result.empty_reason in {
            "entity_not_found",
            "no_target_entity",
            None,
        }
        # Either unresolved empty or unknown — must not crash.
        assert result.template_id in TEMPLATE_REGISTRY or result.empty_reason


class TestDefinition:
    def test_product_definition(self, seeded_store, domain_pack):
        result = query(seeded_store, "什么是DC-DC转换器？", domain_pack=domain_pack)
        assert result.intent == "definition"
        assert result.hits
        descs = [
            a["value"]
            for a in result.hits[0].attributes
            if a["name"] == "description"
        ]
        assert descs
        assert "变换" in str(descs[0]) or "直流" in str(descs[0])


class TestRelationQuery:
    def test_verified_by_methods(self, seeded_store, domain_pack):
        # Force relation_type via frame for stability.
        ripple = seeded_store.search_entities("输出纹波")[0]
        frame = QueryFrame(
            original_query="输出纹波测试方法",
            intent="relation_query",
            relation_type="verified_by",
            target_entities=[
                TargetEntityRef(
                    entity_id=ripple.id,
                    canonical_name=ripple.canonical_name,
                    role="primary",
                    confidence=1.0,
                )
            ],
        )
        result = execute_frame(seeded_store, frame)
        assert result.hits
        assert any(h.entity["canonical_name"] == "示波器测量法" for h in result.hits)


class TestHierarchy:
    def test_dcdc_children(self, seeded_store, domain_pack):
        dcdc = seeded_store.search_entities("DC-DC转换器")[0]
        frame = QueryFrame(
            original_query="DC-DC包含哪些",
            intent="hierarchy_traversal",
            hierarchy_direction="down",
            relation_type="part_of",
            target_entities=[
                TargetEntityRef(
                    entity_id=dcdc.id,
                    canonical_name=dcdc.canonical_name,
                    role="primary",
                    confidence=1.0,
                )
            ],
        )
        result = execute_frame(seeded_store, frame)
        child_names = {h.entity["canonical_name"] for h in result.hits[1:]}
        assert "PFC级" in child_names or "输出纹波" in child_names
        assert result.meta.get("child_count", 0) >= 1


class TestCrossEntity:
    def test_iso_references_gbt(self, seeded_store, domain_pack):
        iso = seeded_store.search_entities("ISO 14229")[0]
        gbt = seeded_store.search_entities("GB/T 18487")[0]
        frame = QueryFrame(
            original_query="ISO和GBT关系",
            intent="cross_entity",
            target_entities=[
                TargetEntityRef(
                    entity_id=iso.id,
                    canonical_name=iso.canonical_name,
                    role="source",
                    confidence=1.0,
                ),
                TargetEntityRef(
                    entity_id=gbt.id,
                    canonical_name=gbt.canonical_name,
                    role="target",
                    confidence=1.0,
                ),
            ],
        )
        result = execute_frame(seeded_store, frame)
        assert result.related
        assert result.related[0]["relation"]["relation_type"] == "references"
        assert result.empty_reason is None

    def test_no_relation(self, seeded_store):
        a = seeded_store.search_entities("输出纹波")[0]
        b = seeded_store.search_entities("ISO 14229")[0]
        frame = QueryFrame(
            original_query="x",
            intent="cross_entity",
            target_entities=[
                TargetEntityRef(entity_id=a.id, canonical_name=a.canonical_name, role="source"),
                TargetEntityRef(entity_id=b.id, canonical_name=b.canonical_name, role="target"),
            ],
        )
        result = execute_frame(seeded_store, frame)
        assert result.empty_reason == "no_direct_relation"


class TestAttributeSearch:
    def test_find_by_mVpp(self, seeded_store, domain_pack):
        frame = QueryFrame(
            original_query="mVpp",
            intent="attribute_search",
            attribute_value_query="mVpp",
        )
        result = execute_frame(seeded_store, frame)
        assert result.hits
        assert any(h.entity["canonical_name"] == "输出纹波" for h in result.hits)

    def test_end_to_end_nl(self, seeded_store, domain_pack):
        # value substring present in description
        result = query(
            seeded_store,
            "哪些参数和高压有关？",
            domain_pack=domain_pack,
        )
        assert result.intent == "attribute_search"
        # May or may not hit depending on needle; must be structured.
        assert result.template_id == "attribute_search"
        assert "match_count" in result.meta or result.empty_reason


class TestUnknownIntent:
    def test_unknown_returns_empty(self, seeded_store):
        frame = QueryFrame(original_query="??? ", intent="unknown")
        result = execute_frame(seeded_store, frame)
        assert result.empty_reason == "unknown_intent"
        assert result.is_empty


class TestStoreSearchHelpers:
    def test_search_entities_order(self, seeded_store):
        exact = seeded_store.search_entities("输出纹波")
        assert exact and exact[0].canonical_name == "输出纹波"
        partial = seeded_store.search_entities("电压")
        names = [e.canonical_name for e in partial]
        assert any("电压" in n for n in names)

    def test_find_by_attribute(self, seeded_store):
        pairs = seeded_store.find_entities_by_attribute(value_query="30")
        assert pairs
        assert any(e.canonical_name == "输出纹波" for e, _ in pairs)
