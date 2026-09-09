#!/usr/bin/env python3
"""负面评测：验证无关/易混淆查询不会被误召回。

指标（越低越好，理想 0%）：
  - 误召回率：负面查询的 top 候选命中"不应命中"节点（exclude）的比例
  - 空目标率：理解层未能正确拒绝的比例（有 target 但不应有）
  - 强命中率：top1 分数 >= 强命中阈值（默认 2.0）的比例

对比规则理解层（默认）与 LLM 理解层（--llm-understanding）的拒绝能力。

用法：
  python3 eval_negative_recall.py                    # 规则理解层
  python3 eval_negative_recall.py --llm-understanding
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.pipeline.production_context import query_production_store  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
NEGATIVE_CASES = TREE / "llm_landing" / "negative_cases.json"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"
DB = ROOT / "agent_kb_core" / "node-index.sqlite3"

STRONG_HIT_THRESHOLD = 2.0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-understanding", action="store_true")
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()

    domain_pack = load_domain_pack(DOMAIN_DIR)
    cases = json.loads(NEGATIVE_CASES.read_text(encoding="utf-8"))
    print(f"negative cases: {len(cases)} | 理解层: {'LLM' if args.llm_understanding else '规则'}")

    from agent_kb.query.understanding import UnderstandingOptions
    opts = UnderstandingOptions(use_llm=args.llm_understanding)

    false_recall = 0      # 命中 exclude 节点
    strong_hits = 0       # top1 分数过高（无关查询不应强命中）
    details = []
    for case in cases:
        res = query_production_store(
            case["query"], db_path=args.db, domain_pack=domain_pack,
            understanding_options=opts, retrieval_top_k=5,
        )
        cands = res.retrieval_result.candidates
        exclude = set(case.get("exclude", []))
        top_ids = [c.source_id.replace("card:obc_dcdc:", "").split("#")[0] for c in cands]
        top1_id = top_ids[0] if top_ids else None
        top1_score = cands[0].score if cands else 0.0

        hit_exclude = bool(exclude & set(top_ids))
        # off_topic 类型不应有强命中（top1 分数应低于阈值）
        strong = case["kind"] == "off_topic" and top1_score >= STRONG_HIT_THRESHOLD
        false_recall += 1 if hit_exclude else 0
        strong_hits += 1 if strong else 0
        details.append({
            "case_id": case["case_id"], "kind": case["kind"],
            "query": case["query"], "exclude": sorted(exclude),
            "top1": top1_id, "top1_score": round(top1_score, 2),
            "hit_exclude": hit_exclude, "strong_hit": strong,
        })

    n = len(cases)
    print(f"\n{'='*70}")
    print(f"负面评测（阈值 top1_score >= {STRONG_HIT_THRESHOLD} 视为强命中）")
    print(f"  误召回（命中 exclude）: {false_recall}/{n} = {false_recall/n*100:.1f}%")
    print(f"  无关强命中:            {strong_hits}/{n} = {strong_hits/n*100:.1f}%")
    print(f"{'='*70}")
    for d in details:
        marks = []
        if d["hit_exclude"]:
            marks.append("❌误召回")
        if d["strong_hit"]:
            marks.append("⚠️强命中")
        flag = " ".join(marks) or "✅"
        print(f"{flag:12s} {d['case_id']:22s} top1={d['top1']} score={d['top1_score']} "
              f"exclude={d['exclude']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
