# -*- coding: utf-8 -*-
"""对齐引擎（V0.3 hardening 版）。

- Defect A 修复：relation 端点查询显式使用 relation 自带 unit_id（零外层变量依赖）；
- Defect C 修复：实体对齐 L1/L2/L3/L4 层级 = 多键 union-find（同一语义实体不因
  ontology_ref 有无而分裂；无关实体不被表面形误并——entity_type 分歧转 IDENTITY_CONFLICT）；
- Defect B 实现：State Alignment（subject cluster + state predicate family + valid_time
  兼容性；contradictory → STATE_CONFLICT 不静默合并）；
- Defect H 修复：temporal 六态（same/overlapping/sequential/contradictory/missing/
  unresolved）真实判定；
- Defect I 修复：event 簇 = 同 event_time AND 参与实体簇重叠 ≥1；
- 全部派生对象显式携带 evidence_id/unit_id/candidate_id（Defect E：零 ambient 依赖）。
"""
from __future__ import annotations

import re
from dataclasses import asdict

from agent_kb.evidence_core.synthesis.models import (
    AlignmentResult,
    EntityAlignmentCluster,
    RelationAlignmentCluster,
)

# state 谓词族（V0.2 R-01/R-02/R-06 谓词词汇的状态表达子集；DomainPack 可扩展）
STATE_PREDICATE_FAMILY = {"has_parameter", "constrained_by", "observed_value"}


def _norm(form: str) -> str:
    """L2 归一（V0.2 N-01..N-08 之上的对齐级归一：空白/小写/全半角标点/尾部系动词剥离）。"""
    t = re.sub(r"\s+", " ", (form or "").strip()).lower()
    t = t.translate({ord(f): ord(t2) for f, t2 in zip("，。：；", ",.:;")})
    # L2b：对齐级尾部系动词剥离（"OBC 额定输入电压是" ≡ "OBC 额定输入电压"）——
    # 语义等价（系动词无实体语义）；属对齐层归一，不改 V0.2 编译产物
    t = re.sub(r"(是|为|均)$", "", t).strip()
    return t


def _interval(tp: dict | None) -> tuple[str | None, str | None]:
    """提取 (valid_from, valid_until)（无则 None）。"""
    if not tp:
        return None, None
    vt = tp.get("valid_time") or {}
    return vt.get("valid_from"), vt.get("valid_until")


class EvidenceAlignmentEngine:
    """对齐纯函数（只读）；簇 ID 按最小 (evidence_id, candidate_id) 稳定编号。"""

    def __init__(self, domain_pack=None, alias_map: dict | None = None):
        self._pack = domain_pack
        self._alias = dict(alias_map or {})
        if domain_pack is not None:
            for term, aliases in (getattr(domain_pack, "terminology", None) or {}).items():
                for a in aliases or []:
                    self._alias.setdefault(a, term)
        self.state_predicate_family = set(STATE_PREDICATE_FAMILY)

    # ---- 实体多键（Defect C：层级 union-find）----
    @staticmethod
    def _entity_keys(e: dict) -> set[str]:
        """L1 精确形 / L2 归一形 / L3 ontology_ref / L4 别名 canonical——多键并存。"""
        nf = e.get("normalized_form") or e.get("surface_form") or ""
        keys = {f"L1:{nf}", f"L2:{_norm(nf)}"}
        # L3 ontology_ref 是 TYPE 级引用（object_type:equipment），非实例唯一——
        # 不作独立 union 键（否则所有同 type 实体误并）；仅随成员快照留审计
        a = e.get("_alias_target")
        if a:
            keys.add(f"L4:{a}")
        return keys

    def align(self, units: list[dict]) -> AlignmentResult:
        result = AlignmentResult()
        # ---- 实体收集（显式所有权：evidence_id/unit_id 内嵌）----
        ents: list[dict] = []
        for u in units:
            for ec in (u.get("entity_candidates") or []):
                nf = ec.get("normalized_form") or ec.get("surface_form") or ""
                ents.append({"evidence_id": u["evidence_id"], "unit_id": u["unit_id"],
                             **ec, "_alias_target": self._alias.get(nf) or self._alias.get(_norm(nf))})
        # ---- union-find 多键聚类（Defect C）----
        parent: dict[int, int] = {}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(ents)):
            parent[i] = i
        key_index: dict[str, int] = {}
        for i, e in enumerate(ents):
            for k in self._entity_keys(e):
                if k in key_index:
                    union(key_index[k], i)
                else:
                    key_index[k] = i
        groups: dict[int, list[int]] = {}
        for i in range(len(ents)):
            groups.setdefault(find(i), []).append(i)
        # 簇编号：按簇内最小 (evidence_id, candidate_id)——全簇（含单证据簇）
        def min_key(idx_list: list[int]):
            return min((ents[i]["evidence_id"], ents[i].get("candidate_id") or "")
                       for i in idx_list)

        ordered = sorted(groups.values(), key=min_key)
        ec_index: dict[tuple, str] = {}
        cluster_divergence: list[dict] = []
        for i, idx_list in enumerate(ordered, 1):
            cid = f"cl_{i:04d}"
            members = sorted((ents[j] for j in idx_list),
                             key=lambda m: (m["evidence_id"], m.get("candidate_id") or ""))
            for m in members:
                if m.get("candidate_id"):
                    ec_index[(m["unit_id"], m["candidate_id"])] = cid
            types = {m.get("entity_type") for m in members if m.get("entity_type")}
            if len(types) > 1:
                cluster_divergence.append({"cluster_id": cid, "types": sorted(types),
                                           "members": members})
            result.entity_clusters.append(EntityAlignmentCluster(
                cluster_id=cid, representative=members[0].get("normalized_form") or "",
                members=[{"evidence_id": m["evidence_id"], "unit_id": m["unit_id"],
                          "candidate_id": m.get("candidate_id"),
                          "normalized_form": m.get("normalized_form"),
                          "entity_type": m.get("entity_type"),
                          "ontology_ref": m.get("ontology_ref")} for m in members]))
        # entity_type 分歧 → IDENTITY_CONFLICT 源数据（经 conflicts 消费）
        result.warnings.extend(
            f"entity cluster {d['cluster_id']}: entity_type divergence {d['types']}"
            for d in cluster_divergence)
        result.rule_audit.append({"rule_id": "ALIGN-ENT-001",
                                  "inputs": {"entities": len(ents)},
                                  "result": {"clusters": len(result.entity_clusters),
                                             "divergent": len(cluster_divergence)}})

        # ---- 关系对齐（Defect A 修复：显式 r["unit_id"]；键=(subject_cluster, predicate)）----
        ent_value_by_cand = {(e.get("unit_id"), e.get("candidate_id")):
                             (e.get("normalized_form") or e.get("surface_form")) for e in ents}
        rels: list[dict] = []
        for u in units:
            for rc in (u.get("relation_candidates") or []):
                rels.append({"evidence_id": u["evidence_id"], "unit_id": u["unit_id"],
                             **rc} | {"object_value": ent_value_by_cand.get(
                                 (u["unit_id"], rc.get("object_candidate_id")))})
        rgroups: dict[tuple, list[dict]] = {}
        for r in rels:
            owner = r["unit_id"]                      # Defect A：显式所有权，零 ambient 依赖
            s_cl = ec_index.get((owner, r.get("subject_candidate_id")))
            o_cl = ec_index.get((owner, r.get("object_candidate_id")))
            if s_cl is None or o_cl is None:
                result.warnings.append(
                    f"relation {r.get('relation_candidate_id')} (unit {owner}): entity cluster missing")
                continue
            key = (s_cl, _norm(r.get("predicate_candidate") or ""))
            rgroups.setdefault(key, []).append(r | {"object_cluster": o_cl})
        for i, (key, members) in enumerate(sorted(rgroups.items()), 1):
            result.relation_clusters.append(RelationAlignmentCluster(
                cluster_id=f"rc_{i:04d}", subject_cluster=key[0], predicate=key[1],
                object_cluster=members[0]["object_cluster"],
                members=[{"evidence_id": m["evidence_id"], "unit_id": m["unit_id"],
                          "candidate_id": m.get("relation_candidate_id"),
                          "confidence": round(float(m.get("confidence", 0.0)), 4),
                          "object_cluster": m["object_cluster"],
                          "object_value": m.get("object_value")}
                         for m in sorted(members, key=lambda m: (m["evidence_id"],
                                                                 m.get("object_value") or ""))]))
        result.rule_audit.append({"rule_id": "ALIGN-REL-001",
                                  "inputs": {"relations": len(rels)},
                                  "result": {"clusters": len(result.relation_clusters)}})

        # ---- temporal 六态（Defect H）----
        result.temporal_alignment = self._temporal_alignment(units)

        # ---- event 簇（Defect I：同时间 AND 参与实体簇重叠 ≥1）----
        result.event_clusters = self._event_clusters(units, ec_index)

        # ---- state 对齐（Defect B）----
        result.state_clusters, state_contradictions = self._state_alignment(
            units, ec_index, result.relation_clusters)
        result.warnings.extend(
            f"state cluster {sc['cluster_id']}: contradictory validity"
            for sc in state_contradictions)
        result.state_contradictions = state_contradictions
        result.rule_audit.append({"rule_id": "ALIGN-STATE-001",
                                  "inputs": {"units": len(units)},
                                  "result": {"state_clusters": len(result.state_clusters),
                                             "contradictions": len(state_contradictions)}})
        return result

    # ---- temporal 六态（Defect H 修复）----
    def _temporal_alignment(self, units: list[dict]) -> dict:
        """六态判定 + contradiction_members（精确矛盾双方——V03-IMPL-004 Defect 修复）。

        contradictory 判定（V0.3 TEMPORAL_SYNTHESIS_SPEC T 系语义）：同 subject 语境下
        两证据 valid_time 区间互斥且不重叠（end_a < start_b 严格）——不同 event_time
        本身不构成 conflict（可能是时序/并存事件）。
        contradiction_members 只含真实参与矛盾的 evidence/unit——供 ConflictDetector
        精确 provenance（scope=actual conflict members，非全部 units）。
        """
        per: dict[str, str] = {}
        anchors: dict[str, str] = {}
        intervals: dict[str, tuple] = {}
        contradiction_members: list[dict] = []
        for u in units:
            eid = u["evidence_id"]
            tp = u.get("temporal_parse")
            if not tp:
                per[eid] = "missing"
                continue
            if tp.get("parse_status") == "unresolved":
                per[eid] = "unresolved"
                vf, vu = _interval(tp)
                if vf or vu or tp.get("event_time"):
                    anchors[eid] = tp.get("event_time") or vf or ""
                    intervals[eid] = (vf, vu)
                continue
            vf, vu = _interval(tp)
            et = tp.get("event_time")
            if vf or vu or et:
                per[eid] = "anchored"
                anchors[eid] = et or vf or ""
                intervals[eid] = (vf or et, vu or et)
            else:
                per[eid] = "missing"
        anchored = [e for e in per if per[e] == "anchored"]
        overall = "missing"
        if any(per[e] == "unresolved" for e in per):
            overall = "unresolved"
        elif len(anchors) == len(units) and len(set(anchors.values())) == 1:
            overall = "same"
        elif anchored:
            # 区间关系判定（全锚定时精确）
            full = [(e, intervals[e]) for e in anchored
                    if intervals[e][0] and intervals[e][1]]
            if len(full) >= 2:
                ordered = sorted(full, key=lambda x: x[1][0])
                disjoint = all(ordered[i][1][1] < ordered[i + 1][1][0]
                               for i in range(len(ordered) - 1))
                overlaps = all(ordered[i][1][1] >= ordered[i + 1][1][0]
                               for i in range(len(ordered) - 1))
                # 互斥相邻对记录（contradiction_members）：同 subject 语境下区间互斥 =
                # TEMPORAL_CONFLICT 候选（P-012 契约：members=真实矛盾双方，非全部 units）。
                # overall 判定分离：全隔=sequential（时序事实）；部分互斥=contradictory。
                for i in range(len(ordered) - 1):
                    if ordered[i][1][1] < ordered[i + 1][1][0]:
                        contradiction_members.append(
                            {"evidence_id": ordered[i][0],
                             "unit_id": next(u["unit_id"] for u in units
                                             if u["evidence_id"] == ordered[i][0]),
                             "valid_from": ordered[i][1][0],
                             "valid_until": ordered[i][1][1]})
                        contradiction_members.append(
                            {"evidence_id": ordered[i + 1][0],
                             "unit_id": next(u["unit_id"] for u in units
                                             if u["evidence_id"] == ordered[i + 1][0]),
                             "valid_from": ordered[i + 1][1][0],
                             "valid_until": ordered[i + 1][1][1]})
                if disjoint:
                    # 恰两证据全隔互斥 = 同事实窗冲突（P-012 场景 → contradictory）；
                    # 3+ 方顺时链 = 时序事实（sequential；互斥对仍记录于 contradiction_members
                    # 供 STATE/TEMPORAL 检测上下文）
                    overall = "contradictory" if len(ordered) == 2 else "sequential"
                elif overlaps:
                    overall = "overlapping"
                else:
                    overall = "contradictory"       # mixed 重叠/互斥并存
            elif len(set(anchors.values())) > 1:
                overall = "overlapping"
        return {"per_evidence": per, "overall": overall,
                "anchors": {e: anchors[e] for e in sorted(anchors)},
                "contradiction_members": contradiction_members}

    # ---- event 簇（Defect I：participant overlap 强制）----
    def _event_clusters(self, units: list[dict], ec_index: dict) -> list[dict]:
        # 参与实体簇集合：unit → 其全部 candidates 所属簇
        unit_clusters: dict[str, set] = {}
        for (uid, cand), cid in ec_index.items():
            unit_clusters.setdefault(uid, set()).add(cid)
        by_time: dict[str, list[dict]] = {}
        for u in units:
            tp = u.get("temporal_parse")
            et = (tp or {}).get("event_time")
            if et:
                by_time.setdefault(et, []).append(u)
        out = []
        for et in sorted(by_time):
            group = by_time[et]
            # 参与重叠：两两 unit 间实体簇交集 ≥1 才归并（否则各自独立——不合成假事件）
            merged: list[list[dict]] = []
            for u in group:
                cset = unit_clusters.get(u["unit_id"], set())
                placed = False
                for grp in merged:
                    gset = set().union(*(unit_clusters.get(x["unit_id"], set())
                                         for x in grp))
                    if cset & gset:
                        grp.append(u)
                        placed = True
                        break
                if not placed:
                    merged.append([u])
            for grp in merged:
                eids = sorted({x["evidence_id"] for x in grp})
                if len(set(eids)) >= 2:
                    out.append({"event_time": et, "evidence_ids": eids,
                                "participants": sorted(unit_clusters.get(
                                    grp[0]["unit_id"], set()))})
        return out

    # ---- state 对齐（Defect B）----
    def _state_alignment(self, units: list[dict], ec_index: dict,
                         relation_clusters: list) -> tuple[list[dict], list[dict]]:
        """(subject_cluster, state predicate family, valid_time 兼容性)。

        返回 (state_clusters, contradictions)。矛盾有效窗不合并——转 STATE_CONFLICT。
        """
        # 用 relation 簇（谓词属 state family）作 state 候选源
        state_groups: dict[tuple, list[dict]] = {}
        unit_tp = {u["unit_id"]: u.get("temporal_parse") for u in units}
        for rc in relation_clusters:
            if rc.predicate not in self.state_predicate_family:
                continue
            key = (rc.subject_cluster, rc.predicate)
            for m in rc.members:
                vf, vu = _interval(unit_tp.get(m["unit_id"]))
                state_groups.setdefault(key, []).append({
                    "evidence_id": m["evidence_id"], "unit_id": m["unit_id"],
                    "object_value": m.get("object_value"),
                    "valid_from": vf, "valid_until": vu,
                    "confidence": m.get("confidence")})
        clusters_out: list[dict] = []
        contradictions: list[dict] = []
        for i, (key, members) in enumerate(sorted(state_groups.items()), 1):
            anchored = [m for m in members if m["valid_from"] or m["valid_until"]]
            missing = [m for m in members if not (m["valid_from"] or m["valid_until"])]
            cluster = {"cluster_id": f"st_{i:04d}", "subject_cluster": key[0],
                       "state_predicate": key[1],
                       "members": sorted(members, key=lambda m: m["evidence_id"]),
                       "missing_anchor_members": [m["evidence_id"] for m in missing],
                       "alignment": "missing" if not anchored else
                       ("aligned" if len(anchored) >= 1 else "missing")}
            # contradictory 判定：同 subject+state，锚定窗互斥且不重叠
            if len(anchored) >= 2:
                ordered = sorted(anchored, key=lambda m: (m["valid_from"] or "",
                                                          m["valid_until"] or ""))
                pairs = []
                for a in range(len(ordered)):
                    for b in range(a + 1, len(ordered)):
                        ma, mb = ordered[a], ordered[b]
                        end_a = ma["valid_until"] or ma["valid_from"]
                        start_b = mb["valid_from"] or mb["valid_until"]
                        if end_a and start_b and end_a < start_b:
                            pairs.append((ma, mb))
                if pairs:
                    cluster["alignment"] = "contradictory"
                    contradictions.append({
                        "cluster_id": cluster["cluster_id"],
                        "state_predicate": key[1],
                        "source_evidence_ids": sorted({m["evidence_id"]
                                                       for p in pairs for m in p}),
                        "members": [{"evidence_id": m["evidence_id"],
                                     "unit_id": m["unit_id"],
                                     "valid_from": m["valid_from"],
                                     "valid_until": m["valid_until"],
                                     "object_value": m["object_value"]}
                                    for p in pairs for m in p],
                        "sides": [{"evidence_id": m["evidence_id"],
                                   "unit_id": m["unit_id"],
                                   "valid_from": m["valid_from"],
                                   "valid_until": m["valid_until"],
                                   "object_value": m["object_value"]}
                                  for p in pairs for m in p]})
            elif missing and anchored:
                cluster["alignment"] = "partial-anchored"   # 缺锚成员不参与窗判定（不伪造）
            clusters_out.append(cluster)
        return clusters_out, contradictions