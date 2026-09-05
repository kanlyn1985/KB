#!/usr/bin/env python3
"""Hash vs BGE-M3 端到端对比评测：同一 node_cards、同一 golden cases，
分别用 HashEmbeddingProvider / BGE-M3 建生产索引，跑完整 query-production 链路。

用法：
  python3 eval_embedding_compare.py --hash-db hash.sqlite3 --bge-db bge.sqlite3 [--skip-build]

说明：
  - 向量维度：Hash 128d / BGE-M3 1024d
  - 指标：Hit@10（子卡归一）、MRR、单查询延迟
  - 评测面是真实生产链路（7 通道融合 + vector channel）
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.pipeline.production_context import query_production_store  # noqa: E402
from eval_node_recall import DEFAULT_CASES  # noqa: E402

NODE_CARDS = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"
CASES = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "golden_cases.json"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"


class LocalBGEProvider:
    """sentence-transformers BGE-M3 包装成 EmbeddingProvider 接口。"""

    provider_id = "local-bge-m3-1024"
    dimensions = 1024

    def __init__(self, model_name: str = r"C:/Users/000043ce/.cache/bge-m3-local"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.provider_id = f"local-bge-m3-{self.dimensions}"

    def embed(self, texts) -> list[list[float]]:
        if not texts:
            return []
        vecs = self.model.encode(list(texts), normalize_embeddings=True, batch_size=64)
        return [v.tolist() for v in vecs]


def build_index(db_path: Path, provider, label: str) -> dict:
    from agent_kb.commands.import_node_cards import run as import_run
    t0 = time.perf_counter()
    summary = import_run(
        db=db_path,
        node_cards=NODE_CARDS,
        domain_dir=DOMAIN_DIR,
        embedding_provider=provider,
    )
    dur = time.perf_counter() - t0
    print(f"[{label}] built in {dur:.1f}s | provider={summary['vector'].get('provider_id')} "
          f"| vectors={summary['vector'].get('vector_count')}")
    return summary


def evaluate(db_path: Path, domain_pack, cases, label: str) -> dict:
    hits = 0
    mrr_sum = 0.0
    latencies = []
    failures = []
    for case in cases:
        frame_q = case["query"]
        expected = case["expected"]
        expected_ids = {f"card:obc_dcdc:{e.split('#')[0]}" for e in expected}
        t0 = time.perf_counter()
        result = query_production_store(
            frame_q, db_path=db_path, domain_pack=domain_pack, retrieval_top_k=10
        )
        latencies.append(time.perf_counter() - t0)
        cand_ids = {c.source_id.split("#")[0] for c in result.retrieval_result.candidates}
        hit = bool(expected_ids & cand_ids)
        first_rank = None
        for rank, c in enumerate(result.retrieval_result.candidates, 1):
            if c.source_id.split("#")[0] in expected_ids:
                first_rank = rank
                break
        hits += 1 if hit else 0
        mrr_sum += 1.0 / first_rank if first_rank else 0.0
        if not hit:
            failures.append({
                "case": case["case_id"], "query": frame_q, "expected": expected,
                "top3": [c.source_id.replace("card:obc_dcdc:", "") for c in result.retrieval_result.candidates[:3]],
            })
    n = len(cases)
    return {
        "provider": label,
        "hit@10": f"{hits}/{n}",
        "hit_rate": round(hits / n * 100, 1),
        "mrr": round(mrr_sum / n, 3),
        "avg_query_s": round(sum(latencies) / len(latencies), 3),
        "failures": failures,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-db", type=Path, default=ROOT / "agent_kb_core" / "hash-eval.sqlite3")
    parser.add_argument("--bge-db", type=Path, default=ROOT / "agent_kb_core" / "bge-eval.sqlite3")
    parser.add_argument("--skip-build", action="store_true", help="跳过建库（复用已有库）")
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--bge-only", action="store_true")
    args = parser.parse_args()

    domain_pack = load_domain_pack(DOMAIN_DIR)
    cases = DEFAULT_CASES
    if CASES.exists():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
    print(f"node_cards: {NODE_CARDS.name} | cases: {len(cases)} | domain: {domain_pack.domain_id}")

    results = []

    # --- Hash 基线 ---
    if not args.bge_only:
        if not args.skip_build or not args.hash_db.exists():
            from agent_kb.embeddings import HashEmbeddingProvider
            build_index(args.hash_db, HashEmbeddingProvider(dimensions=128), "hash")
        results.append(evaluate(args.hash_db, domain_pack, cases, "hash-128d"))

    # --- BGE-M3 ---
    if not args.hash_only:
        if not args.skip_build or not args.bge_db.exists():
            bge = LocalBGEProvider()
            build_index(args.bge_db, bge, "bge-m3")
        results.append(evaluate(args.bge_db, domain_pack, cases, "bge-m3-1024d"))

    print(f"\n{'='*70}")
    print(f"{'provider':<14} {'hit@10':<8} {'hit_rate':<9} {'mrr':<8} {'avg_query_s':<10}")
    for r in results:
        print(f"{r['provider']:<14} {r['hit@10']:<8} {r['hit_rate']:<9} {r['mrr']:<8} {r['avg_query_s']:<10}")
    print("=" * 70)
    for r in results:
        if r["failures"]:
            print(f"\n[{r['provider']}] failures:")
            for f in r["failures"]:
                print(f"  ❌ {f['case']} | {f['query']} | 期望{f['expected']} | top3: {f['top3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
