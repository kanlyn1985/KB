"""Tests for the entity_manager module.

These tests are designed against the GOALS of Phase 2 — proving
that:
  (G1) entities can be created, read, updated
  (G2) entities are bound to a class (FK enforced)
  (G3) name normalization collapses canonical variations
  (G4) de-duplication works (no row created if the same normalized
       name + class + domain already exists)
  (G5) alias merging accumulates spellings
  (G6) the system survives a battery of real standard codes
  (G7) documents can be tagged with multiple job roles

They are NOT adapted from the KB1 main system's tests; they are
written from scratch for the new ontology system's goals.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kb1_ontology.class_registry import (
    ensure_schema as ensure_class_schema,
    seed_core_classes,
)
from kb1_ontology.db import connect
from kb1_ontology.entity_manager import (
    EntityManagerError,
    add_document_role,
    create_entity,
    find_or_create_entity,
    get_document_roles,
    get_entity,
    list_entities,
    merge_aliases,
    normalize_canonical_name,
    normalize_for_match,
    remove_document_role,
    set_document_roles,
)
from kb1_ontology.entity_manager.schema import (
    ensure_schema as ensure_entity_schema,
)


@pytest.fixture
def conn(ontology_db_path: Path) -> sqlite3.Connection:
    """A fresh schema with class + entity tables and class seeds installed."""
    c = connect(ontology_db_path)
    ensure_class_schema(c)
    ensure_entity_schema(c)
    seed_core_classes(c)
    return c


# ----- G3: normalization ----------------------------------------

class TestNormalization:
    """G3: name normalization collapses canonical variations."""

    def test_strips_trailing_year_em_dash(self) -> None:
        assert normalize_canonical_name("ISO 14229-1—2013") == "ISO 14229-1"

    def test_strips_trailing_year_colon(self) -> None:
        assert normalize_canonical_name("ISO 14229-1:2013") == "ISO 14229-1"

    def test_strips_trailing_year_dash(self) -> None:
        assert normalize_canonical_name("GB/T 18487.1-2015") == "GB/T 18487.1"

    def test_strips_trailing_language_marker(self) -> None:
        assert normalize_canonical_name("ISO 14229-7:2015(E)") == "ISO 14229-7"

    def test_no_year_no_change(self) -> None:
        assert normalize_canonical_name("ISO 14229-1") == "ISO 14229-1"

    def test_collapses_whitespace(self) -> None:
        assert normalize_canonical_name("  ISO    14229-1  ") == "ISO 14229-1"

    def test_lowercases_for_match(self) -> None:
        assert normalize_for_match("  iso 14229-1  ") == "iso 14229-1"
        # But canonical_name preserves case
        assert normalize_canonical_name("  iso 14229-1  ") == "iso 14229-1"

    def test_does_not_strip_standard_number_15118(self) -> None:
        """Regression: 1511+8 was being parsed as 1511 then 8, dropping
        the 8. The year regex now requires 1950-2099 range."""
        assert normalize_canonical_name("ISO 15118") == "ISO 15118"
        assert normalize_canonical_name("ISO 15118-1") == "ISO 15118-1"
        assert normalize_canonical_name("ISO 15118-20:2022") == "ISO 15118-20"

    def test_chinese_standard_with_year_in_parens(self) -> None:
        assert normalize_canonical_name("GB/T 18487.1 (2015)") == "GB/T 18487.1"


# ----- G1: CRUD --------------------------------------------------

class TestCRUD:
    """G1: basic CRUD operations work."""

    def test_create_and_get(self, conn) -> None:
        entity = create_entity(
            conn,
            entity_id="ENT-STANDARD-0001",
            canonical_name="ISO 14229-1",
            class_id="CLS-OBC-STANDARD",
            domain="OBC",
        )
        assert entity.entity_id == "ENT-STANDARD-0001"
        fetched = get_entity(conn, "ENT-STANDARD-0001")
        assert fetched is not None
        assert fetched.canonical_name == "ISO 14229-1"

    def test_create_requires_existing_class(self, conn) -> None:
        with pytest.raises(EntityManagerError):
            create_entity(
                conn,
                entity_id="ENT-ORPHAN-0001",
                canonical_name="Whatever",
                class_id="CLS-DOES-NOT-EXIST",
            )

    def test_create_validates_required_fields(self, conn) -> None:
        with pytest.raises(EntityManagerError):
            create_entity(
                conn, entity_id="", canonical_name="X",
                class_id="CLS-OBC-STANDARD",
            )
        with pytest.raises(EntityManagerError):
            create_entity(
                conn, entity_id="E", canonical_name="",
                class_id="CLS-OBC-STANDARD",
            )
        with pytest.raises(EntityManagerError):
            create_entity(
                conn, entity_id="E", canonical_name="X", class_id="",
            )

    def test_list_entities_by_class(self, conn) -> None:
        create_entity(conn, "ENT-S-0001", "ISO 14229-1",
                      class_id="CLS-OBC-STANDARD", domain="OBC")
        create_entity(conn, "ENT-S-0002", "ISO 14229-2",
                      class_id="CLS-OBC-STANDARD", domain="OBC")
        create_entity(conn, "ENT-D-0001", "OBC-Charger-1",
                      class_id="CLS-OBC-DEVICE", domain="OBC")
        standards = list_entities(conn, class_id="CLS-OBC-STANDARD")
        assert len(standards) == 2
        devices = list_entities(conn, class_id="CLS-OBC-DEVICE")
        assert len(devices) == 1

    def test_unique_constraint_on_name_class_domain(self, conn) -> None:
        create_entity(conn, "ENT-1", "ISO 14229-1",
                      class_id="CLS-OBC-STANDARD", domain="OBC")
        with pytest.raises(EntityManagerError):
            create_entity(conn, "ENT-2", "ISO 14229-1",
                          class_id="CLS-OBC-STANDARD", domain="OBC")

    def test_same_name_different_domain_allowed(self, conn) -> None:
        create_entity(conn, "ENT-1", "ISO 14229-1",
                      class_id="CLS-OBC-STANDARD", domain="OBC")
        # Different domain = different entity (future: cross-domain)
        e2 = create_entity(conn, "ENT-2", "ISO 14229-1",
                           class_id="CLS-OBC-STANDARD", domain="Software")
        assert e2.entity_id != "ENT-1"


# ----- G4: dedup via find_or_create ------------------------------

class TestDedup:
    """G4: ``find_or_create_entity`` collapses name variants."""

    def test_first_creates_second_returns_existing(self, conn) -> None:
        e1, created1 = find_or_create_entity(
            conn, "ISO 14229-1—2013", class_id="CLS-OBC-STANDARD",
            domain="OBC",
        )
        assert created1 is True
        e2, created2 = find_or_create_entity(
            conn, "ISO 14229-1:2013", class_id="CLS-OBC-STANDARD",
            domain="OBC",
        )
        assert created2 is False
        assert e1.entity_id == e2.entity_id

    def test_three_variants_one_entity(self, conn) -> None:
        """Real-world test: the same standard referenced three
        different ways in three documents must collapse to one
        entity."""
        variants = [
            "ISO 14229-1—2013",
            "ISO 14229-1:2013",
            "ISO 14229-1",
        ]
        eids = set()
        for v in variants:
            e, _ = find_or_create_entity(
                conn, v, class_id="CLS-OBC-STANDARD", domain="OBC"
            )
            eids.add(e.entity_id)
        assert len(eids) == 1

    def test_extra_aliases_merged_on_repeat(self, conn) -> None:
        e1, _ = find_or_create_entity(
            conn, "ISO 14229-1—2013",
            class_id="CLS-OBC-STANDARD", domain="OBC",
        )
        e2, created = find_or_create_entity(
            conn, "ISO 14229-1:2013",
            class_id="CLS-OBC-STANDARD", domain="OBC",
            extra_aliases=["ISO 14229-1:2013"],
        )
        assert created is False
        # The raw variant should now be in the alias list
        assert "ISO 14229-1:2013" in json.loads(e2.aliases_json)

    def test_dedup_rejects_empty_after_normalization(self, conn) -> None:
        with pytest.raises(EntityManagerError):
            find_or_create_entity(
                conn, "    ", class_id="CLS-OBC-STANDARD", domain="OBC",
            )


# ----- G5: alias merging ----------------------------------------

class TestAliasMerge:
    """G5: aliases accumulate, dedup, and are sorted."""

    def test_aliases_stored_sorted_and_deduped(self, conn) -> None:
        """Aliases are stored as raw strings (preserving year
        suffix), sorted, and deduped at the light-normalize level
        (whitespace + case, NOT year-stripped). The canonical_name
        itself is NOT stored as an alias (it's already in the
        canonical_name column)."""
        create_entity(
            conn, "ENT-1", "ISO 14229-1",
            class_id="CLS-OBC-STANDARD", domain="OBC",
            aliases=["ISO 14229-1—2013", "ISO 14229-1:2013",
                     "ISO 14229-1—2013"],  # duplicate
        )
        e = get_entity(conn, "ENT-1")
        aliases = json.loads(e.aliases_json)
        # Two unique raw forms, sorted, no duplicates
        assert aliases == ["ISO 14229-1—2013", "ISO 14229-1:2013"]

    def test_different_years_kept_distinct(self, conn) -> None:
        """Critical: ISO 14229-1:2013 and ISO 14229-1:2022 are
        DIFFERENT standards. Both should be kept as aliases."""
        create_entity(
            conn, "ENT-1", "ISO 14229-1",
            class_id="CLS-OBC-STANDARD", domain="OBC",
            aliases=["ISO 14229-1:2013", "ISO 14229-1:2022"],
        )
        e = get_entity(conn, "ENT-1")
        aliases = json.loads(e.aliases_json)
        assert "ISO 14229-1:2013" in aliases
        assert "ISO 14229-1:2022" in aliases
        assert len(aliases) == 2

    def test_merge_aliases_adds_new(self, conn) -> None:
        create_entity(conn, "ENT-1", "ISO 14229-1",
                      class_id="CLS-OBC-STANDARD", domain="OBC",
                      aliases=["ISO 14229-1—2013"])
        updated = merge_aliases(
            conn, "ENT-1", ["ISO 14229-1:2013", "ISO 14229-1"]
        )
        aliases = json.loads(updated.aliases_json)
        # The new alias "ISO 14229-1" light-normalizes to the
        # canonical_name, so it is dropped. The two year-suffixed
        # variants remain (deduped against the original).
        assert set(aliases) == {"ISO 14229-1—2013", "ISO 14229-1:2013"}

    def test_merge_aliases_to_nonexistent_raises(self, conn) -> None:
        with pytest.raises(EntityManagerError):
            merge_aliases(conn, "ENT-NOPE", ["X"])


# ----- G6: real standard codes -----------------------------------

class TestRealStandardCodes:
    """G6: the system survives a battery of real-world standard
    codes pulled from the OBC knowledge base."""

    REAL_STANDARDS = [
        # (raw_name, expected_normalized)
        ("ISO 14229-1—2013", "ISO 14229-1"),
        ("ISO 14229-2—2013", "ISO 14229-2"),
        ("ISO 14229-3—2012", "ISO 14229-3"),
        ("ISO 14229-4—2012", "ISO 14229-4"),
        ("ISO 14229-5—2013", "ISO 14229-5"),
        ("ISO 14229-6—2013", "ISO 14229-6"),
        ("ISO 14229-7:2015(E)", "ISO 14229-7"),
        ("GB/T 18487.1—2023", "GB/T 18487.1"),
        ("GB/T 18487.1-2015", "GB/T 18487.1"),  # dedup
        ("GB/T 18487.4—2025", "GB/T 18487.4"),
        ("GB/T 18487.5—2024", "GB/T 18487.5"),
        ("GB/T 40432—2021", "GB/T 40432"),
        ("QC/T 1036—2016", "QC/T 1036"),
        ("IEC 61851-1—2017", "IEC 61851-1"),
        ("ISO 15118", "ISO 15118"),
    ]

    def test_all_real_standards_normalize(self) -> None:
        """All real standard codes produce the expected normalized
        form."""
        for raw, expected in self.REAL_STANDARDS:
            got = normalize_canonical_name(raw)
            assert got == expected, (
                f"normalize_canonical_name({raw!r}) -> {got!r}, "
                f"expected {expected!r}"
            )

    def test_no_duplicate_entities_after_dedup(self, conn) -> None:
        """Inserting the 15 real standard codes should yield
        exactly 13 entities (GB/T 18487.1 appears twice, and the
        second occurrence is a no-op due to dedup)."""
        for raw, _ in self.REAL_STANDARDS:
            find_or_create_entity(
                conn, raw, class_id="CLS-OBC-STANDARD", domain="OBC"
            )
        all_standards = list_entities(
            conn, class_id="CLS-OBC-STANDARD", domain="OBC"
        )
        # 15 inserts, 1 duplicate (GB/T 18487.1) -> 14 entities
        assert len(all_standards) == 14

    def test_each_entity_has_distinct_canonical(self, conn) -> None:
        for raw, _ in self.REAL_STANDARDS:
            find_or_create_entity(
                conn, raw, class_id="CLS-OBC-STANDARD", domain="OBC"
            )
        names = {
            e.canonical_name
            for e in list_entities(
                conn, class_id="CLS-OBC-STANDARD", domain="OBC"
            )
        }
        assert len(names) == 14  # all unique


# ----- G7: document roles ---------------------------------------

class TestDocumentRoles:
    """G7: documents can be tagged with multiple job roles."""

    def test_set_roles_replaces_existing(self, conn) -> None:
        set_document_roles(
            conn, "/path/to/doc.pdf",
            ["systems_engineer", "software_engineer"]
        )
        roles = get_document_roles(conn, "/path/to/doc.pdf")
        assert roles == ["software_engineer", "systems_engineer"]

    def test_set_empty_roles_clears(self, conn) -> None:
        set_document_roles(
            conn, "/path/to/doc.pdf", ["systems_engineer"]
        )
        set_document_roles(conn, "/path/to/doc.pdf", [])
        assert get_document_roles(conn, "/path/to/doc.pdf") == []

    def test_add_single_role(self, conn) -> None:
        add_document_role(
            conn, "/path/to/doc.pdf", "systems_engineer"
        )
        add_document_role(
            conn, "/path/to/doc.pdf", "test_engineer"
        )
        roles = get_document_roles(conn, "/path/to/doc.pdf")
        assert roles == ["systems_engineer", "test_engineer"]

    def test_add_duplicate_role_idempotent(self, conn) -> None:
        add_document_role(
            conn, "/path/to/doc.pdf", "systems_engineer"
        )
        add_document_role(
            conn, "/path/to/doc.pdf", "systems_engineer"
        )
        assert get_document_roles(
            conn, "/path/to/doc.pdf"
        ) == ["systems_engineer"]

    def test_remove_role(self, conn) -> None:
        set_document_roles(
            conn, "/p", ["systems_engineer", "test_engineer"]
        )
        removed = remove_document_role(conn, "/p", "test_engineer")
        assert removed is True
        assert get_document_roles(conn, "/p") == ["systems_engineer"]

    def test_remove_nonexistent_role(self, conn) -> None:
        result = remove_document_role(
            conn, "/p", "nonexistent_role_xyz"
        )
        # not in JOB_ROLES, but doesn't crash; nothing to remove
        assert result is False

    def test_unknown_role_rejected(self, conn) -> None:
        with pytest.raises(ValueError):
            set_document_roles(
                conn, "/p", ["systems_engineer", "unknown_role"]
            )

    def test_multiple_documents_independent(self, conn) -> None:
        set_document_roles(conn, "/a", ["systems_engineer"])
        set_document_roles(conn, "/b", ["software_engineer"])
        assert get_document_roles(conn, "/a") == ["systems_engineer"]
        assert get_document_roles(conn, "/b") == ["software_engineer"]
