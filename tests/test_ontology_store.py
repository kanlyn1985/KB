"""Tests for OntologyStore — the four-table SQLite storage layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_ontology.storage import (
    Attribute,
    Entity,
    Evidence,
    OntologyStore,
    Relation,
    deserialize_value,
    serialize_value,
)


# ═══════════════════════════════════════════════════════════════════════
# Serialization helpers
# ═══════════════════════════════════════════════════════════════════════


class TestSerializeValue:
    def test_number(self):
        assert serialize_value(30, "number") == "30.0"
        assert serialize_value(3.14, "number") == "3.14"

    def test_boolean(self):
        assert serialize_value(True, "boolean") == "true"
        assert serialize_value(False, "boolean") == "false"

    def test_string(self):
        assert serialize_value("hello", "string") == "hello"

    def test_entity_ref(self):
        assert serialize_value("ent_abc123", "entity_ref") == "ent_abc123"

    def test_none(self):
        assert serialize_value(None, "string") is None


class TestDeserializeValue:
    def test_number(self):
        assert deserialize_value("30.0", "number") == 30.0
        assert deserialize_value("3.14", "number") == 3.14

    def test_boolean(self):
        assert deserialize_value("true", "boolean") is True
        assert deserialize_value("false", "boolean") is False

    def test_string(self):
        assert deserialize_value("hello", "string") == "hello"

    def test_none(self):
        assert deserialize_value(None, "number") is None

    def test_number_graceful_degradation(self):
        assert deserialize_value("not_a_number", "number") == "not_a_number"


# ═══════════════════════════════════════════════════════════════════════
# OntologyStore — schema and connection
# ═══════════════════════════════════════════════════════════════════════


class TestStoreConnection:
    def test_context_manager(self, tmp_path):
        db = tmp_path / "test.db"
        with OntologyStore(db) as store:
            assert store.connection is not None
        # After exit, connection closed
        assert store._conn is None

    def test_schema_created(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            tables = {
                row["name"]
                for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "entities" in tables
            assert "attributes" in tables
            assert "relations" in tables
            assert "evidence" in tables

    def test_creates_parent_dir(self, tmp_path):
        db = tmp_path / "subdir" / "nested" / "test.db"
        with OntologyStore(db):
            pass
        assert db.exists()


# ═══════════════════════════════════════════════════════════════════════
# Entity CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestEntityCRUD:
    def test_create_entity(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波", "obc_dcdc")
            assert entity.id.startswith("ent_")
            assert entity.class_name == "Parameter"
            assert entity.canonical_name == "输出纹波"
            assert entity.domain == "obc_dcdc"

    def test_get_entity(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Standard", "ISO 14229")
            fetched = store.get_entity(entity.id)
            assert fetched is not None
            assert fetched.canonical_name == "ISO 14229"

    def test_get_entity_not_found(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            assert store.get_entity("nonexistent") is None

    def test_find_entity_by_name(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            store.upsert_entity("Parameter", "输出纹波", "obc_dcdc")
            store.upsert_entity("Parameter", "效率", "obc_dcdc")
            results = store.find_entity_by_name("Parameter", "输出纹波")
            assert len(results) == 1
            assert results[0].canonical_name == "输出纹波"

    def test_find_entity_by_name_with_domain(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            store.upsert_entity("Concept", "test", "domain_a")
            store.upsert_entity("Concept", "test", "domain_b")
            results = store.find_entity_by_name("Concept", "test", "domain_a")
            assert len(results) == 1
            assert results[0].domain == "domain_a"

    def test_find_or_create_creates_new(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.find_or_create_entity("Method", "示波器测量法")
            assert entity.id.startswith("ent_")

    def test_find_or_create_finds_existing(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            created = store.find_or_create_entity("Method", "示波器测量法", "obc_dcdc")
            found = store.find_or_create_entity("Method", "示波器测量法", "obc_dcdc")
            assert created.id == found.id  # same entity

    def test_list_entities_by_class(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            store.upsert_entity("Parameter", "纹波")
            store.upsert_entity("Parameter", "效率")
            store.upsert_entity("Standard", "ISO 14229")
            params = store.list_entities(class_name="Parameter")
            assert len(params) == 2
            stds = store.list_entities(class_name="Standard")
            assert len(stds) == 1


# ═══════════════════════════════════════════════════════════════════════
# Attribute CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestAttributeCRUD:
    def test_create_number_attribute(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            attr = store.upsert_attribute(entity.id, "value", 30, "number")
            assert attr.value == 30.0
            assert attr.value_type == "number"

    def test_create_boolean_attribute(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Requirement", "安全要求")
            attr = store.upsert_attribute(entity.id, "mandatory", True, "boolean")
            assert attr.value is True

    def test_create_string_attribute(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            attr = store.upsert_attribute(entity.id, "unit", "mVpp", "string")
            assert attr.value == "mVpp"

    def test_get_attributes(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            store.upsert_attribute(entity.id, "value", 30, "number")
            store.upsert_attribute(entity.id, "unit", "mVpp")
            store.upsert_attribute(entity.id, "operator", "<=")
            attrs = store.get_attributes(entity.id)
            assert len(attrs) == 3

    def test_upsert_replaces_existing(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            store.upsert_attribute(entity.id, "value", 30, "number")
            store.upsert_attribute(entity.id, "value", 25, "number")  # update
            attrs = store.get_attributes(entity.id)
            assert len(attrs) == 1  # not duplicated
            assert attrs[0].value == 25.0  # updated value

    def test_get_single_attribute(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            store.upsert_attribute(entity.id, "value", 30, "number")
            attr = store.get_attribute(entity.id, "value")
            assert attr is not None
            assert attr.value == 30.0
            assert store.get_attribute(entity.id, "nonexistent") is None


# ═══════════════════════════════════════════════════════════════════════
# Relation CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestRelationCRUD:
    def test_create_relation(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            rel = store.upsert_relation(ripple.id, "verified_by", method.id)
            assert rel.relation_type == "verified_by"
            assert rel.target_id == method.id

    def test_get_outgoing_relations(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            std = store.upsert_entity("Standard", "ISO 14229")
            store.upsert_relation(ripple.id, "verified_by", method.id)
            store.upsert_relation(ripple.id, "defined_in", std.id)
            rels = store.get_relations(ripple.id)
            assert len(rels) == 2

    def test_get_relations_filtered_by_type(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            std = store.upsert_entity("Standard", "ISO 14229")
            store.upsert_relation(ripple.id, "verified_by", method.id)
            store.upsert_relation(ripple.id, "defined_in", std.id)
            rels = store.get_relations(ripple.id, "verified_by")
            assert len(rels) == 1
            assert rels[0].relation_type == "verified_by"

    def test_get_reverse_relations(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            store.upsert_relation(ripple.id, "verified_by", method.id)
            # From method's perspective, ripple verifies it
            reverse = store.get_reverse_relations(method.id, "verified_by")
            assert len(reverse) == 1
            assert reverse[0].source_id == ripple.id

    def test_upsert_relation_idempotent(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            rel1 = store.upsert_relation(ripple.id, "verified_by", method.id)
            rel2 = store.upsert_relation(ripple.id, "verified_by", method.id)
            assert rel1.id == rel2.id  # same relation, not duplicated


# ═══════════════════════════════════════════════════════════════════════
# Evidence CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestEvidenceCRUD:
    def test_add_evidence(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            evd = store.add_evidence(
                "entity", entity.id, "DOC-000001",
                text_span="DCDC输出纹波应不大于30mVpp",
                location="page 3, paragraph 2",
            )
            assert evd.document_id == "DOC-000001"
            assert "30mVpp" in evd.text_span

    def test_get_evidence(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            store.add_evidence("entity", entity.id, "DOC-000001", text_span="来源1")
            store.add_evidence("entity", entity.id, "DOC-000002", text_span="来源2")
            evidence = store.get_evidence("entity", entity.id)
            assert len(evidence) == 2

    def test_evidence_for_attribute(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波")
            attr = store.upsert_attribute(entity.id, "value", 30, "number")
            store.add_evidence("attribute", attr.id, "DOC-000001", text_span="30mVpp")
            evidence = store.get_evidence("attribute", attr.id)
            assert len(evidence) == 1


# ═══════════════════════════════════════════════════════════════════════
# Graph traversal
# ═══════════════════════════════════════════════════════════════════════


class TestEntityTree:
    def test_traverse_down_part_of(self, tmp_path):
        """OBC → DCDC模块 → 输出纹波"""
        with OntologyStore(tmp_path / "test.db") as store:
            obc = store.upsert_entity("Product", "OBC")
            dcdc = store.upsert_entity("Subsystem", "DCDC模块")
            ripple = store.upsert_entity("Parameter", "输出纹波")
            # DCDC is part_of OBC
            store.upsert_relation(dcdc.id, "part_of", obc.id)
            # Ripple is part_of DCDC
            store.upsert_relation(ripple.id, "part_of", dcdc.id)

            tree = store.get_entity_tree(obc.id, direction="down")
            assert tree["entity"]["canonical_name"] == "OBC"
            assert len(tree["children"]) == 1  # DCDC模块
            assert tree["children"][0]["entity"]["canonical_name"] == "DCDC模块"
            assert len(tree["children"][0]["children"]) == 1  # 输出纹波
            assert tree["children"][0]["children"][0]["entity"]["canonical_name"] == "输出纹波"

    def test_traverse_up_part_of(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            obc = store.upsert_entity("Product", "OBC")
            dcdc = store.upsert_entity("Subsystem", "DCDC模块")
            store.upsert_relation(dcdc.id, "part_of", obc.id)

            tree = store.get_entity_tree(dcdc.id, direction="up")
            assert tree["entity"]["canonical_name"] == "DCDC模块"
            assert len(tree["children"]) == 1  # OBC is parent
            assert tree["children"][0]["entity"]["canonical_name"] == "OBC"

    def test_no_infinite_loop(self, tmp_path):
        """Circular references should not cause infinite recursion."""
        with OntologyStore(tmp_path / "test.db") as store:
            a = store.upsert_entity("Concept", "A")
            b = store.upsert_entity("Concept", "B")
            store.upsert_relation(a.id, "part_of", b.id)
            store.upsert_relation(b.id, "part_of", a.id)  # circular
            tree = store.get_entity_tree(a.id, direction="up", max_depth=10)
            # Should complete without hanging
            assert tree["entity"] is not None


# ═══════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════


class TestStats:
    def test_empty_stats(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            stats = store.stats()
            assert stats == {"entities": 0, "attributes": 0, "relations": 0, "evidence": 0}

    def test_populated_stats(self, tmp_path):
        with OntologyStore(tmp_path / "test.db") as store:
            ripple = store.upsert_entity("Parameter", "输出纹波")
            method = store.upsert_entity("Method", "示波器测量法")
            store.upsert_attribute(ripple.id, "value", 30, "number")
            store.upsert_attribute(ripple.id, "unit", "mVpp")
            store.upsert_relation(ripple.id, "verified_by", method.id)
            store.add_evidence("entity", ripple.id, "DOC-001")

            stats = store.stats()
            assert stats["entities"] == 2
            assert stats["attributes"] == 2
            assert stats["relations"] == 1
            assert stats["evidence"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Dataclass serialization
# ═══════════════════════════════════════════════════════════════════════


class TestDataclassSerialization:
    def test_entity_to_dict_json_serializable(self):
        e = Entity(id="ent_1", class_name="Parameter", canonical_name="纹波")
        d = e.to_dict()
        json.dumps(d)  # should not raise

    def test_attribute_to_dict(self):
        a = Attribute(id="attr_1", entity_id="ent_1", name="value", value=30.0, value_type="number")
        d = a.to_dict()
        assert d["value"] == 30.0

    def test_relation_to_dict(self):
        r = Relation(id="rel_1", source_id="ent_1", relation_type="part_of", target_id="ent_2")
        d = r.to_dict()
        assert d["relation_type"] == "part_of"

    def test_evidence_to_dict(self):
        e = Evidence(id="evd_1", ref_type="entity", ref_id="ent_1", document_id="DOC-001")
        d = e.to_dict()
        assert d["document_id"] == "DOC-001"
