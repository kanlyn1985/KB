# Phase 6 Integration Test Report: Combined Legacy + Ontology

**Date**: 2026-06-10
**Type**: Integration test — new ontology system + legacy KB1
  answer pipeline, side by side

## Goal

Demonstrate that the two systems are **complementary** and
build a **combined query** that gives the user the best of
both:

- **Ontology**: precise typed answers (50.0 ms, "set of 3
  entities", "BFS path")
- **Legacy**: prose context (regulatory citations, paragraphs)

The bridge must:
- Route the question to the right system
- Run BOTH systems in parallel (configurable)
- Combine results into a single user-facing answer
- Degrade gracefully when either system is unavailable

## Architecture

```
User question
   |
   v
[Router]  (ontology/combined_query.py)
   | keyword + structural detection
   |
   +-- parameter  -->  Ontology Handler  -->  Typed Value
   +-- reference  -->  Ontology Handler  -->  Structured Set
   +-- traversal  -->  Ontology Handler  -->  BFS Paths
   +-- service    -->  Ontology Handler  -->  Service List
   +-- definition -->  Ontology Handler  -->  Title String
   +-- free_form  -->  Legacy Handler    -->  Prose Context
   |
   v
[Combiner]    (format_combined)
   |
   v
[Category: parameter]

Structured answer (ontology):
   50.0 ms
   type: typed_value

Context (legacy):
   标准号是 ISO 14229-3，发布日期是 2012-12-01。
```

## What's New in the Codebase

| Path | Purpose |
|------|---------|
| ``src/kb1_ontology/legacy_bridge.py`` | Thin wrapper around ``answer_api.answer_query`` and ``golden_cases`` lookup. The ONLY place in the new package that imports from the legacy system. |
| ``src/kb1_ontology/combined_query.py`` | Router + handlers + combiner. Routes to the right system, runs both (or ontology only via ``use_legacy=False``), merges results. |
| ``src/kb1_ontology/tests/test_combined_query.py`` | 14 tests covering router, structure, real data, error handling. |
| ``src/kb1_ontology/tests/test_combined_e2e.py`` | 56 tests covering G1-G6 + bridge isolation. |

## Router Categories

The router classifies incoming questions into 6 categories:

| Category | Pattern | Goes to |
|----------|---------|---------|
| `parameter` | "P2 timing", "额定电压", "50 ms", "最大输出电压" | Ontology (typed) |
| `reference` | "references", "引用了", "depends on", "what standards reference" | Ontology (set) |
| `traversal` | "2 跳可达", "2-hop", "3 跳" | Ontology (BFS) |
| `service` | "UDS 服务", "0x10", "services defined" | Ontology (list) |
| `definition` | "是什么", "definition", "what is" | Ontology (title) |
| `free_form` | (anything else) | Legacy (prose) |

## Demo Results (10 real questions)

| # | Question | Category | Ontology | Legacy |
|---|----------|----------|----------|--------|
| 1 | ISO 14229-3 P2 timing? | parameter | **50.0 ms** | "标准号是 ISO 14229-3..." |
| 2 | GB/T 18487.1 rated voltage? | parameter | **250.0 V** | "标准号是 GB/T 18487.1—2023..." |
| 3 | GB/T 18487.4 V2L max voltage? | parameter | **250.0 V** | "车载充电机正常工作时..." |
| 4 | GB/T 18487.1 references? | reference | **3 standards** | "代替标准是 GB/T 18487.1—2015" |
| 5 | Who references 14229-1? | reference | **5 standards** | (no excerpt) |
| 6 | 2-hop from 14229-7? | traversal | **5 paths** | (no excerpt) |
| 7 | 14229-1 services? | service | **5 services** | "标准号是 ISO 14229-5..." |
| 8 | What is 14229-1? | definition | "Road vehicles — UDS — Application layer" | "ISO：14229-1:2013(E)" |
| 9 | What is V2L? | definition | "V2L (Vehicle-to-Load) requirements" | "车载充电机..." |
| 10 | 交流电压波动限值? | free_form | (no answer) | **30+ GB/T 规范引用** |

**Pattern**: structured questions → ontology wins; free-form → legacy wins; both work in parallel.

## Test Results

```
Test counts:    56 / 56 passed (test_combined_e2e.py)
                14 / 14 passed (test_combined_query.py)
Total kb1_ontology tests: 201 / 201 passed
KB1 main system:  unaffected
```

Tests cover:
- Router classification for all 6 categories (18 parametric cases)
- CombinedAnswer dataclass structure
- Real-data queries for each category
- Error handling (empty, nonsense, unicode, injection)
- Bridge isolation (T2 exception)
- Legacy skip mode (`use_legacy=False`)

## New Feature: `use_legacy` Parameter

The `combined_query()` function now accepts an optional
`use_legacy: bool = True` parameter:

- `True` (default): Query both ontology and legacy in parallel
- `False`: Skip legacy API call, return ontology-only answer

Use case: Production systems where ontology answers are
sufficient and LLM latency (3-30s) should be avoided.

```python
# Fast path: ontology only (<100ms)
r = combined_query(workspace, "P2 timing in 14229-3?", use_legacy=False)

# Full path: both systems (ontology + legacy context)
r = combined_query(workspace, "P2 timing in 14229-3?", use_legacy=True)
```

## Test Design Note: T2 Exception

Phase 0's T2 test ("zero interference from legacy") was
originally strict. With Phase 6's ``legacy_bridge``, that
strict reading is too tight — the bridge is **designed** to
import the legacy system. We amended the test:

- T2 now excludes the ``legacy_bridge.py`` file (the only
  allowed exception)
- A new test ``test_t2b_legacy_bridge_is_documented_exception``
  verifies the bridge module's docstring explicitly states
  it is the integration point

This preserves the **intent** of T2 (core modules stay
legacy-free) while acknowledging the **explicit design**
(bridge is the one allowed touch point).

## Reproduce

```bash
# Make sure the ontology is built
python3 scripts/ontology_demo/build_obc_ontology.py

# Run the combined query demo
python3 scripts/ontology_demo/combined_query_demo.py

# Run all tests
python3 -m pytest src/kb1_ontology/tests/ -v
```

## What This Report Does NOT Show

- The legacy pipeline is slow (3-30s per query) because it goes
  through LLM. The ontology path is <100ms. In production we'd
  use `use_legacy=False` for structured questions.
- A "smart" router that learned from training data. The current
  router is keyword-based, which is robust but coarse-grained.
- A combined UI. The current output is text; a real product
  would show ontology results in a structured widget and legacy
  results in a prose panel.

## Conclusion

The combined system proves the value of the parallel-isolated
design:

- The new ontology system **cannot stand alone** for every
  question (e.g., free-form regulatory queries).
- The legacy system **cannot give exact answers** for
  structured questions.
- **Combined**, the user gets a richer answer than either
  alone: precise + contextual.

This validates the design decision (Phase 0's "parallel
isolated systems") — we don't have to choose between the
two systems; they coexist and the bridge gives us the best of
both.
