# -*- coding: utf-8 -*-
"""SynthesisEngine 编排（V03-REQ-012/013/015/017/018/019；唯一边界 create_candidate）。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from agent_kb.evidence_core.assertions import AssertionStore, Provenance
from agent_kb.evidence_core.compilation.compiler import configuration_hash as cfg_hash
from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector, MAX_CONFLICTS
from agent_kb.evidence_core.synthesis.errors import (
    E_ALIGN_UNIT_MISSING,
    E_SYNTH_DUPLICATE,
    E_SYNTH_PROVENANCE_MISSING,
    IdempotentSynthesisHit,
    SynthesisError,
)
from agent_kb.evidence_core.synthesis.evidence_set import (
    SYNTHESIS_VERSION,
    EvidenceSetManager,
)
from agent_kb.evidence_core.synthesis.models import (
    SynthesisRunRecord,
    canonical_json,
)
from agent_kb.evidence_core.synthesis.weights import SourceWeightResolver


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def synthesis_fingerprint(set_fingerprint: str, synthesis_version: str,
                          configuration_hash: str) -> str:
    payload = {"set_fingerprint": set_fingerprint,
               "synthesis_version": synthesis_version,
               "configuration_hash": configuration_hash}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _compatibility(alignment, conflicts: ConflictSet) -> dict:
    """五级规则表（按序首中；全记录）。"""
    per_member: dict[str, str] = {}
    conflict_members = {eid for c in conflicts.conflicts for eid in c.source_evidence_ids}
    cluster_members = {m["evidence_id"] for cl in alignment.entity_clusters
                       for m in cl.members}
    for eid in sorted({m["evidence_id"] for cl in alignment.entity_clusters
                       for m in cl.members} | set(alignment.temporal_alignment.get(
                           "per_evidence", {})) if alignment.temporal_alignment else set()):
        if alignment.temporal_alignment.get("per_evidence", {}).get(eid) in (None, "missing") \
                and eid not in cluster_members:
            per_member[eid] = "INVALID"
        elif eid in conflict_members:
            per_member[eid] = "CONFLICTING"
        elif eid in cluster_members:
            per_member[eid] = "COMPATIBLE"
        else:
            per_member[eid] = "INCOMPARABLE"
    alignment.rule_audit.append({"rule_id": "COMPAT-001",
                                 "inputs": {"conflicts": len(conflicts.conflicts)},
                                 "result": per_member})
    return per_member


class SynthesisEngine:
    POLICY = "policy:v0.3"

    def __init__(self, connection: sqlite3.Connection, *, provider_id: str = "builtin-synthesis",
                 synthesis_version: str = SYNTHESIS_VERSION, domain_pack=None,
                 max_conflicts: int = MAX_CONFLICTS):
        self.connection = connection
        self.provider_id = provider_id
        self.synthesis_version = synthesis_version
        self.set_manager = EvidenceSetManager(connection)
        self.alignment_engine = EvidenceAlignmentEngine(domain_pack)
        self.detector = ConflictDetector(max_conflicts, provider_id=provider_id)
        self.weight_resolver = SourceWeightResolver()
        self.builder = AssertionStore(connection)
        self.provenance = Provenance(connection)

    # ---- provenance 查询面（REQ-019）----
    def describe_synthesis_run(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM akb_synthesis_runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def trace_candidate_synthesis(self, assertion_id: str) -> dict:
        a = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id = ?", (assertion_id,)).fetchone()
        if a is None:
            raise LookupError(f"E-V03-NOT-FOUND: {assertion_id}")
        # V0.3 链：assertion.derivation_json.synthesis_run_id → run → set → members
        derivation = json.loads(a["derivation_json"] or "{}")
        run_id = derivation.get("synthesis_run_id")
        if not run_id:  # 兜底：按 evidence_refs 全匹配反查 run
            refs = json.loads(a["evidence_refs_json"] or "[]")
            for r in self.connection.execute(
                    "SELECT run_id FROM akb_synthesis_runs WHERE members_json = ?",
                    (canonical_json(sorted(refs)),)):
                run_id = r["run_id"]
                break
        run = self.describe_synthesis_run(run_id) if run_id else None
        members = json.loads(run["members_json"]) if run else []
        units = []
        documents = []
        for eid in members:
            for u in self.connection.execute(
                    "SELECT * FROM akb_semantic_units WHERE evidence_id = ?", (eid,)):
                units.append(dict(u))
            e = self.connection.execute(
                "SELECT * FROM akb_evidence WHERE evidence_id = ?", (eid,)).fetchone()
            if e is not None:
                d = self.connection.execute(
                    "SELECT * FROM akb_documents WHERE document_id = ?",
                    (e["document_id"],)).fetchone()
                if d is not None:
                    documents.append(dict(d))
        return {"assertion": dict(a), "run": run, "set": self.set_manager.get(run["set_id"])
                if run else None, "members": members, "units": units, "documents": documents}

    # ---- 主入口 ----
    def synthesize(self, evidence_ids: list[str], actor_id: str,
                   config: dict | None = None) -> dict:
        cfg = dict(config or {})
        cfg.update({"synthesis_version": self.synthesis_version,
                    "provider": self.provider_id,
                    "max_conflicts": self.detector.max_conflicts})
        cfg_h = cfg_hash(cfg)
        eset = self.set_manager.create(evidence_ids, actor_id, config)
        fp = synthesis_fingerprint(eset.set_fingerprint, self.synthesis_version, cfg_h)
        hit = self.connection.execute(
            "SELECT * FROM akb_synthesis_runs WHERE fingerprint = ?", (fp,)).fetchone()
        if hit and hit["status"] == "completed":
            return {"run": self._run_from_row(hit),
                    "assertions": self._assertions_for_run(hit["run_id"]),
                    "warnings": json.loads(hit["warnings_json"] or "[]"),
                    "fingerprint": fp, "idempotent_hit": True}

        prov = self.provenance.record(actor_id=actor_id,
                                      actor_kind=actor_id.split(":")[0]
                                      if ":" in actor_id else "system",
                                      activity="synthesize", inputs=[fp])
        if prov is None or not prov.provenance_id:
            raise SynthesisError(E_SYNTH_PROVENANCE_MISSING)
        run = SynthesisRunRecord(
            run_id=f"syn_{prov.provenance_id[5:]}", set_id=eset.set_id,
            members=eset.members, synthesis_version=self.synthesis_version,
            configuration_hash=cfg_h, provider_id=self.provider_id, actor_id=actor_id,
            policy_version=self.POLICY)
        self.connection.execute(
            "INSERT INTO akb_synthesis_runs (run_id, set_id, members_json, synthesis_version,"
            " configuration_hash, provider_id, actor_id, policy_version, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')",
            (run.run_id, run.set_id, canonical_json(run.members), run.synthesis_version,
             run.configuration_hash, run.provider_id, run.actor_id, run.policy_version))
        sp = f"sp_syn_{run.run_id}"
        self.connection.execute(f"SAVEPOINT {sp}")
        try:
            units = self._retrieve_units(eset.members)
            weights, wp_used = self.weight_resolver.resolve(
                self._member_meta(eset.members), cfg.get("weight_policy", "weight_policy=v1"))
            if wp_used == "uniform":
                run.warnings.append("weight policy unknown → uniform")
            alignment = self.alignment_engine.align(units)
            conflicts = self.detector.detect(alignment, units, audit_ts=_now())
            per_member = _compatibility(alignment, conflicts)
            alignment_dict = {"entity_clusters": [asdict_(c) for c in alignment.entity_clusters],
                              "relation_clusters": [asdict_(c) for c in alignment.relation_clusters],
                              "event_clusters": alignment.event_clusters,
                              "temporal_alignment": alignment.temporal_alignment,
                              "rule_audit": alignment.rule_audit}
            candidates = self._synthesize_candidates(
                alignment, conflicts, weights, per_member, eset.members, run, actor_id, cfg)
            run.status = "capped" if conflicts.capped else "completed"
            run.alignment = alignment_dict
            run.conflicts = {"conflicts": [asdict_(c) for c in conflicts.conflicts],
                             "capped": conflicts.capped}
            run.weights = [asdict_(w) for w in weights]
            run.fingerprint = fp
            self.connection.execute(
                "UPDATE akb_synthesis_runs SET status=?, alignment_json=?, conflicts_json=?,"
                " weights_json=?, fingerprint=?, warnings_json=?, finished_at=? WHERE run_id=?",
                (run.status, canonical_json(run.alignment), canonical_json(run.conflicts),
                 canonical_json(run.weights), run.fingerprint, canonical_json(run.warnings),
                 _now(), run.run_id))
            self.connection.execute(f"RELEASE {sp}")
            return {"run": run, "assertions": candidates, "warnings": run.warnings,
                    "fingerprint": fp, "idempotent_hit": False}
        except Exception:
            self.connection.execute(f"ROLLBACK TO {sp}")
            self.connection.execute(f"RELEASE {sp}")
            self.connection.execute(
                "UPDATE akb_synthesis_runs SET status='failed', finished_at=? WHERE run_id=?",
                (_now(), run.run_id))
            raise

    def _retrieve_units(self, members: list[str]) -> list[dict]:
        units = []
        for eid in members:                      # canonical 序（确定性）
            rows = self.connection.execute(
                "SELECT * FROM akb_semantic_units WHERE evidence_id = ?", (eid,)).fetchall()
            if not rows:
                raise SynthesisError(E_ALIGN_UNIT_MISSING, eid)
            for r in rows:
                units.append(dict(r) | {
                    "entity_candidates": json.loads(r["entity_candidates_json"] or "[]"),
                    "relation_candidates": json.loads(r["relation_candidates_json"] or "[]"),
                    "temporal_parse": json.loads(r["temporal_parse_json"])
                    if r["temporal_parse_json"] else None})
        return units

    def _member_meta(self, members: list[str]) -> list[dict]:
        out = []
        for eid in members:
            r = self.connection.execute(
                "SELECT e.evidence_id, e.confidence, e.extraction_method, d.source_id,"
                " s.source_type FROM akb_evidence e"
                " JOIN akb_documents d ON d.document_id = e.document_id"
                " JOIN akb_sources s ON s.source_id = d.source_id"
                " WHERE e.evidence_id = ?", (eid,)).fetchone()
            if r is None:
                raise SynthesisError(E_ALIGN_UNIT_MISSING, eid)
            out.append(dict(r) | {"independent": True})
        return out

    def _synthesize_candidates(self, alignment, conflicts, weights, per_member,
                               members, run, actor_id, cfg):
        wmap = {w.evidence_id: w.weight for w in weights}
        conflict_ids = {c.conflict_type + ":" + ",".join(c.source_evidence_ids)
                        for c in conflicts.conflicts}
        produced = []
        for rc in sorted(alignment.relation_clusters, key=lambda c: c.cluster_id):
            member_eids = sorted({m["evidence_id"] for m in rc.members})
            if any(per_member.get(e) in ("INCOMPARABLE", "INVALID") for e in member_eids):
                run.warnings.append(f"{rc.cluster_id}: incomparable member excluded")
                continue
            # S-01 全对齐簇 → 单候选；S-03 CONFLICTING 带 conflict_ref
            obj_values = [m.get("object_value") for m in rc.members if m.get("object_value")]
            subj = next((cl.representative for cl in alignment.entity_clusters
                         if cl.cluster_id == rc.subject_cluster), None)
            obj = next((cl.representative for cl in alignment.entity_clusters
                        if cl.cluster_id == rc.object_cluster), None)
            if subj is None or obj is None:
                continue
            # S-01 同值簇 → 单值；多值（VALUE_CONFLICT 已记录）→ 字典序最大（确定性）
            obj_value = obj_values[0] if obj_values and len(set(map(str, obj_values))) == 1 \
                else (max(obj_values, key=lambda v: str(v)) if obj_values else obj)
            if subj is None or obj is None:
                continue
            conf = round(sum(wmap.get(e, 0.5) for e in member_eids) / len(member_eids), 4) \
                if member_eids else 0.5
            cref = None
            for c in conflicts.conflicts:
                if set(member_eids) & set(c.source_evidence_ids):
                    cref = c.conflict_type + ":" + ",".join(c.source_evidence_ids)
                    break
            pv = self.provenance.record(actor_id=actor_id, actor_kind="system",
                                        activity="synthesize", inputs=[run.run_id])
            a = self.builder.create_candidate(
                subject_ref=f"entity:{subj}", predicate_ref=f"relation:{rc.predicate}",
                object={"kind": "literal", "value": str(obj_value)},
                assertion_type="extracted", ontology_scope=cfg.get("ontology_scope",
                                                                   "ontology:generic:0.1"),
                actor_id=actor_id, confidence=conf, evidence_refs=member_eids,
                source_unit_refs=[m["unit_id"] for m in rc.members],
                derivation={"synthesis_run_id": run.run_id,
                            "conflict_ref": cref} if cref else
                {"synthesis_run_id": run.run_id})
            produced.append(a)
        return produced

    def _assertions_for_run(self, run_id: str) -> list:
        rows = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE derivation_json LIKE ?",
            (f'%{run_id}%',)).fetchall()
        return [dict(r) for r in rows]

    def _run_from_row(self, row) -> SynthesisRunRecord:
        return SynthesisRunRecord(
            run_id=row["run_id"], set_id=row["set_id"],
            members=json.loads(row["members_json"]),
            synthesis_version=row["synthesis_version"],
            configuration_hash=row["configuration_hash"],
            provider_id=row["provider_id"], actor_id=row["actor_id"],
            policy_version=row["policy_version"], status=row["status"],
            alignment=json.loads(row["alignment_json"]) if row["alignment_json"] else None,
            conflicts=json.loads(row["conflicts_json"]) if row["conflicts_json"] else None,
            weights=json.loads(row["weights_json"] or "[]"),
            fingerprint=row["fingerprint"],
            warnings=json.loads(row["warnings_json"] or "[]"),
            created_at=row["created_at"], finished_at=row["finished_at"])


def asdict_(obj):
    from dataclasses import asdict
    return asdict(obj)