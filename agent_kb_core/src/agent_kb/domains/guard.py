# -*- coding: utf-8 -*-
"""CrossDomainGuard（AKB-V07-IMPL-004；设计 docs/V0.7/ ARCHITECTURE §6）。

V0.7 runtime 层门控：domain namespace 校验 / pack 隔离 / rule binding 校验 /
reasoning context 跨域访问控制。

硬边界：
- fail-closed：未授权跨域 → E-V07-CROSS-DOMAIN-BLOCKED；namespace 冲突 →
  E-V07-NAMESPACE-CONFLICT；
- deterministic：guard decision = canonical JSON 派生 fingerprint——
  同（graph state + pack + policy + context）→ 同 decision；
- provenance：graph:cross-domain-allow / graph:cross-domain-block 复用
  akb_provenance（source_domain/target_domain/pack_ref/policy_ref/decision）；
- 零 candidate 产生、零 governance 生命周期改变、V0.6 orchestrator 单向兼容
  （guard 在编排外围调用，不修改其内部逻辑）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json


class CrossDomainError(ValueError):
    """fail-closed：跨域守卫错误。"""


@dataclass(frozen=True)
class GuardDecision:
    """守卫裁决（immutable；deterministic fingerprint）。"""
    decision: str                      # "allow" | "block"
    source_domain: str
    target_domain: str
    pack_ref: str
    policy_ref: str
    fingerprint: str                   # decision 的 canonical 派生
    reason: str


class CrossDomainGuard:
    """跨域守卫：namespace/binding/context 访问控制（fail-closed + deterministic）。"""

    def __init__(self, connection, domain_runtime=None, rule_runtime=None,
                 policy_runtime=None, actor_id: str = "system:guard"):
        self.connection = connection
        self.domain_runtime = domain_runtime
        self.rule_runtime = rule_runtime
        self.policy_runtime = policy_runtime
        self.actor_id = actor_id

    # ---- helpers ----

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = Provenance(self.connection).record(
            actor_id=self.actor_id, actor_kind=actor_kind_of(self.actor_id),
            activity=activity, inputs=details.get("domains", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _decision_fingerprint(decision: str, source: str, target: str,
                              pack_ref: str, policy_ref: str,
                              subject: str) -> str:
        payload = {"decision": decision, "source_domain": source,
                   "target_domain": target, "pack_ref": pack_ref,
                   "policy_ref": policy_ref, "subject": subject}
        return "gcd_" + hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]

    # ---- namespace 校验 ----

    def check_namespace(self, namespace: str, *, expected_owner: str) -> None:
        """namespace 归属校验：ns 必须被 expected_owner 持有（冲突 fail-close）。"""
        if self.domain_runtime is None:
            return
        owners = {lp.namespace: lp.domain_id for lp in
                  self.domain_runtime.list_packs()}
        if namespace not in owners:
            raise CrossDomainError(
                f"E-V07-NAMESPACE-CONFLICT: namespace {namespace!r} not"
                " registered")
        if owners[namespace] != expected_owner:
            raise CrossDomainError(
                f"E-V07-NAMESPACE-CONFLICT: namespace {namespace!r} owned by"
                f" {owners[namespace]}, not {expected_owner}")

    def check_rule_binding(self, package_ref_pair: tuple) -> None:
        """rule package domain binding 校验：绑定的 pack 必须已加载且 ns 无冲突。"""
        if self.rule_runtime is None or self.domain_runtime is None:
            return
        pkg = self.rule_runtime.get_package(*package_ref_pair)
        if pkg is None:
            raise CrossDomainError(
                f"E-V07-RULE-PACK-NOT-REGISTERED: {package_ref_pair}")
        owners = {lp.domain_id: lp.namespace for lp in
                  self.domain_runtime.list_packs()}
        for binding in pkg.package.domain_bindings:
            did, _ver = binding.split("@", 1)
            if did not in owners:
                raise CrossDomainError(
                    f"E-V07-NAMESPACE-CONFLICT: binding {binding} domain"
                    " not loaded")

    # ---- 主入口：reasoning context 跨域访问控制 ----

    def guard_context(self, *, root_domain: str, context_domains: tuple,
                      pack_ref: str, policy_ref: str,
                      allow_cross_domain: bool = False) -> list[GuardDecision]:
        """对一次 reasoning context 的跨域访问逐域裁决（allow/block + 审计）。

        context_domains = context 实际触达的域（如候选谓词/实体所属 ns）。
        root_domain 之外的域 = 跨域：未授权 → block（fail-closed）。
        """
        decisions: list[GuardDecision] = []
        for target in sorted(set(context_domains)):
            if target == root_domain:
                fp = self._decision_fingerprint("allow", root_domain, target,
                                                pack_ref, policy_ref,
                                                "intra-domain")
                d = GuardDecision(decision="allow", source_domain=root_domain,
                                  target_domain=target, pack_ref=pack_ref,
                                  policy_ref=policy_ref, fingerprint=fp,
                                  reason="intra-domain")
            else:
                if allow_cross_domain:
                    fp = self._decision_fingerprint(
                        "allow", root_domain, target, pack_ref, policy_ref,
                        "cross-domain-authorized")
                    d = GuardDecision(decision="allow",
                                      source_domain=root_domain,
                                      target_domain=target, pack_ref=pack_ref,
                                      policy_ref=policy_ref, fingerprint=fp,
                                      reason="cross-domain-authorized")
                    self._audit(
                        activity="graph:cross-domain-allow",
                        details={"domains": sorted({root_domain, target}),
                                 "source_domain": root_domain,
                                 "target_domain": target,
                                 "pack_ref": pack_ref, "policy_ref": policy_ref,
                                 "decision": "allow", "fingerprint": fp})
                else:
                    fp = self._decision_fingerprint(
                        "block", root_domain, target, pack_ref, policy_ref,
                        "cross-domain-unauthorized")
                    d = GuardDecision(decision="block",
                                      source_domain=root_domain,
                                      target_domain=target, pack_ref=pack_ref,
                                      policy_ref=policy_ref, fingerprint=fp,
                                      reason="cross-domain-unauthorized")
                    self._audit(
                        activity="graph:cross-domain-block",
                        details={"domains": sorted({root_domain, target}),
                                 "source_domain": root_domain,
                                 "target_domain": target,
                                 "pack_ref": pack_ref, "policy_ref": policy_ref,
                                 "decision": "block", "fingerprint": fp})
                    raise CrossDomainError(
                        f"E-V07-CROSS-DOMAIN-BLOCKED: {root_domain} ->"
                        f" {target} (fingerprint {fp})")
            decisions.append(d)
        return decisions

    def enforce(self, decisions: list[GuardDecision]) -> None:
        """对已有裁决集执行 fail-close：任一 block → 抛错（不 fabricate 放行）。"""
        for d in decisions:
            if d.decision == "block":
                raise CrossDomainError(
                    f"E-V07-CROSS-DOMAIN-BLOCKED: {d.source_domain} ->"
                    f" {d.target_domain} (fingerprint {d.fingerprint})")