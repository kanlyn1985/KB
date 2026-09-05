# Phase 1 Test Report: Class Registry

**Date**: 2026-06-08
**Phase Goal**: Prove the 3-layer class hierarchy (Meta / Domain / Instance)
correctly expresses "kinds of things" in an engineering knowledge base.

## Goal Restatement

Per the principle: tests serve the phase's goal, not the existing
test suite. Phase 1 tests verify that the **class registry** — the
taxonomy backbone of the ontology — works as designed.

## Acceptance Criteria vs Results

| ID | Goal | Verified by | Status |
|----|------|-------------|--------|
| G1 | 3-layer structure (Meta / Domain / Instance) is expressible | TestThreeLayerStructure (4 tests) | ✅ PASS |
| G2 | Subclasses inherit from parents (transitive is-a) | TestInheritance (3 tests) | ✅ PASS |
| G3 | Domain classes do not leak into other domains | TestDomainIsolation (2 tests) | ✅ PASS |
| G4 | Core vs auto-discovered classes are distinguishable | TestCoreClasses (2 tests) | ✅ PASS |
| G5 | Re-seeding is idempotent | TestSeedIdempotency (1 test) | ✅ PASS |
| CRUD | Standard CRUD operations work and enforce rules | TestCRUD (8 tests) | ✅ PASS |
| Validation | Layer/parent rules are enforced | TestValidationRules (7 tests) | ✅ PASS |
| Cycles | Acyclic hierarchy enforced, cycles rejected | TestCycleDetection (2 tests) | ✅ PASS |
| Schema integrity | No nulls, idempotent schema, unique constraints | TestSchemaIntegrity (3 tests) | ✅ PASS |

**Test result**: 32/32 passed in 0.97s.

## Bugs Found and Fixed During Phase 1

The test-driven approach paid off: writing tests first surfaced three
real design bugs in the implementation.

### Bug 1: Layer rule was too strict

**Symptom**: `test_domain_layer_subclasses_meta` failed because the
CRUD layer enforced `parent.layer == layer` (same layer required),
but the seed needed Domain classes to hang off Meta classes.

**Fix**: Replaced with the correct rule:
- Domain classes must have a **Meta** parent (cross-layer is-a)
- Meta classes must have a **Meta** parent (no skip to Domain)
- Two Domain classes cannot be directly linked (parent/child)

**Lesson**: The original 3-layer intuition ("3 separate layers")
missed that Meta↔Domain is **is-a**, not "sibling".

### Bug 2: `get_descendants` returned duplicates

**Symptom**: `test_descendants_of_root` got 41 instead of 15.
The recursive CTE visited the same node via multiple paths.

**Fix**: Added `DISTINCT` + `MIN(depth)` aggregation in the
final SELECT. The tree structure means a single class can be
reached through different branches.

### Bug 3: Test semantics were inverted

**Symptom**: `test_creating_cycle_is_rejected` expected
`is_subclass_of(Thing, OBC.STANDARD) == True` (Thing is ancestor
of OBC.STANDARD). The function correctly returned False, but
the test was asserting the wrong direction.

**Fix**: Corrected the test to check the right direction
(OBC.STANDARD is a descendant of Thing, not the other way around).

**Lesson**: When the implementation is correct but the test
fails, the test reflects a wrong mental model. Take the failure
as a signal to think harder.

## Cross-Validation Against Existing System

All 5 Phase 0 tests + 32 Phase 1 tests = **37 tests pass**.
KB1 main system health check: 10/10 PASS. Existing system
unaffected.

## Files Created

| Path | Purpose | Lines |
|------|---------|-------|
| `src/kb1_ontology/class_registry/__init__.py` | Public API | 53 |
| `src/kb1_ontology/class_registry/schema.py` | Schema + ClassDef | 110 |
| `src/kb1_ontology/class_registry/crud.py` | CRUD + validation | 200 |
| `src/kb1_ontology/class_registry/hierarchy.py` | is-a + ancestors + descendants | 130 |
| `src/kb1_ontology/class_registry/seeds.py` | Core class seed | 180 |
| `src/kb1_ontology/tests/test_class_registry.py` | 32 tests | 360 |

Total: **~1030 lines** of new code, all in isolated locations.

## What Phase 1 Does NOT Cover

Following the test-from-goal principle, Phase 1 deliberately
does NOT test:

- ❌ Entity-to-class assignment (Phase 2)
- ❌ Relations between classes (Phase 3)
- ❌ Attribute storage on classes/instances (Phase 4)
- ❌ Auto-discovery of classes from documents (deferred to Phase 6)

## Phase Gate Decision

| Gate | Status |
|------|--------|
| All tests pass | ✅ (32/32) |
| Acceptance criteria met | ✅ (G1-G5 + CRUD + Validation + Cycles + Schema) |
| Test report committed | ✅ (this file) |
| Existing system unaffected | ✅ (verified) |

**Phase 1: COMPLETE — ready to enter Phase 2 (Entity Manager).**
