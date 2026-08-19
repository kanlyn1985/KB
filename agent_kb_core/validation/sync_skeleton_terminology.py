#!/usr/bin/env python3
"""骨架 → 术语表：把 skeleton_v0.4.json 的 210 个节点写进 domain pack terminology。

每个节点生成一条术语：
  node_id → {"aliases": [节点名, 父节点名, ...]}
别名 = 节点名 + 父节点链上的名称（提升可匹配性）

同时给 object_types.json 补充领域类型（Concept/Function/Process 等），
供 projector 按节点类型推断。

用法：
  python3 sync_skeleton_terminology.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.4.json"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"
TERMINOLOGY = DOMAIN_DIR / "terminology.json"
OBJECT_TYPES = DOMAIN_DIR / "object_types.json"

# 层 → 对象类型
LAYER_TO_TYPE = {
    "P": "PhysicalComponent",   # 物理分解（硬件/软件/标定）
    "F": "Function",            # 功能分解
    "L": "Logic",               # 逻辑/策略
    "R": "Requirement",         # 需求与标准
    "G": "Process",             # 过程（开发/生产/方法）
    "Q": "Experience",          # 质量与经验
    "M": "ProjectInstance",     # 项目实例
}


def extract_aliases(name: str) -> list[str]:
    """从节点名提取别名：全名、括号内关键词、核心词。

    过滤 ≤2 字符的通用类别词（测试/检测/试验/输入 等），避免污染匹配。
    """
    aliases = []
    full = name.strip()
    if full:
        aliases.append(full)
    # 括号内关键词（逗号/斜杠分隔），过滤短通用词
    generic_short = {"测试", "检测", "试验", "输入", "输出", "要求", "标准", "方法"}
    for m in re.findall(r"[（(]([^）)]+)[）)]", full):
        for part in re.split(r"[,，/、]", m):
            part = part.strip()
            if part and len(part) >= 3 and part not in generic_short and part not in aliases:
                aliases.append(part)
    # 名称主词（去掉层级前缀和括号）
    main = re.sub(r"^[PFLRGMQ]\s*", "", full)
    main = re.sub(r"[（(].*?[）)]", "", main).strip()
    if main and main not in aliases:
        aliases.append(main)
    return aliases[:12]


def main() -> int:
    skel = json.loads(SKELETON.read_text(encoding="utf-8"))
    nodes = skel["nodes"]
    node_map = {n["id"]: n for n in nodes}

    terms: dict[str, dict] = {}
    for n in nodes:
        aliases = extract_aliases(n["name"])
        # 加父节点名（一层）
        parent = n.get("parent")
        if parent and parent in node_map:
            parent_alias = re.sub(r"[（(].*?[）)]", "", node_map[parent]["name"]).strip()
            if parent_alias and parent_alias not in aliases:
                aliases.append(parent_alias)
        terms[n["id"]] = {"aliases": aliases}

    # 保留原有 6 个参数术语（不覆盖）
    existing = json.loads(TERMINOLOGY.read_text(encoding="utf-8"))
    existing_terms = existing.get("terms", {})
    merged = {**terms, **existing_terms}  # 节点术语优先，保留原参数
    existing["terms"] = merged
    TERMINOLOGY.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 术语表更新: {len(merged)} 条 (骨架 {len(terms)} + 原参数 {len(existing_terms)})")

    # object_types.json 补充领域类型
    ot = json.loads(OBJECT_TYPES.read_text(encoding="utf-8"))
    ot_types = ot.get("object_types", {})
    added = 0
    for tname in set(LAYER_TO_TYPE.values()):
        if tname not in ot_types:
            ot_types[tname] = {"description": f"Ontology node type ({tname}).",
                               "properties": ["canonical_name", "aliases"]}
            added += 1
    ot["object_types"] = ot_types
    OBJECT_TYPES.write_text(json.dumps(ot, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ object_types 补充 {added} 个类型，共 {len(ot_types)}")

    # 输出层→类型映射（供 projector 使用说明）
    print("层→类型映射:", LAYER_TO_TYPE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
