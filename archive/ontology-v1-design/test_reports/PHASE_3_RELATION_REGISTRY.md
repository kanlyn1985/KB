# Phase 3 Test Report: Relation Registry

**Date**: 2026-06-08
**Phase Goal**: Prove that relations between entities can be
defined, queried, and traversed — the core "ontology-driven
query" capability.

## Goal Restatement

Per the principle: tests serve the phase's goal, not the existing
test suite. Phase 3 tests verify that the **relation registry** —
the "edges" of the ontology graph — works as designed.

## Acceptance Criteria vs Results

| ID | Goal | Verified by | Status |
|----|------|-------------|--------|
| G1 | Relation definitions can be created and queried | TestRelationDefCRUD (7 tests) | ✅ PASS |
| G2 | Relation instances can be created | TestRelationInstances (8 tests) | ✅ PASS |
| G3 | Scope (core vs domain) works | TestScope (2 tests) | ✅ PASS |
| G4 | Graph traversal from a starting entity | TestTraversal (4 tests) | ✅ PASS |
| G5 | Inverse-relation helper works | TestInverse (3 tests) | ✅ PASS |
| G6 | Real ISO 14229 family reference graph | TestISO14229Scenario (2 tests) | ✅ PASS |

**Test result**: 28/28 passed in 1.87s.

**Cumulative across all phases**: 5 (P0) + 32 (P1) + 34 (P2) + 28 (P3) = **99/99 passed**.

## Bugs Found and Fixed During Phase 3

### Bug 1: Unregistered relation_name not caught early

**Symptom**: Calling ``create_relation(conn, "nope", ...)`` raised
a ``UNIQUE`` constraint error from SQLite instead of a clean
``RelationRegistryError``.

**Fix**: Added a pre-check that the relation_name is registered
in ``relation_def`` before attempting the INSERT.

### Bug 2: IntegrityError not wrapped in domain exception

**Symptom**: A second call to ``create_relation`` with the same
arguments raised a raw ``sqlite3.IntegrityError`` instead of
``RelationRegistryError``.

**Fix**: Wrapped the INSERT in try/except IntegrityError and
re-raise as ``RelationRegistryError``.

### Bug 3: Global visited prevented multiple paths to same node

**Symptom**: When traversing a graph like
``14229-7 → 14229-1``, ``14229-7 → 14229-2``, the 2-hop path
``14229-7 → 14229-3 → 14229-1`` was missing because
``14229-1`` was already in the global visited set from the
1-hop step.

**The issue**: A single global visited set conflates "node seen
on the current path" (true cycle, must block) with "node
reachable via a different path" (legitimate, must allow).

**Fix**: Replaced global visited with **per-path visited**. Each
path has its own visited set, containing the start node and
the src of every relation on the path. This permits
``14229-1`` to appear in multiple paths (via different
routes) but blocks cycles where a node is the dst of two
consecutive relations on the same path.

## Design Decisions Confirmed

1. **Four relation categories** (structural / attributive /
   referential / temporal) are encoded as CHECK constraints
   at the SQL level. A bad category is rejected at the DB
   boundary, not at the Python layer.

2. **Self-loops are rejected**. A relation from a node to itself
   is almost always a bug. We reject it at the CRUD layer.

3. **UNIQUE on (relation, src_kind, src_id, dst_kind, dst_id,
   domain)**. The domain is part of identity, so two relations
   with the same endpoints in different domains are distinct.

4. **Per-path cycle protection** (not global). See Bug 3 above.

5. **Core + private scope**. Core relations are global;
   domain-specific relations live in ``scope="domain:<name>"``.
   The traversal defaults to no scope filter, returning edges
   across all scopes unless the caller filters.

## Cross-Validation Against Existing System

All KB1 main system health checks pass (10/10). The new system
adds 99 tests without disturbing any existing code.

## Files Created

| Path | Purpose | Lines |
|------|---------|-------|
| `src/kb1_ontology/relation_registry/__init__.py` | Public API | 70 |
| `src/kb1_ontology/relation_registry/schema.py` | Schema + dataclasses | 175 |
| `src/kb1_ontology/relation_registry/crud.py` | CRUD | 240 |
| `src/kb1_ontology/relation_registry/traversal.py` | BFS traversal | 150 |
| `src/kb1_ontology/relation_registry/seeds.py` | 7 core relation seeds | 100 |
| `src/kb1_ontology/tests/test_relation_registry.py` | 28 tests | 510 |

Total: **~1245 lines** of new code.

## What Phase 3 Does NOT Cover

Following the test-from-goal principle, Phase 3 deliberately
does NOT test:

- ❌ Attributes on entities (Phase 4)
- ❌ Reasoning / inference over the relation graph
  (out of scope; would require a separate RDFS/OWL reasoner)
- ❌ Visualizing the graph (separate tool, not a core feature)
- ❌ Bulk import from external sources (e.g., Neo4j CSV)

## Phase Gate Decision

| Gate | Status |
|------|--------|
| All tests pass | ✅ (28/28) |
| Acceptance criteria met | ✅ (G1-G6) |
| Test report committed | ✅ (this file) |
| Existing system unaffected | ✅ (verified) |

**Phase 3: COMPLETE — ready to enter Phase 4 (Attribute Store).**
