# -*- coding: utf-8 -*-
"""V0.6 Provenance Closure（AKB-V06-IMPL-003；设计 docs/V0.6/ PROVENANCE_CONTRACT）。

ReasoningProvenanceService：graph-aware reasoning 的完整可追溯链闭环——

    GraphContext (context_id / graph_fingerprint)
        ↓
    ReasoningRun (akb_reasoning_runs 复用)
        ↓
    Candidate (inferred assertion, derivation_json)
        ↓
    Assertion/Evidence provenance (parent + evidence_refs)
        ↓
    Documents

- 复用 akb_provenance（graph:reason / graph:reason-failed / graph:context-build；
  零第二套 provenance）；
- missing provenance → fail-closed（E-V06-PROVENANCE-MISSING，不 fabricate）；
- READ-ONLY 查询面（trace 提取零写）；
- deterministic：链输出 canonical 排序。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json


class ProvenanceClosureError(ValueError):
    """fail-closed：provenance 闭环错误（缺级/不可解析——不 fabricate）。"""


@dataclass(frozen=True)
class CandidateProvenance:
    """单个候选的完整回溯链（What/Why/From/Context/Version）。"""
    candidate_assertion_id: str
    conclusion: tuple                 # (subject_ref, predicate_ref, object_repr)
    rule_ref: str
    rule_version: str
    reasoning_run_id: str
    context_id: str
    graph_fingerprint: str
    parent_assertion_ids: tuple
    evidence_ids: tuple
    document_ids: tuple
    status: str
    assertion_type: str


@dataclass(frozen=True)
class ReasoningProvenanceTrace:
    """一次 graph-aware reasoning 的完整 trace（context → run → candidates）。"""
    context_id: str
    graph_fingerprint: str
    reasoning_run_id: str | None
    status: str
    parent_assertion_ids: tuple
    candidates: tuple                 # CandidateProvenance（canonical 序）
    root_entity: str = ""
    audit_refs: tuple = ()            # akb_provenance provenance_id（graph:reason*）
    chain: tuple = ()                 # 逐级 label（确定性顺序）


class ReasoningProvenanceService:
    """provenance 闭环查询/校验面（只读 + fail-closed）。"""

    def __init__(self, connection):
        self.connection = connection

    # ---- helpers ----

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.connection.execute(sql, params)]

    def _require_assertion(self, assertion_id: str) -> dict:
        rows = self._rows(
            "SELECT assertion_id, subject_ref, predicate_ref, object_value,"
            " object_entity_ref, assertion_type, status, derivation_json,"
            " evidence_refs_json FROM akb_assertions WHERE assertion_id=?",
            (assertion_id,))
        if not rows:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: assertion {assertion_id} not found")
        return rows[0]

    def _evidence_documents(self, evidence_ids: tuple) -> tuple:
        """evidence → document（批量；缺 evidence fail-closed）。"""
        docs = []
        for eid in evidence_ids:
            rows = self._rows(
                "SELECT document_id FROM akb_evidence WHERE evidence_id=?", (eid,))
            if not rows:
                raise ProvenanceClosureError(
                    f"E-V06-PROVENANCE-MISSING: evidence {eid} not found")
            docs.append(rows[0]["document_id"])
        return tuple(sorted(set(docs)))

    # ---- 主查询 ----

    def trace_candidate(self, assertion_id: str) -> CandidateProvenance:
        """单候选全链回溯（What/Why/From/Context/Version）。"""
        a = self._require_assertion(assertion_id)
        if a["assertion_type"] != "inferred":
            raise ProvenanceClosureError(
                f"E-V06-NOT-INFERRED: {assertion_id} is {a['assertion_type']}")
        d_raw = a["derivation_json"] or ""
        if not d_raw:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: {assertion_id} has no derivation")
        try:
            d = json.loads(d_raw)
        except Exception as exc:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: {assertion_id} unparsable"
                " derivation") from exc
        run_id = d.get("reasoning_run_id")
        if not run_id:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: {assertion_id} lacks reasoning_run_id")
        # run → context（derivation_json 扩展字段由 orchestrator 审计携带）
        run_rows = self._rows(
            "SELECT run_id, status FROM akb_reasoning_runs WHERE run_id=?", (run_id,))
        if not run_rows:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: reasoning run {run_id} not found")
        # context_id / graph_fingerprint 从 graph:reason 审计恢复（单一事实源）
        audit = self._rows(
            "SELECT metadata_json FROM akb_provenance WHERE activity='graph:reason'"
            " ORDER BY provenance_id")
        context_id = graph_fp = None
        for row in audit:
            m = json.loads(row["metadata_json"])
            if m.get("run_id") == run_id:
                context_id = m.get("context_id")
                graph_fp = m.get("graph_fingerprint")
                break
        if not context_id:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: run {run_id} has no graph:reason audit"
                " (context linkage)")
        parents = tuple(sorted(d.get("parent_assertions") or []))
        if not parents:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: {assertion_id} has no parent assertions")
        evidence_ids = set()
        for pid in parents:
            pa = self._require_assertion(pid)
            for eid in sorted(json.loads(pa["evidence_refs_json"] or "[]")):
                evidence_ids.add(eid)
        evidence_ids = tuple(sorted(evidence_ids))
        if not evidence_ids:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: {assertion_id} resolves to no evidence")
        doc_ids = self._evidence_documents(evidence_ids)
        rule_ref = str(d.get("rule_ref") or "")
        # V0.4 rule_ref 形如 "RR-02@v04-rules-v1"——version 从 ref 提取（单一事实源）
        if "@" in rule_ref:
            rule_ref, rule_version = rule_ref.split("@", 1)
        else:
            rule_version = str(d.get("rule_version") or
                               (run_rows[0].get("rule_version")
                                if run_rows else "") or "")
        obj_repr = a["object_entity_ref"] or a["object_value"] or ""
        return CandidateProvenance(
            candidate_assertion_id=assertion_id,
            conclusion=(a["subject_ref"], a["predicate_ref"], obj_repr),
            rule_ref=rule_ref, rule_version=rule_version,
            reasoning_run_id=run_id, context_id=context_id,
            graph_fingerprint=graph_fp or "",
            parent_assertion_ids=parents, evidence_ids=evidence_ids,
            document_ids=doc_ids, status=a["status"],
            assertion_type=a["assertion_type"])

    def trace_run(self, run_id: str) -> ReasoningProvenanceTrace:
        """整 run 的 trace（context → run → 全部候选）。"""
        run_rows = self._rows(
            "SELECT run_id, status, fingerprint FROM akb_reasoning_runs"
            " WHERE run_id=?", (run_id,))
        if not run_rows:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: reasoning run {run_id} not found")
        run = run_rows[0]
        audit = self._rows(
            "SELECT provenance_id, metadata_json FROM akb_provenance"
            " WHERE activity='graph:reason' ORDER BY provenance_id")
        context_id = graph_fp = None
        audit_refs = []
        for row in audit:
            m = json.loads(row["metadata_json"])
            if m.get("run_id") == run_id:
                context_id = m.get("context_id")
                graph_fp = m.get("graph_fingerprint")
                audit_refs.append(row["provenance_id"])
        if not context_id:
            raise ProvenanceClosureError(
                f"E-V06-PROVENANCE-MISSING: run {run_id} has no graph:reason audit")
        # run 的候选 = derivation_json 指向 run_id 的 inferred 断言
        cand_rows = self._rows(
            "SELECT assertion_id FROM akb_assertions WHERE assertion_type='inferred'"
            " AND derivation_json LIKE ? ORDER BY assertion_id",
            (f'%{run_id}%',))
        candidates = tuple(sorted(
            (self.trace_candidate(r["assertion_id"]) for r in cand_rows),
            key=lambda c: c.candidate_assertion_id))
        # context 的 parents（graph:reason 审计）
        parents = ()
        for row in audit:
            m = json.loads(row["metadata_json"])
            if m.get("run_id") == run_id:
                parents = tuple(sorted(m.get("parent_assertions") or []))
                break
        chain = (
            f"context:{context_id}",
            f"graph:{graph_fp or ''}",
            f"run:{run_id}",
            f"candidates:{len(candidates)}",
        )
        return ReasoningProvenanceTrace(
            context_id=context_id, graph_fingerprint=graph_fp or "",
            reasoning_run_id=run_id, status=run["status"],
            parent_assertion_ids=parents, candidates=candidates,
            audit_refs=tuple(sorted(audit_refs)), chain=chain)

    # ---- 校验面（fail-closed 断言）----

    def verify_closure(self, run_id: str) -> dict:
        """验证整 run 闭环：每候选五级链完整。返回 {closed: bool, gaps: []}。"""
        gaps = []
        try:
            tr = self.trace_run(run_id)
        except ProvenanceClosureError as exc:
            return {"closed": False, "gaps": [str(exc)]}
        for c in tr.candidates:
            if not (c.evidence_ids and c.document_ids and c.parent_assertion_ids
                    and c.context_id and c.rule_ref):
                gaps.append(f"incomplete chain: {c.candidate_assertion_id}")
        return {"closed": not gaps, "gaps": gaps,
                "candidates": len(tr.candidates)}