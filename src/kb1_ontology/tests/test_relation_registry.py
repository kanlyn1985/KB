"""Tests for the relation_registry module.

These tests are designed against the GOALS of Phase 3 — proving
the relation graph can be built, queried, and traversed. They
are NOT adapted from the KB1 main system's tests; they are
written from scratch for the new ontology system's goals.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb1_ontology.class_registry import (
    ensure_schema as ensure_class_schema,
    seed_core_classes,
)
from kb1_ontology.db import connect
from kb1_ontology.entity_manager import (
    ensure_schema as ensure_entity_schema,
    find_or_create_entity,
)
from kb1_ontology.relation_registry import (
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_REFERENTIAL,
    CATEGORY_STRUCTURAL,
    CATEGORY_TEMPORAL,
    SCOPE_CORE,
    RelationRegistryError,
    create_relation,
    create_relation_def,
    delete_relation,
    get_relation,
    get_relation_def,
    inverse_relation_name,
    list_relation_defs,
    list_relations,
    relations_of,
    seed_core_relations,
    traverse_relations,
)


# ---- Fixtures --------------------------------------------------------

@pytest.fixture
def conn(ontology_db_path: Path) -> sqlite3.Connection:
    """A fresh schema with classes, entities, and core relations seeded."""
    c = connect(ontology_db_path)
    ensure_class_schema(c)
    ensure_entity_schema(c)
    from kb1_ontology.relation_registry.schema import (
        ensure_schema as ensure_relation_schema,
    )
    ensure_relation_schema(c)
    seed_core_classes(c)
    seed_core_relations(c)
    return c


@pytest.fixture
def standard_entities(conn: sqlite3.Connection) -> dict[str, str]:
    """Create real entities for ISO 14229 series. Returns
    mapping from short name to entity_id."""
    names = {
        "ISO_14229-1": "ISO 14229-1",
        "ISO_14229-2": "ISO 14229-2",
        "ISO_14229-3": "ISO 14229-3",
        "ISO_14229-4": "ISO 14229-4",
        "ISO_14229-7": "ISO 14229-7",
    }
    out: dict[str, str] = {}
    for short, raw in names.items():
        e, _ = find_or_create_entity(
            conn, raw, class_id="CLS-OBC-STANDARD", domain="OBC"
        )
        out[short] = e.entity_id
    return out


# ---- G1: relation definitions ---------------------------------------

class TestRelationDefCRUD:
    """G1: relation definitions can be created and queried."""

    def test_create_and_get(self, conn) -> None:
        rd = create_relation_def(
            conn, "my-rel", CATEGORY_REFERENTIAL,
            scope=SCOPE_CORE, inverse_name="my-rel-inv",
            description="test",
        )
        assert rd.relation_name == "my-rel"
        fetched = get_relation_def(conn, "my-rel")
        assert fetched is not None
        assert fetched.category == CATEGORY_REFERENTIAL

    def test_rejects_empty_name(self, conn) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation_def(
                conn, "", CATEGORY_REFERENTIAL
            )

    def test_rejects_invalid_category(self, conn) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation_def(
                conn, "x", "invalid-cat"
            )

    def test_rejects_invalid_scope(self, conn) -> None:
        with pytest.raises(ValueError):
            create_relation_def(
                conn, "x", CATEGORY_REFERENTIAL, scope="bad-scope"
            )

    def test_list_filters_by_category(self, conn) -> None:
        structural = list_relation_defs(
            conn, category=CATEGORY_STRUCTURAL
        )
        assert {r.relation_name for r in structural} == {"is-a", "part-of"}
        referential = list_relation_defs(
            conn, category=CATEGORY_REFERENTIAL
        )
        assert {r.relation_name for r in referential} == {
            "references", "cites"
        }

    def test_seed_core_relations_idempotent(self, conn) -> None:
        first = seed_core_relations(conn)
        # Some may have been already created during fixture; the
        # important thing is that the second call adds zero.
        second = seed_core_relations(conn)
        assert second == 0
        all_rels = list_relation_defs(conn)
        assert len(all_rels) == 7  # 4 categories, 2+1+2+2 relations

    def test_each_core_relation_has_inverse(self, conn) -> None:
        for rd in list_relation_defs(conn):
            assert rd.inverse_name is not None, (
                f"relation {rd.relation_name} has no inverse"
            )


# ---- G2: relation instances -----------------------------------------

class TestRelationInstances:
    """G2: concrete relation edges can be created."""

    def test_create_relation(self, conn, standard_entities) -> None:
        r = create_relation(
            conn, "references", "entity", standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        assert r.relation_name == "references"
        assert r.relation_id > 0

    def test_rejects_unknown_relation_name(self, conn, standard_entities) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "nope", "entity",
                standard_entities["ISO_14229-7"],
                "entity", standard_entities["ISO_14229-1"],
            )

    def test_rejects_self_loop(self, conn, standard_entities) -> None:
        eid = standard_entities["ISO_14229-7"]
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "references", "entity", eid, "entity", eid,
            )

    def test_rejects_nonexistent_src_entity(self, conn, standard_entities) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "references", "entity", "ENT-DOES-NOT-EXIST",
                "entity", standard_entities["ISO_14229-1"],
            )

    def test_rejects_nonexistent_dst_entity(self, conn, standard_entities) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-1"],
                "entity", "ENT-NOPE",
            )

    def test_confidence_must_be_in_range(self, conn, standard_entities) -> None:
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-7"],
                "entity", standard_entities["ISO_14229-1"],
                confidence=1.5,
            )
        with pytest.raises(RelationRegistryError):
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-7"],
                "entity", standard_entities["ISO_14229-1"],
                confidence=-0.1,
            )

    def test_unique_constraint(self, conn, standard_entities) -> None:
        """Same (relation, src, dst, domain) cannot be added twice."""
        args = ("references", "entity", standard_entities["ISO_14229-7"],
                "entity", standard_entities["ISO_14229-1"])
        create_relation(conn, *args, domain="OBC")
        with pytest.raises(RelationRegistryError):
            create_relation(conn, *args, domain="OBC")

    def test_delete_relation(self, conn, standard_entities) -> None:
        r = create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        assert delete_relation(conn, r.relation_id) is True
        assert get_relation(conn, r.relation_id) is None
        # Deleting again returns False
        assert delete_relation(conn, r.relation_id) is False


# ---- G3: scope (core vs domain) -------------------------------------

class TestScope:
    """G3: core relations are global, domain relations are private."""

    def test_core_relations_have_scope_core(self, conn) -> None:
        for rd in list_relation_defs(conn):
            assert rd.scope == SCOPE_CORE, (
                f"core relation {rd.relation_name} has scope {rd.scope!r}"
            )

    def test_can_register_domain_specific_relation(self, conn) -> None:
        rd = create_relation_def(
            conn, "OBC-has-charging-profile", CATEGORY_ATTRIBUTIVE,
            scope="domain:OBC", description="OBC-specific",
        )
        assert rd.scope == "domain:OBC"
        assert "OBC-has-charging-profile" in {
            r.relation_name for r in list_relation_defs(conn)
        }


# ---- G4: graph traversal --------------------------------------------

class TestTraversal:
    """G4: relations enable graph traversal (the key ontology
    capability)."""

    def test_relations_of_outgoing(self, conn, standard_entities) -> None:
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        rels = relations_of(
            conn, src_id=standard_entities["ISO_14229-7"],
            direction="outgoing", domain="OBC",
        )
        assert len(rels) == 1
        assert rels[0].dst_id == standard_entities["ISO_14229-1"]

    def test_relations_of_incoming(self, conn, standard_entities) -> None:
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        rels = relations_of(
            conn, src_id=standard_entities["ISO_14229-1"],
            direction="incoming", domain="OBC",
        )
        assert len(rels) == 1
        assert rels[0].src_id == standard_entities["ISO_14229-7"]

    def test_relations_of_both(self, conn, standard_entities) -> None:
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        rels = relations_of(
            conn, src_id=standard_entities["ISO_14229-1"],
            direction="both", domain="OBC",
        )
        assert len(rels) == 1  # the same edge is found

    def test_traversal_two_hops(self, conn, standard_entities) -> None:
        """ISO 14229-7 -> ISO 14229-1 -> ISO 14229-2 forms a 2-hop path."""
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-1"],
            "entity", standard_entities["ISO_14229-2"], domain="OBC",
        )
        paths = traverse_relations(
            conn, start_id=standard_entities["ISO_14229-7"],
            max_hops=3, domain="OBC",
        )
        # Should have 1-hop path (to ISO 14229-1) and 2-hop path
        # (to ISO 14229-2 via ISO 14229-1)
        assert len(paths) == 2
        # The 2-hop path should end at ISO 14229-2
        longest = max(paths, key=len)
        assert len(longest) == 2
        assert longest[-1].dst_id == standard_entities["ISO_14229-2"]

    def test_traversal_respects_max_hops(self, conn, standard_entities) -> None:
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-7"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-1"],
            "entity", standard_entities["ISO_14229-2"], domain="OBC",
        )
        paths = traverse_relations(
            conn, start_id=standard_entities["ISO_14229-7"],
            max_hops=1, domain="OBC",
        )
        # With max_hops=1, we only get direct neighbors
        assert all(len(p) == 1 for p in paths)

    def test_traversal_does_not_revisit_nodes(self, conn, standard_entities) -> None:
        """Cycles in the relation graph are not followed
        repeatedly."""
        # ISO 14229-1 -> ISO 14229-2 -> ISO 14229-1 (cycle)
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-1"],
            "entity", standard_entities["ISO_14229-2"], domain="OBC",
        )
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-2"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )
        paths = traverse_relations(
            conn, start_id=standard_entities["ISO_14229-1"],
            max_hops=5, domain="OBC",
        )
        # Without cycle protection, the 2-hop would be added
        # but then the 3-hop, 4-hop, ... indefinitely (we'd
        # see many paths or hang). With cycle protection, only
        # the 1-hop is recorded: 14229-1 -> 14229-2. The 2-hop
        # would be 14229-1 -> 14229-2 -> 14229-1, but 14229-1
        # is the start (already visited) so it's rejected.
        assert len(paths) == 1
        assert paths[0][-1].dst_id == standard_entities["ISO_14229-2"]


# ---- G5: inverse-relation helper ------------------------------------

class TestInverse:
    """G5: ``inverse_relation_name`` returns the inverse."""

    def test_references_inverse(self, conn) -> None:
        assert inverse_relation_name(
            conn, "references"
        ) == "referenced-by"

    def test_is_a_inverse(self, conn) -> None:
        assert inverse_relation_name(conn, "is-a") == "instance-of"

    def test_unknown_returns_none(self, conn) -> None:
        assert inverse_relation_name(conn, "nope-relation") is None


# ---- G6: real-world scenario ---------------------------------------

class TestISO14229Scenario:
    """G6: real-world scenario: build the full ISO 14229 family
    reference graph and traverse it."""

    def test_build_iso_14229_reference_graph(
        self, conn, standard_entities
    ) -> None:
        """The 14229 family references itself heavily. Build a
        realistic graph and verify traversal."""
        # 14229-7 references 14229-1, 14229-2, 14229-3
        for target in ["ISO_14229-1", "ISO_14229-2", "ISO_14229-3"]:
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-7"],
                "entity", standard_entities[target], domain="OBC",
            )
        # 14229-3 references 14229-1, 14229-2
        for target in ["ISO_14229-1", "ISO_14229-2"]:
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-3"],
                "entity", standard_entities[target], domain="OBC",
            )
        # 14229-4 references 14229-1
        create_relation(
            conn, "references", "entity",
            standard_entities["ISO_14229-4"],
            "entity", standard_entities["ISO_14229-1"], domain="OBC",
        )

        # 14229-7 has 3 outgoing references
        out_7 = relations_of(
            conn, src_id=standard_entities["ISO_14229-7"],
            direction="outgoing", domain="OBC",
        )
        assert len(out_7) == 3

        # 14229-1 has 3 incoming references (from 7, 3, 4)
        in_1 = relations_of(
            conn, src_id=standard_entities["ISO_14229-1"],
            direction="incoming", domain="OBC",
        )
        assert len(in_1) == 3

        # 14229-7 -> 14229-1 -> ... reachable in 2 hops
        paths = traverse_relations(
            conn, start_id=standard_entities["ISO_14229-7"],
            max_hops=2, domain="OBC",
        )
        # 1-hop: 3 paths to direct neighbors
        # 2-hop: paths to 14229-2 via each 1-hop neighbor
        assert len(paths) >= 4  # 3 direct + at least 1 2-hop
        # All 2-hop paths should end somewhere
        for p in paths:
            assert len(p) >= 1

    def test_query_what_does_14229_7_depend_on(
        self, conn, standard_entities
    ) -> None:
        """Simulate a real query: 'what standards does ISO 14229-7
        reference?' The answer is the set of outgoing references."""
        for target in ["ISO_14229-1", "ISO_14229-2", "ISO_14229-3"]:
            create_relation(
                conn, "references", "entity",
                standard_entities["ISO_14229-7"],
                "entity", standard_entities[target], domain="OBC",
            )
        rels = relations_of(
            conn, src_id=standard_entities["ISO_14229-7"],
            direction="outgoing", relation_name="references",
            domain="OBC",
        )
        target_ids = {r.dst_id for r in rels}
        assert target_ids == {
            standard_entities["ISO_14229-1"],
            standard_entities["ISO_14229-2"],
            standard_entities["ISO_14229-3"],
        }
