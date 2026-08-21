# ADR 0002: Two-Level Normalization (Canonical vs Alias)

**Date**: 2026-06-08
**Status**: Accepted
**Context**: Phase 2 implementation of entity manager

## Context

When a user references a standard like "ISO 14229-1", they may write
it in many ways: `ISO 14229-1—2013`, `ISO 14229-1:2013`,
`ISO 14229-7:2015(E)`, etc. We need to recognize these as
referring to the same standard, while keeping the original form
visible for human review.

The naive approach is one "normalize" function used everywhere.
This led to a bug in Phase 2 where "ISO 14229-1:2013" and
"ISO 14229-1:2022" were collapsed to the same alias — they are
**different standards** that came out in different years.

## Considered Options

1. **One normalize for everything** — simplest, but loses the
   distinction between "ISO 14229-1:2013" and "ISO 14229-1:2022".
2. **Two normalize functions with different intents**:
   - Deep normalize: strip year, lang marker, dashes → for
     matching against canonical_name.
   - Light normalize: only whitespace + case → for de-duplicating
     aliases that retain the year.
3. **No normalization, full text matching** — most permissive but
   expensive; aliases can proliferate.

## Decision

**Option 2: two-level normalization.**

- `normalize_canonical_name(name)`: aggressive. Strips trailing
  year (4-digit in [1950, 2099]), language markers like `(E)`,
  unicode dash variants, and extra whitespace. The result is what
  we store in the `canonical_name` column. Two strings that
  refer to the same standard collapse to the same canonical name.

- `_light_normalize(s)`: conservative. Only does NFKC, case
  folding, and whitespace collapse. Used for alias de-duplication
  so that "ISO 14229-1:2013" and "ISO 14229-1—2013" are
  recognized as the same alias, but "ISO 14229-1:2013" and
  "ISO 14229-1:2022" are kept distinct.

## Consequences

- A standard referenced with the year and one without can share
  an alias slot.
- A standard referenced with different years stays as two
  separate aliases (and would be two separate entities under
  the same class, since canonical_name includes the year).
- The user can see all the ways a standard has been mentioned
  in the alias list — the year is preserved as raw text.
- The light_normalize is private to the entity_manager module;
  if a future module needs alias-style dedup, it should import
  from there.

## Why Option 1 Was Wrong

Using one normalize for everything would conflate
"the entity's identity" (canonical_name) with "the strings used
to refer to it" (aliases). For standards, the year is part of the
identity in many use cases, so collapsing it at the alias level
loses information.
