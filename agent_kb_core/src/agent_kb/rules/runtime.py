# -*- coding: utf-8 -*-
"""RulePackage Runtime（AKB-V07-IMPL-002；设计 docs/V0.7/ ARCHITECTURE §4）。

RulePackageRuntime：规则包的版本化注册/校验/identity + deterministic provider
实例注入 V0.6 orchestrator（单一 ReasoningEngine 原则——provider 多实例 ≠ 多引擎）。

硬边界：
- 规则只提供**定义**（input_pattern/output_pattern/约束），不直接产生事实——
  候选生成仍走 V0.4 ReasoningEngine（create_candidate 唯一边界）；
- 规则不得绕过 governance（候选恒 inferred/candidate）；
- 零 LLM/vector/数据库依赖；零 migration；
- provenance：graph:rule-load 审计（复用 akb_provenance）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_kb.reasoning import ReasonerProvider
from agent_kb.reasoning.models import InferredProposal, ReasoningContext, canonical_json


class RulePackageError(ValueError):
    """fail-closed：RulePackage runtime 错误。"""


@dataclass(frozen=True)
class RuleSpec:
    """规则定义（声明式；语义冻结于 rule_version）。"""
    rule_id: str
    rule_version: str
    rule_type: str
    input_pattern: dict
    output_pattern: dict
    constraints: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RulePackage:
    """规则包（versioned；domain bindings 声明消费域）。"""
    package_id: str
    version: str
    rules: tuple
    domain_bindings: tuple


@dataclass(frozen=True)
class RegisteredPackage:
    """注册后的包（identity + provider 实例）。"""
    package_ref: str
    package: RulePackage
    provider: ReasonerProvider


class PatternRuleProvider:
    """确定性 pattern-matching provider（RulePackage 的执行实例）。"""

    def __init__(self, package: RulePackage):
        self.package = package

    def reasoner_id(self) -> str:
        return f"rulepkg:{self.package.package_id}"

    def rule_version(self) -> str:
        return self.package.version

    def infer(self, parent_assertions: list, context: ReasoningContext) -> list:
        """按包内规则逐条模式匹配 → InferredProposal 列表（确定性）。"""
        proposals = []
        for spec in self.package.rules:
            pat = spec.input_pattern
            need = sorted(pat.get("predicates", []))
            if not need:
                continue
            by_pred = {}
            for a in parent_assertions:
                by_pred.setdefault(a.predicate_ref, []).append(a)
            missing = [p for p in need if p not in by_pred]
            if missing:
                continue
            pool = [sorted(by_pred[p], key=lambda a: a.assertion_id) for p in need]
            n = 1
            for lst in pool:
                n *= len(lst)
            used = set()
            for i in range(min(n, 64)):
                combo, k = [], i
                for lst in reversed(pool):
                    k, idx = divmod(k, len(lst))
                    combo.append(lst[idx])
                combo.reverse()
                src = combo[0]
                if src.assertion_id in used:
                    continue
                used.add(src.assertion_id)
                proposals.append(InferredProposal(
                    proposal_id=f"prop_{spec.rule_id}_{i:04d}",
                    subject_ref=spec.output_pattern.get("subject_from",
                                                        src.subject_ref),
                    predicate_ref=spec.output_pattern.get("predicate", ""),
                    object=src.object,
                    rule_ref=f"{spec.rule_id}@{spec.rule_version}",
                    parent_assertions=[a.assertion_id for a in combo],
                    reasoner_id=self.reasoner_id(),
                    rule_input_snapshot=canonical_json({
                        "package_id": self.package.package_id,
                        "package_version": self.package.version,
                        "rule_id": spec.rule_id,
                        "matched": [a.assertion_id for a in combo]}),
                ))
        return proposals


class RulePackageRuntime:
    """规则包运行时：注册/校验/identity/provider 实例/provenance（零推理执行）。"""

    def __init__(self, connection, registry: dict | None = None,
                 actor_id: str = "system:rule-runtime"):
        self.connection = connection
        self.registry = registry if registry is not None else {}
        self.actor_id = actor_id

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = Provenance(self.connection).record(
            actor_id=self.actor_id, actor_kind=actor_kind_of(self.actor_id),
            activity=activity, inputs=details.get("package_ids", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _validate(package: RulePackage, bound_packs: dict) -> None:
        if not package.package_id or not package.package_id.strip():
            raise RulePackageError("E-V07-RULE-INVALID: empty package_id")
        if not package.version or not package.version.strip():
            raise RulePackageError(
                f"E-V07-RULE-INVALID: {package.package_id} empty version")
        if not package.rules:
            raise RulePackageError(
                f"E-V07-RULE-INVALID: {package.package_id} has no rules")
        for r in package.rules:
            if not r.rule_id or not r.rule_id.strip():
                raise RulePackageError(
                    f"E-V07-RULE-INVALID: {package.package_id} empty rule_id")
            if not r.rule_version or not r.rule_version.strip():
                raise RulePackageError(
                    f"E-V07-RULE-INVALID: rule {r.rule_id} empty rule_version")
            if r.rule_type.split("_")[0] not in ("deduction", "transitive",
                                                 "corroboration", "contradiction",
                                                 "domain"):
                raise RulePackageError(
                    f"E-V07-RULE-INVALID: rule {r.rule_id} unknown rule_type"
                    f" {r.rule_type}")
            if not r.input_pattern.get("predicates"):
                raise RulePackageError(
                    f"E-V07-RULE-INVALID: rule {r.rule_id} empty input predicates")
        for binding in package.domain_bindings:
            if "@" not in binding:
                raise RulePackageError(
                    f"E-V07-RULE-INVALID: bad binding {binding!r} (need"
                    " domain_id@version)")
            did, ver = binding.split("@", 1)
            if bound_packs is not None and (did, ver) not in bound_packs:
                raise RulePackageError(
                    f"E-V07-DOMAIN-NOT-LOADED: binding {binding} not loaded")

    def register(self, package: RulePackage, *,
                 domain_runtime=None) -> RegisteredPackage:
        bound_packs = None
        if domain_runtime is not None:
            bound_packs = {(lp.domain_id, lp.version): lp
                           for lp in domain_runtime.list_packs()}
        self._validate(package, bound_packs)
        key = (package.package_id, package.version)
        if key in self.registry:
            return self.registry[key]
        package_ref = self.package_identity(package)
        registered = RegisteredPackage(
            package_ref=package_ref, package=package,
            provider=PatternRuleProvider(package))
        self._audit(
            activity="graph:rule-load",
            details={"package_ids": [package.package_id],
                     "package_ref": package_ref, "version": package.version,
                     "rules": [r.rule_id for r in package.rules],
                     "domain_bindings": list(package.domain_bindings)})
        self.registry[key] = registered
        return registered

    @staticmethod
    def package_identity(package: RulePackage) -> str:
        payload = {
            "package_id": package.package_id,
            "version": package.version,
            "rules": sorted(
                (r.rule_id, r.rule_version, r.rule_type,
                 canonical_json(r.input_pattern), canonical_json(r.output_pattern))
                for r in package.rules),
            "domain_bindings": sorted(package.domain_bindings),
        }
        return "rlp_" + hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()[:16]

    def get_package(self, package_id: str,
                    version: str | None = None) -> RegisteredPackage | None:
        if version is not None:
            return self.registry.get((package_id, version))
        cands = [k for k in self.registry if k[0] == package_id]
        if not cands:
            return None
        return self.registry[max(cands)]

    def list_packages(self) -> list[RegisteredPackage]:
        return [self.registry[k] for k in sorted(self.registry)]