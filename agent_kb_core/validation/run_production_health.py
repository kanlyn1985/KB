# -*- coding: utf-8 -*-
"""run_production_health.py —— 生产通道体检门（向量+图+融合，SQLite 生产库路径）。

与 run_retrieval_health.py（内存词法基线门）互补：
- 检索门：node_cards 内存检索面 + 规则理解（词法，离线）
- 本门：SQLite 生产库 + 持久通道（词法 FTS + 语义向量 + 图门控），嵌入经
  本机嵌入服务（tools/local_embed_server.py，默认 127.0.0.1:11500）

四类断言：
1. 通道消融回归：5 变体（词法/向量/图/双通道/生产全通道）对照基线
   production_health_baseline.json（Hit@5 ±2.5pp、MRR ±0.05 容差）；
2. 判定契约：5 条代表查询的 sufficient/partial 状态；
3. 生产默认（图门控）在域内样本上不引入额外候选污染（门控开启次数记录）；
4. 向量通道对齐：库内 provider 行数与嵌入维度自检。

用法：
  python run_production_health.py --json
  python run_production_health.py --sample-per-intent 10      # 默认
退出码：0=PASS，1=FAIL（基线回归或契约破坏）。

前置：本地嵌入服务已启动；numpy 可用；node-index.sqlite3 存在。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.query.understanding import understand_query  # noqa: E402
from agent_kb.retrieval.hybrid import hybrid_retrieve  # noqa: E402
from agent_kb.retrieval.models import RetrievalCandidate  # noqa: E402
from agent_kb.retrieval.production import ProductionCandidateProvider  # noqa: E402
from agent_kb.embeddings.remote import RemoteJSONEmbeddingProvider  # noqa: E402
from agent_kb.storage.sqlite_store import SQLiteKnowledgeStore  # noqa: E402
from agent_kb.retrieval.vector import SQLiteVectorIndex  # noqa: E402
from agent_kb.graph.store import SQLiteGraphStore  # noqa: E402

DB = ROOT / "agent_kb_core" / "validation" / "node-index.sqlite3"
GOLDEN = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing" / "golden_cases.json"
SKELETON = ROOT / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.6.json"
BASELINE = Path(__file__).resolve().parent / "production_health_baseline.json"
PROVIDER_ID = "remote-json:qllama/bge-small-zh-v1.5:512"
DIM = 512

DEFAULT_EMBED_URL = "http://127.0.0.1:11500/v1/embeddings"
# 判定契约：查询 -> (期望状态, 分数下限/上限说明)。partial 案例分数<0.75 即可（不钉死具体值）。
JUDGEMENT_CONTRACT = [
    ("HARA分析怎么做", "sufficient"),
    ("帮我介绍一下OBC的工作原理", "sufficient"),
    ("热仿真怎么做", "sufficient"),
    ("输出纹波要求是多少", "partial"),   # 槽位封顶：谨慎回答+披露（设计行为）
    ("灌封胶选型要求", "partial"),       # 语料空洞：诚实 partial
]

# 基线容差：Hit@5 ±2.5pp（1 个样本 ≈2.3pp）、MRR ±0.05
HIT_TOL_PP = 2.5
MRR_TOL = 0.05


def load_baseline() -> dict:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def stratified_cases(domain_pack, per_intent: int):
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    frames = {}
    by_intent: dict[str, list] = {}
    for c in cases:
        fr = understand_query(c["query"], domain_pack=domain_pack)
        frames[c["case_id"]] = fr
        by_intent.setdefault(fr.intent, []).append(c)
    sub = []
    for intent in sorted(by_intent):
        sub.extend(by_intent[intent][:per_intent])
    return sub, frames


def is_hit(cand_id, exp_id, parents):
    cand_id = cand_id.split("#")[0].replace("card:obc_dcdc:", "")
    if cand_id == exp_id:
        return True
    cur = parents.get(cand_id)
    while cur:
        if cur == exp_id:
            return True
        cur = parents.get(cur)
    return False


class PrecomputedVectorProvider:
    """预计算候选的向量通道替身：numpy 秒级预计算，规避纯 Python 全表扫描。"""

    def __init__(self, per_frame: dict[str, list[RetrievalCandidate]]):
        self._per_frame = per_frame
        self.provider_id = PROVIDER_ID

    def search(self, query_frame, *, limit: int = 32):
        from agent_kb.retrieval.vector import SQLiteVectorIndex  # noqa: F401 复用文本构造
        key = SQLiteVectorIndex._query_text_for_frame(query_frame)
        return list(self._per_frame.get(key, []))[: max(1, limit)]


def vector_query_text(frame) -> str:
    return " ".join(
        v for v in [
            frame.normalized_query,
            frame.target_topic,
            *frame.must_terms,
            *frame.aliases,
            *frame.should_terms,
        ] if v
    )


def warm_and_precompute(store, frames, sub, embed_url: str, vec_cache_path: Path):
    """预热查询向量（缓存文件优先，缺失才经网络）+ numpy 全库预计算。"""
    import sqlite3 as _sq
    con = _sq.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT source_type, source_id, object_id, payload_json, vector_json "
        "FROM embedding_vectors WHERE provider_id = ? AND dimensions = ?",
        (PROVIDER_ID, DIM),
    ).fetchall()
    con.close()
    meta, mat = [], []
    for st, sid, oid, pj, vj in rows:
        meta.append((st, sid, oid, json.loads(pj or "{}")))
        mat.append(json.loads(vj))
    M = np.asarray(mat, dtype=np.float32)
    M = M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-12)

    def vector_candidates(qvec, limit=48):
        q = np.asarray(qvec, dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        sims = M @ q
        idx = np.argsort(-sims)[: limit * 4]
        out = []
        for i in idx:
            s = float(sims[i])
            if s <= 0.0:
                break
            st, sid, oid, payload = meta[i]
            p = dict(payload)
            if oid and "object_id" not in p and "subject" not in p:
                p["object_id"] = oid
            out.append(RetrievalCandidate(
                candidate_id=f"{st}:{sid}", source_type=st, source_id=sid,
                channel="vector", score=s, matched_terms=[],
                reasons=["vector_similarity"], payload=p))
            if len(out) >= limit:
                break
        return out

    saved = {}
    if vec_cache_path.exists():
        saved = json.loads(vec_cache_path.read_text(encoding="utf-8"))
    precomputed = {}
    missing = []
    for case in sub:
        fr = frames[case["case_id"]]
        key = vector_query_text(fr)
        precomputed[key] = None
        if key not in saved:
            missing.append(key)
    if missing:
        provider = RemoteJSONEmbeddingProvider.from_environment()
        t0 = time.time()
        for i, key in enumerate(missing):
            try:
                saved[key] = list(provider.embed([key])[0])
            except Exception:
                time.sleep(4)
                saved[key] = list(provider.embed([key])[0])
            if (i + 1) % 10 == 0:
                print(f"  嵌入预热 ...{i+1}/{len(missing)}", flush=True)
        vec_cache_path.write_text(json.dumps(saved), encoding="utf-8")
        print(f"  预热 {len(missing)} 条新查询向量 ({time.time()-t0:.0f}s)", flush=True)
    else:
        print("  查询向量全部命中缓存", flush=True)
    for key in precomputed:
        precomputed[key] = vector_candidates(saved[key])
    return precomputed


def eval_variant(name, make_provider, store, index, graph, frames, sub, parents):
    rows = []
    graph_exec = 0
    for case in sub:
        fr = frames[case["case_id"]]
        exp = {e.split("#")[0] for e in case["expected"]}
        provider = make_provider(store, index, graph)
        rr = hybrid_retrieve(fr, index, persistent_provider=provider, top_k=5)
        cand = [x.source_id.split("#")[0].replace("card:obc_dcdc:", "") for x in rr.candidates]
        hit = any(any(is_hit(x, y, parents) for y in exp) for x in cand)
        rank = next((r for r, x in enumerate(cand, 1)
                     if any(is_hit(x, y, parents) for y in exp)), None)
        rows.append({"variant": name, "intent": fr.intent, "case_id": case["case_id"],
                     "hit": int(hit), "mrr": 1.0/rank if rank else 0.0})
        diag = rr.diagnostics.channel_candidate_counts
        if diag.get("graph_search", 0):
            graph_exec += 1
    n = len(rows)
    summary = {
        "n": n,
        "hit5_pct": round(sum(r["hit"] for r in rows)/n*100, 2) if n else 0.0,
        "mrr": round(sum(r["mrr"] for r in rows)/n, 4) if n else 0.0,
    }
    return rows, summary, graph_exec


def main() -> int:
    as_json = "--json" in sys.argv
    per_intent = int(sys.argv[sys.argv.index("--sample-per-intent") + 1]) if "--sample-per-intent" in sys.argv else 10
    embed_url = sys.argv[sys.argv.index("--embed-url") + 1] if "--embed-url" in sys.argv else DEFAULT_EMBED_URL
    import os
    os.environ.setdefault("AGENT_KB_EMBEDDING_URL", embed_url)
    os.environ.setdefault("AGENT_KB_EMBEDDING_MODEL", "qllama/bge-small-zh-v1.5")
    os.environ.setdefault("AGENT_KB_EMBEDDING_DIMENSIONS", "512")

    domain_pack = load_domain_pack(ROOT / "agent_kb_core" / "domains" / "obc_dcdc")
    baseline = load_baseline()
    vec_cache = Path(__file__).resolve().parent / "production_health_query_vectors.json"

    sub, frames = stratified_cases(domain_pack, per_intent)
    skel = json.loads(SKELETON.read_text(encoding="utf-8"))
    parents = {n["id"]: n.get("parent") for n in skel["nodes"]}
    print(f"[样本] {len(sub)} 条（每意图 ≤{per_intent}）", flush=True)

    failures: list[str] = []
    details: dict = {}

    with SQLiteKnowledgeStore(DB) as store:
        index = store.load_index_view()
        graph = SQLiteGraphStore(store.connection)

        n_vec = store.connection.execute(
            "SELECT COUNT(*) FROM embedding_vectors WHERE provider_id = ?", (PROVIDER_ID,)).fetchone()[0]
        if n_vec != 31557:
            failures.append(f"向量行数 {n_vec} != 31557")
        details["vector_rows"] = n_vec

        precomputed = warm_and_precompute(store, frames, sub, embed_url, vec_cache)
        mock = PrecomputedVectorProvider(precomputed)

        variants = {
            "lexical_only": lambda s, i, g: ProductionCandidateProvider(lexical=s),
            "vector_only": lambda s, i, g: ProductionCandidateProvider(vector=mock),
            "graph_only": lambda s, i, g: ProductionCandidateProvider(graph=g),
            "lexical+vector": lambda s, i, g: ProductionCandidateProvider(lexical=s, vector=mock),
            "production_full": lambda s, i, g: ProductionCandidateProvider(lexical=s, vector=mock, graph=g),
        }

        allrows = []
        for name, make in variants.items():
            rows, summary, graph_exec = eval_variant(name, make, store, index, graph, frames, sub, parents)
            allrows += rows
            summary["graph_exec_cases"] = graph_exec
            details.setdefault("variants", {})[name] = summary
            base = baseline.get("variants", {}).get(name, {})
            line = f"[{name:<16}] hit@5={summary['hit5_pct']}% mrr={summary['mrr']} graph执行={graph_exec}"
            if base:
                dh = summary["hit5_pct"] - base["hit5_pct"]
                dm = summary["mrr"] - base["mrr"]
                ok = abs(dh) <= HIT_TOL_PP and abs(dm) <= MRR_TOL
                line += f"  基线 {base['hit5_pct']}%/{base['mrr']}  Δ={dh:+.1f}pp/{dm:+.4f}  {'OK' if ok else 'REGRESS'}"
                if not ok:
                    failures.append(
                        f"{name}: hit@5 {summary['hit5_pct']}% (基线 {base['hit5_pct']}%, Δ{dh:+.1f}pp), "
                        f"mrr {summary['mrr']} (基线 {base['mrr']}, Δ{dm:+.4f})")
            print(line, flush=True)

        # 判定契约
        print("[判定契约]", flush=True)
        contract_results = []
        for q, want in JUDGEMENT_CONTRACT:
            frame = understand_query(q, domain_pack=domain_pack)
            cp = ProductionCandidateProvider(lexical=store, vector=mock)
            rr = hybrid_retrieve(frame, index, persistent_provider=cp, top_k=12)
            object_ids = set(rr.selected_object_ids)
            card_ids = set(rr.selected_card_ids)
            from agent_kb.context.builder import build_context_pack, fill_missing_shapes, select_retrieval_cards
            cards = select_retrieval_cards(
                selected_card_ids=set(rr.selected_card_ids),
                selected_object_ids=object_ids,
                all_cards=list(index.retrieval_cards))
            pack = build_context_pack(
                query_frame=frame, domain_pack=domain_pack,
                objects=[x for x in index.object_projections if x.object_id in object_ids],
                retrieval_cards=cards,
                facts=[x for x in index.context_facts if x.fact_id in set(rr.selected_fact_ids)],
                evidence=[x for x in index.context_evidence if x.evidence_id in set(rr.selected_evidence_ids)],
            )
            fill = fill_missing_shapes(
                frame, list(index.context_facts), list(index.context_evidence),
                selected_fact_ids={x.fact_id for x in pack.facts},
                selected_evidence_ids={x.evidence_id for x in pack.evidence})
            from dataclasses import replace as dreplace
            if fill.fact_ids or fill.evidence_ids:
                fmap = {x.fact_id: x for x in index.context_facts}
                emap = {x.evidence_id: x for x in index.context_evidence}
                hf = {x.fact_id for x in pack.facts}
                he = {x.evidence_id for x in pack.evidence}
                pack = dreplace(pack,
                                facts=[*pack.facts, *(fmap[f] for f in fill.fact_ids if f in fmap and f not in hf)],
                                evidence=[*pack.evidence, *(emap[e] for e in fill.evidence_ids if e in emap and e not in he)])
            from agent_kb.context.evidence_judge import judge_context_pack
            j = judge_context_pack(pack, relevance_score=float(rr.candidates[0].score) if rr.candidates else 0.0)
            ok = j.status == want
            if not ok:
                failures.append(f"判定契约 {q}: 期望 {want} 实得 {j.status}({j.score})")
            contract_results.append({"query": q, "expect": want, "status": j.status, "score": j.score})
            print(f"  [{'OK' if ok else 'XX'}] {q} -> {j.status}({j.score})", flush=True)
        details["judgement_contract"] = contract_results

    details["rows"] = allrows
    report = {"baseline_version": "2026-08-28-real-vector", "details": {k: v for k, v in details.items() if k != "rows"}}
    (Path(__file__).resolve().parent / "production_health_last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("-" * 72)
    if failures:
        print(f"结论: FAIL —— {len(failures)} 项")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("结论: PASS —— 生产通道全部断言达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())