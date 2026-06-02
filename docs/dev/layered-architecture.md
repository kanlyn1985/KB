# KB1 Layered Architecture

The KB1 codebase is organized into three layers under `src/enterprise_agent_kb/`:

| Layer | Path | Responsibility |
|---|---|---|
| **Domain** | `domain/` | Pure types, protocols, exceptions. Zero external dependencies. |
| **Service** | `service/` | Business logic / orchestration. Coordinates domain logic. |
| **Infrastructure** | `infrastructure/` | Adapters to external systems (DB, LLM, file system, HTTP). |

## Dependency Direction

The strict DDD dependency direction is:

```
infrastructure → service → domain
infrastructure → domain      (implements domain interfaces)
service → infrastructure     (via dependency injection)
```

Concretely:

- **`domain/`** must NOT import from `service/` or `infrastructure/`.
- **`service/`** may import from `domain/` and `infrastructure/` (only at composition root).
- **`infrastructure/`** may import from `domain/` (it implements `Protocol`s defined there).

## Common Misconceptions

A naive static check might flag `infrastructure/llm_client.py` importing `from ..domain.llm import ILLMClient` as a "reverse dependency". This is **not** a violation — it is the canonical DDD pattern:

- `domain/llm.py` defines the `ILLMClient` `Protocol` (the **interface**).
- `infrastructure/llm_client.py` defines `class LLMClient(ILLMClient)` (the **implementation**).
- The implementation depends on the interface, which is the correct direction.

The correct way to detect *real* DDD violations is:

1. `domain/` should not import from `service/` or `infrastructure/`.
2. `service/` should not import from `infrastructure/` **except** at the composition root (a `__init__` method or a `bootstrap` function).
3. `infrastructure/` should not import from `service/`.

## Where the Layers Live Today

```
src/enterprise_agent_kb/
├── domain/                  # Pure types
│   ├── eval.py              # EvalRun, GoldenCase, RetrievalRun, FailureRecord, ...
│   ├── llm.py               # Provider, Message, LLMResponse, ILLMClient Protocol
│   └── __init__.py
├── infrastructure/          # Adapters
│   ├── eval_repository.py   # EvalRepository, GoldenCaseRepository
│   ├── llm_client.py        # LLMClient(ILLMClient)
│   └── __init__.py
├── service/                 # Orchestration
│   ├── eval_service.py      # EvalService (uses EvalRepository via __init__ injection)
│   └── __init__.py
├── (root .py files)         # Top-level pipeline / entry points
└── (sub-packages)           # Feature packages (closed_loop_store, generated_tests, ...)
```

The top-level `.py` files and feature sub-packages are not part of the strict domain/service/infrastructure layering — they are composition roots and feature modules that pull together the layered primitives.

## Validating the Layers

A simple AST check can verify the dependency rules:

```python
import ast
from pathlib import Path

src = Path("src/enterprise_agent_kb")

# Rule 1: domain/ → no service/, no infrastructure/
for py in (src / "domain").rglob("*.py"):
    for node in ast.walk(ast.parse(py.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "service" in node.module or "infrastructure" in node.module:
                raise AssertionError(f"VIOLATION: {py} imports {node.module}")

# Rule 2: infrastructure/ → no service/
for py in (src / "infrastructure").rglob("*.py"):
    for node in ast.walk(ast.parse(py.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "service" in node.module:
                raise AssertionError(f"VIOLATION: {py} imports {node.module}")
```

Last verified: 2026-06-02 — no violations.
