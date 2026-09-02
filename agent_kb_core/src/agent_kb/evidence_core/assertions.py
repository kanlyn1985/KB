# -*- coding: utf-8 -*-
"""AssertionStore / AssertionValidator / Provenance（V0.1）。"""
from __future__ import annotations

import sqlite3

from agent_kb.evidence_core.ids import mint_id
from agent_kb.evidence_core.models import (
    KnowledgeAssertion,
    ProvenanceRecord,
)
from agent_kb.evidence_core.state_machine import (
    CREATE_STATUS,
    actor_kind_of,
    validate_creation,
    validate_transition,
)

POLICY_VERSION = "policy:v0.1"


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Provenance:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def record(self, *, actor_id: str, actor_kind: str, activity: str,
               inputs: list | None = None, metadata: dict | None = None) -> ProvenanceRecord:
        rec = ProvenanceRecord(
            provenance_id=mint_id("provenance"), actor_id=actor_id, actor_kind=actor_kind,
            activity=activity, policy_version=POLICY_VERSION, occurred_at=_now(),
            inputs=inputs or [], metadata=metadata or {})
        d = rec.to_row()
        self.connection.execute(
            "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
            " policy_version, occurred_at, inputs_json, metadata_json)"
            " VALUES (:provenance_id, :actor_id, :actor_kind, :activity,"
            " :policy_version, :occurred_at, :inputs_json, :metadata_json)", d)
        return rec

    def trace(self, assertion_id: str) -> dict:
        """Assertion → Evidence → Document → Source 全链（V0.1-PROV-001）。"""
        row = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        assertion = KnowledgeAssertion.from_row(row)
        chain: dict = {"assertion": assertion, "steps": []}
        # provenance 链（创建 + 历次迁移）：经 transitions 全量回溯（创建行
        # provenance_ref 会被后续迁移覆盖，故以 transitions 为准）+ 迁移前的创建行
        provs = self.connection.execute(
            "SELECT DISTINCT p.* FROM akb_provenance p WHERE p.provenance_id IN"
            " (SELECT provenance_ref FROM akb_assertion_transitions WHERE assertion_id = ?)"
            "    OR (p.inputs_json LIKE ? AND p.activity = 'create')"
            " ORDER BY p.occurred_at",
            (assertion_id, f'%"{assertion_id}"%')).fetchall()
        chain["provenance"] = [dict(p) for p in provs]
        # evidence → document → source（经 legacy resolver 双格式解析）
        from agent_kb.evidence_core.store import LegacyEvidenceResolver
        resolver = LegacyEvidenceResolver(self.connection)
        ev_chain = []
        for ref in assertion.evidence_refs:
            resolved = resolver.resolve(ref)
            if resolved is None:
                raise LookupError(f"E-CHAIN-BROKEN: evidence {ref} unresolvable")
            ev_chain.append(resolved)
        chain["evidence_chain"] = ev_chain
        if not ev_chain and assertion.status in ("validated", "asserted", "disputed"):
            raise LookupError("E-CHAIN-BROKEN: governed assertion without evidence chain")
        return chain


class AssertionValidator:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.provenance = Provenance(connection)

    def can_transition(self, assertion: KnowledgeAssertion, new_status: str,
                       actor_id: str) -> dict:
        violations = validate_transition(
            current_status=assertion.status, new_status=new_status,
            assertion_type=assertion.assertion_type, actor_id=actor_id,
            evidence_count=len(assertion.evidence_refs))
        return {"allowed": not violations, "violations": violations}

    def validate(self, *, assertion_id: str, actor_id: str = "system:validator") -> dict:
        """candidate → validated（evidence 校验含 hash 复核）。"""
        row = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        assertion = KnowledgeAssertion.from_row(row)
        if assertion.status != "candidate":
            raise ValueError(f"E-WRONG-STATUS: {assertion.status} (expected candidate)")
        # INV-001 evidence 校验 + hash 复核（经 resolver 双格式）
        if not assertion.evidence_refs:
            raise ValueError("E-INV-001-NO-EVIDENCE")
        from agent_kb.evidence_core.store import LegacyEvidenceResolver
        resolver = LegacyEvidenceResolver(self.connection)
        for ref in assertion.evidence_refs:
            resolved = resolver.resolve(ref)
            if resolved is None:
                raise LookupError(f"E-EVIDENCE-NOT-FOUND: {ref}")
            if resolved["kind"] == "canonical":
                canonical_hash = content_hash_of(resolved["row"])
                if canonical_hash and resolved["row"].get("content_hash") != canonical_hash:
                    raise ValueError(f"E-EVIDENCE-BROKEN: {ref} content hash mismatch")
        result = self.can_transition(assertion, "validated", actor_id)
        if not result["allowed"]:
            raise ValueError("; ".join(result["violations"]))
        store = AssertionStore(self.connection)
        store.transition(assertion_id=assertion_id, new_status="validated",
                         actor_id=actor_id, reason="evidence verification passed")
        return {"accepted": True, "violations": []}


def content_hash_of(row: dict) -> str:
    from agent_kb.evidence_core.ids import content_hash
    return content_hash(row.get("content", ""))


class AssertionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.provenance = Provenance(connection)

    # ---- create_candidate（INV-002 / State Machine §3：asserted 直接创建禁止）----
    def create_candidate(self, *, subject_ref: str, predicate_ref: str, object: dict,
                         assertion_type: str, ontology_scope: str, actor_id: str,
                         confidence: float | None = None, evidence_refs: list | None = None,
                         source_unit_refs: list | None = None, temporal_scope: dict | None = None,
                         derivation: dict | None = None) -> KnowledgeAssertion:
        violations = validate_creation(assertion_type, derivation)
        if violations:
            raise ValueError("; ".join(violations))
        kind = actor_kind_of(actor_id)
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("E-INVALID-CONFIDENCE")
        # evidence 引用必须已存在（双格式解析）
        from agent_kb.evidence_core.store import LegacyEvidenceResolver
        resolver = LegacyEvidenceResolver(self.connection)
        for ref in evidence_refs or []:
            if resolver.resolve(ref) is None:
                raise LookupError(f"E-EVIDENCE-NOT-FOUND: {ref}")
        # hypothesized 禁带证据直接 validated 的路径不存在——创建恒 candidate
        assertion_id = mint_id("assertion")
        prov = self.provenance.record(actor_id=actor_id, actor_kind=kind, activity="create",
                                      inputs=[assertion_id, *(evidence_refs or [])])
        assertion = KnowledgeAssertion(
            assertion_id=assertion_id, subject_ref=subject_ref,
            predicate_ref=predicate_ref, object=object, assertion_type=assertion_type,
            status=CREATE_STATUS, confidence=confidence,
            evidence_refs=list(evidence_refs or []),
            source_unit_refs=list(source_unit_refs or []),
            provenance_ref=prov.provenance_id, temporal_scope=temporal_scope,
            ontology_scope=ontology_scope, derivation=derivation)
        d = assertion.to_row()
        self.connection.execute(
            "INSERT INTO akb_assertions (assertion_id, subject_ref, predicate_ref,"
            " object_kind, object_value, object_datatype, object_unit, object_entity_ref,"
            " assertion_type, status, confidence, evidence_refs_json, source_unit_refs_json,"
            " provenance_ref, temporal_scope_json, ontology_scope, derivation_json, canonical_json)"
            " VALUES (:assertion_id, :subject_ref, :predicate_ref, :object_kind, :object_value,"
            " :object_datatype, :object_unit, :object_entity_ref, :assertion_type, :status,"
            " :confidence, :evidence_refs_json, :source_unit_refs_json, :provenance_ref,"
            " :temporal_scope_json, :ontology_scope, :derivation_json, :canonical_json)", d)
        return assertion

    # ---- get / list / list_conflicts ----
    def get(self, assertion_id: str) -> KnowledgeAssertion:
        row = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        return KnowledgeAssertion.from_row(row)

    def list(self, *, status: str | None = None, assertion_type: str | None = None,
             subject_ref: str | None = None, predicate_ref: str | None = None,
             limit: int = 50, offset: int = 0) -> list[KnowledgeAssertion]:
        if limit > 200:
            raise ValueError("E-INVALID-PAGE: limit<=200")
        clauses, params = [], []
        for col, val in (("status", status), ("assertion_type", assertion_type),
                         ("subject_ref", subject_ref), ("predicate_ref", predicate_ref)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params += [limit, offset]
        rows = self.connection.execute(
            f"SELECT * FROM akb_assertions {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params).fetchall()
        return [KnowledgeAssertion.from_row(r) for r in rows]

    def list_conflicts(self, subject_ref: str, predicate_ref: str) -> list[KnowledgeAssertion]:
        """同 S-P 多 object 分组（Golden G016 支撑）。"""
        rows = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE subject_ref = ? AND predicate_ref = ?"
            " AND status NOT IN ('rejected','deprecated') ORDER BY created_at",
            (subject_ref, predicate_ref)).fetchall()
        recs = [KnowledgeAssertion.from_row(r) for r in rows]
        by_obj: dict = {}
        for r in recs:
            key = (r.object.get("kind"), r.object.get("value"), r.object.get("entity_id"))
            by_obj.setdefault(key, []).append(r)
        if len(by_obj) <= 1:
            return []
        return recs

    # ---- transition（原子序列：permission→state→evidence→INSERT t→UPDATE→INSERT p→COMMIT）----
    def transition(self, *, assertion_id: str, new_status: str, actor_id: str,
                   reason: str) -> dict:
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        cur = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if cur is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        assertion = KnowledgeAssertion.from_row(cur)
        if assertion.status == new_status:
            return {"assertion_id": assertion_id, "previous_status": new_status,
                    "new_status": new_status, "transition_id": None, "idempotent_noop": True}

        check = validate_transition(
            current_status=assertion.status, new_status=new_status,
            assertion_type=assertion.assertion_type, actor_id=actor_id,
            evidence_count=len(assertion.evidence_refs))
        if check:
            raise ValueError("; ".join([*check, f"history:{self._history(assertion_id)}"]))

        kind = actor_kind_of(actor_id)
        # 原子序列（SAVEPOINT 兼容 autocommit 与隐式事务两种模式；任一步失败 ROLLBACK ALL）
        sp = f"sp_{assertion_id.replace('-', '_')}"
        self.connection.execute(f"SAVEPOINT {sp}")
        try:
            return self._transition_body(assertion, new_status, actor_id, reason, kind, sp)
        except Exception:
            self.connection.execute(f"ROLLBACK TO {sp}")
            self.connection.execute(f"RELEASE {sp}")
            raise

    def _transition_body(self, assertion, new_status, actor_id, reason, kind, sp):
        prov = self.provenance.record(actor_id=actor_id, actor_kind=kind,
                                      activity=f"transition:{assertion.status}->{new_status}",
                                      inputs=[assertion.assertion_id])
        trans_id = mint_id("transition")
        now = _now()
        # 原子三写：触发器 trg_akb_assertions_controlled_status 校验本事务 transitions 行
        self.connection.execute(
            "INSERT INTO akb_assertion_transitions (transition_id, assertion_id,"
            " previous_status, new_status, actor_id, reason, policy_version, provenance_ref)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (trans_id, assertion.assertion_id, assertion.status, new_status, actor_id, reason,
             POLICY_VERSION, prov.provenance_id))
        self.connection.execute(
            "UPDATE akb_assertions SET status = ?, updated_at = ?, provenance_ref = ?"
            " WHERE assertion_id = ?",
            (new_status, now, prov.provenance_id, assertion.assertion_id))
        self.connection.execute(f"RELEASE {sp}")
        return {"assertion_id": assertion.assertion_id, "previous_status": assertion.status,
                "new_status": new_status, "transition_id": trans_id, "idempotent_noop": False}

    def _history(self, assertion_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM akb_assertion_transitions WHERE assertion_id = ? ORDER BY created_at",
            (assertion_id,)).fetchall()
        return [dict(r) for r in rows]