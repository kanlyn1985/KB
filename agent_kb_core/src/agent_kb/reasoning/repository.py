# -*- coding: utf-8 -*-
"""Reasoning run repository + trace query service（AKB-V04-IMPL-002）。

- ReasoningRunRepository：akb_reasoning_runs 读写（fingerprint 锚幂等——V0.3 锚模式）；
- trace_inference_chain：递归展开 parent 链（DD-003 §3）——确定性 + 环/缺失检测。
"""
from __future__ import annotations

import json

from agent_kb.reasoning.models import canonical_json, reasoning_fingerprint


class ReasoningRunRepository:
    """akb_reasoning_runs 仓储（migration 14 载体；production 执行待批准——仅测试库验证）。"""

    def __init__(self, connection):
        self.connection = connection

    def create_running(self, *, parent_ids: list[str], reasoner_id: str,
                       rule_version: str, configuration_hash: str, actor_id: str,
                       policy_version: str, fingerprint: str | None,
                       run_id: str) -> str:
        self.connection.execute(
            "INSERT INTO akb_reasoning_runs (run_id, parent_ids_json, reasoner_id,"
            " rule_version, configuration_hash, actor_id, policy_version, status,"
            " fingerprint) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, canonical_json(sorted(parent_ids)), reasoner_id, rule_version,
             configuration_hash, actor_id, policy_version, "running", fingerprint))
        return run_id

    def complete(self, run_id: str, *, proposals: list[dict], warnings: list[str],
                 status: str = "completed") -> None:
        self.connection.execute(
            "UPDATE akb_reasoning_runs SET status=?, proposals_json=?, warnings_json=?,"
            " finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE run_id=?",
            (status, canonical_json(proposals), canonical_json(warnings), run_id))

    def fail(self, run_id: str, warnings: list[str]) -> None:
        self.complete(run_id, proposals=[], warnings=warnings, status="failed")

    def find_by_fingerprint(self, fingerprint: str) -> dict | None:
        """锚语义：首个 completed run 持 fingerprint（UNIQUE）——幂等命中。"""
        row = self.connection.execute(
            "SELECT * FROM akb_reasoning_runs WHERE fingerprint=? AND status='completed'",
            (fingerprint,)).fetchone()
        return dict(row) if row else None

    def get(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM akb_reasoning_runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None


class InferenceTraceService:
    """反向追踪（DD-003 §3）：assertion → 递归 parent 链 → Evidence/Document 汇聚。

    确定性：同断言两次 trace 结果等价（V0.3 CMP-025 先例延续）。
    """

    def __init__(self, connection):
        self.connection = connection

    def _load(self, assertion_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT assertion_id, subject_ref, predicate_ref, object_kind, object_value,"
            " assertion_type, status, confidence, evidence_refs_json, derivation_json"
            " FROM akb_assertions WHERE assertion_id=?", (assertion_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["evidence_refs"] = json.loads(d.pop("evidence_refs_json") or "[]")
        derivation_raw = d.pop("derivation_json")
        d["derivation"] = json.loads(derivation_raw) if derivation_raw else None
        return d

    def trace(self, assertion_id: str, _seen: frozenset = frozenset()) -> dict:
        """递归展开；返回 {assertion, parents[], depth, warnings, evidence, documents}。

        - 环检测：祖先路径 seen——环 → warning（不递归崩溃）；
        - 缺失 parent → warning（DC-01 反查面）。
        """
        warnings: list[str] = []
        node = self._load(assertion_id)
        if node is None:
            return {"assertion": None, "parents": [], "depth": 0,
                    "warnings": [f"E-V04-PARENT-NOT-FOUND: {assertion_id}"],
                    "evidence": [], "documents": []}
        if assertion_id in _seen:
            return {"assertion": node, "parents": [], "depth": 0,
                    "warnings": [f"E-V04-CYCLE-DETECTED: {assertion_id}"],
                    "evidence": node["evidence_refs"], "documents": []}
        d = node.get("derivation") or {}
        parent_ids = d.get("parent_assertions") or []
        parents = []
        max_parent_depth = 0
        evidence = set(node["evidence_refs"])
        for pid in sorted(parent_ids):                      # canonical 序
            if pid in _seen:
                warnings.append(f"E-V04-CYCLE-DETECTED: {pid}")
                continue
            sub = self.trace(pid, _seen | {assertion_id})
            warnings.extend(f"{pid}: {w}" for w in sub["warnings"])
            parents.append(sub)
            max_parent_depth = max(max_parent_depth, sub["depth"])
            evidence.update(sub["evidence"])
        documents: list[str] = []
        for eid in sorted(evidence):
            row = self.connection.execute(
                "SELECT document_id FROM akb_evidence WHERE evidence_id=?",
                (eid,)).fetchone()
            if row:
                documents.append(row["document_id"])
        return {"assertion": node, "parents": parents,
                "depth": (max_parent_depth + 1) if parents else 0,
                "warnings": warnings, "evidence": sorted(evidence),
                "documents": sorted(set(documents))}