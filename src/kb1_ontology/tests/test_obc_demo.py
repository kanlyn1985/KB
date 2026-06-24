"""End-to-end test for the OBC ontology demo.

This test is the "acceptance test" for the entire ontology
system (Phases 0-4). It builds a small OBC ontology in a
scratch database, then runs the 5 demo queries and asserts
their results.

If this test passes, the system is end-to-end functional.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def _build_obc_ontology(workspace: Path) -> sqlite3.Connection:
    """Build the OBC ontology into a scratch database and
    return the connection.  All phases 0-4 are exercised."""
    from kb1_ontology.attribute_store import set_attribute
    from kb1_ontology.attribute_store import (
        VALUE_TYPE_NUMBER, VALUE_TYPE_RANGE, VALUE_TYPE_STRING,
    )
    from kb1_ontology.attribute_store.schema import (
        ensure_schema as ensure_attribute_schema,
    )
    from kb1_ontology.class_registry import (
        ensure_schema as ensure_class_schema,
        seed_core_classes,
    )
    from kb1_ontology.db import connect, default_db_path
    from kb1_ontology.entity_manager import find_or_create_entity
    from kb1_ontology.entity_manager.schema import (
        ensure_schema as ensure_entity_schema,
    )
    from kb1_ontology.relation_registry import (
        create_relation,
        create_relation_def,
    )
    from kb1_ontology.relation_registry.schema import (
        ensure_schema as ensure_relation_schema,
    )

    db_path = default_db_path(workspace)
    conn = connect(db_path)
    ensure_class_schema(conn)
    ensure_entity_schema(conn)
    ensure_relation_schema(conn)
    ensure_attribute_schema(conn)
    seed_core_classes(conn)

    # Core relations
    for rel_name in ["is-a", "part-of", "has-attribute", "references"]:
        if conn.execute(
            "SELECT 1 FROM relation_def WHERE relation_name = ?",
            (rel_name,),
        ).fetchone() is None:
            create_relation_def(conn, rel_name, "referential")

    # Standards
    standards = [
        "ISO 14229-1", "ISO 14229-2", "ISO 14229-3",
        "ISO 14229-7", "GB/T 18487.1", "GB/T 18487.4",
    ]
    eids: dict[str, str] = {}
    for s in standards:
        e, _ = find_or_create_entity(
            conn, s, class_id="CLS-OBC-STANDARD", domain="OBC"
        )
        eids[s] = e.entity_id

    # References: 14229-7 → {1,2,3}; 18487.1 → 18487.4
    for src, dst in [
        ("ISO 14229-7", "ISO 14229-1"),
        ("ISO 14229-7", "ISO 14229-2"),
        ("ISO 14229-7", "ISO 14229-3"),
        ("GB/T 18487.1", "GB/T 18487.4"),
    ]:
        create_relation(
            conn, "references", "entity",
            eids[src], "entity", eids[dst], domain="OBC",
        )

    # Attributes on ISO 14229-3
    set_attribute(
        conn, "entity", eids["ISO 14229-3"], "P2_Server_Timing",
        value_text="50 ms", value_type=VALUE_TYPE_NUMBER,
    )
    set_attribute(
        conn, "entity", eids["ISO 14229-3"], "S3_Server_Timing",
        value_text="5000 ± 100 ms", value_type=VALUE_TYPE_RANGE,
    )
    set_attribute(
        conn, "entity", eids["ISO 14229-1"], "service_TesterPresent",
        value_text="0x3E", value_type=VALUE_TYPE_STRING,
    )
    return conn


@pytest.fixture
def obc_conn(ontology_db_path: Path) -> sqlite3.Connection:
    """A fresh ontology with the OBC demo built into it."""
    # ontology_db_path is the scratch dir; default_db_path puts
    # the file at <scratch>/ontology/ontology.db.
    workspace = ontology_db_path.parent
    return _build_obc_ontology(workspace)


# ---- The 5 demo questions, as tests --------------------------------

def test_q1_14229_7_depends_on(obc_conn) -> None:
    """Q1: What does ISO 14229-7 reference?"""
    from kb1_ontology.relation_registry import relations_of
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    target_norm = normalize_canonical_name("ISO 14229-7")
    eid = None
    for row in obc_conn.execute("SELECT entity_id, canonical_name FROM entity"):
        if normalize_canonical_name(row["canonical_name"]) == target_norm:
            eid = row["entity_id"]
            break
    assert eid is not None, "ISO 14229-7 not in ontology"
    rels = relations_of(
        obc_conn, src_id=eid, direction="outgoing",
        relation_name="references", domain="OBC",
    )
    target_ids = {r.dst_id for r in rels}
    # Should reference ISO 14229-1, 14229-2, 14229-3
    target_norms = set()
    for row in obc_conn.execute(
        "SELECT entity_id, canonical_name FROM entity "
        "WHERE entity_id IN ({})".format(",".join("?"*len(target_ids))),
        list(target_ids),
    ):
        target_norms.add(normalize_canonical_name(row["canonical_name"]))
    assert "ISO 14229-1" in target_norms
    assert "ISO 14229-2" in target_norms
    assert "ISO 14229-3" in target_norms


def test_q2_what_depends_on_14229_1(obc_conn) -> None:
    """Q2: What depends on ISO 14229-1?"""
    from kb1_ontology.relation_registry import relations_of
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    target_norm = normalize_canonical_name("ISO 14229-1")
    eid = None
    for row in obc_conn.execute("SELECT entity_id, canonical_name FROM entity"):
        if normalize_canonical_name(row["canonical_name"]) == target_norm:
            eid = row["entity_id"]
            break
    assert eid is not None
    rels = relations_of(
        obc_conn, src_id=eid, direction="incoming",
        relation_name="references", domain="OBC",
    )
    # Only ISO 14229-7 references 14229-1 in this seed
    assert len(rels) == 1
    src_id = rels[0].src_id
    cur = obc_conn.execute(
        "SELECT canonical_name FROM entity WHERE entity_id = ?", (src_id,)
    ).fetchone()
    assert normalize_canonical_name(cur["canonical_name"]) == "ISO 14229-7"


def test_q3_p2_timing_is_exact(obc_conn) -> None:
    """Q3: P2_Server_Timing is an exact value, not a fuzzy match."""
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    eid = None
    for row in obc_conn.execute("SELECT entity_id, canonical_name FROM entity"):
        if normalize_canonical_name(row["canonical_name"]) == "ISO 14229-3":
            eid = row["entity_id"]
            break
    cur = obc_conn.execute(
        "SELECT * FROM attribute "
        "WHERE subject_kind='entity' AND subject_id=? "
        "AND attribute_name='P2_Server_Timing'",
        (eid,),
    ).fetchone()
    assert cur is not None
    assert cur["value_num"] == 50.0
    assert cur["value_unit"] == "ms"

    # S3_Server_Timing is a range
    cur = obc_conn.execute(
        "SELECT * FROM attribute "
        "WHERE subject_kind='entity' AND subject_id=? "
        "AND attribute_name='S3_Server_Timing'",
        (eid,),
    ).fetchone()
    assert cur is not None
    assert cur["value_min"] == 4900.0
    assert cur["value_max"] == 5100.0
    assert cur["value_tol"] == 100.0


def test_q4_transitive_references(obc_conn) -> None:
    """Q4: GB/T 18487.1 → 18487.4 is a 1-hop reference."""
    from kb1_ontology.relation_registry import traverse_relations
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    eid = None
    for row in obc_conn.execute("SELECT entity_id, canonical_name FROM entity"):
        if normalize_canonical_name(row["canonical_name"]) == "GB/T 18487.1":
            eid = row["entity_id"]
            break
    paths = traverse_relations(
        obc_conn, start_id=eid, max_hops=1,
        relation_name="references", domain="OBC",
    )
    assert len(paths) >= 1
    # First path should end at GB/T 18487.4
    cur = obc_conn.execute(
        "SELECT canonical_name FROM entity WHERE entity_id = ?",
        (paths[0][-1].dst_id,),
    ).fetchone()
    assert normalize_canonical_name(cur["canonical_name"]) == "GB/T 18487.4"


def test_q5_services_listed_by_attribute_name(obc_conn) -> None:
    """Q5: Services are listed by structured attribute query."""
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    eid = None
    for row in obc_conn.execute("SELECT entity_id, canonical_name FROM entity"):
        if normalize_canonical_name(row["canonical_name"]) == "ISO 14229-1":
            eid = row["entity_id"]
            break
    cur = obc_conn.execute(
        "SELECT attribute_name, value_text FROM attribute "
        "WHERE subject_kind='entity' AND subject_id=? "
        "AND attribute_name LIKE 'service_%'",
        (eid,),
    ).fetchall()
    assert len(cur) == 1
    assert cur[0]["attribute_name"] == "service_TesterPresent"
    assert cur[0]["value_text"] == "0x3E"
