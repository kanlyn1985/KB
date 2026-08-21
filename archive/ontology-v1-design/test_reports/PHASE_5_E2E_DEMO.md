# Phase 5 Test Report: End-to-End Demo

**Date**: 2026-06-08
**Phase Goal**: Prove that the ontology system can represent
real-world OBC knowledge AND answer real systems-engineer
questions through structured graph queries — not fuzzy text
search.

## Goal Restatement

This is the final acceptance phase. The system is "done" when:
- A small OBC ontology can be built from real standard codes
- Five representative questions can be answered via structured
  queries (relations + attributes) without any LLM or vector search

## What Phase 5 Delivered

### Build script

``scripts/ontology_demo/build_obc_ontology.py`` seeds the ontology
with 13 hand-curated standards, 13 reference relations, and 18
typed attributes. The result lives in
``knowledge_base/ontology/ontology.db``.

### Query script

``scripts/ontology_demo/query_obc_ontology.py`` runs 5 demo queries
that exercise every Phase 0-4 capability.

### End-to-end tests

``src/kb1_ontology/tests/test_obc_demo.py`` runs the same 5
queries in pytest, asserting exact results.

## Acceptance Criteria vs Results

| ID | Goal | Verified by | Status |
|----|------|-------------|--------|
| G1 | Hand-curated OBC ontology builds | build_obc_ontology.py | ✅ PASS |
| G2 | Ontology-driven queries | query_obc_ontology.py (5 queries) | ✅ PASS |
| G3 | Cross-entity reference discovery | test_q1, test_q2, test_q4 | ✅ PASS |
| G4 | Attribute queries return exact values | test_q3 | ✅ PASS |
| G5 | E2E demo reproducible as a test | test_q1..q5 | ✅ PASS |

**Test result**: 5/5 E2E tests passed in 0.42s.

**Cumulative across all phases**: 5 + 32 + 34 + 28 + 24 + 5 = **128/128 passed**.

## The 5 Demo Questions (and their answers)

### Q1: What standards does ISO 14229-7 (UDS on LIN) reference?

```
ISO 14229-7 directly references 3 standards:
  → ISO 14229-1
  → ISO 14229-2
  → ISO 14229-3
```

This is a **single-hop relation traversal**. RAG would do fuzzy
matching; the ontology answer is exact.

### Q2: What standards depend on ISO 14229-1?

```
5 standards reference ISO 14229-1:
  ← ISO 14229-7
  ← ISO 14229-3
  ← ISO 14229-4
  ← ISO 14229-5
  ← ISO 14229-6
```

**Reverse-direction traversal** of the same graph. Without
an inverse-relation helper (Phase 3) this would be a separate
query.

### Q3: What is the P2 Server Timing for ISO 14229-3?

```
P2_Server_Timing = 50.0 ms
(text representation: '50 ms')

S3_Server_Timing: 5000.0 ± 100.0 ms
  range: [4900.0, 5100.0]
```

A **typed attribute query**. The answer is a number, not a
text snippet. The S3 range also shows the parser handling
"5000 ± 100 ms" correctly (with Unicode ±).

### Q4: Charging standards reachable from GB/T 18487.1 in 2 hops

```
Found 4 reachable path(s):
  GB/T 18487.4
  GB/T 18487.5
  ISO 15118
  GB/T 18487.4 → GB/T 20234.2
```

A **BFS traversal** with hop limit. Per-path cycle protection
prevents infinite walking.

### Q5: What UDS services does ISO 14229-1 define?

```
5 UDS services defined:
  DiagnosticSessionControl: 0x10
  ECUReset: 0x11
  ReadDataByIdentifier: 0x22
  SecurityAccess: 0x27
  TesterPresent: 0x3E
```

A **structured query** (`attribute_name LIKE 'service_%'`) that
RAG cannot replicate — the hex codes are too short and ambiguous
for fuzzy matching.

## Comparison: Ontology vs RAG

| Question type | RAG (vector search) | Ontology-driven |
|--------------|---------------------|-----------------|
| "What does 14229-7 reference?" | Returns text mentions of "14229-7" + nearby paragraphs. May include wrong standard. | Exact 3-set. |
| "P2 Server Timing value?" | Returns text mentioning P2, but the number is buried in prose. | 50.0 ms — a float. |
| "List services defined in 14229-1" | Hard — hex codes (0x10, 0x3E) collide with anything containing them. | Exact list, ordered. |
| "Transitive references" | Cannot do at all. | BFS with hop limit. |

The key value of the ontology is **structured query power**, not
similarity. For questions that have a structured answer
("what depends on what", "what is the value of X"), the ontology
wins decisively. For purely free-form questions ("summarize
this document"), RAG remains the right tool.

## Cross-Validation Against Existing System

All KB1 main system health checks pass (10/10). The new system
adds 128 tests without disturbing any existing code.

## Files Created

| Path | Purpose | Lines |
|------|---------|-------|
| `scripts/ontology_demo/build_obc_ontology.py` | Seed script | 240 |
| `scripts/ontology_demo/query_obc_ontology.py` | 5 demo queries | 290 |
| `src/kb1_ontology/tests/test_obc_demo.py` | E2E test | 270 |

## What Phase 5 Does NOT Cover

- ❌ LLM-based discovery of new classes from documents
  (deferred; out of MVP scope)
- ❌ Bulk import from existing KB1's knowledge base
- ❌ A persistent web UI for browsing the ontology
- ❌ Cross-domain queries ("show me what software engineers
  should know about UDS")

## Phase Gate Decision

| Gate | Status |
|------|--------|
| All tests pass | ✅ (128/128) |
| Demo script works end-to-end | ✅ (verified) |
| Test report committed | ✅ (this file) |
| Existing system unaffected | ✅ (verified) |

**Phase 5: COMPLETE — the ontology MVP is end-to-end functional.**

---

## Overall Project Status (P0–P5)

| Phase | Status | Tests | Lines |
|-------|--------|-------|-------|
| Phase 0 | ✅ | 5/5 | ~157 |
| Phase 1 | ✅ | 32/32 | ~1030 |
| Phase 2 | ✅ | 34/34 | ~1195 |
| Phase 3 | ✅ | 28/28 | ~1245 |
| Phase 4 | ✅ | 24/24 | ~905 |
| Phase 5 | ✅ | 5/5 | ~800 |
| **Total** | **✅** | **128/128** | **~5332** |

**The KB1 ontology system is end-to-end functional, fully
isolated from the existing system, and ready for evaluation
against the legacy KB1 implementation in a future phase.**
