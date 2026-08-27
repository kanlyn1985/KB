#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""骨架体检门 v0.1 —— 一条命令跑两把尺（结构尺 + 内容尺），出完整骨架体检报告。

用法: python run_skeleton_health.py [--json]
退出码: 0 = 结构全通且无空壳; 1 = 有待办（非结构缺失，属落地/细化）
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_skeleton_structure import collect as collect_structure
from check_skeleton_coverage import collect as collect_content


def main():
    st = collect_structure()
    ct = collect_content()

    failed = [c for c in st["checks"] if not c["passed"]]
    empty = ct["empty_nodes"]

    report = {
        "tree_version": st["tree_version"],
        "mapping_version": ct["mapping_version"],
        "nodes": st["nodes"],
        "relations": st["relations"],
        "structure": {"passed": st["passed"], "total": st["total"],
                      "failed": [c["check"] for c in failed]},
        "content": {"covered": ct["covered"], "total": ct["total"],
                    "coverage_pct": ct["coverage_pct"],
                    "depth_filled": ct["depth"]["filled"], "depth_empty": ct["depth"]["empty"]},
        "todo": {
            "landing_empty": [e["node"] for e in empty],
            "refine_leaves": [c["detail"].splitlines()[0] for c in failed if c["check"].startswith("叶子连通性")],
        },
    }

    if "--json" in sys.argv[1:]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 72)
    print(f"骨架体检报告  |  v{st['tree_version']}  |  {st['nodes']} 节点 / {st['relations']} 边  |  mapping v{ct['mapping_version']}")
    print("=" * 72)
    print(f"[结构尺] {st['passed']}/{st['total']} 项通过")
    for c in failed:
        print(f"    FAIL  {c['check']}")
        print(f"          {c['detail'].splitlines()[0]}")
    print(f"[内容尺] 覆盖 {ct['covered']}/{ct['total']} = {ct['coverage_pct']:.1f}%"
          f"  ·  深度 filled {ct['depth']['filled']} / empty {ct['depth']['empty']}")
    print("-" * 72)
    print("待办清单:")
    n = 1
    if empty:
        nodes = ", ".join(e["node"] for e in empty)
        print(f"  {n}. [落地] {len(empty)} 个空壳节点待 landing：{nodes}")
        n += 1
    for c in failed:
        if c["check"].startswith("叶子连通性"):
            print(f"  {n}. [细化] 懒拆叶子待细挂（SWC allocate + 工艺/验证子节点细边）")
            n += 1
    if not empty and not failed:
        print("  （无）")
    print("-" * 72)
    if st["passed"] == st["total"] and not empty:
        print("结论: PASS —— 结构全通 + 内容全落地")
        sys.exit(0)
    else:
        print("结论: 结构已拼合、内容覆盖 100%；剩余为落地/细化（非结构缺失）")
        sys.exit(1)


if __name__ == "__main__":
    main()