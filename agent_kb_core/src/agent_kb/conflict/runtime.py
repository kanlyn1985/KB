# -*- coding: utf-8 -*-
"""ConflictRuntime v2（AKB-V09-IMPL-003；设计 docs/V0.9/ ARCHITECTURE §5）。

只读语义分析层：消费 CausalProjection + KnowledgeHealth 信号 + 既有
provenance 活动 + 断言只读视图 → 产出 ConflictRecord（仅此而已）。

不变量：
- Conflict ≠ Resolution（无自动解决状态——status 只有 open/reviewed/dismissed）；
- Conflict ≠ Truth（标记不裁决——裁决 human，V0.3 flag 语义延续）；
- Conflict ≠ Mutation（零 assertion/graph/hypothesis 写入）。

冲突类型白名单（未知类型 fail-close）：
1. ASSERTION_VALUE_CONFLICT —— 同语义目标不同值（V0.3 值冲突语义）
2. CAUSAL_MECHANISM_CONFLICT —— 同因果目标不同机制投影（消费 CausalProjection）
3. DOMAIN_SCOPE_CONFLICT —— 同概念不同域约束

deterministic：conflict_id = "cf_"+SHA256(canonical_json(sorted refs))——
零时间/零随机/零 runtime ordering。
provenance：graph:conflict-detect（复用 akb_provenance，零第二套审计）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json

CONFLICT_TYPES = ("ASSERTION_VALUE_CONFLICT", "CAUSAL_MECHANISM_CONFLICT",
                  "DOMAIN_SCOPE_CONFLICT")
CONFLICT_STATUSES = ("open", "reviewed", "dismissed")
SEVERITY_LEVELS = ("low", "medium", "high")


class ConflictError(ValueError):
    """fail-closed：Conflict 运行时错误。"""


@dataclass(frozen=True)
class ConflictSignal:
    """冲突信号（检测结果的最小单元）。"""
    signal_type: str
    source_refs: tuple
    detail: str


@dataclass(frozen=True)
class ConflictRecord:
    """immutable 冲突记录（零解决语义）。"""
    conflict_id: str
    conflict_type: str
    source_refs: tuple
    target_refs: tuple
    domain_refs: tuple
    causal_refs: tuple
    severity: str
    status: str
    evidence_refs: tuple
    fingerprint: str
    created_from_snapshot: str
    metadata: tuple                    # (k, v) canonical 对


def conflict_identity(*, conflict_type: str, source_refs: tuple,
                      target_refs: tuple, created_from_snapshot: str) -> str:
    """deterministic conflict_id：canonical JSON（sorted refs；零时间/零随机）。"""
    payload = {"conflict_type": conflict_type,
               "source_refs": sorted(source_refs),
               "target_refs": sorted(target_refs),
               "created_from_snapshot": created_from_snapshot}
    return "cf_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class ConflictRuntime:
    """冲突运行时（只读检测 + 记录产出；零 mutation/零 resolution）。"""

    def __init__(self, connection, causal_runtime=None,
                 actor_id: str = "system:conflict"):
        self.connection = connection
        self._cr = causal_runtime
        self.actor_id = actor_id

    # ---- helpers ----

    def _services(self):
        if self._cr is None:
            from agent_kb.causal import CausalProjectionRuntime
            self._cr = CausalProjectionRuntime(self.connection)
        return self._cr

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:conflict-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("targets", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _record_fingerprint(rec: dict) -> str:
        return hashlib.sha256(canonical_json(rec).encode("utf-8")).hexdigest()[:16]

    # ---- 检测一：ASSERTION_VALUE_CONFLICT（同 subject+predicate 不同 object 值）----

    def _detect_value_conflicts(self, snapshot: str) -> list[ConflictRecord]:
        rows = [dict(r) for r in self.connection.execute(
            "SELECT assertion_id, subject_ref, predicate_ref, object_value,"
            " provenance_ref, status FROM akb_assertions WHERE status IN"
            " ('candidate','validated','asserted','disputed') AND"
            " object_value IS NOT NULL ORDER BY subject_ref, predicate_ref")]
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            groups.setdefault((r["subject_ref"], r["predicate_ref"]),
                              []).append(r)
        out = []
        for (subj, pred), grp in sorted(groups.items()):
            values = {r["object_value"] for r in grp}
            if len(values) < 2:
                continue
            src = tuple(sorted(r["assertion_id"] for r in grp))
            cid = conflict_identity(conflict_type="ASSERTION_VALUE_CONFLICT",
                                    source_refs=src, target_refs=(subj,),
                                    created_from_snapshot=snapshot)
            rec = {"conflict_type": "ASSERTION_VALUE_CONFLICT",
                   "source_refs": sorted(src), "target_refs": [subj],
                   "created_from_snapshot": snapshot}
            sev = "high" if len(values) > 2 else "medium"
            out.append(ConflictRecord(
                conflict_id=cid, conflict_type="ASSERTION_VALUE_CONFLICT",
                source_refs=src, target_refs=(subj,),
                domain_refs=(), causal_refs=(), severity=sev, status="open",
                evidence_refs=tuple(sorted(
                    r["provenance_ref"] for r in grp if r["provenance_ref"])),
                fingerprint=self._record_fingerprint(rec),
                created_from_snapshot=snapshot,
                metadata=(("values", sorted(values)),
                          ("predicate", pred))))
        return out

    # ---- 检测二：CAUSAL_MECHANISM_CONFLICT（同 effect 互斥机制/多因果源）----

    def _detect_causal_conflicts(self, snapshot: str,
                                 projection) -> list[ConflictRecord]:
        by_effect: dict[str, list] = {}
        for e in projection.causal_edges:
            by_effect.setdefault(e.target_ref, []).append(e)
        out = []
        for effect, edges in sorted(by_effect.items()):
            # 同 effect 多 source（候选机制冲突——确定性检测：源集合 size > 1）
            sources = sorted({e.source_ref for e in edges})
            if len(sources) < 2:
                continue
            causal_refs = tuple(sorted(e.causal_id for e in edges))
            src = tuple(sorted(
                a for e in edges for a in e.provenance_refs)) or causal_refs
            cid = conflict_identity(
                conflict_type="CAUSAL_MECHANISM_CONFLICT", source_refs=src,
                target_refs=(effect,), created_from_snapshot=snapshot)
            rec = {"conflict_type": "CAUSAL_MECHANISM_CONFLICT",
                   "source_refs": sorted(src), "target_refs": [effect],
                   "created_from_snapshot": snapshot}
            out.append(ConflictRecord(
                conflict_id=cid, conflict_type="CAUSAL_MECHANISM_CONFLICT",
                source_refs=src, target_refs=(effect,),
                domain_refs=(), causal_refs=causal_refs,
                severity="high" if len(sources) > 2 else "medium",
                status="open",
                evidence_refs=tuple(sorted(
                    p for e in edges for p in e.provenance_refs)),
                fingerprint=self._record_fingerprint(rec),
                created_from_snapshot=snapshot,
                metadata=(("effect", effect), ("causal_sources", sources),
                          ("detection", "condition-set-mutual-exclusion"))))
        return out

    # ---- 检测三：DOMAIN_SCOPE_CONFLICT（同概念不同域约束——ontology_scope 维度）----

    def _detect_domain_conflicts(self, snapshot: str) -> list[ConflictRecord]:
        rows = [dict(r) for r in self.connection.execute(
            "SELECT assertion_id, subject_ref, ontology_scope, status"
            " FROM akb_assertions WHERE status IN"
            " ('candidate','validated','asserted','disputed')")]
        groups: dict[str, set] = {}
        for r in rows:
            groups.setdefault(r["subject_ref"], set()).add(
                r["ontology_scope"])
        out = []
        for subj, scopes in sorted(groups.items()):
            if len(scopes) < 2:
                continue
            src = tuple(sorted(
                r["assertion_id"] for r in rows
                if r["subject_ref"] == subj))
            cid = conflict_identity(
                conflict_type="DOMAIN_SCOPE_CONFLICT", source_refs=src,
                target_refs=(subj,), created_from_snapshot=snapshot)
            rec = {"conflict_type": "DOMAIN_SCOPE_CONFLICT",
                   "source_refs": sorted(src), "target_refs": [subj],
                   "created_from_snapshot": snapshot}
            out.append(ConflictRecord(
                conflict_id=cid, conflict_type="DOMAIN_SCOPE_CONFLICT",
                source_refs=src, target_refs=(subj,),
                domain_refs=tuple(sorted(scopes)), causal_refs=(),
                severity="low", status="open", evidence_refs=(),
                fingerprint=self._record_fingerprint(rec),
                created_from_snapshot=snapshot,
                metadata=(("ontology_scopes", sorted(scopes)),)))
        return out

    # ---- 主入口 ----

    def detect(self, *, conflict_type: str | None = None,
               actor_id: str | None = None) -> tuple:
        """运行检测（确定性：同投影/库面 → 同记录集）。conflict_type 过滤可选
        （非白名单 → fail-close）。"""
        if conflict_type is not None and conflict_type not in CONFLICT_TYPES:
            raise ConflictError(
                f"E-V09-CONFLICT-INVALID: unknown conflict type"
                f" {conflict_type!r} (whitelist: {CONFLICT_TYPES})")
        cr = self._services()
        projection = cr.project()
        snapshot = projection.source_snapshot
        records: list[ConflictRecord] = []
        if conflict_type in (None, "ASSERTION_VALUE_CONFLICT"):
            records += self._detect_value_conflicts(snapshot)
        if conflict_type in (None, "CAUSAL_MECHANISM_CONFLICT"):
            records += self._detect_causal_conflicts(snapshot, projection)
        if conflict_type in (None, "DOMAIN_SCOPE_CONFLICT"):
            records += self._detect_domain_conflicts(snapshot)
        records = tuple(sorted(records, key=lambda r: r.conflict_id))
        actor = actor_id or self.actor_id
        # 幂等审计：同状态（同 snapshot+同冲突集）重复检测零重复审计
        if records:
            new_fps = sorted(r.fingerprint for r in records)
            last = None
            for r in self.connection.execute(
                    "SELECT metadata_json FROM akb_provenance WHERE activity ="
                    " 'graph:conflict-detect' ORDER BY occurred_at DESC,"
                    " provenance_id DESC LIMIT 1"):
                m = json.loads(r["metadata_json"])
                last = m.get("last_fingerprints")
            if last == new_fps:
                return records
            self._audit(
                activity="graph:conflict-detect",
                details={"targets": sorted({t for r in records
                                            for t in r.target_refs}),
                         "snapshot": snapshot,
                         "conflicts": [r.conflict_id for r in records],
                         "fingerprint": hashlib.sha256(canonical_json(
                             [r.fingerprint for r in records]).encode(
                             "utf-8")).hexdigest()[:16],
                         "last_fingerprints": new_fps,
                         "actor": actor})
        return records

    # ---- 只读读面 ----

    def get_record(self, conflict_id: str) -> ConflictRecord | None:
        """provenance 重放重建（不存在 → None 不 fabricate）。"""
        if not conflict_id or not conflict_id.startswith("cf_"):
            raise ConflictError(f"E-V09-CONFLICT-INVALID: bad id {conflict_id!r}")
        rows = []
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:conflict-detect'"):
            meta = json.loads(r["metadata_json"])
            if conflict_id in meta.get("conflicts", []):
                rows.append(meta)
        rows.sort(key=lambda m: m.get("seq", 0))
        return None if not rows else rows[0]   # 最新快照记录（dict 形态）