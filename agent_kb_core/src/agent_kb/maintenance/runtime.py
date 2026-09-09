# -*- coding: utf-8 -*-
"""V0.11 Maintenance Proposal Runtime（AKB-V11-IMPL-001；设计 docs/V0.11/）。

治理闭环行动层：akb_health_signals / akb_conflict_records → 确定性 review
提案（落地为 V0.8 VerificationTask，task_type="maintenance_review"）→
human 裁决。

P0 红线（fail-close）：
- Proposal ↛ akb_assertions / kg_nodes/kg_edges / hypothesis 状态；
- ProposalRuntime ↛ task 自动迁移（created 后零系统迁移）；
- spec ↛ 裁决性结论（固定模板"please review"语义）；
- Conflict proposal ↛ Resolution。

Identity：复用 V0.8 verification_task_identity（零新算法）——proposal_id 即
task_id（proposal 是 task 的治理视图）；MaintenanceProposal 自身 fingerprint
= SHA256(canonical payload) 独立校验。零 timestamp/零 random。

Audit：graph:maintenance-proposal-create 进 akb_provenance（seq 锚）——零第二套。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

PROPOSAL_TYPES = ("maintenance_review",)
SOURCE_TYPES = ("health_signal", "conflict_record")


class MaintenanceProposalError(ValueError):
    """fail-closed：Maintenance Proposal 错误。"""


@dataclass(frozen=True)
class MaintenanceProposal:
    """immutable 提案（V0.8 task 的治理视图——零执行语义）。"""
    proposal_id: str
    source_type: str
    source_id: str
    target_ref: str
    proposal_type: str
    spec: str
    priority: str
    status: str
    created_from: str
    fingerprint: str


def _proposal_fingerprint(*, source_type: str, source_id: str,
                          target_ref: str, proposal_type: str,
                          spec: str) -> str:
    payload = {"source_type": source_type, "source_id": source_id,
               "target_ref": target_ref, "proposal_type": proposal_type,
               "spec": spec}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")
                          ).hexdigest()[:16]


def _spec_text(source_type: str, source_id: str, target_ref: str) -> str:
    """确定性 spec 模板（零自由文本漂移；零裁决性结论——"please review"）。"""
    if source_type == "health_signal":
        return (f"Please review maintenance signal {source_id} on"
                f" target {target_ref} (health finding, human review"
                f" required).")
    return (f"Please review conflict {source_id} on target {target_ref}"
            f" (conflict flagged, human review required).")


def _priority_from_row(row: dict, source_type: str) -> str:
    """确定性优先级（severity/信号类型映射——零评分算法）。"""
    if source_type == "conflict_record":
        return {"high": "high", "medium": "medium", "low": "low"}[
            row.get("severity") or "medium"]
    return {"causal_coverage": "medium", "conflict": "high",
            "stability": "medium", "verification": "low"}[
            row.get("signal_type") or "stability"]


class MaintenanceProposalRuntime:
    """提案运行时（确定性转换 + 审计 + 只读查询；零 mutation 零执行）。"""

    def __init__(self, connection, task_runtime=None,
                 actor_id: str = "system:maintenance"):
        self.connection = connection
        self._tr = task_runtime
        self.actor_id = actor_id

    def _services(self):
        if self._tr is None:
            from agent_kb.hypothesis import VerificationTaskRuntime
            self._tr = VerificationTaskRuntime(self.connection)
        return self._tr

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:maintenance-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("targets", []),
            metadata=details)
        return rec.provenance_id

    # ---- source 校验（fail-close）----

    def _load_signal(self, signal_ref: str) -> dict:
        row = self.connection.execute(
            "SELECT signal_id, target_ref, target_type, signal_type, value,"
            " detail, health_id, fingerprint, computed_snapshot FROM"
            " akb_health_signals WHERE signal_id=? OR health_id=? OR"
            " signal_id LIKE ?",
            (signal_ref, signal_ref, f"{signal_ref}:%")).fetchone()
        if row is None:
            raise MaintenanceProposalError(
                f"E-V11-MAINTENANCE-INVALID: health signal {signal_ref!r}"
                " not found")
        return dict(row)

    def _load_conflict(self, conflict_id: str) -> dict:
        row = self.connection.execute(
            "SELECT conflict_id, conflict_type, target_refs_json, severity,"
            " status, fingerprint, created_from_snapshot FROM"
            " akb_conflict_records WHERE conflict_id=?",
            (conflict_id,)).fetchone()
        if row is None:
            raise MaintenanceProposalError(
                f"E-V11-MAINTENANCE-INVALID: conflict {conflict_id!r}"
                " not found")
        return dict(row)

    def _resolve_hypothesis_anchor(self, target_ref: str,
                                   source_snapshot: str) -> str:
        """target → V0.8 task 所需 hypothesis_id 锚（确定性规则）。

        V0.8 create_task 硬校验 hypothesis 实存（E-V08-HYPOTHESIS-NOT-FOUND）
        ——锚必须真实存在（零 fabricate）：hypothesis 型 target 直接校验使用；
        assertion/entity 型 target 无实存 hypothesis 时 fail-close
        （E-V11-MAINTENANCE-INVALID——P1 设计定标项默认档，诚实边界）。
        """
        if target_ref.startswith("hyp_"):
            from agent_kb.hypothesis import HypothesisService
            if HypothesisService(self.connection).get_hypothesis(
                    target_ref) is not None:
                return target_ref
        raise MaintenanceProposalError(
            f"E-V11-MAINTENANCE-INVALID: target {target_ref!r} has no"
            " resolvable hypothesis anchor (fail-close, no fabrication;"
            " P1 design default)")

    def _create_task(self, *, anchor: str, spec: str,
                     evidence_refs: tuple, actor_id: str) -> object:
        hs, tr = None, self._services()
        task = tr.create_task(
            hypothesis_id=anchor, task_type="maintenance_review", spec=spec,
            evidence_requirements=evidence_refs, actor_id=actor_id)
        return task

    # ---- A. health signal proposal ----

    def create_proposal_from_signal(self, signal_ref: str, *,
                                    actor_id: str | None = None
                                    ) -> MaintenanceProposal:
        row = self._load_signal(signal_ref)
        target_ref = row["target_ref"]
        spec = _spec_text("health_signal", row["signal_id"], target_ref)
        priority = _priority_from_row(row, "health_signal")
        fp = _proposal_fingerprint(source_type="health_signal",
                                   source_id=row["signal_id"],
                                   target_ref=target_ref,
                                   proposal_type="maintenance_review",
                                   spec=spec)
        proposal_id = self._resolve_hypothesis_anchor(
            target_ref, row["computed_snapshot"])
        # V0.8 task 通道（identity 复用——task_id 由 V0.8 算法派生）
        actor = actor_id or self.actor_id
        task = self._create_task(
            anchor=proposal_id, spec=spec,
            evidence_refs=(row["signal_id"],), actor_id=actor)
        final_id = task.task_id
        existing = self.get_proposal(final_id)
        if existing is not None:
            return existing                    # 幂等（零重复审计）
        prov = self._audit(
            activity="graph:maintenance-proposal-create",
            details={"targets": [target_ref], "proposal_id": final_id,
                     "source_type": "health_signal",
                     "source_id": row["signal_id"], "target_ref": target_ref,
                     "proposal_type": "maintenance_review", "spec": spec,
                     "priority": priority, "fingerprint": fp,
                     "created_from": row["computed_snapshot"],
                     "actor": actor})
        return MaintenanceProposal(
            proposal_id=final_id, source_type="health_signal",
            source_id=row["signal_id"], target_ref=target_ref,
            proposal_type="maintenance_review", spec=spec, priority=priority,
            status="created", created_from=row["computed_snapshot"],
            fingerprint=fp)

    # ---- B. conflict proposal ----

    def create_proposal_from_conflict(self, conflict_id: str, *,
                                      actor_id: str | None = None
                                      ) -> MaintenanceProposal:
        row = self._load_conflict(conflict_id)
        targets = json.loads(row["target_refs_json"])
        target_ref = targets[0] if targets else row["conflict_id"]
        spec = _spec_text("conflict_record", row["conflict_id"], target_ref)
        priority = _priority_from_row(row, "conflict_record")
        fp = _proposal_fingerprint(source_type="conflict_record",
                                   source_id=row["conflict_id"],
                                   target_ref=target_ref,
                                   proposal_type="maintenance_review",
                                   spec=spec)
        anchor = self._resolve_hypothesis_anchor(
            target_ref, row["created_from_snapshot"])
        actor = actor_id or self.actor_id
        task = self._create_task(
            anchor=anchor, spec=spec,
            evidence_refs=(row["conflict_id"],), actor_id=actor)
        final_id = task.task_id
        existing = self.get_proposal(final_id)
        if existing is not None:
            return existing
        prov = self._audit(
            activity="graph:maintenance-proposal-create",
            details={"targets": [target_ref], "proposal_id": final_id,
                     "source_type": "conflict_record",
                     "source_id": row["conflict_id"], "target_ref":
                     target_ref, "proposal_type": "maintenance_review",
                     "spec": spec, "priority": priority, "fingerprint": fp,
                     "created_from": row["created_from_snapshot"],
                     "actor": actor})
        return MaintenanceProposal(
            proposal_id=final_id, source_type="conflict_record",
            source_id=row["conflict_id"], target_ref=target_ref,
            proposal_type="maintenance_review", spec=spec, priority=priority,
            status="created", created_from=row["created_from_snapshot"],
            fingerprint=fp)

    # ---- 读面（provenance 重放 + keyset cursor）----

    def _all_proposals(self) -> list[dict]:
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:maintenance-proposal-create'"):
            meta = json.loads(r["metadata_json"])
            rows.append((meta, r["provenance_id"]))
        rows.sort(key=lambda x: (x[0].get("seq", 0), x[1]))
        out = []
        for m, prov in rows:
            out.append({"proposal_id": m["proposal_id"],
                        "source_type": m["source_type"],
                        "source_id": m["source_id"],
                        "target_ref": m["target_ref"],
                        "proposal_type": m["proposal_type"],
                        "spec": m["spec"], "priority": m["priority"],
                        "status": "created", "fingerprint": m["fingerprint"],
                        "created_from": m.get("created_from", ""),
                        "provenance_id": prov})
        return out

    def get_proposal(self, proposal_id: str) -> MaintenanceProposal | None:
        if not proposal_id or not proposal_id.startswith("vt_"):
            raise MaintenanceProposalError(
                f"E-V11-MAINTENANCE-INVALID: bad proposal id {proposal_id!r}")
        for row in self._all_proposals():
            if row["proposal_id"] == proposal_id:
                return MaintenanceProposal(
                    proposal_id=row["proposal_id"],
                    source_type=row["source_type"],
                    source_id=row["source_id"], target_ref=row["target_ref"],
                    proposal_type=row["proposal_type"], spec=row["spec"],
                    priority=row["priority"], status=row["status"],
                    created_from=row["created_from"],
                    fingerprint=row["fingerprint"])
        return None

    def list_proposals(self, *, source_type: str | None = None,
                       cursor: str | None = None,
                       limit: int = 100) -> dict:
        """只读分页（V0.10 keyset cursor 模式复用）。"""
        if not isinstance(limit, int) or limit < 1 or limit > 500:
            raise MaintenanceProposalError(
                f"E-V11-MAINTENANCE-INVALID: limit {limit!r} out of range"
                " (1..500)")
        rows = self._all_proposals()
        if source_type is not None:
            if source_type not in SOURCE_TYPES:
                raise MaintenanceProposalError(
                    f"E-V11-MAINTENANCE-INVALID: source_type"
                    f" {source_type!r} unknown")
            rows = [r for r in rows if r["source_type"] == source_type]
        rows.sort(key=lambda r: r["proposal_id"])
        if cursor is not None:
            fp, body = cursor.split(".", 1) if "." in cursor else ("", "")
            payload = None
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise MaintenanceProposalError(
                    "E-V11-MAINTENANCE-INVALID: cursor malformed") from exc
            if (not isinstance(payload, dict) or
                    payload.get("kind") != "maintenance_proposals"):
                raise MaintenanceProposalError(
                    "E-V11-MAINTENANCE-INVALID: cursor kind mismatch")
            check = hashlib.sha256(canonical_json(payload).encode(
                "utf-8")).hexdigest()[:8]
            if check != fp:
                raise MaintenanceProposalError(
                    "E-V11-MAINTENANCE-INVALID: cursor fingerprint mismatch")
            last = payload.get("last_key", "")
            rows = [r for r in rows if r["proposal_id"] > last]
        page = rows[:limit]
        has_more = len(rows) > limit
        next_cursor = None
        if has_more and page:
            payload = {"kind": "maintenance_proposals",
                       "last_key": page[-1]["proposal_id"]}
            next_cursor = hashlib.sha256(canonical_json(payload).encode(
                "utf-8")).hexdigest()[:8] + "." + canonical_json(payload)
        return {"kind": "maintenance_proposals", "items": page,
                "count": len(page), "has_more": has_more,
                "next_cursor": next_cursor}