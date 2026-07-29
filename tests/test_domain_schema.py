"""Tests for domain pack schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_ontology.domains.schema import (
    AttributeSpec,
    CORE_RELATION_TYPES,
    ClassSpec,
    DomainPack,
    DomainPackError,
    RelationRole,
    RelationTypeSpec,
    VALUE_TYPES,
)
from kb_ontology.domains.loader import load_domain_pack

# ── Paths ──

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAINS_DIR = PROJECT_ROOT / "domains"


# ═══════════════════════════════════════════════════════════════════════
# Schema dataclass tests
# ═══════════════════════════════════════════════════════════════════════


class TestAttributeSpec:
    def test_default_string_type(self):
        attr = AttributeSpec(name="foo")
        assert attr.value_type == "string"
        assert attr.required is False

    def test_required_number(self):
        attr = AttributeSpec(name="value", value_type="number", required=True)
        assert attr.value_type == "number"
        assert attr.required is True

    def test_enum_values(self):
        attr = AttributeSpec(
            name="operator",
            value_type="string",
            enum_values=["<=", ">=", "="],
        )
        assert attr.enum_values == ["<=", ">=", "="]

    def test_invalid_value_type_raises(self):
        with pytest.raises(DomainPackError, match="invalid value_type"):
            AttributeSpec(name="x", value_type="float32")

    def test_all_value_types_accepted(self):
        for vt in VALUE_TYPES:
            AttributeSpec(name="x", value_type=vt)

    def test_to_dict(self):
        attr = AttributeSpec(name="value", value_type="number", required=True)
        d = attr.to_dict()
        assert d["name"] == "value"
        assert d["value_type"] == "number"
        assert d["required"] is True


class TestRelationTypeSpec:
    def test_core_relation_defaults(self):
        spec = RelationTypeSpec(name="part_of", is_core=True)
        assert spec.is_core is True
        assert spec.inverse_name is None

    def test_to_dict(self):
        spec = RelationTypeSpec(name="verified_by", description="x", inverse_name="verifies")
        d = spec.to_dict()
        assert d["name"] == "verified_by"
        assert d["inverse_name"] == "verifies"
        assert d["is_core"] is False


class TestClassSpec:
    def test_basic_class(self):
        cls = ClassSpec(name="Parameter")
        assert cls.name == "Parameter"
        assert cls.display_primary == "name"

    def test_class_with_attributes(self):
        cls = ClassSpec(
            name="Parameter",
            attribute_template={
                "value": AttributeSpec(name="value", value_type="number"),
                "unit": AttributeSpec(name="unit"),
            },
        )
        assert "value" in cls.attribute_template
        assert cls.attribute_template["value"].value_type == "number"

    def test_to_dict_roundtrip(self):
        cls = ClassSpec(
            name="X",
            description="test",
            attribute_template={"name": AttributeSpec(name="name", required=True)},
            identity_attributes=["name"],
            display_primary="name",
        )
        d = cls.to_dict()
        assert d["name"] == "X"
        assert d["attribute_template"]["name"]["required"] is True
        assert d["identity_attributes"] == ["name"]


class TestCoreRelationTypes:
    def test_part_of_exists(self):
        assert "part_of" in CORE_RELATION_TYPES
        assert CORE_RELATION_TYPES["part_of"].is_core is True
        assert CORE_RELATION_TYPES["part_of"].inverse_name == "has_part"

    def test_references_exists(self):
        assert "references" in CORE_RELATION_TYPES
        assert CORE_RELATION_TYPES["references"].is_core is True
        assert CORE_RELATION_TYPES["references"].inverse_name == "referenced_by"

    def test_only_two_core_types(self):
        assert len(CORE_RELATION_TYPES) == 2


class TestDomainPack:
    def test_all_relation_types_merges_core_and_domain(self):
        dp = DomainPack(
            domain_id="test",
            relation_types={
                "verified_by": RelationTypeSpec(name="verified_by"),
            },
        )
        merged = dp.all_relation_types
        assert "part_of" in merged  # core
        assert "references" in merged  # core
        assert "verified_by" in merged  # domain
        assert len(merged) == 3

    def test_get_class(self):
        dp = DomainPack(
            domain_id="test",
            classes={"X": ClassSpec(name="X")},
        )
        assert dp.get_class("X") is not None
        assert dp.get_class("Y") is None

    def test_get_relation_type_checks_core(self):
        dp = DomainPack(domain_id="test")
        assert dp.get_relation_type("part_of") is not None
        assert dp.get_relation_type("nonexistent") is None


# ═══════════════════════════════════════════════════════════════════════
# Loader tests
# ═══════════════════════════════════════════════════════════════════════


class TestLoaderErrors:
    def test_missing_directory(self):
        with pytest.raises(DomainPackError, match="domain directory not found"):
            load_domain_pack(Path("/nonexistent/path"))

    def test_missing_domain_json(self, tmp_path):
        (tmp_path / "classes.json").write_text('{"classes": {}}')
        with pytest.raises(DomainPackError, match="missing domain metadata"):
            load_domain_pack(tmp_path)

    def test_missing_domain_id(self, tmp_path):
        (tmp_path / "domain.json").write_text('{"name": "test"}')
        with pytest.raises(DomainPackError, match="domain_id is required"):
            load_domain_pack(tmp_path)

    def test_invalid_json_not_object(self, tmp_path):
        (tmp_path / "domain.json").write_text('[1, 2, 3]')
        with pytest.raises(DomainPackError, match="must contain a JSON object"):
            load_domain_pack(tmp_path)


class TestLoaderMinimal:
    def test_load_minimal_pack(self, tmp_path):
        (tmp_path / "domain.json").write_text(
            json.dumps({"domain_id": "minimal", "name": "Minimal Test"})
        )
        dp = load_domain_pack(tmp_path)
        assert dp.domain_id == "minimal"
        assert dp.name == "Minimal Test"
        assert len(dp.classes) == 0
        assert len(dp.terminology) == 0
        # Core relations always available
        assert "part_of" in dp.all_relation_types

    def test_load_with_id_alias(self, tmp_path):
        (tmp_path / "domain.json").write_text(
            json.dumps({"id": "aliased"})
        )
        dp = load_domain_pack(tmp_path)
        assert dp.domain_id == "aliased"

    def test_tolerates_missing_optional_files(self, tmp_path):
        (tmp_path / "domain.json").write_text(
            json.dumps({"domain_id": "no_files"})
        )
        dp = load_domain_pack(tmp_path)
        assert dp.classes == {}
        assert dp.relation_types == {}
        assert dp.terminology == {}


# ═══════════════════════════════════════════════════════════════════════
# Real domain pack tests
# ═══════════════════════════════════════════════════════════════════════


class TestGenericDomainPack:
    def test_loads_successfully(self):
        dp = load_domain_pack(DOMAINS_DIR / "generic")
        assert dp.domain_id == "generic"

    def test_has_concept_class(self):
        dp = load_domain_pack(DOMAINS_DIR / "generic")
        cls = dp.get_class("Concept")
        assert cls is not None
        assert "name" in cls.attribute_template
        assert cls.attribute_template["name"].required is True

    def test_concept_has_core_relation_roles(self):
        dp = load_domain_pack(DOMAINS_DIR / "generic")
        cls = dp.get_class("Concept")
        role_types = {r.relation_type for r in cls.relation_roles}
        assert "part_of" in role_types
        assert "references" in role_types


class TestObcDcdcDomainPack:
    def test_loads_successfully(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        assert dp.domain_id == "obc_dcdc"
        assert "OBC" in dp.name

    def test_has_six_classes(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        expected = {"Product", "Subsystem", "Parameter", "Standard", "Method", "Requirement"}
        assert set(dp.classes.keys()) == expected

    def test_parameter_class_has_value_unit_operator(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        param = dp.get_class("Parameter")
        assert param is not None
        assert "value" in param.attribute_template
        assert param.attribute_template["value"].value_type == "number"
        assert "unit" in param.attribute_template
        assert "operator" in param.attribute_template
        assert param.attribute_template["operator"].enum_values == ["<=", ">=", "=", ">", "<", "~"]

    def test_parameter_identity_uses_name_and_condition(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        param = dp.get_class("Parameter")
        assert "name" in param.identity_attributes
        assert "condition" in param.identity_attributes

    def test_parameter_relation_roles(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        param = dp.get_class("Parameter")
        role_types = {r.relation_type for r in param.relation_roles}
        assert "part_of" in role_types
        assert "verified_by" in role_types
        assert "constrained_by" in role_types
        assert "defined_in" in role_types

    def test_domain_relations_include_verified_by(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        assert "verified_by" in dp.relation_types
        assert dp.relation_types["verified_by"].inverse_name == "verifies"

    def test_all_relation_types_has_core_plus_domain(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        merged = dp.all_relation_types
        assert "part_of" in merged  # core
        assert "references" in merged  # core
        assert "verified_by" in merged  # domain
        assert "constrained_by" in merged  # domain
        assert "defined_in" in merged  # domain

    def test_core_relations_are_marked_core(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        assert dp.all_relation_types["part_of"].is_core is True
        assert dp.all_relation_types["verified_by"].is_core is False

    def test_standard_identity_by_code(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        std = dp.get_class("Standard")
        assert std.identity_attributes == ["code"]
        assert std.display_primary == "code"

    def test_terminology_has_core_terms(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        assert "DCDC_OUTPUT_RIPPLE" in dp.terminology
        assert "输出纹波" in dp.terminology["DCDC_OUTPUT_RIPPLE"]
        assert "OBC" in dp.terminology
        assert "ISO_14229" in dp.terminology
        assert "AUTOSAR" in dp.terminology

    def test_to_dict_serializable(self):
        dp = load_domain_pack(DOMAINS_DIR / "obc_dcdc")
        d = dp.to_dict()
        # Should be JSON-serializable
        json.dumps(d)
        assert d["domain_id"] == "obc_dcdc"
        assert "Parameter" in d["classes"]
