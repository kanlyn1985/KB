from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_kb.context.context_pack import ContextEvidence, ContextFact
from agent_kb.projection.models import EvidenceRef, ObjectProjection
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.cards import RetrievalCard
from agent_kb.retrieval.models import RetrievalCandidate, RetrievalResult


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@dataclass(frozen=True)
class PersistentIndexView:
    """Retrieval-compatible index reconstructed from SQLite."""

    object_projections: list[ObjectProjection]
    retrieval_cards: list[RetrievalCard]
    context_facts: list[ContextFact]
    context_evidence: list[ContextEvidence]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "object_projections": len(self.object_projections),
            "retrieval_cards": len(self.retrieval_cards),
            "context_facts": len(self.context_facts),
            "context_evidence": len(self.context_evidence),
        }


class SQLiteKnowledgeStore:
    """Dependency-free persistent store with an optional SQLite FTS5 surface.

    The relational tables are authoritative. FTS5 is a recall adapter: when FTS5
    is unavailable, search falls back to deterministic LIKE queries without
    changing the public contract.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._fts_enabled = False
        self.initialize()

    def __enter__(self) -> SQLiteKnowledgeStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    @property
    def fts_enabled(self) -> bool:
        return self._fts_enabled

    def initialize(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS object_projections (
                object_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                object_type TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                description TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS retrieval_cards (
                card_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                object_id TEXT,
                card_type TEXT NOT NULL,
                title TEXT NOT NULL,
                search_text TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                related_object_ids_json TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                answer_shapes_json TEXT NOT NULL,
                structured_payload_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                fact_type TEXT NOT NULL,
                subject TEXT,
                predicate TEXT NOT NULL,
                object_value_json TEXT NOT NULL,
                qualifiers_json TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                document_id TEXT,
                page_no INTEGER,
                snippet TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_documents (
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                object_id TEXT,
                text TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (source_type, source_id)
            );
            CREATE TABLE IF NOT EXISTS retrieval_runs (
                run_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                query_frame_json TEXT NOT NULL,
                retrieval_result_json TEXT NOT NULL,
                evidence_judgement_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES retrieval_runs(run_id)
            );
            CREATE INDEX IF NOT EXISTS idx_cards_object_id ON retrieval_cards(object_id);
            CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
            CREATE INDEX IF NOT EXISTS idx_evidence_document_id ON evidence(document_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_run_id ON feedback(run_id);
            """
        )
        try:
            self.connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                    source_type UNINDEXED,
                    source_id UNINDEXED,
                    object_id UNINDEXED,
                    text,
                    payload_json UNINDEXED,
                    tokenize='unicode61'
                )
                """
            )
            self._fts_enabled = True
        except sqlite3.OperationalError:
            self._fts_enabled = False
        self.connection.commit()

    def upsert_index(self, index: Any) -> dict[str, int]:
        now = _utc_now_iso()
        with self.connection:
            for item in index.object_projections:
                self.connection.execute(
                    """
                    INSERT INTO object_projections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(object_id) DO UPDATE SET
                        domain=excluded.domain,
                        object_type=excluded.object_type,
                        canonical_name=excluded.canonical_name,
                        description=excluded.description,
                        aliases_json=excluded.aliases_json,
                        properties_json=excluded.properties_json,
                        evidence_refs_json=excluded.evidence_refs_json,
                        confidence=excluded.confidence,
                        status=excluded.status,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.object_id,
                        item.domain,
                        item.object_type,
                        item.canonical_name,
                        item.description,
                        _json(item.aliases),
                        _json(item.properties),
                        _json([ref.to_dict() for ref in item.evidence_refs]),
                        item.confidence,
                        item.status,
                        now,
                    ),
                )
                self._replace_search_document(
                    source_type="object",
                    source_id=item.object_id,
                    object_id=item.object_id,
                    text=" ".join([item.object_id, item.canonical_name, item.description, *item.aliases]),
                    payload={"object_id": item.object_id, "object_type": item.object_type},
                )

            for item in index.retrieval_cards:
                self.connection.execute(
                    """
                    INSERT INTO retrieval_cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(card_id) DO UPDATE SET
                        domain=excluded.domain,
                        object_id=excluded.object_id,
                        card_type=excluded.card_type,
                        title=excluded.title,
                        search_text=excluded.search_text,
                        aliases_json=excluded.aliases_json,
                        related_object_ids_json=excluded.related_object_ids_json,
                        evidence_ids_json=excluded.evidence_ids_json,
                        answer_shapes_json=excluded.answer_shapes_json,
                        structured_payload_json=excluded.structured_payload_json,
                        confidence=excluded.confidence,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.card_id,
                        item.domain,
                        item.object_id,
                        item.card_type,
                        item.title,
                        item.search_text,
                        _json(item.aliases),
                        _json(item.related_object_ids),
                        _json(item.evidence_ids),
                        _json(item.answer_shapes),
                        _json(item.structured_payload),
                        item.confidence,
                        now,
                    ),
                )
                self._replace_search_document(
                    source_type="card",
                    source_id=item.card_id,
                    object_id=item.object_id,
                    text=" ".join([item.title, item.search_text, *item.aliases, *item.answer_shapes]),
                    payload={
                        "object_id": item.object_id,
                        "evidence_ids": item.evidence_ids,
                        "answer_shapes": item.answer_shapes,
                    },
                )

            for item in index.context_facts:
                self.connection.execute(
                    """
                    INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fact_id) DO UPDATE SET
                        fact_type=excluded.fact_type,
                        subject=excluded.subject,
                        predicate=excluded.predicate,
                        object_value_json=excluded.object_value_json,
                        qualifiers_json=excluded.qualifiers_json,
                        evidence_ids_json=excluded.evidence_ids_json,
                        confidence=excluded.confidence,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.fact_id,
                        item.fact_type,
                        item.subject,
                        item.predicate,
                        _json(item.object_value),
                        _json(item.qualifiers),
                        _json(item.evidence_ids),
                        item.confidence,
                        now,
                    ),
                )
                self._replace_search_document(
                    source_type="fact",
                    source_id=item.fact_id,
                    object_id=item.subject,
                    text=" ".join(
                        [
                            item.subject or "",
                            item.fact_type,
                            item.predicate,
                            str(item.object_value),
                            " ".join(f"{key} {value}" for key, value in item.qualifiers.items()),
                        ]
                    ),
                    payload={
                        "subject": item.subject,
                        "fact_type": item.fact_type,
                        "evidence_ids": item.evidence_ids,
                    },
                )

            for item in index.context_evidence:
                self.connection.execute(
                    """
                    INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(evidence_id) DO UPDATE SET
                        document_id=excluded.document_id,
                        page_no=excluded.page_no,
                        snippet=excluded.snippet,
                        confidence=excluded.confidence,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.evidence_id,
                        item.document_id,
                        item.page_no,
                        item.snippet,
                        item.confidence,
                        now,
                    ),
                )
                self._replace_search_document(
                    source_type="evidence",
                    source_id=item.evidence_id,
                    object_id=None,
                    text=item.snippet,
                    payload={"document_id": item.document_id, "page_no": item.page_no},
                )
        return self.summary()

    def load_index_view(self) -> PersistentIndexView:
        objects = [self._object_from_row(row) for row in self.connection.execute("SELECT * FROM object_projections")]
        cards = [self._card_from_row(row) for row in self.connection.execute("SELECT * FROM retrieval_cards")]
        facts = [self._fact_from_row(row) for row in self.connection.execute("SELECT * FROM facts")]
        evidence = [self._evidence_from_row(row) for row in self.connection.execute("SELECT * FROM evidence")]
        return PersistentIndexView(
            object_projections=objects,
            retrieval_cards=cards,
            context_facts=facts,
            context_evidence=evidence,
        )

    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]:
        terms = self._query_terms(query_frame)
        if not terms:
            return []
        rows: list[sqlite3.Row]
        if self._fts_enabled:
            try:
                expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:12])
                rows = list(
                    self.connection.execute(
                        """
                        SELECT source_type, source_id, object_id, text, payload_json, bm25(search_fts) AS rank_score
                        FROM search_fts
                        WHERE search_fts MATCH ?
                        ORDER BY rank_score
                        LIMIT ?
                        """,
                        (expression, max(1, limit)),
                    )
                )
                return [self._candidate_from_search_row(row, query_frame, channel="sqlite_fts") for row in rows]
            except sqlite3.OperationalError:
                pass
        return self._search_like(query_frame, terms, limit=max(1, limit))

    def record_retrieval(
        self,
        *,
        query_frame: QueryFrame,
        retrieval_result: RetrievalResult,
        evidence_judgement: dict[str, Any] | None = None,
    ) -> str:
        run_id = f"run_{uuid4().hex}"
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO retrieval_runs(
                    run_id, query, query_frame_json, retrieval_result_json,
                    evidence_judgement_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    query_frame.original_query,
                    _json(query_frame.to_dict()),
                    _json(retrieval_result.to_dict()),
                    _json(evidence_judgement) if evidence_judgement is not None else None,
                    _utc_now_iso(),
                ),
            )
        return run_id

    def add_feedback(
        self,
        *,
        run_id: str,
        rating: int,
        comment: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self.connection.execute("SELECT 1 FROM retrieval_runs WHERE run_id = ?", (run_id,)).fetchone():
            raise ValueError(f"unknown retrieval run: {run_id}")
        feedback_id = f"fb_{uuid4().hex}"
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO feedback(feedback_id, run_id, rating, comment, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, run_id, int(rating), comment, _json(metadata or {}), _utc_now_iso()),
            )
        return feedback_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM retrieval_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "query": row["query"],
            "query_frame": _loads(row["query_frame_json"], {}),
            "retrieval_result": _loads(row["retrieval_result_json"], {}),
            "evidence_judgement": _loads(row["evidence_judgement_json"], None),
            "created_at": row["created_at"],
        }

    def summary(self) -> dict[str, int]:
        tables = ["object_projections", "retrieval_cards", "facts", "evidence", "retrieval_runs", "feedback"]
        return {table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}

    def close(self) -> None:
        self.connection.close()

    def _replace_search_document(
        self,
        *,
        source_type: str,
        source_id: str,
        object_id: str | None,
        text: str,
        payload: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO search_documents(source_type, source_id, object_id, text, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id) DO UPDATE SET
                object_id=excluded.object_id,
                text=excluded.text,
                payload_json=excluded.payload_json
            """,
            (source_type, source_id, object_id, text, _json(payload)),
        )
        if self._fts_enabled:
            self.connection.execute(
                "DELETE FROM search_fts WHERE source_type = ? AND source_id = ?",
                (source_type, source_id),
            )
            self.connection.execute(
                "INSERT INTO search_fts(source_type, source_id, object_id, text, payload_json) VALUES (?, ?, ?, ?, ?)",
                (source_type, source_id, object_id, text, _json(payload)),
            )

    def _search_like(self, frame: QueryFrame, terms: list[str], *, limit: int) -> list[RetrievalCandidate]:
        clauses = " OR ".join("LOWER(text) LIKE ?" for _ in terms[:12])
        params = [f"%{term.lower()}%" for term in terms[:12]]
        rows = list(
            self.connection.execute(
                f"SELECT source_type, source_id, object_id, text, payload_json, 0.0 AS rank_score "
                f"FROM search_documents WHERE {clauses} LIMIT ?",
                (*params, limit),
            )
        )
        return [self._candidate_from_search_row(row, frame, channel="sqlite_like") for row in rows]

    def _candidate_from_search_row(
        self,
        row: sqlite3.Row,
        frame: QueryFrame,
        *,
        channel: str,
    ) -> RetrievalCandidate:
        payload = dict(_loads(row["payload_json"], {}))
        if row["object_id"] and not payload.get("object_id") and not payload.get("subject"):
            payload["object_id"] = row["object_id"]
        rank_score = float(row["rank_score"] or 0.0)
        score = 1.0 / (1.0 + abs(rank_score)) if channel == "sqlite_fts" else 0.65
        target_ids = {target.object_id for target in frame.target_objects}
        linked_id = str(payload.get("object_id") or payload.get("subject") or "")
        reasons = [channel]
        if linked_id and linked_id in target_ids:
            score += 1.5
            reasons.append("persistent_target_match")
        if payload.get("fact_type") in set(frame.preferred_fact_types):
            score += 0.75
            reasons.append("persistent_fact_shape_match")
        source_type = str(row["source_type"])
        return RetrievalCandidate(
            candidate_id=f"{source_type}:{row['source_id']}",
            source_type=source_type,
            source_id=str(row["source_id"]),
            channel=channel,
            score=score,
            matched_terms=[],
            reasons=reasons,
            payload=payload,
        )

    @staticmethod
    def _query_terms(frame: QueryFrame) -> list[str]:
        values = [
            frame.normalized_query,
            frame.target_topic,
            *frame.must_terms,
            *frame.aliases,
            *frame.should_terms,
            *(target.object_id for target in frame.target_objects),
            *(target.canonical_name for target in frame.target_objects),
            *(target.matched_text for target in frame.target_objects),
        ]
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result[:32]

    @staticmethod
    def _object_from_row(row: sqlite3.Row) -> ObjectProjection:
        refs = [EvidenceRef(**item) for item in _loads(row["evidence_refs_json"], []) if isinstance(item, dict)]
        return ObjectProjection(
            object_id=row["object_id"],
            domain=row["domain"],
            object_type=row["object_type"],
            canonical_name=row["canonical_name"],
            description=row["description"],
            aliases=list(_loads(row["aliases_json"], [])),
            properties=dict(_loads(row["properties_json"], {})),
            evidence_refs=refs,
            confidence=float(row["confidence"]),
            status=row["status"],
        )

    @staticmethod
    def _card_from_row(row: sqlite3.Row) -> RetrievalCard:
        return RetrievalCard(
            card_id=row["card_id"],
            domain=row["domain"],
            object_id=row["object_id"],
            card_type=row["card_type"],
            title=row["title"],
            search_text=row["search_text"],
            aliases=list(_loads(row["aliases_json"], [])),
            related_object_ids=list(_loads(row["related_object_ids_json"], [])),
            evidence_ids=list(_loads(row["evidence_ids_json"], [])),
            answer_shapes=list(_loads(row["answer_shapes_json"], [])),
            structured_payload=dict(_loads(row["structured_payload_json"], {})),
            confidence=float(row["confidence"]),
        )

    @staticmethod
    def _fact_from_row(row: sqlite3.Row) -> ContextFact:
        return ContextFact(
            fact_id=row["fact_id"],
            fact_type=row["fact_type"],
            subject=row["subject"],
            predicate=row["predicate"],
            object_value=_loads(row["object_value_json"], None),
            qualifiers=dict(_loads(row["qualifiers_json"], {})),
            evidence_ids=list(_loads(row["evidence_ids_json"], [])),
            confidence=float(row["confidence"]),
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> ContextEvidence:
        return ContextEvidence(
            evidence_id=row["evidence_id"],
            document_id=row["document_id"],
            page_no=row["page_no"],
            snippet=row["snippet"],
            confidence=float(row["confidence"]),
        )
