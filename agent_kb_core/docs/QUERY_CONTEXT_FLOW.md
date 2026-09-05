# Query Understanding and Context Pack Flow

This document freezes the next rebuild boundary for `agent-kb-core`.

## Why this layer exists

The old KB already had query rewrite, LLM semantic parsing, expansion, routing, graph retrieval, reranking, and answer generation. The failure pattern was not simply missing LLM support. The failure pattern was that the system still treated user questions mainly as text queries instead of converting them into domain-aware machine frames.

The new flow introduces a stable intermediate contract:

```text
User Query
  -> QueryFrame
  -> Object-centered Retrieval Cards
  -> AgentContextPack
  -> Agent final answer
```

## QueryFrame

`QueryFrame` is the contract between query understanding and retrieval. It contains:

- `intent`
- `domain`
- `target_objects`
- `slots`
- `missing_slots`
- `preferred_fact_types`
- `required_evidence_shapes`
- `retrieval_channels`
- `answer_contract`
- `answer_strategy`

The MVP implementation is deterministic and domain-pack driven. LLM support can be added later behind the same schema.

## Object Projection

`ObjectProjection` is the ontology-lite object layer. It is domain-neutral. A domain pack may define objects such as:

- `Parameter`
- `StandardClause`
- `TestMethod`
- `PolicyRule`
- `LawArticle`
- `Risk`

Core only sees generic object projections.

## Retrieval Card

`RetrievalCard` is a recall-optimized object card. It aggregates:

- canonical object id
- canonical display name
- aliases
- object type
- related objects
- evidence refs
- answer shapes
- search text

This is the bridge from chunk-first recall to object-centered recall.

## AgentContextPack

`AgentContextPack` is not a final answer. It is structured input to an agent. It contains:

- query frame
- answer contract
- target objects
- object relations
- retrieval cards
- facts
- evidence
- hidden context
- warnings
- knowledge gaps
- recommended answer strategy

## Design rule

Core must stay domain-neutral.

Domain-specific interpretation belongs in:

```text
domains/<domain_id>/
```

For example, `domains/obc_dcdc` defines output ripple aliases and hidden context. It is a validation domain pack, not a Core dependency.
