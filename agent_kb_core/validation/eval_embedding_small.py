#!/usr/bin/env python3
"""小样本 embedding 对比：Hash vs BGE-M3（只编码 210 个父节点简短描述）。

用途：CPU 上全量编码 1266 卡 × 4000 字符不可行（实测 9h+ 未完成）。
本脚本只编码父节点 title+aliases+content[:300]（~100KB 文本），
几分钟完成，直接对比两种 provider 的向量通道召回能力。

用法：
  python3 eval_embedding_small.py [--hash-only | --bge-only]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from agent_kb.embeddings import HashEmbeddingProvider, cosine_similarity, normalize_vector  # noqa: E402
from eval_node_recall import DEFAULT_CASES  # noqa: E402

NODE_CARDS = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "node_cards.jsonl"
CASES = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "golden_cases.json"


def load_parent_nodes() -> list[dict]:
    """只取父节点（node_id 无 # 后缀），文本 = title + aliases + content[:300]。"""
    nodes: dict[str, dict] = {}
    for line in NODE_CARDS.open(encoding="utf-8"):
        c = json.loads(line)
        nid = c["node_id"]
        if "#" in nid:
            continue
        nodes[nid] = c
    out = []
    for nid, c in nodes.items():
        text = " ".join([
            c["node_name"], c.get("content", "")[:300],
            *c.get("aliases", []),
        ])
        out.append({"node_id": nid, "text": text})
    return out


def embed_all(provider, nodes: list[dict]) -> dict[str, list[float]]:
    t0 = time.perf_counter()
    vecs = provider.embed([n["text"] for n in nodes])
    dur = time.perf_counter() - t0
    print(f"  [{provider.provider_id}] embedded {len(nodes)} in {dur:.1f}s "
          f"({dur / max(len(nodes), 1) * 1000:.0f} ms/node)")
    return {n["node_id"]: v for n, v in zip(nodes, vecs, strict=True)}


def evaluate(provider, nodes: list[dict], vectors: dict[str, list[float]], cases: list[dict]) -> dict:
    hits = 0
    mrr_sum = 0.0
    latencies = []
    failures = []
    for case in cases:
        query = case["query"]
        expected = case["expected"]
        qv = normalize_vector(provider.embed([query])[0])
        t0 = time.perf_counter()
        scored = sorted(
            ((cosine_similarity(qv, v), nid) for nid, v in vectors.items()),
            key=lambda x: x[0],
            reverse=True,
        )
        latencies.append(time.perf_counter() - t0)
        rank = None
        for i, (sim, nid) in enumerate(scored, 1):
            if nid.split("#")[0] in expected:
                rank = i
                break
        hits += 1 if rank else 0
        mrr_sum += 1.0 / rank if rank else 0.0
        if not rank:
            failures.append({
                "case": case["case_id"], "query": query, "expected": expected,
                "top3": [nid for _, nid in scored[:3]],
            })
    n = len(cases)
    return {
        "provider": provider.provider_id,
        "hit@10": f"{hits}/{n}",
        "hit_rate": round(hits / n * 100, 1),
        "mrr": round(mrr_sum / n, 3),
        "avg_query_ms": round(sum(latencies) / len(latencies) * 1000, 1),
        "failures": failures,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--bge-only", action="store_true")
    args = parser.parse_args()

    nodes = load_parent_nodes()
    cases = DEFAULT_CASES
    if CASES.exists():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
    print(f"parent nodes: {len(nodes)} | cases: {len(cases)}")

    results = []
    if not args.bge_only:
        from agent_kb.embeddings import HashEmbeddingProvider
        provider = HashEmbeddingProvider(dimensions=128)
        vecs = embed_all(provider, nodes)
        results.append(evaluate(provider, nodes, vecs, cases))

    if not args.hash_only:
        from eval_embedding_compare import LocalBGEProvider
        provider = LocalBGEProvider()
        vecs = embed_all(provider, nodes)
        results.append(evaluate(provider, nodes, vecs, cases))

    print(f"\n{'='*66}")
    print(f"{'provider':<22} {'hit@10':<8} {'hit_rate':<9} {'mrr':<8} {'avg_query_ms':<10}")
    for r in results:
        print(f"{r['provider']:<22} {r['hit@10']:<8} {r['hit_rate']:<9} {r['mrr']:<8} {r['avg_query_ms']:<10}")
    print("=" * 66)
    for r in results:
        if r["failures"]:
            print(f"\n[{r['provider']}] failures:")
            for f in r["failures"]:
                print(f"  ❌ {f['case']} | {f['query']} | 期望{f['expected']} | top3: {f['top3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
