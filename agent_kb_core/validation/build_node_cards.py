#!/usr/bin/env python3
"""落位数据 → 节点检索卡：按骨架节点聚合落位内容，生成节点级检索表面。

输入：merged_full_records_v04.jsonl（303,981 条落位记录）
输出：llm_landing/node_cards.jsonl（每骨架节点一卡）
  card: {node_id, node_name, layer, type, parent, alias[], content(聚合文本), unit_count, doc_count}

用途：把节点卡导入 agent_kb_core 索引（或作为检索评估的 golden 表面），
使查询先命中节点再下钻内容——修复"文本碎片投影"导致的召回不准。
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.4.json"
MERGED = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "merged_full_records_v04.jsonl"
OUT = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"

MAX_CONTENT_CHARS = 8000  # 每节点聚合文本上限（防超长卡）


def extract_aliases(name: str) -> list[str]:
    aliases = []
    full = name.strip()
    if full:
        aliases.append(full)
    for m in re.findall(r"[（(]([^）)]+)[）)]", full):
        for part in re.split(r"[,，/、]", m):
            part = part.strip()
            if part and len(part) >= 2 and part not in aliases:
                aliases.append(part)
    main = re.sub(r"^[PFLRGMQ]\s*", "", full)
    main = re.sub(r"[（(].*?[）)]", "", main).strip()
    if main and main not in aliases:
        aliases.append(main)
    return aliases[:12]


def main() -> int:
    skel = json.loads(SKELETON.read_text(encoding="utf-8"))
    nodes = skel["nodes"]
    node_map = {n["id"]: n for n in nodes}

    # 按节点聚合落位单元
    agg: dict[str, list[str]] = defaultdict(list)
    doc_set: dict[str, set] = defaultdict(set)
    total = 0
    with MERGED.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("unit_type") == "empty":
                continue
            nid = r.get("node_id")
            text = r.get("text", "")
            if nid in node_map and text:
                agg[nid].append(text)
                doc_set[nid].add(r.get("doc", ""))
                total += 1

    # 生成节点卡：大节点分块成子卡（父卡 + N 张子卡）
    CHUNK_CHARS = 4000
    SPLIT_UNIT_THRESHOLD = 300  # 单元数超过此值才分块
    MAX_CHUNKS_PER_NODE = 60  # 单节点最大子卡数（防索引膨胀）
    with OUT.open("w", encoding="utf-8") as fo:
        for nid, n in node_map.items():
            texts = agg.get(nid, [])
            if not texts:
                continue
            # 去重
            seen = set()
            unique: list[str] = []
            for t in texts:
                key = t[:50]
                if key in seen:
                    continue
                seen.add(key)
                unique.append(t)
            content = "\n".join(unique)
            base = {
                "node_id": nid,
                "node_name": n["name"],
                "layer": n["layer"],
                "type": n.get("type", ""),
                "parent": n.get("parent"),
                "aliases": extract_aliases(n["name"]),
                "unit_count": len(texts),
                "doc_count": len(doc_set[nid]),
            }
            need_split = len(texts) >= SPLIT_UNIT_THRESHOLD and len(content) > CHUNK_CHARS
            if not need_split:
                fo.write(json.dumps({**base, "content": content[:MAX_CONTENT_CHARS]}, ensure_ascii=False) + "\n")
                continue
            # 分块：按字符数切，尽量在换行处断开；超 MAX_CHUNKS 截断
            chunks: list[str] = []
            current = ""
            for line in unique:
                if len(current) + len(line) + 1 > CHUNK_CHARS and current:
                    chunks.append(current)
                    current = line
                else:
                    current = (current + "\n" + line) if current else line
            if current:
                chunks.append(current)
            if len(chunks) > MAX_CHUNKS_PER_NODE:
                chunks = chunks[:MAX_CHUNKS_PER_NODE]
            # 父卡：前 2000 字符 + 子卡引用
            fo.write(json.dumps({
                **base,
                "content": chunks[0],
                "chunk_of": None,
                "child_chunks": [f"{nid}#{i + 1}" for i in range(1, len(chunks))],
            }, ensure_ascii=False) + "\n")
            # 子卡
            for i, chunk in enumerate(chunks[1:], start=1):
                fo.write(json.dumps({
                    **base,
                    "node_id": f"{nid}#{i}",
                    "content": chunk,
                    "chunk_of": nid,
                    "child_chunks": [],
                }, ensure_ascii=False) + "\n")

    n_cards = sum(1 for _ in OUT.open(encoding="utf-8"))
    print(f"✅ 节点卡生成: {n_cards} 张（含内容的节点 {len(agg)} / 骨架 {len(node_map)}）")
    print(f"聚合单元: {total}")
    # 样例
    with OUT.open(encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c["node_id"] == "P-KNOW-OBC":
                print(f"样例 P-KNOW-OBC: {c['unit_count']} 单元 / {c['doc_count']} 文档 / 内容 {len(c['content'])} 字符")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
