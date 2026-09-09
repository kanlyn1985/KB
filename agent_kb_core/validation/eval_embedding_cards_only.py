#!/usr/bin/env python3
"""卡-only embedding 对比：Hash vs BGE-M3（只对检索卡嵌入，跳过 evidence/fact）。

背景：全量嵌入 30k 条（evidence+fact+card）在纯 CPU 上需数小时；节点级召回评测
只依赖卡片向量，因此本脚本只对 1,266 张检索卡做嵌入（~30 分钟），词法面保持全量，
公平对比两种 provider 在向量通道上的差异。

用法：
  python3 eval_embedding_cards_only.py [--hash-only | --bge-only] [--top-k 10]
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
from agent_kb.commands.import_node_cards import build_node_index  # noqa: E402
from agent_kb.embeddings import HashEmbeddingProvider  # noqa: E402
from agent_kb.pipeline.production_context import query_production_store  # noqa: E402
from agent_kb.storage.sqlite_store import SQLiteKnowledgeStore  # noqa: E402
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402
from agent_kb.retrieval.vector import SQLiteVectorIndex  # noqa: E402
from eval_node_recall import DEFAULT_CASES  # noqa: E402

NODE_CARDS = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"
CASES = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "golden_cases.json"
DOMAIN_DIR = ROOT / "agent_kb_core" / "domains" / "obc_dcdc"


class CardsOnlyIndex:
    """只暴露检索卡给向量索引（不嵌入 evidence/fact）。"""

    def __init__(self, index):
        self.object_projections = []
        self.retrieval_cards = index.retrieval_cards
        self.context_facts = []
        self.context_evidence = []


def build_cards_only_db(db_path: Path, provider, label: str) -> None:
    """建库：词法面全量（对象/卡/证据），向量面只嵌卡片。"""
    domain_pack = load_domain_pack(DOMAIN_DIR)
    index = build_node_index(NODE_CARDS, domain_pack)
    t0 = time.perf_counter()
    with SQLiteKnowledgeStore(db_path) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        store.upsert_index(index)  # 全量词法面
        vector = SQLiteVectorIndex(store.connection, provider=provider)
        vsum = vector.index_view(CardsOnlyIndex(index))  # 只嵌卡片
        summary = getattr(vsum, "to_dict", lambda: dict(vsum))()
    print(f"[{label}] built in {time.perf_counter() - t0:.1f}s | provider={summary.get('provider_id')} "
          f"| vector_count={summary.get('vector_count')}")


def evaluate(db_path: Path, domain_pack, cases, label: str, top_k: int) -> dict:
    hits = 0
    mrr_sum = 0.0
    latencies = []
    failures = []
    for case in cases:
        expected = case["expected"]
        expected_ids = {f"card:obc_dcdc:{e.split('#')[0]}" for e in expected}
        t0 = time.perf_counter()
        result = query_production_store(
            case["query"], db_path=db_path, domain_pack=domain_pack, retrieval_top_k=top_k
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
            failures.append({"case": case["case_id"], "query": case["query"], "expected": expected,
                             "top3": [c.source_id.replace("card:obc_dcdc:", "")
                                      for c in result.retrieval_result.candidates[:3]]})
    n = len(cases)
    return {
        "provider": label,
        f"hit@{top_k}": f"{hits}/{n}",
        "hit_rate": round(hits / n * 100, 1),
        "mrr": round(mrr_sum / n, 3),
        "avg_query_s": round(sum(latencies) / len(latencies), 3),
        "failures": failures,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--bge-only", action="store_true")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    domain_pack = load_domain_pack(DOMAIN_DIR)
    cases = DEFAULT_CASES
    if CASES.exists():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
    print(f"node_cards: {NODE_CARDS.name} | cases: {len(cases)} | domain: {domain_pack.domain_id} | top_k={args.top_k}")

    results = []
    if not args.bge_only:
        hash_db = ROOT / "agent_kb_core" / "cards-hash.sqlite3"
        if not args.skip_build or not hash_db.exists():
            build_cards_only_db(hash_db, HashEmbeddingProvider(dimensions=128), "hash")
        results.append(evaluate(hash_db, domain_pack, cases, "hash-128d", args.top_k))

    if not args.hash_only:
        bge_db = ROOT / "agent_kb_core" / "cards-bge.sqlite3"
        if not args.skip_build or not bge_db.exists():
            from eval_embedding_compare import LocalBGEProvider
            build_cards_only_db(bge_db, LocalBGEProvider(), "bge-m3")
        results.append(evaluate(bge_db, domain_pack, cases, "bge-m3-1024d", args.top_k))

    print(f"\n{'='*70}")
    header = f"{'provider':<14} {f'hit@{args.top_k}':<10} {'hit_rate':<9} {'mrr':<8} {'avg_query_s':<10}"
    print(header)
    for r in results:
        print(f"{r['provider']:<14} {r[f'hit@{args.top_k}']:<10} {r['hit_rate']:<9} {r['mrr']:<8} {r['avg_query_s']:<10}")
    print("=" * 70)
    for r in results:
        if r["failures"]:
            print(f"\n[{r['provider']}] failures:")
            for f in r["failures"]:
                print(f"  ❌ {f['case']} | {f['query']} | 期望{f['expected']} | top3: {f['top3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
