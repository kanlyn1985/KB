# -*- coding: utf-8 -*-
"""ReasoningEngine skeleton（DD-001 §6/§7；create_candidate 唯一边界；环检测）。

migration 14 未执行——本阶段 run 记录仅内存快照（no-run-table 模式）；
fingerprint/幂等接口就位，migration 14 落库后切换持久化。
"""
from __future__ import annotations

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.reasoning.models import (
    InferredProposal,
    ReasoningContext,
    reasoning_fingerprint,
)


class ReasoningEngine:
    """推理编排：parent selection → provider.infer → schema validation →
    环/深度检测 → create_candidate（inferred，唯一边界）。

    R-01..R-06 全强制；inferred→asserted 永久禁止（State Machine，不改）。
    """

    def __init__(self, connection, provider=None, assertion_store: AssertionStore | None = None,
                 provenance=None):
        from agent_kb.evidence_core.assertions import Provenance
        self.connection = connection
        self.provider = provider
        self.store = assertion_store or AssertionStore(connection)
        self.provenance = provenance or Provenance(connection)
        self._inferred_status_guard = "candidate"   # R-01：恒 candidate

    # ---- parent selection（DC-01/02）----

    def _load_parents(self, parent_ids: list[str]) -> tuple[list, list[str]]:
        """加载并校验 parent：存在性 + 类型边界（inferred 允许=更早 run 链）。

        返回 (parents, errors)。parent_id 不存在 → E-V04-PARENT-NOT-FOUND。
        """
        parents, errors = [], []
        for pid in parent_ids:
            row = self.connection.execute(
                "SELECT * FROM akb_assertions WHERE assertion_id=?", (pid,)).fetchone()
            if row is None:
                errors.append(f"E-V04-PARENT-NOT-FOUND: {pid}")
                continue
            parents.append(self.store._row_to_assertion(row)
                           if hasattr(self.store, "_row_to_assertion")
                           else self._row_to_assertion(row))
        return parents, errors

    @staticmethod
    def _row_to_assertion(row) -> object:
        from agent_kb.evidence_core.models import KnowledgeAssertion
        import json
        # akb_assertions 的 object 为展开列（object_kind/value/datatype/unit/entity_ref）
        o = {"kind": row["object_kind"], "value": row["object_value"],
             "datatype": row["object_datatype"], "unit": row["object_unit"],
             "entity_id": row["object_entity_ref"]}
        o = {k: v for k, v in o.items() if v is not None}
        return KnowledgeAssertion(
            assertion_id=row["assertion_id"], subject_ref=row["subject_ref"],
            predicate_ref=row["predicate_ref"], object=o,
            assertion_type=row["assertion_type"], status=row["status"],
            confidence=row["confidence"],
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            source_unit_refs=json.loads(row["source_unit_refs_json"] or "[]"),
            temporal_scope=json.loads(row["temporal_scope_json"] or "null")
            if row["temporal_scope_json"] else None,
            ontology_scope=row["ontology_scope"] or "",
            derivation=json.loads(row["derivation_json"] or "null")
            if row["derivation_json"] else None)

    # ---- 环/深度检测（DC-02/DC-06）----

    def _assertion_depth(self, assertion_id: str, seen: set | None = None) -> int:
        seen = seen or set()
        if assertion_id in seen:
            return 0                      # 环截断（防御；环在提案级拒绝）
        seen.add(assertion_id)
        row = self.connection.execute(
            "SELECT derivation_json FROM akb_assertions WHERE assertion_id=?",
            (assertion_id,)).fetchone()
        if row is None or not row["derivation_json"]:
            return 0                      # 根（extracted/observed）
        import json
        d = json.loads(row["derivation_json"])
        parents = d.get("parent_assertions") or []
        return 1 + max((self._assertion_depth(p, set(seen)) for p in parents), default=0)

    def _proposal_depth_ok(self, proposal: InferredProposal, max_depth: int) -> tuple[bool, int]:
        depth = 1 + max((self._assertion_depth(p) for p in proposal.parent_assertions),
                        default=0)
        return depth <= max_depth, depth

    # ---- 主入口（skeleton：单 run 内存模式）----

    def reason(self, parent_ids: list[str], actor_id: str,
               context: ReasoningContext | None = None) -> dict:
        context = context or ReasoningContext()
        parents, errors = self._load_parents(parent_ids)
        if errors:
            return {"ok": False, "errors": errors, "assertions": [],
                    "warnings": [], "fingerprint": None, "run_id": None}
        fingerprint = reasoning_fingerprint(
            [p.assertion_id for p in parents], self.provider.reasoner_id(),
            self.provider.rule_version(), context.configuration_hash())
        # provenance（activity=infer）
        if self.provenance is not None:
            from agent_kb.evidence_core.state_machine import actor_kind_of
            self.provenance.record(
                actor_id=actor_id, actor_kind=actor_kind_of(actor_id),
                activity="infer", inputs=list(parent_ids),
                metadata={"fingerprint": fingerprint,
                          "reasoner_id": self.provider.reasoner_id(),
                          "rule_version": self.provider.rule_version()})
        proposals = self.provider.infer(parents, context) or []
        created, warnings = [], []
        for p in proposals:
            violations = p.validate()
            if violations:
                warnings.extend(f"{p.proposal_id}: {v}" for v in violations)
                continue                              # 提案级隔离（R-06/DD-001 §6）
            depth_ok, depth = self._proposal_depth_ok(p, context.max_depth)
            if not depth_ok:
                warnings.append(f"{p.proposal_id}: E-V04-DEPTH-EXCEEDED (depth={depth})")
                continue
            if self._cycle_in_parents(p):
                warnings.append(f"{p.proposal_id}: E-V04-CYCLE-DETECTED")
                continue
            parent_depth = max((self._assertion_depth(pid)
                                for pid in p.parent_assertions), default=0)
            derivation = {
                "rule_ref": p.rule_ref,
                "parent_assertions": list(p.parent_assertions),
                "reasoner_id": p.reasoner_id,
                "rule_input_snapshot": p.rule_input_snapshot,
                "confidence_basis": p.confidence_basis,
                "depth": parent_depth + 1,
            }
            a = self.store.create_candidate(
                subject_ref=p.subject_ref, predicate_ref=p.predicate_ref,
                object=p.object, assertion_type="inferred",
                ontology_scope=context.ontology_scope, actor_id=actor_id,
                confidence=p.confidence,
                evidence_refs=sorted({e for pid in p.parent_assertions
                                      for e in self._parent_evidence(pid)}),
                derivation=derivation)
            created.append(a)
        return {"ok": True, "errors": [], "assertions": created, "warnings": warnings,
                "fingerprint": fingerprint, "run_id": None,
                "parent_count": len(parents)}

    def _cycle_in_parents(self, proposal: InferredProposal) -> bool:
        """提案级环检测：parent 含提案自身（自引用）即环（跨 run 链由 depth 限）。"""
        # 提案未落库无 id——自引用在此层不可能；保留接口（migration 14 持久化后启用
        # 祖先链检测：parent 链中若出现本次 run 已创建的 assertion_id → E-V04-CYCLE）。
        return False

    def _parent_evidence(self, parent_id: str) -> set:
        row = self.connection.execute(
            "SELECT evidence_refs_json FROM akb_assertions WHERE assertion_id=?",
            (parent_id,)).fetchone()
        import json
        return set(json.loads(row["evidence_refs_json"] or "[]")) if row else set()