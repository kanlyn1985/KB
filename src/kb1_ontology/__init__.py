"""KB1 Ontology System.

A parallel, fully-isolated implementation of an ontology-driven
knowledge graph for KB1. See docs/ontology/CONTEXT.md for design
principles and docs/ontology/ROADMAP.md for delivery plan.

This package is intentionally NOT integrated with the existing
enterprise_agent_kb package. They share a database file only by
accident — the new system writes to a different SQLite file.
"""

__version__ = "0.1.0"
