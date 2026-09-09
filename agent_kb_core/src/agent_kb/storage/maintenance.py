from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .migrations import SchemaMigrator


@dataclass(frozen=True)
class PurgeReport:
    logical_document_id: str
    compiler_document_ids: list[str]
    evidence_ids: list[str]
    fact_ids: list[str]
    card_ids: list[str]
    object_ids: list[str]
    deleted_rows: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeMaintenance:
    """Transactional cleanup for a logical document and derived index surfaces."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def purge_document(self, logical_document_id: str) -> PurgeReport:
        versions = list(
            self.connection.execute(
                "SELECT compiler_document_id FROM document_versions WHERE logical_document_id = ?",
                (logical_document_id,),
            )
        )
        if not versions:
            raise KeyError(logical_document_id)
        compiler_ids = sorted({str(row["compiler_document_id"]) for row in versions})
        evidence_ids = sorted(
            str(row["evidence_id"])
            for row in self.connection.execute(
                f"SELECT evidence_id FROM evidence WHERE document_id IN ({_placeholders(compiler_ids)})",
                compiler_ids,
            )
        )
        fact_ids = self._ids_referencing("facts", "fact_id", "evidence_ids_json", evidence_ids)
        card_ids = self._ids_referencing("retrieval_cards", "card_id", "evidence_ids_json", evidence_ids)
        object_ids = self._objects_referencing(evidence_ids)

        deleted: dict[str, int] = {}
        with self.connection:
            deleted["graph_edges"] = self._delete_graph_edges(object_ids)
            deleted["embedding_vectors"] = self._delete_vectors(
                {
                    "evidence": evidence_ids,
                    "fact": fact_ids,
                    "card": card_ids,
                    "object": object_ids,
                }
            )
            deleted["search_documents"] = self._delete_search_documents(
                {
                    "evidence": evidence_ids,
                    "fact": fact_ids,
                    "card": card_ids,
                    "object": object_ids,
                }
            )
            deleted["search_fts"] = self._delete_fts(
                {
                    "evidence": evidence_ids,
                    "fact": fact_ids,
                    "card": card_ids,
                    "object": object_ids,
                }
            )
            deleted["facts"] = self._delete_ids("facts", "fact_id", fact_ids)
            deleted["retrieval_cards"] = self._delete_ids("retrieval_cards", "card_id", card_ids)
            deleted["object_projections"] = self._delete_ids("object_projections", "object_id", object_ids)
            deleted["evidence"] = self._delete_ids("evidence", "evidence_id", evidence_ids)
            deleted["document_versions"] = int(
                self.connection.execute(
                    "DELETE FROM document_versions WHERE logical_document_id = ?",
                    (logical_document_id,),
                ).rowcount
            )
            deleted["documents"] = int(
                self.connection.execute(
                    "DELETE FROM documents WHERE logical_document_id = ?",
                    (logical_document_id,),
                ).rowcount
            )
        return PurgeReport(
            logical_document_id=logical_document_id,
            compiler_document_ids=compiler_ids,
            evidence_ids=evidence_ids,
            fact_ids=fact_ids,
            card_ids=card_ids,
            object_ids=object_ids,
            deleted_rows=deleted,
        )

    def _ids_referencing(
        self,
        table: str,
        id_column: str,
        json_column: str,
        evidence_ids: list[str],
    ) -> list[str]:
        wanted = set(evidence_ids)
        values: list[str] = []
        for row in self.connection.execute(f"SELECT {id_column}, {json_column} FROM {table}"):
            raw = _loads(row[json_column], [])
            if any(str(item) in wanted for item in raw if item):
                values.append(str(row[id_column]))
        return sorted(set(values))

    def _objects_referencing(self, evidence_ids: list[str]) -> list[str]:
        wanted = set(evidence_ids)
        values: list[str] = []
        for row in self.connection.execute("SELECT object_id, evidence_refs_json FROM object_projections"):
            refs = _loads(row["evidence_refs_json"], [])
            if any(isinstance(ref, dict) and str(ref.get("evidence_id") or "") in wanted for ref in refs):
                values.append(str(row["object_id"]))
        return sorted(set(values))

    def _delete_graph_edges(self, object_ids: list[str]) -> int:
        if not object_ids:
            return 0
        placeholders = _placeholders(object_ids)
        cursor = self.connection.execute(
            f"DELETE FROM graph_edges WHERE source_object_id IN ({placeholders}) OR target_object_id IN ({placeholders})",
            [*object_ids, *object_ids],
        )
        return int(cursor.rowcount)

    def _delete_vectors(self, ids_by_type: dict[str, list[str]]) -> int:
        total = 0
        for source_type, source_ids in ids_by_type.items():
            if not source_ids:
                continue
            cursor = self.connection.execute(
                f"DELETE FROM embedding_vectors WHERE source_type = ? AND source_id IN ({_placeholders(source_ids)})",
                [source_type, *source_ids],
            )
            total += int(cursor.rowcount)
        return total

    def _delete_search_documents(self, ids_by_type: dict[str, list[str]]) -> int:
        total = 0
        for source_type, source_ids in ids_by_type.items():
            if not source_ids:
                continue
            cursor = self.connection.execute(
                f"DELETE FROM search_documents WHERE source_type = ? AND source_id IN ({_placeholders(source_ids)})",
                [source_type, *source_ids],
            )
            total += int(cursor.rowcount)
        return total

    def _delete_fts(self, ids_by_type: dict[str, list[str]]) -> int:
        try:
            self.connection.execute("SELECT 1 FROM search_fts LIMIT 1")
        except sqlite3.OperationalError:
            return 0
        total = 0
        for source_type, source_ids in ids_by_type.items():
            if not source_ids:
                continue
            cursor = self.connection.execute(
                f"DELETE FROM search_fts WHERE source_type = ? AND source_id IN ({_placeholders(source_ids)})",
                [source_type, *source_ids],
            )
            total += int(cursor.rowcount)
        return total

    def _delete_ids(self, table: str, id_column: str, values: list[str]) -> int:
        if not values:
            return 0
        cursor = self.connection.execute(
            f"DELETE FROM {table} WHERE {id_column} IN ({_placeholders(values)})",
            values,
        )
        return int(cursor.rowcount)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _placeholders(values: list[str]) -> str:
    if not values:
        raise ValueError("placeholders require at least one value")
    return ",".join("?" for _ in values)
