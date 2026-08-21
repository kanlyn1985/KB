# ADR 0001: Meta ↔ Domain Layer Rule

**Date**: 2026-06-08
**Status**: Accepted
**Context**: Phase 1 implementation of class registry

## Context

The 3-layer class hierarchy was defined as Meta (abstract universals) +
Domain (engineering-role subtrees) + Instance (concrete entities).
The question arose: when a Domain class is created, what layer must
its parent be in?

## Considered Options

1. **Same-layer rule** — A Domain class's parent must also be Domain.
   Meta classes hang only off Meta.
2. **Meta-only-for-Domain** — Domain classes must have a Meta parent.
   Meta classes must have a Meta parent. Cross-layer is-a is allowed
   (Domain ⊆ Meta).
3. **No rules** — any class can be parent of any class.

## Decision

Option 2. The class hierarchy is a **single tree of is-a relations**
that crosses layer boundaries at exactly one point: when moving from
a Meta class to its Domain specializations.

This means:
- `OBC.STANDARD is-a META.INFORMATION-ENTITY` — the is-a crosses layers
- `OBC.STANDARD is-a META.THING` (transitive) — also crosses
- `META.PHYSICAL-ENTITY` and `OBC.DEVICE` are on different branches
  of the same tree

## Consequences

- Domain classes inherit any properties defined on their Meta
  ancestors. This is what makes the ontology a **unified knowledge
  graph**, not two disconnected forests.
- Cross-domain sharing (e.g., OBC using SoftwareDomain classes)
  is NOT an is-a relationship. It must be expressed via a different
  mechanism — most likely a Relation (Phase 3), not a class link.
- An OBC engineer querying for "what standards exist" naturally
  traverses OBC.STANDARD's ancestors and finds the Meta layer.
- The rule is enforced at the CRUD layer
  (`crud.create_class`), not in SQL.

## Why Option 1 Was Wrong

Option 1 (same-layer rule) would force the hierarchy to be two
**disconnected** forests: one Meta tree, one Domain tree. Then
"is-a across layers" would not be expressible, and an OBC class
would have **no link to the abstract InformationEntity universal** —
defeating the purpose of having a Meta layer at all.

## Why Option 3 Was Wrong

Option 3 (no rules) would let a Domain class parent another
Domain class. This conflates "is-a" (subclass) with "uses" or
"related-to" (relation), and would make the hierarchy unmaintainable.

## Implementation Note

The seed (`seeds.py`) correctly builds the tree with this rule:
every OBC class has a Meta parent. The CRUD layer enforces
the rule, so future seed additions cannot violate it.
