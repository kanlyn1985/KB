# Phase 2 Test Report: Entity Manager

**Date**: 2026-06-08
**Phase Goal**: Prove that concrete entity instances are correctly
managed: bound to a class, de-duplicated by canonical name, with
aliases accumulated, and that documents can be tagged with job roles.

## Goal Restatement

Per the principle: tests serve the phase's goal, not the existing
test suite. Phase 2 tests verify that the **entity manager** — the
instance layer of the ontology — works as designed.

## Acceptance Criteria vs Results

| ID | Goal | Verified by | Status |
|----|------|-------------|--------|
| G3 | Name normalization collapses canonical variations | TestNormalization (9 tests) | ✅ PASS |
| G1 | CRUD operations work | TestCRUD (6 tests) | ✅ PASS |
| G4 | De-duplication via find_or_create | TestDedup (4 tests) | ✅ PASS |
| G5 | Alias merging works | TestAliasMerge (4 tests) | ✅ PASS |
| G6 | Real standard codes survive the system | TestRealStandardCodes (3 tests) | ✅ PASS |
| G7 | Documents can be tagged with job roles | TestDocumentRoles (8 tests) | ✅ PASS |

**Test result**: 34/34 passed in 1.08s.

**Cumulative across all phases**: 5 (Phase 0) + 32 (Phase 1) + 34 (Phase 2) = **71/71 passed**.

## Bugs Found and Fixed During Phase 2

### Bug 1: 4-digit year stripped from standard numbers

**Symptom**: `normalize_canonical_name("ISO 15118")` returned
`"ISO 1"`. The regex `\d{4}$` was matching `1511` and dropping
`8`.

**Fix**: Constrained the year regex to `(19[5-9]\d|20\d{2})$` —
a real year is in [1950, 2099]. This prevents false matches
on 4-digit standard-number fragments.

### Bug 2: Trailing language marker not stripped

**Symptom**: `normalize_canonical_name("ISO 14229-7:2015(E)")`
returned `"ISO 14229-7:2015(E)"`. The `(E)` suffix indicates
"English version" and should be dropped.

**Fix**: Added a second regex `_TRAILING_LANG_MARKER` to strip
parenthetical suffixes like `(E)`, `(英文版)`.

### Bug 3: Year-stripping applied to alias de-dup was wrong

**Symptom**: When merging aliases like
`["ISO 14229-1:2013", "ISO 14229-1:2022"]`, both got rejected
because their normalized form (`"ISO 14229-1"`) matched the
canonical name.

**The deeper issue**: I had been using `normalize_canonical_name`
(treats year as discardable) for alias de-duplication. But for
standards, the year IS the distinguishing information:
"ISO 14229-1:2013" and "ISO 14229-1:2022" are different standards
that came out in different years.

**Fix**: Introduced a separate `_light_normalize` function for
alias de-duplication that only does whitespace + case + NFKC, NOT
year-stripping. The "deep" normalization (year-stripped) is only
used for matching `canonical_name` to itself.

### Bug 4: test fixture missing entity schema

**Symptom**: All document-role tests failed with
`no such table: document_role`. The fixture only installed
class_def schema.

**Fix**: Fixture now also calls `ensure_entity_schema`.

## Design Decisions Confirmed

1. **Light normalize vs deep normalize**: Two distinct functions
   serve two purposes:
   - `normalize_canonical_name` — for canonical names (drops year)
   - `_light_normalize` — for alias dedup (preserves year)

2. **Aliases preserve raw form**: The alias list stores the exact
   strings users wrote. Normalization is only used for de-dup,
   never for storage. This preserves information that the year
   encodes.

3. **canonical_name not in aliases**: The canonical name lives
   in its own column. Storing it as an alias too would be
   redundant and waste storage.

4. **Domains are part of identity**: Two entities with the same
   normalized name but different domains are kept distinct.
   This is preparation for cross-domain knowledge (e.g., a
   standard used in both OBC and Software domains).

## Cross-Validation Against Existing System

All KB1 main system health checks pass (10/10). The new system
adds 71 tests without disturbing any existing code.

## Files Created

| Path | Purpose | Lines |
|------|---------|-------|
| `src/kb1_ontology/entity_manager/__init__.py` | Public API | 60 |
| `src/kb1_ontology/entity_manager/schema.py` | Schema + dataclasses | 165 |
| `src/kb1_ontology/entity_manager/normalization.py` | normalize_canonical_name | 110 |
| `src/kb1_ontology/entity_manager/crud.py` | CRUD + find_or_create + merge_aliases | 280 |
| `src/kb1_ontology/entity_manager/document_roles.py` | Job-role tag CRUD | 100 |
| `src/kb1_ontology/tests/test_entity_manager.py` | 34 tests | 480 |

Total: **~1195 lines** of new code.

## What Phase 2 Does NOT Cover

Following the test-from-goal principle, Phase 2 deliberately
does NOT test:

- ❌ Relations between entities (Phase 3)
- ❌ Attributes on entities (Phase 4)
- ❌ Cross-domain queries ("give me all entities visible to
  systems_engineer")
- ❌ Cross-checking against the legacy KB1 entity table

## Phase Gate Decision

| Gate | Status |
|------|--------|
| All tests pass | ✅ (34/34) |
| Acceptance criteria met | ✅ (G1-G7) |
| Test report committed | ✅ (this file) |
| Existing system unaffected | ✅ (verified) |

**Phase 2: COMPLETE — ready to enter Phase 3 (Relation Registry).**
