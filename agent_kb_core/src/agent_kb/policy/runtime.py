# -*- coding: utf-8 -*-
"""ReasoningPolicy Runtime（AKB-V07-IMPL-003；设计 docs/V0.7/ ARCHITECTURE §5）。

ReasoningPolicyRuntime：策略的版本化激活/校验/identity + 预算管理 + 审计。
Policy 即数据——只控制 reasoning 行为（启停/预算/顺序），零事实产生、零
governance 绕过、零 frozen 修改。

硬边界：
- enabled_rules ⊆ 已注册规则（RulePackageRuntime）；
- per_domain_budgets 键 ⊆ 已加载 namespace（DomainPackRuntime）；
- 深度/候选预算 ≤ V0.6 frozen 上限（4/1024）——policy 只能收紧不能放宽；
- provenance：graph:reason-policy 审计（激活快照 before/after CanonicalJSON）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json


class PolicyError(ValueError):
    """fail-closed：ReasoningPolicy 错误。"""


@dataclass(frozen=True)
class ReasoningPolicy:
    """策略（versioned；policy 即数据）。"""
    policy_id: str
    version: str
    enabled_rules: tuple                  # ("flow-rules@1.0.0", ...) 包@版本
    per_domain_budgets: dict              # {"industrial": {"max_candidates": 64}}
    load_order: tuple                     # ("flow-rules@1.0.0", ...) 确定性顺序
    max_derivation_depth: int = 4         # ≤ V0.6 frozen 上限
    max_candidates: int = 1024            # ≤ V0.6 frozen 上限
    status_filter: tuple = ("valid", "flagged")


class ReasoningPolicyRuntime:
    """策略运行时：激活/校验/identity/预算管理/审计（零推理执行）。"""

    # V0.6 frozen 上限（policy 只能收紧）
    HARD_MAX_DEPTH = 4
    HARD_MAX_CANDIDATES = 1024

    def __init__(self, connection, registry: dict | None = None,
                 actor_id: str = "system:policy-runtime"):
        self.connection = connection
        self.registry = registry if registry is not None else {}
        self.actor_id = actor_id

    # ---- helpers ----

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = Provenance(self.connection).record(
            actor_id=self.actor_id, actor_kind=actor_kind_of(self.actor_id),
            activity=activity, inputs=details.get("policy_ids", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _validate(policy: ReasoningPolicy, registered: dict, namespaces: set) -> None:
        if not policy.policy_id or not policy.policy_id.strip():
            raise PolicyError("E-V07-POLICY-INVALID: empty policy_id")
        if not policy.version or not policy.version.strip():
            raise PolicyError(
                f"E-V07-POLICY-INVALID: {policy.policy_id} empty version")
        if not policy.enabled_rules:
            raise PolicyError(
                f"E-V07-POLICY-INVALID: {policy.policy_id} enables no rules")
        for ref in policy.enabled_rules:
            if "@" not in ref:
                raise PolicyError(
                    f"E-V07-POLICY-INVALID: bad rule ref {ref!r} (need"
                    " package_id@version)")
            if registered is not None and ref not in registered:
                raise PolicyError(
                    f"E-V07-POLICY-INVALID: rule {ref} not registered")
        for ns, budget in policy.per_domain_budgets.items():
            if namespaces is not None and ns not in namespaces:
                raise PolicyError(
                    f"E-V07-POLICY-INVALID: domain {ns} not loaded")
            if not isinstance(budget, dict):
                raise PolicyError(
                    f"E-V07-POLICY-INVALID: budget for {ns} must be dict")
        # 深度/候选预算 ≤ V0.6 frozen 上限（policy 只能收紧）
        if not isinstance(policy.max_derivation_depth, int) or \
                policy.max_derivation_depth < 1 or \
                policy.max_derivation_depth > ReasoningPolicyRuntime.HARD_MAX_DEPTH:
            raise PolicyError(
                f"E-V07-POLICY-INVALID: max_derivation_depth"
                f" {policy.max_derivation_depth} out of 1.."
                f"{ReasoningPolicyRuntime.HARD_MAX_DEPTH}")
        if not isinstance(policy.max_candidates, int) or \
                policy.max_candidates < 1 or \
                policy.max_candidates > ReasoningPolicyRuntime.HARD_MAX_CANDIDATES:
            raise PolicyError(
                f"E-V07-POLICY-INVALID: max_candidates {policy.max_candidates}"
                f" out of 1..{ReasoningPolicyRuntime.HARD_MAX_CANDIDATES}")
        if policy.status_filter and any(
                s not in ("valid", "flagged") for s in policy.status_filter):
            raise PolicyError(
                f"E-V07-POLICY-INVALID: status_filter {policy.status_filter}"
                " (invalidated/hypothesized cannot be enabled)")
        # load_order ⊆ enabled_rules
        for ref in policy.load_order:
            if ref not in policy.enabled_rules:
                raise PolicyError(
                    f"E-V07-POLICY-INVALID: load_order {ref} not enabled")

    # ---- 主入口 ----

    def activate(self, policy: ReasoningPolicy, *, rule_runtime=None,
                 domain_runtime=None) -> dict:
        """激活策略 → 校验（引用完整性/预算上限/状态合法）→ identity → 审计
        （幂等：同 policy_id+version 重复激活零重复审计）。"""
        registered = None
        if rule_runtime is not None:
            registered = {f"{k[0]}@{k[1]}": v for k, v
                          in rule_runtime.registry.items()}
        namespaces = None
        if domain_runtime is not None:
            namespaces = {lp.namespace for lp in domain_runtime.list_packs()}
        self._validate(policy, registered, namespaces)
        key = (policy.policy_id, policy.version)
        if key in self.registry:
            return {"policy_ref": self.registry[key],
                    "idempotent_hit": True, "policy": policy}
        policy_ref = self.policy_identity(policy)
        before = canonical_json(sorted(self.registry.keys().__iter__().__next__()
                                       if False else []))  # 占位（首激活 before 空）
        before = canonical_json(sorted(f"{k[0]}@{k[1]}" for k in self.registry))
        self._audit(
            activity="graph:reason-policy",
            details={"policy_ids": [policy.policy_id],
                     "policy_ref": policy_ref, "version": policy.version,
                     "enabled_rules": sorted(policy.enabled_rules),
                     "per_domain_budgets": policy.per_domain_budgets,
                     "max_derivation_depth": policy.max_derivation_depth,
                     "max_candidates": policy.max_candidates,
                     "before_snapshot": before,
                     "after_snapshot": canonical_json(
                         sorted([f"{k[0]}@{k[1]}" for k in self.registry] +
                                [f"{policy.policy_id}@{policy.version}"]))})
        self.registry[key] = policy_ref
        return {"policy_ref": policy_ref, "idempotent_hit": False,
                "policy": policy, "before_snapshot": before}

    @staticmethod
    def policy_identity(policy: ReasoningPolicy) -> str:
        """deterministic policy_id：SHA256(canonical_json(policy 全量))。"""
        payload = {
            "policy_id": policy.policy_id,
            "version": policy.version,
            "enabled_rules": sorted(policy.enabled_rules),
            "per_domain_budgets": policy.per_domain_budgets,
            "load_order": sorted(policy.load_order),
            "max_derivation_depth": policy.max_derivation_depth,
            "max_candidates": policy.max_candidates,
            "status_filter": sorted(policy.status_filter),
        }
        return "pol_" + hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]

    def get_policy(self, policy_id: str,
                   version: str | None = None) -> str | None:
        if version is not None:
            return self.registry.get((policy_id, version))
        cands = [k for k in self.registry if k[0] == policy_id]
        if not cands:
            return None
        return self.registry[max(cands)]

    def list_policies(self) -> list[str]:
        return [f"{k[0]}@{k[1]}" for k in sorted(self.registry)]

    # ---- 预算管理（编排面应用）----

    def apply_budgets(self, policy: ReasoningPolicy, domain_ns: str,
                      candidate_count: int) -> dict:
        """预算执行：返回该域下裁剪后的预算判定（fail-closed 超限拒绝）。"""
        budget = policy.per_domain_budgets.get(domain_ns, {})
        max_c = budget.get("max_candidates", policy.max_candidates)
        if candidate_count > max_c:
            raise PolicyError(
                f"E-V07-BUDGET-EXCEEDED: domain {domain_ns} candidates"
                f" {candidate_count} > {max_c}")
        return {"domain": domain_ns, "allowed": candidate_count,
                "budget": max_c}

    def check_enabled(self, policy: ReasoningPolicy,
                      package_ref_pair: tuple) -> bool:
        """规则启停语义：package_id@version 是否被策略启用。"""
        return f"{package_ref_pair[0]}@{package_ref_pair[1]}" \
            in policy.enabled_rules