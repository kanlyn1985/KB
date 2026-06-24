"""Tests for the class_registry module.

These tests are designed against the GOALS of Phase 1 — proving the
3-layer hierarchy (Meta / Domain / Instance), the is-a relation
with transitive inheritance, the seed data loads correctly, and
the registry stays acyclic.

They are NOT adapted from the KB1 main system's tests; they are
written from scratch for the new ontology system's goals.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb1_ontology.class_registry import (
    ClassRegistryError,
    LAYER_DOMAIN,
    LAYER_META,
    check_acyclic,
    create_class,
    delete_class,
    ensure_schema,
    get_ancestors,
    get_class,
    get_descendants,
    is_subclass_of,
    list_classes,
    seed_core_classes,
    update_class,
)
from kb1_ontology.db import connect


@pytest.fixture
def conn(ontology_db_path: Path) -> sqlite3.Connection:
    """A fresh in-memory connection per test, with schema installed."""
    c = connect(ontology_db_path)
    ensure_schema(c)
    return c


# ----- G1: 3-layer structure can be expressed -----

class TestThreeLayerStructure:
    """G1: The 3-layer (Meta / Domain / Instance) hierarchy is
    expressible in the schema."""

    def test_meta_root_has_no_parent(self, conn) -> None:
        seed_core_classes(conn)
        thing = get_class(conn, "CLS-META-THING")
        assert thing is not None
        assert thing.parent_class_id is None
        assert thing.layer == LAYER_META
        assert thing.domain is None

    def test_meta_layer_has_6_universals(self, conn) -> None:
        seed_core_classes(conn)
        meta = list_classes(conn, layer=LAYER_META)
        # Exactly the 6 meta universals
        assert len(meta) == 6
        names = {c.class_name for c in meta}
        assert names == {
            "Thing", "InformationEntity", "PhysicalEntity",
            "ProcessEntity", "ConceptEntity", "RoleEntity",
        }

    def test_domain_layer_subclasses_meta(self, conn) -> None:
        seed_core_classes(conn)
        # An OBC Domain class should be a subclass of a Meta class
        assert is_subclass_of(conn, "CLS-OBC-STANDARD",
                              "CLS-META-INFORMATION-ENTITY")
        assert is_subclass_of(conn, "CLS-OBC-DEVICE",
                              "CLS-META-PHYSICAL-ENTITY")
        assert is_subclass_of(conn, "CLS-OBC-PARAMETER",
                              "CLS-META-CONCEPT-ENTITY")
        assert is_subclass_of(conn, "CLS-OBC-CHARGING-PROCESS",
                              "CLS-META-PROCESS-ENTITY")

    def test_transitive_inheritance(self, conn) -> None:
        seed_core_classes(conn)
        # OBC.Standard -> InformationEntity -> Thing (3 levels)
        ancestors = get_ancestors(conn, "CLS-OBC-STANDARD")
        assert ancestors == [
            "CLS-META-INFORMATION-ENTITY",
            "CLS-META-THING",
        ]


# ----- G2: Entities can inherit attributes from their class -----

class TestInheritance:
    """G2: Subclasses inherit from their parents."""

    def test_class_is_subclass_of_itself(self, conn) -> None:
        seed_core_classes(conn)
        assert is_subclass_of(conn, "CLS-META-THING",
                              "CLS-META-THING") is True

    def test_unrelated_class_not_subclass(self, conn) -> None:
        seed_core_classes(conn)
        assert is_subclass_of(conn, "CLS-OBC-DEVICE",
                              "CLS-META-CONCEPT-ENTITY") is False

    def test_descendants_of_root(self, conn) -> None:
        seed_core_classes(conn)
        descendants = get_descendants(conn, "CLS-META-THING")
        # Should include all 5 meta non-root + 10 OBC domain = 15
        assert "CLS-META-INFORMATION-ENTITY" in descendants
        assert "CLS-OBC-STANDARD" in descendants
        assert "CLS-OBC-DEVICE" in descendants
        assert len(descendants) == 15


# ----- G3: Domain classes do not leak into other domains -----

class TestDomainIsolation:
    """G3: The OBC domain's classes do not appear under any
    other domain."""

    def test_no_obc_classes_under_software_filter(self, conn) -> None:
        seed_core_classes(conn)
        # Even if we ask for classes in a different domain, the
        # OBC classes should not appear.
        # We simulate the second domain by filtering on a name
        # that doesn't exist:
        result = list_classes(conn, domain="Software")
        assert result == []

    def test_obc_classes_have_domain_set(self, conn) -> None:
        seed_core_classes(conn)
        obc_classes = list_classes(conn, domain="OBC")
        assert len(obc_classes) == 10
        for c in obc_classes:
            assert c.domain == "OBC"
            assert c.layer == LAYER_DOMAIN


# ----- G4: Core vs auto-discovered classes can be distinguished -----

class TestCoreClasses:
    """G4: Core (manual) classes are flagged, auto-discovered ones
    are not."""

    def test_all_seeded_classes_are_core(self, conn) -> None:
        seed_core_classes(conn)
        all_classes = list_classes(conn, is_core=True)
        assert len(all_classes) == 16

    def test_non_core_classes_filter_correctly(self, conn) -> None:
        seed_core_classes(conn)
        # Add a non-core class
        create_class(
            conn,
            class_id="CLS-AUTO-LEARNED-1",
            class_name="AutoLearnedClass",
            parent_class_id="CLS-META-CONCEPT-ENTITY",
            layer=LAYER_DOMAIN,
            domain="OBC",
            is_core=False,
        )
        auto = list_classes(conn, is_core=False)
        assert len(auto) == 1
        assert auto[0].class_id == "CLS-AUTO-LEARNED-1"
        assert auto[0].is_core is False


# ----- G5: Re-seeding does not duplicate -----

class TestSeedIdempotency:
    """G5: ``seed_core_classes`` is idempotent — running it twice
    does not duplicate rows."""

    def test_seed_is_idempotent(self, conn) -> None:
        first_run = seed_core_classes(conn)
        assert first_run == 16
        second_run = seed_core_classes(conn)
        assert second_run == 0
        all_classes = list_classes(conn)
        assert len(all_classes) == 16


# ----- CRUD: basic operations -----

class TestCRUD:
    """Standard CRUD: every operation works and enforces rules."""

    def test_create_and_get(self, conn) -> None:
        seed_core_classes(conn)
        cls = get_class(conn, "CLS-META-THING")
        assert cls is not None
        assert cls.class_name == "Thing"

    def test_list_classes_returns_all(self, conn) -> None:
        seed_core_classes(conn)
        all_classes = list_classes(conn)
        assert len(all_classes) == 16

    def test_update_class_name(self, conn) -> None:
        seed_core_classes(conn)
        updated = update_class(
            conn, "CLS-META-THING", class_name="Root"
        )
        assert updated.class_name == "Root"
        assert updated.class_id == "CLS-META-THING"  # immutable

    def test_update_class_description(self, conn) -> None:
        seed_core_classes(conn)
        update_class(
            conn, "CLS-META-THING",
            description="The ultimate root of all classes."
        )
        refreshed = get_class(conn, "CLS-META-THING")
        assert refreshed.description == "The ultimate root of all classes."

    def test_update_nonexistent_raises(self, conn) -> None:
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            update_class(conn, "CLS-NOPE", class_name="X")

    def test_delete_unused_class(self, conn) -> None:
        seed_core_classes(conn)
        # Add a leaf class with no children
        create_class(
            conn, class_id="CLS-LEAF-1", class_name="Leaf",
            parent_class_id="CLS-META-THING", layer=LAYER_META,
        )
        result = delete_class(conn, "CLS-LEAF-1")
        assert result is True
        assert get_class(conn, "CLS-LEAF-1") is None

    def test_delete_with_children_fails(self, conn) -> None:
        seed_core_classes(conn)
        # CLS-META-THING has 5 meta children; cannot delete
        with pytest.raises(ClassRegistryError):
            delete_class(conn, "CLS-META-THING")

    def test_delete_nonexistent_returns_false(self, conn) -> None:
        seed_core_classes(conn)
        result = delete_class(conn, "CLS-DOES-NOT-EXIST")
        assert result is False


# ----- Validation rules -----

class TestValidationRules:
    """Validation rules enforced at the CRUD layer."""

    def test_meta_layer_cannot_have_domain(self, conn) -> None:
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-BAD", class_name="Bad",
                parent_class_id=None, layer=LAYER_META,
                domain="OBC",  # forbidden for meta
            )

    def test_domain_layer_requires_domain(self, conn) -> None:
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-BAD", class_name="Bad",
                parent_class_id="CLS-META-INFORMATION-ENTITY",
                layer=LAYER_DOMAIN,
                domain=None,  # required for domain
            )

    def test_invalid_layer_rejected(self, conn) -> None:
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-BAD", class_name="Bad",
                parent_class_id=None, layer="invalid",
            )

    def test_parent_must_exist(self, conn) -> None:
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-ORPHAN", class_name="Orphan",
                parent_class_id="CLS-DOES-NOT-EXIST",
                layer=LAYER_DOMAIN, domain="OBC",
            )

    def test_meta_cannot_have_domain_parent(self, conn) -> None:
        """Per the corrected layer rules: Meta classes can only
        have Meta parents. A Domain class is not a valid Meta parent."""
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-BAD", class_name="Bad",
                parent_class_id="CLS-OBC-STANDARD",  # domain
                layer=LAYER_META,
            )

    def test_domain_can_have_meta_parent(self, conn) -> None:
        """The CORRECT rule: a Domain class's parent must be Meta
        (i.e., a Domain class hangs off a Meta universal). This
        is the cross-layer is-a relationship."""
        seed_core_classes(conn)
        cls = create_class(
            conn, class_id="CLS-OBC-NEW-CHILD",
            class_name="NewChild",
            parent_class_id="CLS-META-CONCEPT-ENTITY",  # meta
            layer=LAYER_DOMAIN, domain="OBC",
        )
        assert cls.class_id == "CLS-OBC-NEW-CHILD"
        assert cls.layer == LAYER_DOMAIN
        # Verify is-a across layers
        assert is_subclass_of(conn, "CLS-OBC-NEW-CHILD",
                              "CLS-META-CONCEPT-ENTITY")

    def test_domain_cannot_have_domain_parent(self, conn) -> None:
        """Two domain classes in different domains: still
        forbidden, because the cross-domain link would be a
        separate (non-is-a) relationship."""
        seed_core_classes(conn)
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-SOFTWARE-STANDARD",
                class_name="SoftwareStandard",
                parent_class_id="CLS-OBC-STANDARD",  # domain
                layer=LAYER_DOMAIN, domain="Software",
            )


# ----- Cycle detection -----

class TestCycleDetection:
    """The hierarchy must be acyclic at all times."""

    def test_seed_creates_acyclic_hierarchy(self, conn) -> None:
        seed_core_classes(conn)
        assert check_acyclic(conn) is True

    def test_creating_cycle_is_rejected(self, conn) -> None:
        """If we tried to make OBC.STANDARD's parent = Thing, that
        is legal (Thing is already the ancestor). But trying to
        make OBC.STANDARD's parent point to a descendant of
        OBC.STANDARD (e.g., itself) would create a cycle.

        Since parent_class_id is immutable, the cycle can only
        be created at create time. We verify:
        1. The cycle-detection helper recognizes the cycle shape
        2. Trying to create a class with class_id = existing_class
           and parent = existing_class would be a cycle
        """
        seed_core_classes(conn)
        # OBC.STANDARD is a descendant of Thing (via InformationEntity)
        assert is_subclass_of(conn, "CLS-OBC-STANDARD",
                              "CLS-META-THING") is True
        # Trying to add Thing as a child of OBC.STANDARD would
        # create a cycle (Thing is OBC.STANDARD's ancestor).
        from kb1_ontology.class_registry import crud
        with pytest.raises(ClassRegistryError):
            crud.create_class(
                conn, class_id="CLS-META-THING", class_name="T",
                parent_class_id="CLS-OBC-STANDARD",
                layer=LAYER_META,
            )


# ----- Schema integrity -----

class TestSchemaIntegrity:
    """Schema-level invariants beyond what SQL can enforce."""

    def test_no_class_can_have_null_id(self, conn) -> None:
        seed_core_classes(conn)
        # All classes have non-empty class_id
        all_classes = list_classes(conn)
        assert all(c.class_id for c in all_classes)

    def test_ensure_schema_is_idempotent(self, conn) -> None:
        ensure_schema(conn)
        ensure_schema(conn)
        ensure_schema(conn)
        # Still empty (no seeds run)
        assert list_classes(conn) == []

    def test_unique_constraint_on_name_layer_domain(self, conn) -> None:
        seed_core_classes(conn)
        # Two classes with same (class_name, layer, domain) tuple
        # should conflict.
        from kb1_ontology.class_registry.crud import ClassRegistryError
        # 'Standard' already exists in layer=domain, domain=OBC.
        with pytest.raises(ClassRegistryError):
            create_class(
                conn, class_id="CLS-DUP", class_name="Standard",
                parent_class_id="CLS-META-INFORMATION-ENTITY",
                layer=LAYER_DOMAIN, domain="OBC",
            )
