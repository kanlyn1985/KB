# KB1 Ontology Glossary

**Status**: Working draft (grill session 2026-06-08)
**Scope**: Cross-cutting vocabulary for ontology-driven queries

## Core Terms

### Entity
A node in the knowledge graph that can be the subject or object of a query.
- Has a `class` (what kind of thing it is)
- Has `canonical_name` (human-readable identifier)
- Participates in relations with other entities
- May have attributes (key-value properties)

### Class
The **type** of an entity — answers "what kind of thing is this?"
- **Decision**: Classes are **hybrid-sourced**
  - **Core classes**: Manually defined by domain experts (e.g., Standard, Document, Concept)
  - **Extended classes**: Auto-discovered from documents (clustering / pattern mining)
- Classes form a **3-layer hierarchy**:
  - Meta layer (abstract, e.g., Thing)
  - Domain layer (engineering role domains — see below)
  - Instance layer (concrete entities)

### Class Hierarchy (3 layers, decided)
- **Meta layer**: Abstract universals
  - `Thing` → `InformationEntity`, `PhysicalEntity`, `ProcessEntity`, `ConceptEntity`, `RoleEntity`
- **Domain layer**: Engineering role domains (NOT industry domains)
  - Engineering roles in scope: **Systems Engineering** (current focus),
    Software, Electronics, Testing (future)
  - Each domain owns a subtree of meta classes
  - Example: `SystemsEngDomain.PhysicalEntity.Device.OBC`
- **Instance layer**: Concrete entities from documents
  - Example: `Entity: ISO 14229-1 (class=Standard)`, `Entity: CC1 (class=Component)`

### Job Role (revised)
- The current focus is the **Systems Engineer** role — the engineer
  responsible for the overall behavior, integration, and requirements
  of the OBC system.
- A single document is "what a systems engineer should know" — the
  role is implicit, not a property of the knowledge base.
- During **document ingestion**, a **job role tag** is recorded so
  that the same piece of knowledge can be associated with multiple
  roles (e.g., a CAN protocol document is relevant to systems,
  software, and electronics engineers).
- **Current status**: The `document_role` table schema is ready but
  **not populated** in the current demo. All documents are implicitly
  tagged `systems_engineer`. Population is deferred to Phase 7+
  when multi-role queries are needed.
- Future roles: software engineer, electronics engineer, test engineer.
  They share the same knowledge base but view it through their
  role lens.

### Product Scope (revised 2026-06-08)
The current knowledge base focuses on the **Systems Engineer's**
perspective across these specific products:

- **OBC (On-Board Charger)** — primary product, the focus of the
  current knowledge base
- **DCDC (DC-DC Converter)** — high-voltage to low-voltage
  conversion in the EV powertrain
- **Wallbox** — the AC charging station (off-board)
- **eFuse** — electronic fuse, replacing mechanical fuses in
  high-voltage systems
- **EVCC (Electric Vehicle Communication Controller)** — the
  in-vehicle controller for high-level charging communication
  (e.g., ISO 15118, PLC)

These products are **instances** of the Meta-layer classes, not
classes themselves. The ontology classes (Standard, Device,
Component, Process, Parameter, etc.) are the **shared abstractions**
across all these products. So the class hierarchy stays simple;
the products populate the Instance layer.

Note: OBC is **the primary product**, with the others being
secondary but sharing the same engineering knowledge base.

### Why Engineering-Role Domains
- The user population is **engineers in specific roles** (OBC systems engineer, software engineer, etc.)
- An OBC engineer needs cross-industry knowledge (charging standards,
  power electronics, etc.) — partitioning by industry would scatter it
- A software engineer's knowledge structure differs from an electronics
  engineer's — role-based domains keep related knowledge together
- New roles (testing, mechanical, etc.) add new domain subtrees without
  disturbing existing ones

### Relation
A typed connection between two entities. The mechanism that makes
"ontology-driven" queries possible — instead of fuzzy vector search,
we **traverse** relations.

#### Relation Classification (decided)
Relations are categorized by **function** (4 functional classes):
- **Structural**: `is-a`, `part-of` (build the skeleton of the graph)
- **Attributive**: `has-attribute` (attach properties to entities)
- **Referential**: `references`, `cites` (cross-entity links)
- **Temporal**: `precedes`, `follows` (event ordering)

#### Relation Scope (decided)
- **Core relations** (global): `is-a`, `part-of`, `references`,
  `has-attribute` — usable across all domains
- **Domain-private relations**: Each engineering-role domain can
  define its own relations (e.g., `OBCDomain.has-charging-profile`,
  `SoftwareDomain.has-API`)
- **Decision**: Hybrid (core + private). Core for cross-domain queries,
  private for domain-specific knowledge.

### Attribute
A typed property of an entity. The mechanism for **attribute-value
queries** (e.g., "what is the P2 timing value?").

#### Attribute Granularity (decided)
- **Decision**: **Triple form** — each attribute is a separate
  `(subject, attribute, value)` triple
- Matches RDF/OWL conventions
- Easy to extend without schema changes
- Maps naturally to fact table storage

#### Attribute Scope (decided)
- **Hybrid** (mirrors relation scope)
- Core attributes global (`name`, `description`, `source`)
- Domain-specific attributes in domain subtrees

#### Attribute Value Types (decided)
- **Simple values**: string, number, boolean, date
- **Range values**: `{min, max, unit, tolerance}` (e.g., `50 ± 10 ms`)
- **Reference values**: value is itself an entity (e.g., `defined_in`
  pointing to a Standard entity). Used when an entity's *property*
  is another entity, not when two entities are connected by a
  semantic relationship.

### Fact vs Attribute vs Relation
- **Fact ⊃ Attribute** (decided): fact is the broader concept
- **Rule of thumb**:
  - Use **Relation** when two entities have a *semantic connection*
    (e.g., "A references B", "A is-a B", "A part-of B")
  - Use **Attribute (reference)** when an entity has a *property*
    whose value is another entity (e.g., "Parameter P2 is
    defined_in Standard ISO 14229-3")
- Examples:
  - "ISO 14229-3 references GB/T 18487.1" → **Relation** (`references`)
  - "P2_Server_Timing = 50 ms" → **Attribute** (number)
  - "P2_Server_Timing is defined in ISO 14229-3" → **Attribute**
    (reference: `defined_in` → ISO 14229-3 entity)
  - "Charge completed at 14:30" → **Fact** (neither attribute nor
    relation — it's an event, not a static property)
- Using "fact" as the upper-level concept gives more flexibility

### Migration Strategy (decided)
- **Parallel system, fully isolated from existing** — do NOT modify the
  current implementation
- Rationale: existing system is in production; new ontology is a
  fundamental redesign; risk of breaking working code is too high
- The new system will live alongside the existing one
- Will be evaluated against the existing system (golden questions,
  cross-validation) before any consolidation

### Test Discipline (decided)
**Every step must have thorough testing with explicit acceptance criteria.**

This is a non-negotiable rule. Each phase of work produces:
1. **Unit tests** — for every public function/method
2. **Integration tests** — for cross-component behavior
3. **Acceptance criteria** — explicit pass/fail thresholds defined
   *before* code is written
4. **Test report** — documented results before moving to next phase

#### Acceptance Criteria Template
Each phase must answer these 4 questions before starting:
1. **What** are we building? (scope, in/out)
2. **Why**? (which user need it serves)
3. **How** will we know it works? (specific measurable criteria)
4. **What's the test plan**? (which tests, which datasets, what
   thresholds)

#### Phase Gate
No phase proceeds to the next without:
- All tests passing
- Acceptance criteria met
- Test report committed to docs/ontology/test_reports/

### Relation
A typed connection between two entities. The mechanism that makes
"ontology-driven" queries possible — instead of fuzzy vector search,
we **traverse** relations.
- Examples: `references_standard`, `defines_term`, `has_constraint`
- Has direction and inverse
- May have cardinality constraints (1:1, 1:N, N:M)

### Query (in ontology context)
A structured request that uses class + attribute + relation traversal
to find an answer. Not vector search.
- Example: "P2 timing in ISO 14229-3" →
  `{class: ISO_14229_3, attribute: P2_timing_value}`

## Why Ontology

The purpose of the KB is to let users **find relevant knowledge fast**.
- **Traditional RAG** (semantic similarity) is imprecise
- **Ontology-driven queries** traverse the class hierarchy + relations to
  find exactly the right entity and attribute
- For subclass-attribute questions, ontology traversal is fundamentally
  more accurate than vector matching

## What an Entity Is NOT

- Not just a string key (needs class + relations)
- Not a "topic" or "theme" (those are navigation aids, not entities)
- Not a table or section (those are **information carriers**, not entities)
- Not a "process code" string (that's an identifier, not the entity)

## Known Limitations

These are deliberate boundaries of the current system. They are
not bugs — they are trade-offs made for the MVP.

### 1. Router is keyword-based, not semantic
- The router matches regex patterns (e.g., "P2 timing",
  "额定电压") rather than understanding natural language
- Synonyms are not handled: "标称电压" or "nominal voltage"
  will not match the "额定电压" pattern
- Future work: train a lightweight classifier or use LLM for
  semantic routing

### 2. Ontology data is hand-curated and small-scale
- Only 13 entities, 13 relations, 27 attributes in the demo
- Many real-world standards are not yet in the ontology
  (e.g., ISO 15118 has only a `title` attribute)
- Queries against missing entities return
  `entity_not_in_ontology` — this is correct behavior, but
  the user experience could be better (e.g., suggest similar
  entities or fall back to legacy)

### 3. Legacy system depends on LLM, may be slow or fail
- Legacy pipeline takes 3-30s per query (LLM round-trip)
- LLM API may be unavailable or rate-limited
- The bridge handles failures gracefully (returns None), but
  the user sees "(no context from legacy)"
- Use `use_legacy=False` to skip legacy for known-fast queries

### 4. No caching
- Every query re-runs the full ontology + legacy pipeline
- No deduplication of identical queries
- Production use should add a cache layer (e.g., Redis or
  SQLite-based) for repeated queries

### 5. Combined query does not distinguish "partial success"
- If ontology succeeds but legacy fails, the result is still
  marked as a success (ontology answer is present)
- There is no field indicating "legacy was attempted but failed"
  vs "legacy was skipped"
- Future work: add a `legacy_status` field to `CombinedAnswer`

## Open Questions

- How to balance manual vs auto class discovery?
- How to handle conflicting class assignments from different sources?
- How to evolve classes over time as domain knowledge grows?
