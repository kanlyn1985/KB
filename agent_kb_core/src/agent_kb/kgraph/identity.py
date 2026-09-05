# -*- coding: utf-8 -*-
"""Entity Identity Resolution（V0.5-DD-002）——canonical id 派生层。

红线：Entity A + Entity B 不能因为文本相似自动 merge——
本层只做 L1 精确归一簇的 canonical 收敛（继承 V0.3 对齐簇输出）；
相似度建议/merge 执行属 IMPL-002 治理面，不在本轮。
"""
from __future__ import annotations

import hashlib

from agent_kb.reasoning.models import canonical_json


class EntityIdentityResolver:
    """实体身份解析：normalized_form 精确归一簇（L1）→ canonical_id。

    entity_type 分歧不合并（V0.3 CONF-005 教训固化——DD-002 §4）。
    """

    def __init__(self, domain_pack_version: str = "default"):
        self._dpv = domain_pack_version

    def canonical_id(self, canonical_form: str, entity_type: str) -> str:
        payload = {"canonical_form": canonical_form, "entity_type": entity_type,
                   "domain_pack_version": self._dpv}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]

    def resolve_clusters(self, entity_members: list[dict]) -> list[dict]:
        """输入 V0.3 对齐簇成员（normalized_form/entity_type/evidence_id…），
        输出 canonical 簇列表（L1 精确键 + type 一致约束）。

        返回：[{canonical_id, canonical_form, entity_type, members[], aliases[]}]
        （deterministic 排序）。
        """
        groups: dict[tuple, list[dict]] = {}
        for m in entity_members:
            key = ((m.get("normalized_form") or m.get("surface_form") or "").strip(),
                   m.get("entity_type") or "")
            groups.setdefault(key, []).append(m)
        out = []
        for (form, etype), members in sorted(groups.items()):
            out.append({
                "canonical_id": self.canonical_id(form, etype),
                "canonical_form": form,
                "entity_type": etype,
                "members": sorted(members, key=lambda m: (m.get("evidence_id", ""),
                                                          m.get("candidate_id", ""))),
                "aliases": sorted({m.get("surface_form") or m.get("normalized_form") or ""
                                   for m in members}),
            })
        return out
