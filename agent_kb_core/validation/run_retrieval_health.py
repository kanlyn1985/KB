# -*- coding: utf-8 -*-
"""run_retrieval_health.py —— 检索层体检门。

两把尺（依据均独立于 case 集合本身）：
1. 充分性尺：oracle 要素全覆盖 + 骨架节点全覆盖 + 分层地板 + 负例数（依据 retrieval_case_rules.json）
2. 质量尺：正例 Hit@K / MRR + 负例假召回（依据 retrieval_case_rules.json 阈值）

用法：
  python run_retrieval_health.py              # 人类可读报告
  python run_retrieval_health.py --json       # 机器可读
  python run_retrieval_health.py --top-k 5    # 覆盖 top_k

退出码：0 = PASS（充分性全达标 且 质量达标）；1 = 有待办。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from eval_node_recall import load_cards  # noqa: E402
from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.query.understanding import understand_query  # noqa: E402
from agent_kb.retrieval.engine import retrieve  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
RULES = TREE / "retrieval_case_rules.json"
SKELETON = TREE / "skeleton_v0.6.json"
MAP = TREE / "skeleton_coverage_map.json"
CASES = TREE / "llm_landing" / "golden_cases.json"
NEG = TREE / "llm_landing" / "negative_cases.json"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"


def load_hierarchy():
    skel = json.loads(SKELETON.read_text(encoding="utf-8"))
    parents = {n["id"]: n.get("parent") for n in skel["nodes"]}
    nodes = [n for n in skel["nodes"]]
    return parents, nodes


def is_hit(cand_id: str, exp_id: str, parents: dict) -> bool:
    """cand 命中 exp：相等 或 cand 是 exp 的后代（打到子节点算命中父概念）。"""
    cand_id = cand_id.split("#")[0].replace("card:obc_dcdc:", "")
    if cand_id == exp_id:
        return True
    cur = parents.get(cand_id)
    while cur:
        if cur == exp_id:
            return True
        cur = parents.get(cur)
    return False


def main() -> int:
    as_json = "--json" in sys.argv
    top_k = int(sys.argv[sys.argv.index("--top-k") + 1]) if "--top-k" in sys.argv else 5
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    suf = rules["sufficiency"]
    neg_rule = rules["negative_cases"]
    q = rules["quality"]
    layer_floor = rules["layer_floor"]["min_layer_coverage_pct"]

    parents, nodes = load_hierarchy()
    nmap = {n["id"]: n for n in nodes}
    mp = json.loads(MAP.read_text(encoding="utf-8"))
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    negs = json.loads(NEG.read_text(encoding="utf-8")) if NEG.exists() else []

    domain_pack = load_domain_pack(DOMAIN_DIR)
    cards, node2card = load_cards()

    # ---------- 充分性尺 ----------
    # 1) oracle 要素覆盖：每个 wbs 有 case 打到其映射节点（或后代）
    wbs_case_map = {m["wbs_id"]: m for m in mp["mappings"]}
    covered_wbs = set()
    for c in cases:
        exp = {e.split("#")[0] for e in c["expected"]}
        for m in mp["mappings"]:
            mnodes = [x.strip() for x in str(m.get("node", "")).split(";")]
            if any(any(is_hit(x, y, parents) for x in exp) for y in mnodes if y):
                covered_wbs.add(m["wbs_id"])
    wbs_miss = [w for w in wbs_case_map if w not in covered_wbs]

    # 2) 节点覆盖 + 分层地板
    covered_nodes = set()
    for c in cases:
        for e in c["expected"]:
            covered_nodes.add(e.split("#")[0])
    layer_total, layer_cov = {}, {}
    for n in nodes:
        layer_total[n["layer"]] = layer_total.get(n["layer"], 0) + 1
        if n["id"] in covered_nodes:
            layer_cov[n["layer"]] = layer_cov.get(n["layer"], 0) + 1
    layer_pct = {L: layer_cov.get(L, 0) / layer_total[L] * 100 for L in layer_total}
    node_miss = [n["id"] for n in nodes if n["id"] not in covered_nodes]
    layer_low = {L: round(layer_pct[L], 1) for L in layer_pct if layer_pct[L] < layer_floor}

    suf_pass = (not wbs_miss and not node_miss and not layer_low
                and len(negs) >= neg_rule["min_count"])

    # ---------- 质量尺 ----------
    class Index:
        object_projections = []
        retrieval_cards = cards
        context_facts = []
        context_evidence = []

    index = Index()
    hits, mrrs, details = 0, [], []
    for c in cases:
        frame = understand_query(c["query"], domain_pack=domain_pack)
        result = retrieve(frame, index, top_k=top_k)
        exp = {e.split("#")[0] for e in c["expected"]}
        cand = [x.source_id.split("#")[0].replace("card:obc_dcdc:", "") for x in result.candidates]
        hit = any(any(is_hit(x, y, parents) for x in cand) for y in exp)
        first_rank = None
        for rank, x in enumerate(cand, 1):
            if any(is_hit(x, y, parents) for y in exp):
                first_rank = rank
                break
        hits += 1 if hit else 0
        mrrs.append(1.0 / first_rank if first_rank else 0.0)
        if not hit:
            details.append({"case_id": c["case_id"], "query": c["query"],
                            "expected": sorted(exp), "top5": sorted(set(cand))[:5]})

    n = len(cases)
    hit_rate = hits / n
    mrr = sum(mrrs) / n

    # 负例：top1 分数
    neg_scores = []
    for c in negs:
        frame = understand_query(c["query"], domain_pack=domain_pack)
        result = retrieve(frame, index, top_k=1)
        neg_scores.append(result.candidates[0].score if result.candidates else 0.0)
    neg_top = max(neg_scores) if neg_scores else 0.0

    qual_pass = (hit_rate >= q["min_hit_rate"] and mrr >= q["min_mrr"]
                 and neg_top < neg_rule["max_top_score"])

    passed = suf_pass and qual_pass

    # ---------- 报告 ----------
    def pct(x): return f"{x*100:.1f}%"
    if as_json:
        print(json.dumps({
            "sufficiency": {"wbs_miss": wbs_miss, "node_miss": node_miss,
                            "layer_low": layer_low, "negatives": len(negs),
                            "pass": suf_pass},
            "quality": {"hit_at_k": top_k, "hit_rate": round(hit_rate, 4),
                        "mrr": round(mrr, 4), "neg_top_score": round(neg_top, 4),
                        "pass": qual_pass},
            "conclusion": "PASS" if passed else "FAIL",
            "residual_fails": details,
        }, ensure_ascii=False, indent=1))
        return 0 if passed else 1

    line = "=" * 72
    print(line)
    print(f"检索体检报告 | mapping v0.9 | {n} 正例 / {len(negs)} 负例 | {len(nodes)} 节点")
    print(line)
    print(f"[充分性尺] oracle 要素 {len(wbs_case_map)-len(wbs_miss)}/{len(wbs_case_map)} 有 case"
          f" · 节点 {len(nodes)-len(node_miss)}/{len(nodes)} 有 case"
          f" · 分层地板 {layer_floor}%"
          f" · 负例 {len(negs)}>={neg_rule['min_count']}")
    if wbs_miss:
        print(f"  缺 case 的 oracle 要素: {wbs_miss}")
    if layer_low:
        print(f"  低于地板的层: {layer_low}")
    print(f"[质量尺] Hit@{top_k}: {hits}/{n} = {pct(hit_rate)} · MRR: {mrr:.3f}"
          f" · 负例 top1 最高分 {neg_top:.3f} < {neg_rule['max_top_score']}")
    for L in sorted(layer_total):
        print(f"  层 {L}: 节点覆盖 {layer_cov.get(L,0)}/{layer_total[L]} = {layer_pct[L]:.0f}%")
    print("-" * 72)
    if details:
        print(f"残余失败 {len(details)} 个:")
        for d in details:
            print(f"  ✗ {d['case_id']}: {d['query']} -> 期望{d['expected']} top5={d['top5']}")
    print(f"结论: {'PASS' if passed else 'FAIL'}"
          f" —— 充分性{'达标' if suf_pass else '不达标'} + 质量{'达标' if qual_pass else '不达标'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())