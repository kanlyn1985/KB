# -*- coding: utf-8 -*-
"""Entity Identity Resolution（V0.5-DD-002）——canonical id 派生层。

红线：Entity A + Entity B 不能因为文本相似自动 merge——
本层只做 L1 精确归一簇的 canonical 收敛（继承 V0.3 对齐簇输出）；
相似度建议/merge 执行属 IMPL-002 治理面，不在本轮。
"""
from __future__ import annotations

import hashlib

from agent_kb.reasoning.models import canonical_json


class EntityIdentityResolver:
    """实体身份解析：normalized_form 精确归一簇（L1）→ canonical_id。

    entity_type 分歧不合并（V0.3 CONF-005 教训固化——DD-002 §4）。
    """

    def __init__(self, domain_pack_version: str = "default"):
        self._dpv = domain_pack_version

    def canonical_id(self, canonical_form: str, entity_type: str) -> str:
        payload = {"canonical_form": canonical_form, "entity_type": entity_type,
                   "domain_pack_version": self._dpv}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]

    def resolve_clusters(self, entity_members: list[dict]) -> list[dict]:
        """输入 V0.3 对齐簇成员（normalized_form/entity_type/evidence_id…），
        输出 canonical 簇列表（L1 精确键 + type 一致约束）。

        返回：[{canonical_id, canonical_form, entity_type, members[], aliases[]}]
        （deterministic 排序）。
        """
        groups: dict[tuple, list[dict]] = {}
        for m in entity_members:
            key = ((m.get("normalized_form") or m.get("surface_form") or "").strip(),
                   m.get("entity_type") or "")
            groups.setdefault(key, []).append(m)
        out = []
        for (form, etype), members in sorted(groups.items()):
            out.append({
                "canonical_id": self.canonical_id(form, etype),
                "canonical_form": form,
                "entity_type": etype,
                "members": sorted(members, key=lambda m: (m.get("evidence_id", ""),
                                                          m.get("candidate_id", ""))),
                "aliases": sorted({m.get("surface_form") or m.get("normalized_form") or ""
                                   for m in members}),
            })
        return out


# ---- V0.5-IMPL-002：Merge Candidate Model + 治理动作（ER-01..10）----

from dataclasses import dataclass, field


@dataclass
class MergeCandidate:
    """合并候选（相似度/精确匹配产物——**候选 ≠ merge**，ER-01/02）。"""
    candidate_id: str
    source_entity_ids: list          # 两个及以上 entity（canonical_id 列表）
    canonical_candidate_id: str      # 批准后的 canonical id（确定性派生）
    match_strategy: str              # L1_EXACT / L2_NORMALIZED / L3_SIMILARITY / L4_CANONICAL
    match_score: float
    evidence_refs: list
    entity_types: list
    status: str = "pending"          # pending / approved / rejected / superseded
    created_at: str = ""
    provenance_ref: str = ""


class EntityGovernanceService:
    """实体治理服务（merge/split/alias/rollback——全部 human-only；ER-03/05/06/08）。

    内存治理模型（任务书 DATABASE：优先最小变更——无 migration）；
    provenance 全部落 akb_provenance（activity=graph:entity-*，ER-10/DD-003 §3）。
    fail-closed：基础设施不足以判定 M-01/M-02/M-03 时拒绝（任务书 §4）。
    """

    ACTOR_KINDS_FORBIDDEN = ("system", "agent", "llm")

    def __init__(self, connection, resolver: EntityIdentityResolver | None = None,
                 provenance=None):
        from agent_kb.evidence_core.assertions import Provenance
        self.connection = connection
        self.resolver = resolver or EntityIdentityResolver()
        self.provenance = provenance or Provenance(connection)
        self.candidates: dict[str, MergeCandidate] = {}
        self.merges: dict[str, dict] = {}          # canonical_id → merge record
        self.splits: list[dict] = []
        self.aliases: dict[str, list[dict]] = {}   # canonical_id → alias actions
        self.rollback_log: list[dict] = []

    # ---- helpers ----

    def _audit(self, *, actor_id: str, activity: str, reason: str, details: dict) -> str:
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = self.provenance.record(
            actor_id=actor_id, actor_kind=actor_kind_of(actor_id), activity=activity,
            inputs=details.get("entity_ids", []), metadata={"reason": reason, **details})
        return rec.provenance_id

    def _snapshot(self, entity_ids: list) -> str:
        return canonical_json(sorted(entity_ids))

    # ---- candidate generation（相似度/精确——只产候选）----

    def generate_merge_candidate(self, source_entity_ids: list, canonical_form: str,
                                 entity_types: list, evidence_refs: list,
                                 match_strategy: str, match_score: float = 1.0) -> MergeCandidate:
        """产生 MergeCandidate（零自动合并——ER-02）。

        canonical_candidate_id 由 resolver 确定性派生（复用 IMPL-001 算法——ER-08/§8）。
        """
        import time
        if match_strategy not in ("L1_EXACT", "L2_NORMALIZED", "L3_SIMILARITY",
                                  "L4_CANONICAL"):
            raise ValueError(f"E-V05-INVALID-STRATEGY: {match_strategy}")
        if len(source_entity_ids) < 2:
            raise ValueError("E-V05-CANDIDATE-MALFORMED: need >=2 source entities")
        canonical_candidate_id = self.resolver.canonical_id(canonical_form,
                                                            entity_types[0])
        cid = "mc_" + hashlib.sha256(canonical_json(
            {"sources": sorted(source_entity_ids), "strategy": match_strategy,
             "form": canonical_form}).encode("utf-8")).hexdigest()[:16]
        cand = MergeCandidate(
            candidate_id=cid, source_entity_ids=sorted(source_entity_ids),
            canonical_candidate_id=canonical_candidate_id,
            match_strategy=match_strategy, match_score=round(match_score, 4),
            evidence_refs=sorted(set(evidence_refs)), entity_types=list(entity_types),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self.candidates[cid] = cand
        return cand

    # ---- approve_merge（human-only；M-01..M-04 fail-closed）----

    def approve_merge(self, *, candidate_id: str, actor_id: str, reason: str,
                      required_evidence: list | None = None) -> dict:
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise ValueError(f"E-V05-MERGE-CANDIDATE-NOT-FOUND: {candidate_id}")
        if not actor_id.startswith("human:"):
            raise ValueError("E-V05-GOVERNANCE-ACTOR: merge approval requires human actor"
                             f" (got {actor_id})")
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        if cand.status != "pending":
            raise ValueError(f"E-V05-CANDIDATE-STATUS: {cand.status}")
        # M-02：entity type 兼容（fail-closed）
        if len(set(cand.entity_types)) != 1:
            raise ValueError("E-V05-ENTITY-TYPE-CONFLICT: "
                             f"{sorted(set(cand.entity_types))}")
        # M-03：共同 Evidence 支撑（fail-closed——无独立证据基础设施时要求显式 required）
        if not cand.evidence_refs:
            raise ValueError("E-V05-NO-MERGE-EVIDENCE: candidate has no evidence")
        if required_evidence is not None:
            missing = set(required_evidence) - set(cand.evidence_refs)
            if missing:
                raise ValueError(f"E-V05-NO-MERGE-EVIDENCE: missing {sorted(missing)}")
        # M-04：merge 携带 provenance（audit 先行）
        before = self._snapshot(cand.source_entity_ids)
        prov_id = self._audit(
            actor_id=actor_id, activity="graph:entity-merge", reason=reason,
            details={"entity_ids": cand.source_entity_ids,
                     "canonical_id": cand.canonical_candidate_id,
                     "before_snapshot": before,
                     "after_snapshot": canonical_json(
                         {"canonical_id": cand.canonical_candidate_id}),
                     "candidate_id": candidate_id,
                     "evidence_refs": cand.evidence_refs,
                     "match_strategy": cand.match_strategy})
        cand.status = "approved"
        cand.provenance_ref = prov_id
        merge_rec = {"canonical_id": cand.canonical_candidate_id,
                     "source_entity_ids": list(cand.source_entity_ids),
                     "candidate_id": candidate_id, "actor_id": actor_id,
                     "reason": reason, "provenance_ref": prov_id,
                     "evidence_refs": cand.evidence_refs,
                     "before_snapshot": before,
                     "after_snapshot": canonical_json(
                         {"canonical_id": cand.canonical_candidate_id}),
                     "superseded": False, "rolled_back": False}
        self.merges[cand.canonical_candidate_id] = merge_rec
        for sid in cand.source_entity_ids:
            # 逻辑 superseded（不物理删除——ER-08/任务书 §5）
            src = self.candidates.get(f"src_{sid}")
        return {"accepted": True, "canonical_id": cand.canonical_candidate_id,
                "provenance_ref": prov_id, "merge": merge_rec}

    # ---- split（human-only；ER-05/任务书 §6）----

    def split_entity(self, *, canonical_id: str, actor_id: str, reason: str,
                     partition: list) -> dict:
        if not canonical_id or canonical_id not in self.merges:
            raise ValueError(f"E-V05-MERGE-NOT-FOUND: {canonical_id}")
        if not actor_id.startswith("human:"):
            raise ValueError("E-V05-GOVERNANCE-ACTOR: split requires human actor")
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        rec = self.merges[canonical_id]
        all_sources = set(rec["source_entity_ids"])
        covered = set()
        for part in partition:
            part_set = set(part)
            if not part_set <= all_sources:
                raise ValueError("E-V05-SPLIT-PARTITION: partition exceeds merge members")
            covered |= part_set
        if covered != all_sources:
            raise ValueError("E-V05-SPLIT-PARTITION: partition does not cover all members")
        before = canonical_json({"canonical_id": canonical_id,
                                 "sources": sorted(all_sources)})
        prov_id = self._audit(
            actor_id=actor_id, activity="graph:entity-split", reason=reason,
            details={"entity_ids": rec["source_entity_ids"],
                     "canonical_id": canonical_id, "before_snapshot": before,
                     "after_snapshot": canonical_json({"partition": [sorted(p)
                                                                     for p in partition]}),
                     "candidate_id": rec["candidate_id"],
                     "evidence_refs": rec["evidence_refs"]})
        rec["superseded"] = True
        split_rec = {"canonical_id": canonical_id, "partition": [sorted(p)
                                                                 for p in partition],
                     "actor_id": actor_id, "reason": reason,
                     "provenance_ref": prov_id, "merge_provenance_ref":
                         rec["provenance_ref"]}
        self.splits.append(split_rec)
        return {"accepted": True, "split": split_rec}

    # ---- alias（governed；ER-06/任务书 §7）----

    def add_alias(self, *, entity_id: str, alias: str, actor_id: str, reason: str,
                  source: str = "governed") -> dict:
        """governed alias（terminology alias 属 DomainPack 只读——不在此通道）。

        跨实体冲突（alias 已属另一 entity）→ E-V05-ALIAS-CONFLICT。
        """
        if not actor_id.startswith("human:"):
            raise ValueError("E-V05-GOVERNANCE-ACTOR: alias requires human actor")
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        if source not in ("governed", "terminology"):
            raise ValueError("E-V05-INVALID-ALIAS-SOURCE")
        if source == "terminology":
            raise ValueError("E-V05-TERMINOLOGY-READONLY: terminology alias belongs to"
                             " DomainPack, not governance channel")
        # 跨实体冲突检测
        for other_id, entries in self.aliases.items():
            if other_id != entity_id and any(e["alias"] == alias for e in entries):
                raise ValueError(f"E-V05-ALIAS-CONFLICT: '{alias}' already maps to"
                                 f" {other_id}")
        before = canonical_json(sorted(e["alias"]
                                       for e in self.aliases.get(entity_id, [])))
        prov_id = self._audit(
            actor_id=actor_id, activity="graph:entity-alias", reason=reason,
            details={"entity_ids": [entity_id], "alias": alias, "source": source,
                     "before_snapshot": before,
                     "after_snapshot": canonical_json(
                         sorted([e["alias"] for e in self.aliases.get(entity_id, [])] +
                                [alias]))})
        self.aliases.setdefault(entity_id, []).append(
            {"alias": alias, "actor_id": actor_id, "reason": reason,
             "provenance_ref": prov_id, "source": source, "active": True})
        return {"accepted": True, "provenance_ref": prov_id}

    # ---- rollback（logical；ER-08/任务书 §9）----

    def rollback(self, *, canonical_id: str, actor_id: str, reason: str) -> dict:
        if not actor_id.startswith("human:"):
            raise ValueError("E-V05-GOVERNANCE-ACTOR: rollback requires human actor")
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        rec = self.merges.get(canonical_id)
        if rec is None or rec["rolled_back"]:
            raise ValueError(f"E-V05-ROLLBACK-NOT-FOUND: {canonical_id}")
        prov_id = self._audit(
            actor_id=actor_id, activity="graph:entity-rollback", reason=reason,
            details={"entity_ids": rec["source_entity_ids"],
                     "canonical_id": canonical_id,
                     "candidate_id": rec["candidate_id"],
                     "before_snapshot": rec["after_snapshot"],
                     "after_snapshot": rec["before_snapshot"],
                     "evidence_refs": rec["evidence_refs"]})
        rec["rolled_back"] = True
        rec["superseded"] = True
        rb = {"canonical_id": canonical_id, "actor_id": actor_id, "reason": reason,
              "provenance_ref": prov_id,
              "merge_provenance_ref": rec["provenance_ref"]}
        self.rollback_log.append(rb)
        return {"accepted": True, "rollback": rb,
                "source_entity_ids": rec["source_entity_ids"]}
