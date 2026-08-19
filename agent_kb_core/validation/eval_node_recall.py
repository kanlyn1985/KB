#!/usr/bin/env python3
"""节点级召回评测：验证骨架（210 节点）的检索正确性。

用 209 张节点卡作为检索表面，golden cases（真实查询 → 期望命中节点）
跑 understand_query + retrieve，输出 Hit@K / MRR / object recall。

这是骨架正确性的直接检验：查询能命中正确节点 = 骨架语义划分正确。

用法：
  python3 eval_node_recall.py [--top-k 5] [--cases cases.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.projection.models import ObjectProjection  # noqa: E402
from agent_kb.query.understanding import understand_query  # noqa: E402
from agent_kb.retrieval.cards import RetrievalCard  # noqa: E402
from agent_kb.retrieval.engine import retrieve  # noqa: E402
from agent_kb.retrieval.card_builder import build_retrieval_card  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
NODE_CARDS = TREE / "llm_landing" / "node_cards.jsonl"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"
CASES = TREE / "llm_landing" / "golden_cases.json"

# 默认 golden cases：真实查询 → 期望命中的骨架节点
DEFAULT_CASES = [
    {"case_id": "obc_principle", "query": "帮我介绍一下OBC的工作原理",
     "expected": ["P-KNOW-OBC"]},
    {"case_id": "dcdc_principle", "query": "DCDC的工作原理是什么",
     "expected": ["P-KNOW-DCDC"]},
    {"case_id": "ripple_req", "query": "输出纹波要求是多少",
     "expected": ["R-PERF"]},
    {"case_id": "thermal_sim", "query": "热仿真怎么做",
     "expected": ["G-VERIFY-CAE-THERMAL", "G-METHOD-CAE-THERMAL"]},
    {"case_id": "modal_analysis", "query": "模态分析的方法",
     "expected": ["G-METHOD-CAE-STRUCT-MODAL", "G-VERIFY-CAE-VIBRATION"]},
    {"case_id": "autosar_comm", "query": "AUTOSAR通信怎么配置",
     "expected": ["G-METHOD-AUTOSAR-COMM"]},
    {"case_id": "mcu_safety", "query": "MCU安全监控机制",
     "expected": ["P-SW-BSW", "R-FSC"]},
    {"case_id": "potting", "query": "灌封胶选型要求",
     "expected": ["G-PROD-POTTING-POT", "G-PROD-POTTING-THERMAL"]},
    {"case_id": "fault_diag", "query": "故障诊断逻辑",
     "expected": ["L-FAULT", "P-SW-ASW-DCDCFAULTDET"]},
    {"case_id": "vibration_test", "query": "振动测试标准",
     "expected": ["G-VERIFY-VIBRATION-VIB"]},
    {"case_id": "can_comm", "query": "CAN通信协议",
     "expected": ["L-COMM", "G-METHOD-AUTOSAR-COMM"]},
    {"case_id": "safety_req", "query": "功能安全要求",
     "expected": ["R-FSC"]},
    {"case_id": "efficiency", "query": "OBC效率要求",
     "expected": ["R-PERF"]},
    {"case_id": "assembl", "query": "装配工艺要求",
     "expected": ["G-PROD-ASSEMBLY", "G-PROD-ASSEMBLY-GEN"]},
    {"case_id": "sealing", "query": "密封测试方法",
     "expected": ["G-VERIFY-AIRTIGHT", "G-PROD-POTTING-SEAL"]},
]


def load_cards() -> tuple[list[RetrievalCard], dict]:
    """从 node_cards.jsonl 构建 RetrievalCard 列表 + node_id → card_id 映射。

    合并两类卡片：
    1. 参数对象卡（术语表投影，如 DCDC_OUTPUT_RIPPLE）
    2. 骨架节点卡（node_cards.jsonl，如 P-KNOW-OBC）
    """
    domain_pack = load_domain_pack(DOMAIN_DIR)
    from agent_kb.projection.projector import build_terminology_projections
    from agent_kb.retrieval.card_builder import build_retrieval_cards

    cards: list[RetrievalCard] = []
    node2card: dict[str, str] = {}

    # 1. 参数对象卡
    projections = build_terminology_projections(domain_pack)
    param_cards = build_retrieval_cards(projections)
    cards.extend(param_cards)
    for card in param_cards:
        node2card[card.object_id] = card.card_id

    # 2. 骨架节点卡
    for line in NODE_CARDS.open(encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        card_id = f"card:obc_dcdc:{c['node_id']}"
        search_text = " ".join([
            c["node_name"], c.get("content", "")[:2000],
            *c.get("aliases", []),
        ])
        card = RetrievalCard(
            card_id=card_id,
            domain="obc_dcdc",
            object_id=c["node_id"],
            card_type=c["layer"],
            title=c["node_name"],
            search_text=search_text,
            aliases=c.get("aliases", []),
            related_object_ids=[],
            evidence_ids=[],
            answer_shapes=["definition", "general_search"],
            structured_payload={"node": c["node_id"]},
            confidence=1.0,
        )
        cards.append(card)
        node2card[c["node_id"]] = card_id
    return cards, node2card


def main() -> int:
    top_k = int(sys.argv[sys.argv.index("--top-k") + 1]) if "--top-k" in sys.argv else 5

    domain_pack = load_domain_pack(DOMAIN_DIR)
    cards, node2card = load_cards()
    print(f"节点卡: {len(cards)} 张 | 领域: {domain_pack.domain_id}")

    cases = DEFAULT_CASES
    if CASES.exists():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
    print(f"golden cases: {len(cases)} 个")

    # 构造 RetrievalIndexView 需要的完整对象（cards + 空 facts/evidence）
    class Index:
        object_projections = [c for c in []]
        retrieval_cards = cards
        context_facts = []
        context_evidence = []

    index = Index()

    hits = 0
    mrrs = []
    details = []
    for case in cases:
        frame = understand_query(case["query"], domain_pack=domain_pack)
        result = retrieve(frame, index, top_k=top_k)
        expected = case["expected"]
        # 期望节点对应的 card_id
        expected_ids = {node2card.get(e) for e in expected if e in node2card}
        expected_ids.discard(None)
        # 命中判定：候选里出现期望 card
        cand_ids = {c.source_id for c in result.candidates}
        hit_ids = expected_ids & cand_ids
        hit = bool(hit_ids)
        first_rank = None
        for rank, c in enumerate(result.candidates, 1):
            if c.source_id in expected_ids:
                first_rank = rank
                break
        mrr = 1.0 / first_rank if first_rank else 0.0
        hits += 1 if hit else 0
        mrrs.append(mrr)
        top_objs = [c.source_id.replace("card:obc_dcdc:", "") for c in result.candidates[:3]]
        details.append({
            "case_id": case["case_id"], "query": case["query"],
            "expected": expected, "hit": hit, "first_rank": first_rank,
            "mrr": mrr, "top3": top_objs,
        })

    n = len(cases)
    print(f"\n{'='*60}")
    print(f"节点级召回评测（top_k={top_k}）")
    print(f"  Hit@{top_k}: {hits}/{n} = {hits/n*100:.1f}%")
    print(f"  MRR: {sum(mrrs)/n:.3f}")
    print(f"{'='*60}")
    for d in details:
        mark = "✅" if d["hit"] else "❌"
        print(f"{mark} {d['case_id']:20s} rank={d['first_rank']} | 期望{d['expected']}")
        print(f"   top3: {d['top3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
