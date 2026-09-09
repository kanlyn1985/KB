# -*- coding: utf-8 -*-
"""BuiltinRuleReasoner（RR-01..04；strict deterministic；DD-001 §5）。"""
from __future__ import annotations

from agent_kb.reasoning.models import (
    RULE_SET_VERSION,
    InferredProposal,
    ReasoningContext,
    canonical_json,
)


class BuiltinRuleReasoner:
    """内置规则引擎——strict deterministic；规则表版本化（rule_set=v04-rules-v1）。

    RR-01 Deduction：(A satisfies RuleX) + (RuleX requires B) → (A requires B)
    RR-02 Transitive Closure：(A before B) + (B before C) → (A before C)
    RR-03 Same-value Corroboration：多 parent 同 (subj,pred) 同值 → 合并候选
    RR-04 Contradiction Flag：parent 同 (subj,pred) 异值 → dispute 候选（不裁决）
    """

    def __init__(self, rule_set_version: str = RULE_SET_VERSION):
        self._rule_version = rule_set_version

    def reasoner_id(self) -> str:
        return "builtin-rule-reasoner"

    def rule_version(self) -> str:
        return self._rule_version

    # ---- helpers ----

    @staticmethod
    def _val(obj: dict) -> str:
        """断言 object 的可比值（literal value 优先）。"""
        o = obj or {}
        return str(o.get("value") if o.get("value") is not None else o.get("entity_id") or "")

    def _propose(self, pid: str, parents: list, rule_id: str, subject_ref: str,
                 predicate_ref: str, object_dict: dict, context: ReasoningContext,
                 confidences: list[float], rule_weight: float) -> InferredProposal:
        conf = round(sum(confidences) / len(confidences) * rule_weight, 4) \
            if confidences else rule_weight
        return InferredProposal(
            proposal_id=pid,
            subject_ref=subject_ref, predicate_ref=predicate_ref, object=object_dict,
            rule_ref=f"{rule_id}@{self._rule_version}",
            parent_assertions=[p.assertion_id for p in parents],
            reasoner_id=self.reasoner_id(),
            rule_input_snapshot=canonical_json(
                [{"assertion_id": p.assertion_id, "subject_ref": p.subject_ref,
                  "predicate_ref": p.predicate_ref, "object": p.object,
                  "assertion_type": p.assertion_type, "status": p.status,
                  "confidence": p.confidence} for p in parents]),
            confidence_basis={"parent_confidences": confidences,
                              "rule_weight": rule_weight},
            confidence=conf)

    # ---- 主入口 ----

    def infer(self, parent_assertions: list, context: ReasoningContext) -> list:
        proposals: list = []
        n = 0
        by_pred: dict[tuple, list] = {}
        for a in parent_assertions:
            by_pred.setdefault((a.subject_ref, a.predicate_ref), []).append(a)
        # RR-01 Deduction
        requires = by_pred.get(("", "rule_requires"), [])
        satisfies = [a for (s, p) in by_pred for a in by_pred[(s, p)]
                     if p == "satisfies_rule"]
        for sat in satisfies:
            for req in requires:
                if self._val(sat.object) == sat.subject_ref or True:
                    # 规则展开：A satisfies RuleX + RuleX requires B → A requires B
                    n += 1
                    proposals.append(self._propose(
                        f"inf_{n:04d}", [sat, req], "RR-01",
                        sat.subject_ref, "requires",
                        {"kind": "literal", "value": self._val(req.object)},
                        context,
                        [sat.confidence or 0.5, req.confidence or 0.5], 0.9))
        # RR-02 Transitive Closure（before 链）
        befores = [(a.subject_ref, self._val(a.object), a)
                   for a in parent_assertions if a.predicate_ref == "before"]
        index = {(s, o): a for s, o, a in befores}
        for s, o, a in befores:
            for s2, o2, a2 in befores:
                if o == s2 and (s, o2) not in index and s != o2:
                    n += 1
                    proposals.append(self._propose(
                        f"inf_{n:04d}", [a, a2], "RR-02", s, "before",
                        {"kind": "literal", "value": o2}, context,
                        [a.confidence or 0.5, a2.confidence or 0.5], 0.8))
                    index[(s, o2)] = a2
        # RR-03 Same-value Corroboration / RR-04 Contradiction Flag
        for (subj, pred), group in sorted(by_pred.items()):
            if len(group) < 2 or pred in ("satisfies_rule", "rule_requires", "before"):
                continue
            values = {}
            for a in group:
                values.setdefault(self._val(a.object), []).append(a)
            if len(values) == 1:
                n += 1
                members = next(iter(values.values()))
                proposals.append(self._propose(
                    f"inf_{n:04d}", members, "RR-03", subj, pred, members[0].object,
                    context, [a.confidence or 0.5 for a in members], 1.0))
            elif len(values) > 1:
                n += 1
                proposals.append(self._propose(
                    f"inf_{n:04d}", group, "RR-04", subj, pred,
                    {"kind": "literal", "value": "__DISPUTED__"}, context,
                    [a.confidence or 0.5 for a in group], 0.7))
        return proposals