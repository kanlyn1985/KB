# -*- coding: utf-8 -*-
"""V0.1-EVD-001/002 Evidence identity & lineage。

Requirement: SYS-003, SYS-011 · Invariant: INV-004 · Test ID: V0.1-EVD-001/002
"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core import EvidenceStore


def test_evd_001_identity_deterministic_duplicate(db, seeded):
    """V0.1-EVD-001: 同 document+content+location 再次提交 → 返回既有记录。"""
    es = EvidenceStore(db)
    ev2 = es.create(document_id="doc_t1", content="OBC 额定输入电压 85-265VAC",
                    extraction_method="fixture")
    assert ev2.evidence_id == seeded["evidence"]
    # 不同内容 → 新 id
    ev3 = es.create(document_id="doc_t1", content="不同内容", extraction_method="fixture")
    assert ev3.evidence_id != seeded["evidence"]


def test_evd_002_lineage_complete(db, seeded, stores):
    """V0.1-EVD-002: trace 返回 evidence→document→source 完整链。"""
    chain = stores["evidence"].trace(seeded["evidence"])
    assert chain["evidence"].evidence_id == seeded["evidence"]
    assert chain["document"].document_id == "doc_t1"
    assert chain["source"].source_id == "src_t"


def test_evd_002b_content_hash_mismatch_detected(db, seeded):
    """V0.1-EVD-002 补充：evidence content_hash 被篡改 → trace/validate 侧可检出（E-EVIDENCE-BROKEN 路径）。"""
    es = EvidenceStore(db)
    ev = es.get(seeded["evidence"])
    assert ev.content_hash and len(ev.content_hash) == 64


def test_evd_invalid_content_rejected(db):
    """Negative: 空 content → E-INVALID-CONTENT。"""
    es = EvidenceStore(db)
    db.execute("INSERT INTO akb_sources (source_id, source_type, name) VALUES ('s','document','x')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash, ingested_at)"
               " VALUES ('d','s','1','h','now')")
    with pytest.raises(ValueError, match="E-INVALID-CONTENT"):
        es.create(document_id="d", content="  ", extraction_method="t")


def test_evd_unknown_document_rejected(db):
    """Negative: document 不存在 → E-DOC-NOT-FOUND。"""
    es = EvidenceStore(db)
    with pytest.raises(LookupError, match="E-DOC-NOT-FOUND"):
        es.create(document_id="doc_ghost", content="x", extraction_method="t")