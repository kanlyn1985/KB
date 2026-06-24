"""Tests for the attribute_store module.

These tests are designed against the GOALS of Phase 4 — proving
the attribute store supports the four value types (string, number,
range, reference), parses real-world range formats, and answers
attribute-value queries.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb1_ontology.attribute_store import (
    AttributeStoreError,
    VALUE_TYPE_NUMBER,
    VALUE_TYPE_RANGE,
    VALUE_TYPE_REFERENCE,
    VALUE_TYPE_STRING,
    delete_attribute,
    get_attribute,
    list_attributes,
    parse_range_value,
    query_attributes,
    set_attribute,
)
from kb1_ontology.class_registry import (
    ensure_schema as ensure_class_schema,
    seed_core_classes,
)
from kb1_ontology.db import connect
from kb1_ontology.entity_manager import (
    ensure_schema as ensure_entity_schema,
    find_or_create_entity,
)


@pytest.fixture
def conn(ontology_db_path: Path) -> sqlite3.Connection:
    """Fresh schema with class and entity seeds."""
    c = connect(ontology_db_path)
    ensure_class_schema(c)
    ensure_entity_schema(c)
    from kb1_ontology.attribute_store.schema import (
        ensure_schema as ensure_attribute_schema,
    )
    ensure_attribute_schema(c)
    seed_core_classes(c)
    return c


@pytest.fixture
def iso_14229_3(conn) -> str:
    """A canonical ISO 14229-3 entity for tests that need one."""
    e, _ = find_or_create_entity(
        conn, "ISO 14229-3", class_id="CLS-OBC-STANDARD", domain="OBC"
    )
    return e.entity_id


# ---- G3: range value parsing ---------------------------------------

class TestRangeParser:
    """G3: range value parser handles real-world formats."""

    def test_single_value_with_unit(self) -> None:
        r = parse_range_value("50 ms")
        assert r is not None
        assert r.nominal == 50.0
        assert r.min == 50.0
        assert r.max == 50.0
        assert r.unit == "ms"
        assert r.tolerance == 0.0

    def test_tolerance_with_unicode_sign(self) -> None:
        r = parse_range_value("50 ± 10 ms")
        assert r is not None
        assert r.nominal == 50.0
        assert r.min == 40.0
        assert r.max == 60.0
        assert r.tolerance == 10.0

    def test_tolerance_with_ascii_sign(self) -> None:
        r = parse_range_value("50+/-10 ms")
        assert r is not None
        assert r.nominal == 50.0
        assert r.tolerance == 10.0

    def test_range_with_dots(self) -> None:
        r = parse_range_value("10..20 Hz")
        assert r is not None
        assert r.nominal == 15.0
        assert r.min == 10.0
        assert r.max == 20.0
        assert r.tolerance is None

    def test_decimal_value(self) -> None:
        r = parse_range_value("12.5 V")
        assert r is not None
        assert r.nominal == 12.5

    def test_no_unit(self) -> None:
        r = parse_range_value("100")
        assert r is not None
        assert r.nominal == 100.0
        assert r.unit is None

    def test_unparseable_returns_none(self) -> None:
        assert parse_range_value("not a number") is None
        assert parse_range_value("") is None
        assert parse_range_value("   ") is None


# ---- G1: set / get attribute ---------------------------------------

class TestSetGet:
    """G1: set / get work for all four value types."""

    def test_set_string(self, conn, iso_14229_3) -> None:
        a = set_attribute(
            conn, "entity", iso_14229_3, "title",
            value_text="Road vehicles — UDS on CAN",
            value_type=VALUE_TYPE_STRING,
        )
        assert a.value_type == "string"
        assert a.value_text == "Road vehicles — UDS on CAN"
        fetched = get_attribute(conn, "entity", iso_14229_3, "title")
        assert fetched is not None
        assert fetched.value_text == "Road vehicles — UDS on CAN"

    def test_set_number(self, conn, iso_14229_3) -> None:
        a = set_attribute(
            conn, "entity", iso_14229_3, "P2_Server_Timing",
            value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
        )
        # Auto-parse populates value_num
        assert a.value_num == 50.0
        assert a.value_unit == "ms"

    def test_set_range(self, conn, iso_14229_3) -> None:
        a = set_attribute(
            conn, "entity", iso_14229_3, "supply_voltage",
            value_text="12 ± 0.5 V", value_type=VALUE_TYPE_RANGE,
        )
        assert a.value_type == "range"
        assert a.value_num == 12.0
        assert a.value_min == 11.5
        assert a.value_max == 12.5
        assert a.value_tol == 0.5
        assert a.value_unit == "V"

    def test_set_reference(self, conn, iso_14229_3) -> None:
        e, _ = find_or_create_entity(
            conn, "ISO 14229-1",
            class_id="CLS-OBC-STANDARD", domain="OBC",
        )
        a = set_attribute(
            conn, "entity", iso_14229_3, "depends_on",
            value_type=VALUE_TYPE_REFERENCE,
            value_ref_kind="entity", value_ref_id=e.entity_id,
        )
        assert a.value_type == "reference"
        assert a.value_ref_kind == "entity"
        assert a.value_ref_id == e.entity_id

    def test_set_overwrites_existing(self, conn, iso_14229_3) -> None:
        set_attribute(
            conn, "entity", iso_14229_3, "version",
            value_text="2013", value_type=VALUE_TYPE_STRING,
        )
        set_attribute(
            conn, "entity", iso_14229_3, "version",
            value_text="2022", value_type=VALUE_TYPE_STRING,
        )
        attrs = list_attributes(
            conn, subject_kind="entity", subject_id=iso_14229_3,
            attribute_name="version",
        )
        assert len(attrs) == 1
        assert attrs[0].value_text == "2022"

    def test_unparseable_number_falls_back_to_string(
        self, conn, iso_14229_3
    ) -> None:
        a = set_attribute(
            conn, "entity", iso_14229_3, "free_form",
            value_text="to be determined", value_type=VALUE_TYPE_NUMBER,
        )
        # Falls back to string when the text isn't a number
        assert a.value_type == "string"
        assert a.value_text == "to be determined"


# ---- G2: validation -----------------------------------------------

class TestValidation:
    """Validation: bad inputs raise AttributeStoreError."""

    def test_invalid_value_type(self, conn, iso_14229_3) -> None:
        with pytest.raises(AttributeStoreError):
            set_attribute(
                conn, "entity", iso_14229_3, "x",
                value_text="x", value_type="not-a-type",
            )

    def test_invalid_subject_kind(self, conn, iso_14229_3) -> None:
        with pytest.raises(AttributeStoreError):
            set_attribute(
                conn, "thing", iso_14229_3, "x",
                value_text="x", value_type=VALUE_TYPE_STRING,
            )

    def test_empty_attribute_name(self, conn, iso_14229_3) -> None:
        with pytest.raises(AttributeStoreError):
            set_attribute(
                conn, "entity", iso_14229_3, "",
                value_text="x", value_type=VALUE_TYPE_STRING,
            )

    def test_reference_requires_ref_id(self, conn, iso_14229_3) -> None:
        with pytest.raises(AttributeStoreError):
            set_attribute(
                conn, "entity", iso_14229_3, "x",
                value_type=VALUE_TYPE_REFERENCE,
            )

    def test_reference_to_nonexistent_entity_fails(
        self, conn, iso_14229_3
    ) -> None:
        with pytest.raises(AttributeStoreError):
            set_attribute(
                conn, "entity", iso_14229_3, "x",
                value_type=VALUE_TYPE_REFERENCE,
                value_ref_kind="entity",
                value_ref_id="ENT-DOES-NOT-EXIST",
            )


# ---- G4: query by attribute name and value range ------------------

class TestQuery:
    """G4: attribute-value queries work."""

    def test_query_by_name(self, conn, iso_14229_3) -> None:
        set_attribute(
            conn, "entity", iso_14229_3, "P2",
            value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
        )
        results = query_attributes(
            conn, attribute_name="P2", subject_kind="entity"
        )
        assert len(results) == 1
        assert results[0].subject_id == iso_14229_3

    def test_query_by_value_range(self, conn) -> None:
        # Multiple entities with different values
        for raw, val in [("ISO 14229-1", 100), ("ISO 14229-2", 200),
                          ("ISO 14229-3", 300)]:
            e, _ = find_or_create_entity(
                conn, raw, class_id="CLS-OBC-STANDARD", domain="OBC"
            )
            set_attribute(
                conn, "entity", e.entity_id, "P2",
                value_text=f"{val} ms", value_type=VALUE_TYPE_NUMBER,
            )
        # Query for values between 150 and 250
        results = query_attributes(
            conn, attribute_name="P2", min_value=150, max_value=250
        )
        # Only ISO 14229-2 (200) is in range
        assert len(results) == 1
        assert results[0].value_num == 200

    def test_list_attributes_for_subject(self, conn, iso_14229_3) -> None:
        set_attribute(
            conn, "entity", iso_14229_3, "P2",
            value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
        )
        set_attribute(
            conn, "entity", iso_14229_3, "P2*",
            value_text="5000 ms", value_type=VALUE_TYPE_NUMBER,
        )
        set_attribute(
            conn, "entity", iso_14229_3, "title",
            value_text="UDS on CAN", value_type=VALUE_TYPE_STRING,
        )
        attrs = list_attributes(
            conn, subject_kind="entity", subject_id=iso_14229_3
        )
        assert len(attrs) == 3
        names = {a.attribute_name for a in attrs}
        assert names == {"P2", "P2*", "title"}


# ---- G5: deletion --------------------------------------------------

class TestDelete:
    """Delete an attribute."""

    def test_delete_existing(self, conn, iso_14229_3) -> None:
        set_attribute(
            conn, "entity", iso_14229_3, "P2",
            value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
        )
        assert delete_attribute(
            conn, "entity", iso_14229_3, "P2"
        ) is True
        assert get_attribute(
            conn, "entity", iso_14229_3, "P2"
        ) is None

    def test_delete_nonexistent_returns_false(self, conn, iso_14229_3) -> None:
        assert delete_attribute(
            conn, "entity", iso_14229_3, "never-set"
        ) is False


# ---- G6: real-world scenario --------------------------------------

class TestISO14229Scenario:
    """Real ISO 14229-3 timing parameters scenario."""

    def test_14229_3_timing_attributes(
        self, conn, iso_14229_3
    ) -> None:
        """Set the standard UDS-on-CAN timing parameters as
        attributes and query them."""
        # P2_Server_Timing
        set_attribute(
            conn, "entity", iso_14229_3, "P2_Server_Timing",
            value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
        )
        # P2*_Server_Timing
        set_attribute(
            conn, "entity", iso_14229_3, "P2_Star_Server_Timing",
            value_text="5000 ms", value_type=VALUE_TYPE_NUMBER,
        )
        # S3_Server_Timing (often given as range)
        set_attribute(
            conn, "entity", iso_14229_3, "S3_Server_Timing",
            value_text="5000 ± 100 ms", value_type=VALUE_TYPE_RANGE,
        )
        # Title (string)
        set_attribute(
            conn, "entity", iso_14229_3, "title",
            value_text="UDS on CAN", value_type=VALUE_TYPE_STRING,
        )

        # Query: what is P2_Server_Timing?
        p2 = get_attribute(
            conn, "entity", iso_14229_3, "P2_Server_Timing"
        )
        assert p2 is not None
        assert p2.value_num == 50.0
        assert p2.value_unit == "ms"

        # Query: what is S3_Server_Timing? (range)
        s3 = get_attribute(
            conn, "entity", iso_14229_3, "S3_Server_Timing"
        )
        assert s3 is not None
        assert s3.value_type == "range"
        assert s3.value_min == 4900.0
        assert s3.value_max == 5100.0
        assert s3.value_tol == 100.0

        # Query: which attributes has this entity?
        attrs = list_attributes(
            conn, subject_kind="entity", subject_id=iso_14229_3
        )
        assert {a.attribute_name for a in attrs} == {
            "P2_Server_Timing", "P2_Star_Server_Timing",
            "S3_Server_Timing", "title",
        }


class TestReferenceValueType:
    """Verify value_type='reference' works: an attribute whose value
    is another entity (e.g., a parameter defined in a standard)."""

    def test_reference_value_set_and_get(self, conn) -> None:
        from kb1_ontology.entity_manager import find_or_create_entity
        # Create two entities: a parameter and the standard that defines it
        param, _ = find_or_create_entity(
            conn, "P2_Server_Timing",
            class_id="CLS-OBC-PARAMETER", domain="OBC",
        )
        std, _ = find_or_create_entity(
            conn, "ISO 14229-3",
            class_id="CLS-OBC-STANDARD", domain="OBC",
        )

        # Set a reference attribute: parameter is defined_in standard
        set_attribute(
            conn, "entity", param.entity_id, "defined_in",
            value_type=VALUE_TYPE_REFERENCE,
            value_ref_kind="entity", value_ref_id=std.entity_id,
        )

        # Get it back
        attr = get_attribute(conn, "entity", param.entity_id, "defined_in")
        assert attr is not None
        assert attr.value_type == "reference"
        assert attr.value_ref_kind == "entity"
        assert attr.value_ref_id == std.entity_id

    def test_reference_value_query_by_ref_id(self, conn) -> None:
        from kb1_ontology.entity_manager import find_or_create_entity
        std, _ = find_or_create_entity(
            conn, "ISO 14229-3",
            class_id="CLS-OBC-STANDARD", domain="OBC",
        )
        param, _ = find_or_create_entity(
            conn, "P2_Server_Timing",
            class_id="CLS-OBC-PARAMETER", domain="OBC",
        )

        set_attribute(
            conn, "entity", param.entity_id, "defined_in",
            value_type=VALUE_TYPE_REFERENCE,
            value_ref_kind="entity", value_ref_id=std.entity_id,
        )

        # Query: find all entities whose 'defined_in' points to this standard
        results = query_attributes(
            conn, attribute_name="defined_in",
            value_ref_kind="entity", value_ref_id=std.entity_id,
        )
        assert len(results) == 1
        assert results[0].subject_id == param.entity_id
        assert results[0].attribute_name == "defined_in"
