#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""骨架结构尺检查器 v0.3 —— 数据驱动的结构完整检查（规则外置，可复用）。

被测: skeleton_v0.6.json
规则: skeleton_health_rules.json 的 structure 段（层名/边类型/豁免前缀/检查项）
检查项由配置定义:
  - leaf_connectivity: 叶子连通性（豁免软关系/参考节点，其余分类报待细化）
  - chain_checks:     逐层覆盖（如 R→F satisfy、F→L realize、L→P allocate）
  - closure_checks:   闭环（如 R 被 verify、M 有 instance-of）
  - produce_check:    物理件被 produce

用法: python check_skeleton_structure.py [--json]
可 import: from check_skeleton_structure import collect
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.6.json"
RULES = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_health_rules.json"


def load():
    sk = json.loads(SKELETON.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in sk["nodes"]}
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    return sk, nodes, rules


def leaf(nodes, nid):
    return not any(n.get("parent") == nid for n in nodes.values())


def _edge_check(check, layer_leaves, inn, out, nm):
    """通用边检查：某层叶子是否满足 in_edge/out_edge 要求。返回 (label, passed, total, detail)。"""
    lv = layer_leaves(check["layer"])
    miss = []
    for x in lv:
        if check.get("in_edge") and not any(t == check["in_edge"] for t, _ in inn[x]):
            miss.append(x)
        if check.get("out_edge") and not any(t == check["out_edge"] for t, _ in out[x]):
            miss.append(x)
    miss = sorted(set(miss))
    detail = (f"缺 {len(miss)}: {[nm(x) for x in miss]}" if miss
              else "全部叶子满足所需边")
    return check["label"], len(miss) == 0, len(lv), detail


def collect():
    sk, nodes, rules = load()
    struct = rules["structure"]
    relations = sk.get("relations", [])

    out = defaultdict(set)
    inn = defaultdict(set)
    for r in relations:
        out[r["source"]].add((r["type"], r["target"]))
        inn[r["target"]].add((r["type"], r["source"]))

    def nm(nid):
        return nodes.get(nid, {}).get("name", nid)

    leaves = {nid for nid in nodes if leaf(nodes, nid)}

    def layer_leaves(l):
        return [nid for nid in nodes if nodes[nid]["layer"] == l and nid in leaves]

    results = []

    # 1. 叶子连通性
    lc = struct["leaf_connectivity"]
    exempt = lc["exempt_prefix"]
    buckets = lc["buckets"]

    def is_exempt(nid):
        return any(nid.startswith(p) for p in exempt)

    unconnected = [nid for nid in nodes
                   if nid in leaves and nid not in out and nid not in inn and not is_exempt(nid)]
    cat = {}
    for nid in unconnected:
        for b in buckets:
            if any(nid.startswith(p) for p in b["prefix"]):
                cat.setdefault(b["name"], []).append(nid)
                break
        else:
            cat.setdefault("其他", []).append(nid)
    parts = " / ".join(f"{b['name']} {len(cat.get(b['name'], []))}" for b in buckets)
    parts += f" / 其他 {len(cat.get('其他', []))}"
    detail = f"待细化叶子 {len(unconnected)} 个（{parts}）"
    for name in [b["name"] for b in buckets] + ["其他"]:
        if cat.get(name):
            detail += f"\n        {name}: {[nm(x) for x in cat[name]]}"
    results.append(("叶子连通性（待细化 = 0）", len(unconnected) == 0, len(unconnected),
                    detail if unconnected else "全部叶子已连通（软关系/参考节点按规则豁免）"))

    # 2. 逐层覆盖 + 3. 闭环（同构，读配置）
    for c in struct["chain_checks"]:
        results.append(_edge_check(c, layer_leaves, inn, out, nm))
    for c in struct["closure_checks"]:
        results.append(_edge_check(c, layer_leaves, inn, out, nm))

    # 4. produce
    pc = struct["produce_check"]
    phys = [x for x in layer_leaves(pc["layer"]) if x.startswith(tuple(pc["physical_prefix"]))]
    miss = [x for x in phys if not any(t == pc["in_edge"] for t, _ in inn[x])]
    results.append((pc["label"], len(miss) == 0, len(phys),
                    f"缺 {len(miss)}: {[nm(x) for x in miss]}" if miss else "全部物理件有 produce 入边"))

    passed_n = sum(1 for c, p, t, d in results if p)
    return {
        "tree_version": sk.get("tree_version"),
        "nodes": len(nodes),
        "relations": len(relations),
        "passed": passed_n,
        "total": len(results),
        "checks": [{"check": c, "passed": p, "total": t, "detail": d} for c, p, t, d in results],
    }


def main():
    data = collect()
    if "--json" in sys.argv[1:]:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print("=" * 72)
    print(f"骨架结构尺检查报告  |  {data['tree_version']}  |  {data['nodes']} 节点 / {data['relations']} 边")
    print("=" * 72)
    for chk in data["checks"]:
        mark = "PASS" if chk["passed"] else "FAIL"
        print(f"  [{mark}] {chk['check']}  ({chk['total']})")
        if not chk["passed"]:
            print(f"        {chk['detail']}")
    print("-" * 72)
    print(f"  结构完整度: {data['passed']}/{data['total']} 项通过")
    print()


if __name__ == "__main__":
    main()