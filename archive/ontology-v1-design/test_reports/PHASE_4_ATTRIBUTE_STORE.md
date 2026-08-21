# Phase 4 Test Report: Attribute Store

**Date**: 2026-06-08
**Phase Goal**: Prove that attributes on entities work in all four
value types (string, number, range, reference), with real-world
range parsing and attribute-value queries.

## Goal Restatement

Per the principle: tests serve the phase's goal, not the existing
test suite. Phase 4 tests verify that the **attribute store** —
the (subject, attribute, value) triple machinery — works as
designed.

## Acceptance Criteria vs Results

| ID | Goal | Verified by | Status |
|----|------|-------------|--------|
| G3 | Range value parsing for real-world formats | TestRangeParser (7 tests) | ✅ PASS |
| G1 | Set/get works for all four value types | TestSetGet (6 tests) | ✅ PASS |
| G2 | Validation rules enforced | TestValidation (5 tests) | ✅ PASS |
| G4 | Query by name, value range, subject | TestQuery (3 tests) | ✅ PASS |
| G5 | Deletion works | TestDelete (2 tests) | ✅ PASS |
| G6 | Real ISO 14229-3 timing parameters | TestISO14229Scenario (1 test) | ✅ PASS |

**Test result**: 24/24 passed in 0.88s.

**Cumulative across all phases**: 5 + 32 + 34 + 28 + 24 = **123/123 passed**.

## Bugs Found and Fixed During Phase 4

### Bug 1: `+` in character class acts as quantifier

**Symptom**: `parse_range_value("50+/-10 ms")` returned None
even though the regex should match. The Unicode-tolerance pattern
used a character class `[±+/-]`, where the bare `+` was being
interpreted as "one or more" of the previous character group.

**Fix**: Replaced the character class with a non-capturing
alternation: `(?:±|\+/-)`. This avoids the quantifier trap.

### Bug 2: Unit not auto-populated for `number` type

**Symptom**: Setting `value_text="50 ms"` with `value_type=number`
correctly parsed `value_num=50.0` but left `value_unit=None`.

**Fix**: After parsing, inherit the unit from the parsed text
unless the caller already provided one. This makes
`set_attribute(... value_text="50 ms")` work end-to-end without
requiring the caller to also pass `value_unit="ms"`.

## Design Decisions Confirmed

1. **Four columns, not one JSON**. The schema uses separate
   columns for value_text, value_num, value_min, value_max,
   value_unit, value_tol, value_ref_kind, value_ref_id. This
   makes range queries (`WHERE value_num BETWEEN ? AND ?`)
   fast and indexable.

2. **Auto-parse on text input**. When value_type is
   `number` or `range` and the caller supplies value_text,
   we run the range parser. If parsing fails, the type
   downgrades to `string` (no data lost). This matches the
   way real data is typically entered.

3. **One row per (subject, attribute_name)**. Setting an
   attribute that already exists overwrites it. This matches
   the "value of X is now Y" semantic of attributes.

4. **Reference type requires a valid referent**. The referent
   (entity or class) is checked at write time, not lazily.
   This prevents dangling references.

## Cross-Validation Against Existing System

All KB1 main system health checks pass (10/10). The new system
adds 123 tests without disturbing any existing code.

## Files Created

| Path | Purpose | Lines |
|------|---------|-------|
| `src/kb1_ontology/attribute_store/__init__.py` | Public API | 45 |
| `src/kb1_ontology/attribute_store/schema.py` | Schema + dataclass | 130 |
| `src/kb1_ontology/attribute_store/range_parser.py` | Range value parser | 130 |
| `src/kb1_ontology/attribute_store/crud.py` | CRUD + query | 220 |
| `src/kb1_ontology/tests/test_attribute_store.py` | 24 tests | 380 |

Total: **~905 lines** of new code.

## What Phase 4 Does NOT Cover

Following the test-from-goal principle, Phase 4 deliberately
does NOT test:

- ❌ Class-level attributes (only entity-level is tested; the
  schema supports both, but a richer class-level test belongs
  to a later phase)
- ❌ Inference over attributes (e.g., "compute the total budget
  from per-component prices")
- ❌ Bulk import of attributes from external sources

## Phase Gate Decision

| Gate | Status |
|------|--------|
| All tests pass | ✅ (24/24) |
| Acceptance criteria met | ✅ (G1-G6) |
| Test report committed | ✅ (this file) |
| Existing system unaffected | ✅ (verified) |

**Phase 4: COMPLETE — ready to enter Phase 5 (End-to-End Demo).**
