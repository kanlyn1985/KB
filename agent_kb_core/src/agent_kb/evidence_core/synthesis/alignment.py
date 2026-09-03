# -*- coding: utf-8 -*-
"""对齐引擎：entity(L1-L4)/relation/event/state/temporal 六态 + 五级兼容性（规则表驱动）。"""
from __future__ import annotations

import json
import re
from dataclasses import asdict

from agent_kb.evidence_core.synthesis.models import (
    AlignmentResult,
    EntityAlignmentCluster,
    RelationAlignmentCluster,
)


def _norm(form: str) -> str:
    t = re.sub(r"\s+", " ", (form or "").strip()).lower()
    return t.translate({ord(f): ord(t2) for f, t2 in zip("，。：；", ",.:;")})


class EvidenceAlignmentEngine:
    """对齐纯函数（只读）；聚类 ID 按最小 (evidence_id, candidate_id) 稳定编号。"""

    def __init__(self, domain_pack=None, alias_map: dict | None = None):
        self._pack = domain_pack
        self._alias = dict(alias_map or {})
        if domain_pack is not None:
            for term, aliases in (getattr(domain_pack, "terminology", None) or {}).items():
                for a in aliases or []:
                    self._alias.setdefault(a, term)

    # ---- L1-L4 实体对齐 ----
    def _entity_key(self, ec: dict) -> tuple[int, str]:
        """(level, key)——L1 精确 > L2 归一 > L3 ontology > L4 别名。"""
        nf = ec.get("normalized_form") or ec.get("surface_form") or ""
        if ec.get("ontology_ref"):
            return (3, f"ref:{ec['ontology_ref']}")
        a = self._alias.get(nf) or self._alias.get(_norm(nf))
        if a:
            return (4, f"alias:{a}")
        return (1, f"exact:{_norm(nf)}")

    def align(self, units: list[dict]) -> AlignmentResult:
        result = AlignmentResult()
        # 收集全部 entity candidates（带 evidence 归属）
        ents: list[dict] = []
        for u in units:
            for ec in (u.get("entity_candidates") or []):
                ents.append({"evidence_id": u["evidence_id"], "unit_id": u["unit_id"], **ec})
        # 分组：L1/L2 键为主；同键不同成员 → 簇
        groups: dict[tuple, list[dict]] = {}
        for e in ents:
            groups.setdefault(self._entity_key(e), []).append(e)
        # 单成员簇也保留（跨证据簇才有对齐价值，但编号需全簇稳定）
        all_groups = sorted(groups.items(), key=lambda kv: min(
            (m["evidence_id"], m.get("candidate_id") or "") for m in kv[1]))
        for i, (key, members) in enumerate(all_groups, 1):
            cross_evidence = len({m["evidence_id"] for m in members}) >= 2
            if not cross_evidence:
                continue  # 单证据内簇无合成价值（保留在快照外）
            rep = sorted(members, key=lambda m: (m["evidence_id"], m.get("candidate_id") or ""))[0]
            result.entity_clusters.append(EntityAlignmentCluster(
                cluster_id=f"cl_{i:04d}",
                members=[{"evidence_id": m["evidence_id"], "candidate_id": m.get("candidate_id"),
                          "normalized_form": m.get("normalized_form"),
                          "ontology_ref": m.get("ontology_ref")} for m in
                         sorted(members, key=lambda m: (m["evidence_id"], m.get("candidate_id") or ""))],
                representative=rep.get("normalized_form") or ""))
        ec_index = {m["candidate_id"]: cl for cl in result.entity_clusters for m in cl.members}

        # ---- 关系对齐 ----
        rels: list[dict] = []
        ent_value_by_cand = {e.get("candidate_id"): (e.get("normalized_form")
                                                     or e.get("surface_form"))
                             for e in ents}
        for u in units:
            for rc in (u.get("relation_candidates") or []):
                rels.append({"evidence_id": u["evidence_id"], "unit_id": u["unit_id"], **rc} | {
                    "object_value": ent_value_by_cand.get(rc.get("object_candidate_id"))})
        rgroups: dict[tuple, list[dict]] = {}
        for r in rels:
            s_cl = ec_index.get(r.get("subject_candidate_id"))
            o_cl = ec_index.get(r.get("object_candidate_id"))
            if s_cl is None or o_cl is None:
                result.warnings.append(
                    f"relation {r.get('relation_candidate_id')}: entity cluster missing (single-evidence entity)")
                continue
            key = (s_cl.cluster_id, _norm(r.get("predicate_candidate") or ""), o_cl.cluster_id)
            rgroups.setdefault(key, []).append(r)
        for i, (key, members) in enumerate(sorted(rgroups.items()), 1):
            cross = len({m["evidence_id"] for m in members}) >= 2
            if not cross:
                continue
            result.relation_clusters.append(RelationAlignmentCluster(
                cluster_id=f"rc_{i:04d}", subject_cluster=key[0], predicate=key[1],
                object_cluster=key[2],
                members=[{"evidence_id": m["evidence_id"], "unit_id": m["unit_id"],
                          "confidence": round(float(m.get("confidence", 0.0)), 4),
                          "object_value": m.get("object_value") or
                          (m.get("object_surface") if "object_surface" in m else None)}
                         for m in sorted(members, key=lambda m: m["evidence_id"])]))

        # ---- temporal 对齐（六态）+ event/state 簇 ----
        result.temporal_alignment = self._temporal_alignment(units)
        result.event_clusters = self._event_clusters(units, result.entity_clusters)
        result.state_clusters = []  # state 谓词族对齐（配置驱动；V0.3 内置最小实现）
        result.rule_audit.append({"rule_id": "ALIGN-001", "inputs": {"units": len(units)},
                                  "result": {"entity_clusters": len(result.entity_clusters),
                                             "relation_clusters": len(result.relation_clusters)}})
        return result

    def _temporal_alignment(self, units: list[dict]) -> dict:
        states = {}
        for u in units:
            tp = u.get("temporal_parse")
            if not tp:
                states[u["evidence_id"]] = "missing"
                continue
            if tp.get("parse_status") == "unresolved":
                states[u["evidence_id"]] = "unresolved"
            elif tp.get("valid_time") or tp.get("event_time"):
                states[u["evidence_id"]] = "anchored"
            else:
                states[u["evidence_id"]] = "missing"
        anchored = {k for k, v in states.items() if v == "anchored"}
        overall = "missing"
        if len(anchored) == len(units) and units:
            overall = "same"        # V0.3 内置：全部锚定即 same（区间细分留配置）
        elif anchored and len(anchored) < len(units):
            overall = "partial"
        return {"per_evidence": states, "overall": overall}

    def _event_clusters(self, units, entity_clusters):
        out = []
        by_time: dict[str, list] = {}
        for u in units:
            tp = u.get("temporal_parse")
            et = (tp or {}).get("event_time")
            if et:
                by_time.setdefault(et, []).append(u["evidence_id"])
        for et, eids in sorted(by_time.items()):
            if len(set(eids)) >= 2:
                out.append({"event_time": et, "evidence_ids": sorted(set(eids))})
        return out