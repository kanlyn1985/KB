# -*- coding: utf-8 -*-
"""Inferred candidate governance（AKB-V04-IMPL-003；DD-001 §7 / DD-002 §4）。

- InferenceGovernanceService：inferred candidate → validated 人工治理流
  （validator service/interface；validation provenance activity；governance audit trail）；
- 状态迁移检查（state transition checks）——inferred→asserted 永久禁止（硬门）。

继承：AssertionStore.validate()（INV-001 hash 复核）/ transition()（reason 必填）/
State Machine LEGAL_TRANSITIONS。V0.3 frozen code 零触碰；production DB 不执行。
"""
from __future__ import annotations

import json

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.reasoning.models import canonical_json


class InferenceGovernanceService:
    """inferred candidate 治理服务（validator service/interface）。

    - validate_inferred()：candidate → validated（人工治理流；inferred 专用校验面）；
    - transition()：通用迁移（state transition checks 硬门）；
    - audit_trail()：治理审计轨迹查询（validation activity + transition 记录）。
    """

    def __init__(self, connection, assertion_store: AssertionStore | None = None):
        from agent_kb.evidence_core.assertions import AssertionValidator
        self.connection = connection
        self.store = assertion_store or AssertionStore(connection)
        self.validator = AssertionValidator(connection)

    # ---- internal helpers ----

    def _load(self, assertion_id: str) -> dict:
        row = self.connection.execute(
            "SELECT * FROM akb_assertions WHERE assertion_id=?", (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        return dict(row)

    def _audit(self, *, assertion_id: str, actor_id: str, action: str,
               from_status: str, to_status: str, reason: str,
               details: dict | None = None) -> str:
        """GovernanceAuditTrail 落库（akb_provenance activity=govern:<action>）。

        V0.4 治理审计模型：action/状态对/reason/details 全记录——
        audit trail 可回放（INV 精神：治理动作显式化）。
        """
        from agent_kb.evidence_core.state_machine import actor_kind_of
        metadata = {"assertion_id": assertion_id, "action": action,
                    "from_status": from_status, "to_status": to_status,
                    "reason": reason, **(details or {})}
        rec = self.store.provenance.record(
            actor_id=actor_id, actor_kind=actor_kind_of(actor_id),
            activity=f"govern:{action}", inputs=[assertion_id], metadata=metadata)
        return rec.provenance_id

    # ---- validation provenance activity ----

    def validate_inferred(self, *, assertion_id: str, actor_id: str, reason: str,
                          require_independent_evidence: bool = True) -> dict:
        """inferred candidate → validated（人工治理流）。

        - actor 必须人工（human:）——R-06 无自动晋升（system validator 通道留给
          extracted/observed；inferred 的 validated 是治理决定）；
        - reason 必填（审计面）；
        - require_independent_evidence：治理复核须引用独立证据（DD-001 §7）——
          校验 assertion 的 evidence_refs 非空且 derivation.depth 有限；
        - inferred → asserted 在迁移层永久禁止（本方法只到 validated）。
        """
        if not actor_id.startswith("human:"):
            raise ValueError("E-V04-GOVERNANCE-ACTOR: inferred validation requires human actor")
        if not reason or not reason.strip():
            raise ValueError("E-INVALID-REASON: reason required")
        row = self._load(assertion_id)
        if row["assertion_type"] != "inferred":
            raise ValueError(f"E-V04-NOT-INFERRED: {row['assertion_type']}")
        if row["status"] != "candidate":
            raise ValueError(f"E-WRONG-STATUS: {row['status']} (expected candidate)")
        if require_independent_evidence:
            refs = json.loads(row["evidence_refs_json"] or "[]")
            if not refs:
                raise ValueError("E-V04-NO-INDEPENDENT-EVIDENCE: governance review"
                                 " requires evidence references")
        from agent_kb.evidence_core.state_machine import validate_transition
        violations = validate_transition(
            current_status="candidate", new_status="validated",
            assertion_type="inferred", actor_id=actor_id,
            evidence_count=len(json.loads(row["evidence_refs_json"] or "[]")))
        if violations:
            raise ValueError("; ".join(violations))
        result = self.validator.validate(assertion_id=assertion_id, actor_id=actor_id)
        self._audit(assertion_id=assertion_id, actor_id=actor_id, action="validate",
                    from_status="candidate", to_status="validated", reason=reason,
                    details={"validation_provenance": result.get("provenance_ref")})
        return result

    # ---- state transition checks（硬门）----

    def transition(self, *, assertion_id: str, new_status: str, actor_id: str,
                   reason: str) -> dict:
        """通用迁移（state transition checks）。

        inferred → asserted：永久禁止（双保险——validate_transition 预检 + 触发器）。
        """
        row = self._load(assertion_id)
        from agent_kb.evidence_core.state_machine import validate_transition
        violations = validate_transition(
            current_status=row["status"], new_status=new_status,
            assertion_type=row["assertion_type"], actor_id=actor_id,
            evidence_count=len(json.loads(row["evidence_refs_json"] or "[]")))
        if violations:
            self._audit(assertion_id=assertion_id, actor_id=actor_id,
                        action="transition-rejected", from_status=row["status"],
                        to_status=new_status, reason=reason,
                        details={"violations": violations})
            raise ValueError("; ".join(violations))
        result = self.store.transition(assertion_id=assertion_id,
                                       new_status=new_status, actor_id=actor_id,
                                       reason=reason)
        self._audit(assertion_id=assertion_id, actor_id=actor_id, action="transition",
                    from_status=row["status"], to_status=new_status, reason=reason)
        return result

    # ---- governance audit trail ----

    def audit_trail(self, assertion_id: str) -> list[dict]:
        """治理审计轨迹（时序）：govern:* activity 全记录。"""
        rows = list(self.connection.execute(
            "SELECT provenance_id, actor_id, actor_kind, activity, occurred_at,"
            " metadata_json FROM akb_provenance"
            " WHERE activity LIKE 'govern:%' AND inputs_json LIKE ?"
            " ORDER BY occurred_at, provenance_id",
            (f"%{assertion_id}%",)))
        out = []
        for r in rows:
            m = json.loads(r["metadata_json"] or "{}")
            if m.get("assertion_id") != assertion_id:
                continue                     # LIKE 粗筛后精确过滤（防 id 子串误配）
            out.append({"provenance_id": r["provenance_id"], "actor_id": r["actor_id"],
                        "actor_kind": r["actor_kind"], "activity": r["activity"],
                        "occurred_at": r["occurred_at"],
                        "action": m.get("action"), "from_status": m.get("from_status"),
                        "to_status": m.get("to_status"), "reason": m.get("reason")})
        return out