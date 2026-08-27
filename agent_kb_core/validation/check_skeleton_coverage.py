#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""骨架内容尺检查器 v0.8 —— 显式映射 + 节点深度（阈值读配置）。

被测: skeleton_v0.6.json + node_cards.jsonl
尺子: skeleton_coverage_map.json（81 工作包要素 → 骨架节点，人工显式映射，独立于骨架）
阈值: skeleton_health_rules.json 的 content 段（unit_min / doc_min）

两把尺（Q6：结构与内容分开测）:
  1. 覆盖（结构尺）: 81 要素是否有对应节点 → full / partial / gap
  2. 深度（内容尺）: 映射节点是否有内容 → filled / thin / empty

用法: python check_skeleton_coverage.py [--json]
可 import: from check_skeleton_coverage import collect
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.6.json"
CARDS = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"
MAPPING = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_coverage_map.json"
RULES = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_health_rules.json"


def load():
    sk = json.loads(SKELETON.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in sk["nodes"]}
    cards = {}
    for line in CARDS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if "#" not in c["node_id"]:
            cards[c["node_id"]] = c
    mp = json.loads(MAPPING.read_text(encoding="utf-8"))
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    return sk, nodes, cards, mp, rules


def depth_of(nid, nodes, cards, unit_min, doc_min, canonical_unit_min, markers):
    if nid not in nodes:
        return "missing"
    c = cards.get(nid)
    if not c:
        return "empty"
    unit = c.get("unit_count", 0)
    doc = c.get("doc_count", 0)
    if unit >= unit_min and doc >= doc_min:
        return "filled"
    # 单本权威源：doc>=1 且 unit>=canonical_unit_min 且文档名含权威标记
    if unit >= canonical_unit_min and doc >= 1:
        for d in c.get("docs", []):
            if any(m in d for m in markers):
                return "filled"
    return "thin"


def collect():
    sk, nodes, cards, mp, rules = load()
    unit_min = rules["content"]["unit_min"]
    doc_min = rules["content"]["doc_min"]
    canonical_unit_min = rules["content"].get("canonical_unit_min", unit_min)
    markers = rules["content"].get("authoritative_doc_markers", [])
    rows = mp["mappings"]

    cov = {"full": 0, "partial": 0, "gap": 0}
    dep = {"filled": 0, "thin": 0, "empty": 0, "missing": 0}
    dims = {}
    empty_nodes = []
    stale = []

    for m in rows:
        dim = m["dim"]
        c = m.get("coverage", "gap")
        cov[c] = cov.get(c, 0) + 1
        d = dims.setdefault(dim, {"name": dim, "full":0, "partial":0, "gap":0, "filled":0, "thin":0, "empty":0})
        d[c] = d.get(c, 0) + 1

        nids = [x.strip() for x in str(m.get("node","")).split(";") if x.strip() and x.strip() != "GAP"]
        if not nids:
            dep["empty"] += 1
            d["empty"] = d.get("empty", 0) + 1
            continue
        depths = [depth_of(nid, nodes, cards, unit_min, doc_min, canonical_unit_min, markers) for nid in nids]
        for nid, dd in zip(nids, depths):
            if dd == "missing":
                stale.append((m["wbs_id"], nid))
        if "filled" in depths: best = "filled"
        elif "thin" in depths: best = "thin"
        elif "missing" in depths: best = "missing"
        else: best = "empty"
        dep[best] += 1
        d[best] = d.get(best, 0) + 1
        if best == "empty":
            empty_nodes.append({"wbs_id": m["wbs_id"], "node": nids[0], "name": m["wbs_name"]})

    total = len(rows)
    pct = lambda a, b: (100.0 * a / b) if b else 0.0
    return {
        "mapping_version": mp.get("mapping_version"),
        "tree_version": sk.get("tree_version"),
        "nodes": len(nodes),
        "total": total,
        "coverage": cov,
        "covered": cov["full"] + cov["partial"],
        "coverage_pct": pct(cov["full"] + cov["partial"], total),
        "depth": dep,
        "empty_nodes": empty_nodes,
        "stale": stale,
        "dims": dims,
    }


def main():
    data = collect()
    if "--json" in sys.argv[1:]:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    unit_min = json.loads(RULES.read_text(encoding="utf-8"))["content"]["unit_min"]
    doc_min = json.loads(RULES.read_text(encoding="utf-8"))["content"]["doc_min"]
    print("=" * 72)
    print(f"骨架内容尺检查报告  |  {data['tree_version']}  |  {data['nodes']} 节点 / {data['total']} 要素")
    print("=" * 72)
    print(f"[覆盖] 有对应节点 {data['covered']}/{data['total']} = {data['coverage_pct']:.1f}%")
    print(f"        full {data['coverage']['full']} · partial {data['coverage']['partial']} · gap {data['coverage']['gap']}")
    print(f"[深度] filled {data['depth']['filled']} · thin {data['depth']['thin']} · empty {data['depth']['empty']}"
          + (f" · missing {data['depth']['missing']}" if data['depth']['missing'] else ""))
    c2 = json.loads(RULES.read_text(encoding="utf-8"))["content"]
    print(f"        阈值: unit>={unit_min} 且 doc>={doc_min}；或 单本权威源(unit>={c2.get('canonical_unit_min')} 且 doc>=1 且文档名含权威标记)")
    print("-" * 72)
    for dim in sorted(data["dims"]):
        d = data["dims"][dim]
        tot = d['full']+d['partial']+d['gap']
        print(f"  {dim:5s} {d['full']+d['partial']:2d}/{tot:<2d} "
              f"full {d['full']:<2d} partial {d['partial']:<2d} gap {d['gap']:<2d} | "
              f"filled {d['filled']:<2d} thin {d['thin']:<2d} empty {d['empty']}")
    print("-" * 72)
    if data["stale"]:
        print(f"映射失效（节点不存在，{len(data['stale'])} 条）: {data['stale']}")
    print(f"空壳节点（有节点无内容，待落地，{len(data['empty_nodes'])} 个）:")
    for e in data["empty_nodes"]:
        print(f"  ○ [{e['wbs_id']}] {e['name']}  ->  {e['node']}")
    print()


if __name__ == "__main__":
    main()