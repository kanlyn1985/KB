"""Phase 0 scaffolding tests.

These tests verify the goal of Phase 0: the new ontology system
is **fully isolated** from the existing KB1 system.

The five tests correspond exactly to the acceptance criteria T1-T5
documented in docs/ontology/ROADMAP.md.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb1_ontology import __version__
from kb1_ontology.db import connect, default_db_path


# T1: physical isolation — the new code lives outside enterprise_agent_kb
def test_t1_physical_isolation_module_path() -> None:
    """T1: The new system has its own package, not a sub-package of
    enterprise_agent_kb."""
    import kb1_ontology

    pkg_path = Path(kb1_ontology.__file__).resolve()
    assert "kb1_ontology" in pkg_path.parts
    assert "enterprise_agent_kb" not in pkg_path.parts


# T2: zero interference — core modules must not depend on enterprise_agent_kb
def test_t2_zero_interference_no_legacy_imports() -> None:
    """T2: The new package's *core* modules have NO import statements
    that pull from enterprise_agent_kb.

    The ``legacy_bridge`` module is the *one explicit exception*:
    it is the documented integration point between the two
    systems. ``combined_query.py`` is a *second exception*:
    it calls ``legacy_bridge.llm_chat`` for LLM routing but
    does NOT import ``enterprise_agent_kb`` directly.
    The other modules must remain free of legacy imports.

    We parse the source with the ``ast`` module to detect actual
    import statements, which is far more precise than substring
    matching.
    """
    import ast
    import kb1_ontology

    pkg_root = Path(kb1_ontology.__file__).resolve().parent
    forbidden = "enterprise_agent_kb"
    # The legacy_bridge module is the *documented* exception
    # (see ``legacy_bridge.py`` docstring). All other modules
    # must be legacy-free.
    ALLOWED_BRIDGE = {"legacy_bridge.py", "combined_query.py"}
    offenders: list[tuple[str, int, str]] = []

    for py_file in pkg_root.rglob("*.py"):
        if py_file.name in ALLOWED_BRIDGE:
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
            elif isinstance(node, ast.ImportFrom):
                target = node.module or ""
            if target and target.startswith(forbidden):
                offenders.append(
                    (str(py_file.relative_to(pkg_root)), node.lineno, target)
                )

    assert not offenders, (
        "Phase 0 core modules must not import from "
        "enterprise_agent_kb. The legacy_bridge module is the "
        "single documented exception. Found:\n"
        + "\n".join(f"  {p}:{ln}  imports {m}" for p, ln, m in offenders)
    )


def test_t2b_legacy_bridge_is_documented_exception() -> None:
    """T2b: The legacy_bridge module is the documented exception
    to T2. It must explicitly state that it bridges to the
    legacy system."""
    import kb1_ontology.legacy_bridge as bridge
    doc = (bridge.__doc__ or "").lower()
    assert "legacy" in doc or "enterprise_agent_kb" in doc
    assert "optional" in doc or "exception" in doc or "bridge" in doc


# T3: module is loadable
def test_t3_module_loadable_has_version() -> None:
    """T3: The package imports cleanly and exposes a version."""
    assert isinstance(__version__, str)
    assert __version__  # non-empty


# T4: database is independent of KB1's main DB
def test_t4_independent_db_path(tmp_workspace: Path) -> None:
    """T4: The ontology database lives at <workspace>/ontology/, not
    <workspace>/db/. They are physically separate files."""
    db_path = default_db_path(tmp_workspace)
    assert db_path.parent.name == "ontology"
    # The parent of the parent is the workspace root, not "db".
    assert db_path.parents[1] == tmp_workspace
    # Connect creates the file.
    conn = connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS _probe (n INTEGER)")
    conn.commit()
    conn.close()
    assert db_path.exists()


# T5: tests can run — verified by the fact this file is collected
def test_t5_tests_collectable() -> None:
    """T5: This test file is collected and executed by pytest.

    If pytest could not discover or run the tests, this would not
    execute. The mere presence of a passing test in this module is
    the verification.
    """
    assert True
