# -*- coding: utf-8 -*-
"""EvidenceStore（V0.1）：akb_evidence 持久化 + legacy resolver（compatibility adapter）。"""
from __future__ import annotations

import sqlite3

from agent_kb.evidence_core.ids import content_hash, mint_id
from agent_kb.evidence_core.models import Evidence


class EvidenceStore:
    """akb_evidence 的唯一写入口。幂等：内容寻址去重（V0.1-EVD-001）。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create(
        self,
        *,
        document_id: str,
        content: str,
        extraction_method: str,
        actor_id: str = "system:compiler",
        evidence_type: str = "text",
        location: dict | None = None,
        observed_at: str | None = None,
        confidence: float = 1.0,
        metadata: dict | None = None,
    ) -> Evidence:
        # precondition 校验（Interface Behavior §1.1）
        if not content or not content.strip():
            raise ValueError("E-INVALID-CONTENT: content must be non-empty")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("E-INVALID-CONFIDENCE: confidence must be within [0, 1]")
        loc = location or {}
        if not self.connection.execute(
            "SELECT 1 FROM akb_documents WHERE document_id = ?", (document_id,)
        ).fetchone():
            raise LookupError(f"E-DOC-NOT-FOUND: {document_id}")

        chash = content_hash(content)
        row = self.connection.execute(
            "SELECT evidence_id FROM akb_evidence "
            "WHERE document_id = ? AND content_hash = ? AND location_start IS ? AND location_end IS ?",
            (document_id, chash, loc.get("start"), loc.get("end")),
        ).fetchone()
        if row:  # deterministic duplicate → return existing（不产生第二条）
            return self.get(row["evidence_id"])

        ev = Evidence(
            evidence_id=mint_id("evidence"), document_id=document_id, content=content,
            evidence_type=evidence_type, location=loc, observed_at=observed_at,
            extraction_method=extraction_method, confidence=confidence,
            metadata=metadata or {}, content_hash=chash)
        d = ev.to_row()
        self.connection.execute(
            "INSERT INTO akb_evidence (evidence_id, document_id, location_page, location_section,"
            " location_start, location_end, content, evidence_type, observed_at,"
            " extraction_method, confidence, metadata_json, content_hash)"
            " VALUES (:evidence_id, :document_id, :location_page, :location_section,"
            " :location_start, :location_end, :content, :evidence_type, :observed_at,"
            " :extraction_method, :confidence, :metadata_json, :content_hash)",
            d)
        return ev

    def get(self, evidence_id: str) -> Evidence:
        row = self.connection.execute(
            "SELECT * FROM akb_evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {evidence_id}")
        return Evidence.from_row(row)

    def trace(self, evidence_id: str) -> dict:
        """evidence → document → source 全链（V0.1-EVD-002）。"""
        ev = self.get(evidence_id)
        doc_row = self.connection.execute(
            "SELECT * FROM akb_documents WHERE document_id = ?", (ev.document_id,)).fetchone()
        if doc_row is None:
            raise LookupError("E-CHAIN-BROKEN: document missing")
        src_row = self.connection.execute(
            "SELECT * FROM akb_sources WHERE source_id = ?", (doc_row["source_id"],)).fetchone()
        if src_row is None:
            raise LookupError("E-CHAIN-BROKEN: source missing")
        from agent_kb.evidence_core.models import Document, Source
        return {
            "evidence": ev,
            "document": Document.from_row(doc_row),
            "source": Source.from_row(src_row),
        }


class LegacyEvidenceResolver:
    """Compatibility adapter（MIGRATION_PLAN §3）：旧 evd:node:* 引用解析。

    边界：不产生 akb_evidence 行、不修改 legacy 数据、不属 Canonical Data Model；
    V0.2 搬运完成后退役。
    """

    LEGACY_PREFIX = "evd:node:"

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def resolve(self, ref: str) -> dict | None:
        """返回 {'kind': ..., 'row': ...}；无法解析返回 None（调用方决定报错）。"""
        if ref.startswith("evd_"):
            row = self.connection.execute(
                "SELECT * FROM akb_evidence WHERE evidence_id = ?", (ref,)).fetchone()
            return {"kind": "canonical", "row": dict(row)} if row else None
        if ref.startswith(self.LEGACY_PREFIX):
            row = self.connection.execute(
                "SELECT evidence_id, document_id, snippet FROM evidence WHERE evidence_id = ?",
                (ref,)).fetchone()
            return {"kind": "legacy", "row": dict(row)} if row else None
        return None

    @staticmethod
    def is_legacy(ref: str) -> bool:
        return ref.startswith(LegacyEvidenceResolver.LEGACY_PREFIX)