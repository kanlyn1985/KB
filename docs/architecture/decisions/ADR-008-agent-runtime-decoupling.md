# ADR-008: Agent Runtime is Decoupled from Semantic Runtime

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-014, SYS-015, SYS-016, SYS-017
- Related Data Model: DM-013 Memory, DM-014 Context, DM-015 Goal, DM-016 Decision, DM-017 Action, DM-018 Observation (Agent-plane objects)
- Related ICD: AgentRuntime (5.14) depends only on ContextEngine (5.11), MemoryStore (5.9), StateStore (5.10), DecisionEngine (5.12), ObservationStore (5.13) - and via them, Retrieval/Reasoning
- Related V&V: V&V Plan section 17 (memory verification: promotion pipeline), 19 (agent E2E), 16 (context must not hide gaps); Golden G029/G030

## Context

AKB agent loop (Goal, Context, Retrieve, Reason, Decision, Action, Policy, Observation, State, Memory) must remain evolvable: agent frameworks churn fast, semantic storage/reasoning changes on a different cadence. Current agent_kb code keeps answer/agent concerns in separate modules (commands/answer_query, service/api) but nothing forbids a future module from reaching into storage internals or a specific graph SDK.

## Problem

If Agent Runtime code imports Neo4j drivers, Qdrant clients, Semantica graph classes or a concrete LLM SDK directly: (a) storage swaps break the agent; (b) policy/audit boundaries become unenforceable (an agent holding a graph driver can bypass read-only knowledge guarantees - INV-008); (c) testing the E2E loop requires the entire infrastructure instead of interface fakes.

## Decision

1. Agent Runtime is NOT Semantic Runtime. The agent plane talks only to stable ICD interfaces: Knowledge (AssertionStore read paths), Retrieval, Reasoning, Context, Memory, State, Decision.
2. Forbidden direct dependencies from agent-plane code: Neo4j or any graph driver, Qdrant or any vector client, Semantica classes, concrete LLM SDKs (LLM access is behind the Reasoning/gateway interface).
3. Agent writes are confined to: Memory (working/episodic), Action proposals, Observation records. Authoritative Knowledge is read-only for agents (INV-008); memory-to-knowledge promotion goes through the governed pipeline (INV-009).
4. Decision objects must be replayable: goal/context/options/selected/trace/refs/confidence (DM-016) - enabling why-did-the-agent-choose-this audits.

## Alternatives Considered

- A. Agent owns its storage (fast prototyping): rejected - fragments the knowledge plane, kills auditability, recreates the shadow-knowledge problem.
- B. Agent calls storage directly but read-only: rejected - read-only discipline cannot be enforced by convention; interface isolation is the enforceable boundary.
- C. Merge agent and semantic runtime into one service: rejected - couples unrelated change cadences and makes security review (V&V 20) unbounded.

## Rationale

Interface decoupling is the only mechanism making INV-008/009 technically enforced rather than aspirational, and it matches the existing ICD structure where AgentRuntime is defined solely by its ICD dependencies. It also enables the E2E golden case G029 to run against interface fakes in CI (offline, no LLM) - consistent with the local-AI workflow.

## Consequences

- Agent features must express needs as interface extensions (new ICD methods), not new direct clients.
- E2E tests use ContextEngine/MemoryStore fakes - faster, deterministic, offline.
- Any agent-needed bulk operation (e.g. propose-knowledge-write) becomes an interface method with policy hooks.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

V&V 19 E2E golden (G029): all object references legal, no unauthorized knowledge mutation - testable with fakes. V&V 17: illegal memory-to-knowledge promotion must fail (INV-009). Static check (V0.1+): agent-plane modules must not import graph/vector/LLM SDK packages (lint-level guard).

## Change Impact

V0.1 agent modules organized as agent-plane vs semantic-plane packages with import rules. No change to existing retrieval behavior; answer_query already conforms (talks to pipeline, not storage internals).

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
