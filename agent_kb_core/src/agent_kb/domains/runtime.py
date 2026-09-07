# -*- coding: utf-8 -*-
"""DomainPack Runtime（AKB-V07-IMPL-001；设计 docs/V0.7/ V0.7_DESIGN §3.1）。

复用 frozen DomainPack schema（agent_kb/domains/schema.py）与 loader
（agent_kb/domains/loader.py）——零 schema 修改。

- load_runtime_pack：frozen pack → LoadedPack（校验 + namespace 分配 + 确定性
  pack identity + provenance 审计）；
- deterministic：pack_ref = SHA256(canonical_json({domain_id, version, 内容}))——
  同 pack 同 ref；跨实例全等；
- fail-closed：非法 pack / namespace 冲突 / 重复版本 → 显式错误；
- provenance：graph:pack-load 审计落 akb_provenance（复用，零第二套系统）；
- 边界：pack 只提供词汇/约束/配置——不产生事实、不写图、不参与推理执行。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent_kb.domains.loader import DomainPackError, load_domain_pack
from agent_kb.domains.schema import DomainPack
from agent_kb.reasoning.models import canonical_json

DEFAULT_NAMESPACE_FMT = "{domain_id}"
NAMESPACE_RE_STRICT = True


class DomainPackRuntimeError(ValueError):
    """fail-closed：DomainPack runtime 错误。"""


@dataclass(frozen=True)
class LoadedPack:
    """运行时域包（frozen DomainPack + namespace + 确定性 identity）。"""
    domain_id: str
    version: str
    namespace: str
    pack_ref: str
    pack: DomainPack                  # frozen dataclass 原样复用
    terminology_namespaced: dict      # ns 前缀化术语表（只读视图）


class DomainPackRuntime:
    """DomainPack 运行时：加载/校验/identity/provenance（零推理执行）。"""

    def __init__(self, connection, registry: dict | None = None,
                 actor_id: str = "system:pack-runtime"):
        self.connection = connection
        # registry: (domain_id, version) -> LoadedPack（实例级；跨实例由 pack_ref 保证一致）
        self.registry = registry if registry is not None else {}
        self.actor_id = actor_id

    # ---- helpers ----

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = Provenance(self.connection).record(
            actor_id=self.actor_id, actor_kind=actor_kind_of(self.actor_id),
            activity=activity, inputs=details.get("domain_ids", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _namespaced_terminology(pack: DomainPack, namespace: str) -> dict:
        """术语表 ns 前缀化视图（只读派生；不改 frozen pack）。"""
        return {f"{namespace}:{term}": list(aliases)
                for term, aliases in pack.terminology.items()}

    @staticmethod
    def _validate_pack(pack: DomainPack) -> None:
        """pack 校验（fail-closed）：必填字段/类型面/术语结构。"""
        if not pack.domain_id or not pack.domain_id.strip():
            raise DomainPackRuntimeError("E-V07-PACK-INVALID: empty domain_id")
        if not pack.version or not pack.version.strip():
            raise DomainPackRuntimeError(
                f"E-V07-PACK-INVALID: {pack.domain_id} empty version")
        for ot_name, spec in pack.object_types.items():
            if not ot_name or not ot_name.strip():
                raise DomainPackRuntimeError(
                    f"E-V07-PACK-INVALID: {pack.domain_id} empty object type name")
        for rt_name, spec in pack.relation_types.items():
            if not rt_name or not rt_name.strip():
                raise DomainPackRuntimeError(
                    f"E-V07-PACK-INVALID: {pack.domain_id} empty relation type name")
            for st in spec.source_types:
                if st and st not in pack.object_types:
                    raise DomainPackRuntimeError(
                        f"E-V07-PACK-INVALID: {pack.domain_id} relation"
                        f" {rt_name} unknown source type {st}")
            for tt in spec.target_types:
                if tt and tt not in pack.object_types:
                    raise DomainPackRuntimeError(
                        f"E-V07-PACK-INVALID: {pack.domain_id} relation"
                        f" {rt_name} unknown target type {tt}")
        for term, aliases in pack.terminology.items():
            if not term.strip():
                raise DomainPackRuntimeError(
                    f"E-V07-PACK-INVALID: {pack.domain_id} empty terminology key")

    # ---- 主入口 ----

    def load_runtime_pack(self, pack_source, *, namespace: str | None = None) -> LoadedPack:
        """加载 frozen DomainPack → 校验 → namespace 分配 → 确定性 identity → 审计。

        pack_source: Path（frozen loader 通道）或 DomainPack 实例（测试/程序化）。
        """
        if isinstance(pack_source, DomainPack):
            pack = pack_source
        else:
            try:
                pack = load_domain_pack(Path(pack_source))
            except DomainPackError as exc:
                raise DomainPackRuntimeError(
                    f"E-V07-PACK-INVALID: loader rejected pack: {exc}") from exc
        self._validate_pack(pack)
        ns = namespace or DEFAULT_NAMESPACE_FMT.format(domain_id=pack.domain_id)
        if not ns or ":" in ns:
            raise DomainPackRuntimeError(
                f"E-V07-PACK-INVALID: namespace {ns!r} must be non-empty and"
                " contain no ':'")
        # namespace 冲突（同 ns 不同 domain_id）fail-closed
        for (did, _v), loaded in self.registry.items():
            if loaded.namespace == ns and did != pack.domain_id:
                raise DomainPackRuntimeError(
                    f"E-V07-PACK-NAMESPACE-CONFLICT: {ns} already owned by"
                    f" {did}")
        # 同 domain+version 重复加载 → 幂等返回（零重复审计）
        key = (pack.domain_id, pack.version)
        if key in self.registry:
            return self.registry[key]
        pack_ref = self.pack_identity(pack)
        loaded = LoadedPack(
            domain_id=pack.domain_id, version=pack.version, namespace=ns,
            pack_ref=pack_ref, pack=pack,
            terminology_namespaced=self._namespaced_terminology(pack, ns))
        self._audit(
            activity="graph:pack-load",
            details={"domain_ids": [pack.domain_id], "pack_ref": pack_ref,
                     "version": pack.version, "namespace": ns,
                     "object_types": sorted(pack.object_types),
                     "relation_types": sorted(pack.relation_types),
                     "terminology_terms": sorted(pack.terminology)})
        self.registry[key] = loaded
        return loaded

    @staticmethod
    def pack_identity(pack: DomainPack) -> str:
        """deterministic pack identity：SHA256(canonical_json({domain_id, version,
        词汇/类型面}))——同 pack 同 ref（跨实例全等）。"""
        payload = {
            "domain_id": pack.domain_id,
            "version": pack.version,
            "object_types": sorted(pack.object_types),
            "relation_types": sorted(
                (rt, tuple(spec.source_types), tuple(spec.target_types))
                for rt, spec in pack.relation_types.items()),
            "terminology": sorted(
                (term, tuple(aliases))
                for term, aliases in pack.terminology.items()),
        }
        return "dpr_" + hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]

    # ---- 查询面（只读）----

    def get_pack(self, domain_id: str, version: str | None = None) -> LoadedPack | None:
        if version is not None:
            return self.registry.get((domain_id, version))
        # 最新版本（按 (domain_id, version) 键序取最大）
        candidates = [k for k in self.registry if k[0] == domain_id]
        if not candidates:
            return None
        return self.registry[max(candidates)]

    def list_packs(self) -> list[LoadedPack]:
        return [self.registry[k] for k in sorted(self.registry)]