"""OntologyStore — SQLite storage for the ontology four-table model.

Provides CRUD operations for entities, attributes, relations, and evidence.
Uses context-manager connection pattern and auto-generates IDs.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from kb_ontology.storage.models import (
    Attribute,
    Entity,
    Evidence,
    Relation,
    deserialize_value,
    serialize_value,
)
from kb_ontology.storage.schema import SCHEMA_SQL


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class OntologyStore:
    """SQLite-backed ontology storage.

    Usage::

        with OntologyStore("ontology.db") as store:
            entity = store.upsert_entity("Parameter", "输出纹波", "obc_dcdc")
            store.upsert_attribute(entity.id, "value", 30, "number")
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Connection management ──

    def __enter__(self) -> OntologyStore:
        self._connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._connect()
        assert self._conn is not None
        return self._conn

    def _connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ════════════════════════════════════════════════════════════════════
    # Entity CRUD
    # ════════════════════════════════════════════════════════════════════

    def upsert_entity(
        self,
        class_name: str,
        canonical_name: str,
        domain: str = "default",
        status: str = "active",
    ) -> Entity:
        """Insert or update an entity. Returns the Entity."""
        entity_id = _gen_id("ent")
        now = _utc_now_iso()
        self.connection.execute(
            "INSERT INTO entities (id, class, canonical_name, domain, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, class_name, canonical_name, domain, status, now),
        )
        self.connection.commit()
        return Entity(
            id=entity_id,
            class_name=class_name,
            canonical_name=canonical_name,
            domain=domain,
            status=status,
            created_at=now,
        )

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self.connection.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return Entity.from_row(row) if row else None

    def find_entity_by_name(
        self,
        class_name: str,
        canonical_name: str,
        domain: str | None = None,
    ) -> list[Entity]:
        """Find entities by class + name, optionally filtered by domain."""
        if domain is not None:
            rows = self.connection.execute(
                "SELECT * FROM entities WHERE class = ? AND canonical_name = ? AND domain = ?",
                (class_name, canonical_name, domain),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM entities WHERE class = ? AND canonical_name = ?",
                (class_name, canonical_name),
            ).fetchall()
        return [Entity.from_row(r) for r in rows]

    def find_or_create_entity(
        self,
        class_name: str,
        canonical_name: str,
        domain: str = "default",
        status: str = "active",
    ) -> Entity:
        """Find an existing entity by class+name+domain, or create if not found."""
        existing = self.find_entity_by_name(class_name, canonical_name, domain)
        if existing:
            return existing[0]
        return self.upsert_entity(class_name, canonical_name, domain, status)

    def list_entities(
        self,
        class_name: str | None = None,
        domain: str | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        query = "SELECT * FROM entities WHERE 1=1"
        params: list[Any] = []
        if class_name:
            query += " AND class = ?"
            params.append(class_name)
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [Entity.from_row(r) for r in rows]

    def search_entities(
        self,
        name_query: str,
        *,
        class_name: str | None = None,
        domain: str | None = None,
        limit: int = 20,
    ) -> list[Entity]:
        """Case-insensitive substring match on ``canonical_name``.

        Exact (case-insensitive) matches are returned first, then partials.
        Empty ``name_query`` returns an empty list.
        """
        needle = (name_query or "").strip()
        if not needle:
            return []
        clauses = ["1=1"]
        params: list[Any] = []
        if class_name:
            clauses.append("class = ?")
            params.append(class_name)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = " AND ".join(clauses)

        # Prefer exact match (case-insensitive).
        exact_rows = self.connection.execute(
            f"SELECT * FROM entities WHERE {where} AND lower(canonical_name) = lower(?) "
            f"ORDER BY created_at DESC LIMIT ?",
            (*params, needle, limit),
        ).fetchall()
        exact = [Entity.from_row(r) for r in exact_rows]
        if len(exact) >= limit:
            return exact[:limit]

        seen = {e.id for e in exact}
        like_rows = self.connection.execute(
            f"SELECT * FROM entities WHERE {where} AND lower(canonical_name) LIKE lower(?) "
            f"ORDER BY length(canonical_name) ASC, created_at DESC LIMIT ?",
            (*params, f"%{needle}%", limit),
        ).fetchall()
        partials = [Entity.from_row(r) for r in like_rows if r["id"] not in seen]
        return (exact + partials)[:limit]

    def find_entities_by_attribute(
        self,
        *,
        attr_name: str | None = None,
        value_query: str,
        domain: str | None = None,
        limit: int = 50,
    ) -> list[tuple[Entity, Attribute]]:
        """Reverse lookup: attribute value substring → (entity, attribute) pairs."""
        needle = (value_query or "").strip()
        if not needle:
            return []
        sql = (
            "SELECT e.*, a.id AS a_id, a.entity_id AS a_entity_id, a.name AS a_name, "
            "a.value AS a_value, a.value_type AS a_value_type, "
            "a.confidence AS a_confidence, a.created_at AS a_created_at "
            "FROM attributes a JOIN entities e ON e.id = a.entity_id "
            "WHERE lower(COALESCE(a.value, '')) LIKE lower(?)"
        )
        params: list[Any] = [f"%{needle}%"]
        if attr_name:
            sql += " AND a.name = ?"
            params.append(attr_name)
        if domain:
            sql += " AND e.domain = ?"
            params.append(domain)
        sql += " ORDER BY a.confidence DESC, e.created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        results: list[tuple[Entity, Attribute]] = []
        for row in rows:
            entity = Entity(
                id=row["id"],
                class_name=row["class"],
                canonical_name=row["canonical_name"],
                domain=row["domain"],
                status=row["status"],
                created_at=row["created_at"],
            )
            attr = Attribute(
                id=row["a_id"],
                entity_id=row["a_entity_id"],
                name=row["a_name"],
                value=deserialize_value(row["a_value"], row["a_value_type"]),
                value_type=row["a_value_type"],
                confidence=row["a_confidence"] if row["a_confidence"] is not None else 1.0,
                created_at=row["a_created_at"],
            )
            results.append((entity, attr))
        return results

    # ════════════════════════════════════════════════════════════════════
    # Attribute CRUD
    # ════════════════════════════════════════════════════════════════════

    def upsert_attribute(
        self,
        entity_id: str,
        name: str,
        value: Any,
        value_type: str = "string",
        confidence: float = 1.0,
    ) -> Attribute:
        """Insert or update an attribute. Uses entity_id + name as unique key."""
        attr_id = _gen_id("attr")
        now = _utc_now_iso()
        stored_value = serialize_value(value, value_type)

        # Upsert: delete existing attribute with same entity_id + name, then insert
        self.connection.execute(
            "DELETE FROM attributes WHERE entity_id = ? AND name = ?",
            (entity_id, name),
        )
        self.connection.execute(
            "INSERT INTO attributes (id, entity_id, name, value, value_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (attr_id, entity_id, name, stored_value, value_type, confidence, now),
        )
        self.connection.commit()
        return Attribute(
            id=attr_id,
            entity_id=entity_id,
            name=name,
            value=deserialize_value(stored_value, value_type),
            value_type=value_type,
            confidence=confidence,
            created_at=now,
        )

    def get_attributes(self, entity_id: str) -> list[Attribute]:
        rows = self.connection.execute(
            "SELECT * FROM attributes WHERE entity_id = ? ORDER BY name",
            (entity_id,),
        ).fetchall()
        return [Attribute.from_row(r) for r in rows]

    def get_attribute(self, entity_id: str, name: str) -> Attribute | None:
        row = self.connection.execute(
            "SELECT * FROM attributes WHERE entity_id = ? AND name = ?",
            (entity_id, name),
        ).fetchone()
        return Attribute.from_row(row) if row else None

    # ════════════════════════════════════════════════════════════════════
    # Relation CRUD
    # ════════════════════════════════════════════════════════════════════

    def upsert_relation(
        self,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 1.0,
    ) -> Relation:
        """Insert or update a relation. Uses (source, type, target) as unique key."""
        rel_id = _gen_id("rel")
        now = _utc_now_iso()

        # Upsert: check existing triple
        existing = self.connection.execute(
            "SELECT id FROM relations WHERE source_id = ? AND relation_type = ? AND target_id = ?",
            (source_id, relation_type, target_id),
        ).fetchone()

        if existing:
            return self.get_relation(existing["id"])  # type: ignore[return-value]

        self.connection.execute(
            "INSERT INTO relations (id, source_id, relation_type, target_id, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rel_id, source_id, relation_type, target_id, confidence, now),
        )
        self.connection.commit()
        return Relation(
            id=rel_id,
            source_id=source_id,
            relation_type=relation_type,
            target_id=target_id,
            confidence=confidence,
            created_at=now,
        )

    def get_relation(self, relation_id: str) -> Relation | None:
        row = self.connection.execute(
            "SELECT * FROM relations WHERE id = ?", (relation_id,)
        ).fetchone()
        return Relation.from_row(row) if row else None

    def get_relations(
        self,
        source_id: str,
        relation_type: str | None = None,
    ) -> list[Relation]:
        """Get outgoing relations from an entity, optionally filtered by type."""
        if relation_type:
            rows = self.connection.execute(
                "SELECT * FROM relations WHERE source_id = ? AND relation_type = ? ORDER BY created_at",
                (source_id, relation_type),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM relations WHERE source_id = ? ORDER BY created_at",
                (source_id,),
            ).fetchall()
        return [Relation.from_row(r) for r in rows]

    def get_reverse_relations(
        self,
        target_id: str,
        relation_type: str | None = None,
    ) -> list[Relation]:
        """Get incoming relations to an entity, optionally filtered by type."""
        if relation_type:
            rows = self.connection.execute(
                "SELECT * FROM relations WHERE target_id = ? AND relation_type = ? ORDER BY created_at",
                (target_id, relation_type),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM relations WHERE target_id = ? ORDER BY created_at",
                (target_id,),
            ).fetchall()
        return [Relation.from_row(r) for r in rows]

    # ════════════════════════════════════════════════════════════════════
    # Evidence CRUD
    # ════════════════════════════════════════════════════════════════════

    def add_evidence(
        self,
        ref_type: str,
        ref_id: str,
        document_id: str,
        text_span: str = "",
        location: str = "",
        confidence: float = 1.0,
    ) -> Evidence:
        evd_id = _gen_id("evd")
        now = _utc_now_iso()
        self.connection.execute(
            "INSERT INTO evidence (id, ref_type, ref_id, document_id, text_span, location, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (evd_id, ref_type, ref_id, document_id, text_span, location, confidence, now),
        )
        self.connection.commit()
        return Evidence(
            id=evd_id,
            ref_type=ref_type,
            ref_id=ref_id,
            document_id=document_id,
            text_span=text_span,
            location=location,
            confidence=confidence,
            created_at=now,
        )

    def get_evidence(self, ref_type: str, ref_id: str) -> list[Evidence]:
        rows = self.connection.execute(
            "SELECT * FROM evidence WHERE ref_type = ? AND ref_id = ? ORDER BY created_at",
            (ref_type, ref_id),
        ).fetchall()
        return [Evidence.from_row(r) for r in rows]

    # ════════════════════════════════════════════════════════════════════
    # Graph traversal
    # ════════════════════════════════════════════════════════════════════

    def get_entity_tree(
        self,
        entity_id: str,
        direction: str = "down",
        relation_type: str = "part_of",
        max_depth: int = 10,
    ) -> dict[str, Any]:
        """Traverse the entity tree via part_of (or other) relations.

        Args:
            entity_id: Starting entity.
            direction: "down" (this → children via has_part/inverse) or
                       "up" (this → parents via part_of).
            relation_type: The relation to traverse (default part_of).
            max_depth: Safety limit on traversal depth.

        Returns:
            Nested dict: {entity_id, entity, children: [...]}
        """
        visited: set[str] = set()

        def _walk(eid: str, depth: int) -> dict[str, Any]:
            if depth > max_depth or eid in visited:
                return {"entity_id": eid, "entity": None, "children": [], "truncated": eid in visited}
            visited.add(eid)
            entity = self.get_entity(eid)
            if direction == "down":
                # Find entities that point to this one via part_of
                rels = self.get_reverse_relations(eid, relation_type)
            else:
                # Find entities this one points to via part_of
                rels = self.get_relations(eid, relation_type)
            children = [
                _walk(r.source_id if direction == "down" else r.target_id, depth + 1)
                for r in rels
            ]
            return {
                "entity_id": eid,
                "entity": entity.to_dict() if entity else None,
                "children": children,
                "truncated": False,
            }

        return _walk(entity_id, 0)

    # ════════════════════════════════════════════════════════════════════
    # Stats
    # ════════════════════════════════════════════════════════════════════

    def stats(self) -> dict[str, int]:
        """Return row counts for each table."""
        result: dict[str, int] = {}
        for table in ("entities", "attributes", "relations", "evidence"):
            row = self.connection.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
            result[table] = row["c"] if row else 0
        return result
