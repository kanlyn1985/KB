# -*- coding: utf-8 -*-
"""EvidenceSetManager（V03-REQ-001/002/003；成员 canonical 序；指纹锚）。"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

from agent_kb.evidence_core.synthesis.errors import (
    E_SET_DUPLICATE,
    E_SET_EMPTY,
    E_SET_MEMBER_NOT_FOUND,
    E_SET_TOO_LARGE,
    SynthesisError,
)
from agent_kb.evidence_core.synthesis.models import canonical_json

MAX_SET_SIZE = 32
SYNTHESIS_VERSION = "v03-synthesis-1.0"


def evidence_set_fingerprint(members: list[str], synthesis_version: str,
                             configuration_hash: str) -> str:
    """Set 指纹 = SHA256(CanonicalJSON({members sorted, version, cfg}))——顺序不敏感。"""
    payload = {
        "members": sorted(members),
        "synthesis_version": synthesis_version,
        "configuration_hash": configuration_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def configuration_hash(config: dict) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


@dataclass
class EvidenceSetRecord:
    set_id: str
    members: list
    set_fingerprint: str
    synthesis_version: str
    configuration_hash: str
    actor_id: str
    created_at: str | None = None


class EvidenceSetManager:
    """Set 创建/复用（[A,B]==[B,A]；重复成员拒绝；成员不可变）。"""

    def __init__(self, connection: sqlite3.Connection, max_set_size: int = MAX_SET_SIZE):
        self.connection = connection
        self.max_set_size = max_set_size

    def create(self, evidence_ids: list[str], actor_id: str,
               config: dict | None = None) -> EvidenceSetRecord:
        if not evidence_ids:
            raise SynthesisError(E_SET_EMPTY, "empty member list")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise SynthesisError(E_SET_DUPLICATE, "duplicate evidence_id in set")
        if len(evidence_ids) > self.max_set_size:
            raise SynthesisError(E_SET_TOO_LARGE, f">{self.max_set_size} members")
        for eid in evidence_ids:
            if not isinstance(eid, str) or not eid.strip():
                raise SynthesisError(E_SET_INVALID if False else E_SET_MEMBER_NOT_FOUND,
                                     f"invalid member id: {eid!r}")
            row = self.connection.execute(
                "SELECT 1 FROM akb_evidence WHERE evidence_id = ?", (eid,)).fetchone()
            if row is None:
                raise SynthesisError(E_SET_MEMBER_NOT_FOUND, eid)
        members = sorted(evidence_ids)                      # canonical 序（D-01）
        cfg_hash = configuration_hash(dict(config or {}))
        fp = evidence_set_fingerprint(members, SYNTHESIS_VERSION, cfg_hash)
        hit = self.connection.execute(
            "SELECT * FROM akb_evidence_sets WHERE set_fingerprint = ?", (fp,)).fetchone()
        if hit:                                             # Set 复用（幂等）
            return self._from_row(hit)
        set_id = f"set_{fp[:24]}"
        self.connection.execute(
            "INSERT INTO akb_evidence_sets (set_id, members_json, set_fingerprint,"
            " synthesis_version, configuration_hash, actor_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (set_id, canonical_json(members), fp, SYNTHESIS_VERSION, cfg_hash, actor_id))
        return EvidenceSetRecord(set_id=set_id, members=members, set_fingerprint=fp,
                                 synthesis_version=SYNTHESIS_VERSION,
                                 configuration_hash=cfg_hash, actor_id=actor_id)

    def get(self, set_id: str) -> EvidenceSetRecord:
        row = self.connection.execute(
            "SELECT * FROM akb_evidence_sets WHERE set_id = ?", (set_id,)).fetchone()
        if row is None:
            raise SynthesisError("E-V03-NOT-FOUND", set_id)
        return self._from_row(row)

    @staticmethod
    def _from_row(row) -> EvidenceSetRecord:
        import json as _j
        return EvidenceSetRecord(
            set_id=row["set_id"], members=_j.loads(row["members_json"]),
            set_fingerprint=row["set_fingerprint"],
            synthesis_version=row["synthesis_version"],
            configuration_hash=row["configuration_hash"],
            actor_id=row["actor_id"], created_at=row["created_at"])