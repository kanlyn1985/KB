# -*- coding: utf-8 -*-
"""SourceWeightResolver（weight≠adjudication；weight_policy=v1）。"""
from __future__ import annotations

from agent_kb.evidence_core.synthesis.models import SourceWeight

WEIGHT_POLICY = "weight_policy=v1"
_DIMS = {"authority": 0.30, "reliability": 0.20, "recency": 0.15,
         "document_version": 0.15, "evidence_quality": 0.10, "corroboration": 0.10}


class SourceWeightResolver:
    def resolve(self, members: list[dict], policy_version: str = WEIGHT_POLICY
                ) -> tuple[list[SourceWeight], str]:
        """members: [{evidence_id, source_type, confidence, extraction_method, source_count}]"""
        if policy_version != WEIGHT_POLICY:
            policy = "uniform"   # 未知策略 → uniform 降级 + warning（调用方记录）
        else:
            policy = WEIGHT_POLICY
        out: list[SourceWeight] = []
        type_rank = {"governed": 1.0, "document": 0.7, "ingested": 0.4}
        counts: dict[str, int] = {}
        for m in members:
            counts[m.get("source_id") or m["evidence_id"]] = \
                counts.get(m.get("source_id") or m["evidence_id"], 0) + 1
        for m in sorted(members, key=lambda x: x["evidence_id"]):
            authority = type_rank.get(m.get("source_type") or "ingested", 0.4)
            quality = min(1.0, float(m.get("confidence") or 0.5))
            sid = m.get("source_id") or m["evidence_id"]
            corrob = 1.0 if counts.get(sid, 0) >= 1 and m.get("independent") else 0.0
            w = SourceWeight(
                evidence_id=m["evidence_id"], authority=round(authority, 4),
                reliability=round(float(m.get("reliability") or 0.5), 4),
                recency=round(float(m.get("recency") or 0.5), 4),
                document_version=round(float(m.get("document_version") or 0.5), 4),
                evidence_quality=round(quality, 4), corroboration=corrob)
            w.weight = round(sum(getattr(w, d) * wt for d, wt in _DIMS.items()), 4)
            out.append(w)
        return out, policy