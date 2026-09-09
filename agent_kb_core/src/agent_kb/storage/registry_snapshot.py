# -*- coding: utf-8 -*-
"""V0.10 Registry Snapshot Runtime（AKB-V10-IMPL-003；设计 ARCHITECTURE §4）。

将 V0.7/V0.9 runtime registry 的内存态转换为 deterministic、immutable、
可恢复的 snapshot。

MIGRATION DECISION：**NO MIGRATION 维持**——snapshot payload 保存在
akb_provenance metadata（graph:registry-snapshot-create；canonical JSON）。
零新表：registry 快照为低频治理动作（跨进程恢复时点触发），payload 为
registry 条目摘要（key@version + 内容 ref——非全量 pack 内容），基数 10^1-10^2
级，provenance metadata 完全可行。migration 18 触发条件：registry 条目数
增长到全量 payload 超出 metadata 实用上限（单活动 metadata 数十 KB 级）或
需要快照间结构化 diff 查询——出现时按任务书评估。

原则：
- deterministic：snapshot_id = "rgs_"+SHA256(canonical_json({registry_type,
  schema_version, entries}))——零 timestamp/零 random；同输入同 id；
- canonical ordering：entries 按 entry_key ASC 排序；duplicate entry_key
  fail-close（同 key 双版本语义冲突——不可静默去重）；
- immutable：RegistrySnapshot frozen dataclass；
- restore：fingerprint 校验 + schema_version 校验 fail-close；
- 零 frozen registry 行为修改（只读引用 registry 内容）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_REGISTRY_TYPES = ("domain_pack", "rule_package", "policy",
                            "causal")


class RegistrySnapshotError(ValueError):
    """fail-closed：RegistrySnapshot 错误。"""


@dataclass(frozen=True)
class RegistrySnapshot:
    """immutable registry 快照（canonical payload + fingerprint）。"""
    snapshot_id: str
    schema_version: int
    registry_type: str
    created_from: str
    entries: tuple                     # {"entry_key","content_ref","detail"} canonical 序
    fingerprint: str
    provenance_refs: tuple


def _entry_key_from_obj(key, value, registry_type: str) -> dict:
    """registry 条目 → canonical entry（key@version + content ref）。"""
    if isinstance(key, tuple):
        k = "@".join(str(part) for part in key)
    else:
        k = str(key)
    # value 提取 content ref（runtime 已派生的 identity ref——零新算法）
    content_ref = None
    detail = ""
    if hasattr(value, "pack_ref"):             # LoadedPack
        content_ref = value.pack_ref
        detail = f"namespace={value.namespace}"
    elif hasattr(value, "package_ref"):        # RegisteredPackage
        content_ref = value.package_ref
        detail = f"package_id={value.package.package_id}"
    elif hasattr(value, "fingerprint"):        # CausalProjection
        content_ref = value.fingerprint
        detail = f"projection_id={value.projection_id}"
    elif isinstance(value, dict) and "policy_ref" in value:   # policy 激活态
        content_ref = value["policy_ref"]
        detail = "activated"
    elif isinstance(value, str):               # policy_ref str
        content_ref = value
        detail = "activated"
    else:
        content_ref = hashlib.sha256(canonical_json(
            repr(value)).encode("utf-8")).hexdigest()[:16]
        detail = "opaque"
    return {"entry_key": k, "content_ref": content_ref, "detail": detail}


def registry_snapshot_identity(*, registry_type: str, schema_version: int,
                               entries: tuple) -> str:
    """deterministic snapshot_id（canonical JSON；entries 按 entry_key 排序）。"""
    payload = {"registry_type": registry_type,
               "schema_version": schema_version,
               "entries": sorted(entries, key=lambda e: e["entry_key"])}
    return "rgs_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class RegistrySnapshotRuntime:
    """registry 快照运行时（只读引用 + 审计 + 校验恢复）。"""

    def __init__(self, connection, actor_id: str = "system:registry-snapshot"):
        self.connection = connection
        self.actor_id = actor_id

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:registry-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("targets", []),
            metadata=details)
        return rec.provenance_id

    # ---- create ----

    def create_snapshot(self, registry, *, registry_type: str,
                        created_from: str = "runtime:memory",
                        actor_id: str | None = None) -> RegistrySnapshot:
        """registry → RegistrySnapshot（幂等：同状态同 id + 零重复审计）。"""
        if registry_type not in SUPPORTED_REGISTRY_TYPES:
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: registry_type {registry_type!r}"
                f" not in {SUPPORTED_REGISTRY_TYPES}")
        if not hasattr(registry, "items"):
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: registry is not a mapping")
        raw_entries = [_entry_key_from_obj(k, v, registry_type)
                       for k, v in registry.items()]
        # duplicate entry_key fail-close（同 key 语义冲突不可静默去重）
        keys = [e["entry_key"] for e in raw_entries]
        if len(keys) != len(set(keys)):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: duplicate entry_key {dupes}"
                " (fail-close, no silent dedup)")
        entries = tuple(sorted(raw_entries, key=lambda e: e["entry_key"]))
        snapshot_id = registry_snapshot_identity(
            registry_type=registry_type,
            schema_version=SNAPSHOT_SCHEMA_VERSION, entries=entries)
        existing = self.get_snapshot(snapshot_id)
        if existing is not None:
            return existing                    # 幂等（零重复审计）
        payload = {"registry_type": registry_type,
                   "schema_version": SNAPSHOT_SCHEMA_VERSION,
                   "entries": list(entries)}
        fingerprint = hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]
        actor = actor_id or self.actor_id
        prov = self._audit(
            activity="graph:registry-snapshot-create",
            details={"targets": [registry_type],
                     "snapshot_id": snapshot_id, "registry_type":
                     registry_type, "schema_version":
                     SNAPSHOT_SCHEMA_VERSION, "entry_count": len(entries),
                     "entries": list(entries), "fingerprint": fingerprint,
                     "created_from": created_from, "actor": actor})
        return RegistrySnapshot(
            snapshot_id=snapshot_id,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            registry_type=registry_type, created_from=created_from,
            entries=entries, fingerprint=fingerprint,
            provenance_refs=(prov,))

    # ---- 读面（provenance 重放）----

    def get_snapshot(self, snapshot_id: str) -> RegistrySnapshot | None:
        if not snapshot_id or not snapshot_id.startswith("rgs_"):
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: bad id {snapshot_id!r}")
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:registry-snapshot-create'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("snapshot_id") != snapshot_id:
                continue
            rows.append((meta, r["provenance_id"]))
        rows.sort(key=lambda x: x[0].get("seq", 0))
        if not rows:
            return None
        m, prov = rows[0]
        return RegistrySnapshot(
            snapshot_id=snapshot_id, schema_version=m["schema_version"],
            registry_type=m["registry_type"],
            created_from=m.get("created_from", ""),
            entries=tuple(m["entries"]), fingerprint=m["fingerprint"],
            provenance_refs=(prov,))

    def list_snapshots(self, *, registry_type: str | None = None) -> list:
        out = []
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:registry-snapshot-create'"):
            meta = json.loads(r["metadata_json"])
            if registry_type and meta.get("registry_type") != registry_type:
                continue
            s = self.get_snapshot(meta["snapshot_id"])
            if s is not None:
                out.append(s)
        return sorted(out, key=lambda s: s.snapshot_id)

    # ---- restore ----

    @staticmethod
    def restore_snapshot(snapshot: RegistrySnapshot) -> dict:
        """fingerprint + schema_version 校验 → deterministic 恢复载荷。"""
        if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: schema_version"
                f" {snapshot.schema_version} unsupported (expected"
                f" {SNAPSHOT_SCHEMA_VERSION})")
        payload = {"registry_type": snapshot.registry_type,
                   "schema_version": snapshot.schema_version,
                   "entries": list(snapshot.entries)}
        check = hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]
        if check != snapshot.fingerprint:
            raise RegistrySnapshotError(
                f"E-V10-REGISTRY-INVALID: fingerprint mismatch"
                f" (snapshot integrity failure)")
        return {"registry_type": snapshot.registry_type,
                "entries": sorted(snapshot.entries,
                                  key=lambda e: e["entry_key"]),
                "fingerprint": snapshot.fingerprint}