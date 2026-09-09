#!/usr/bin/env python3
"""节点卡正式接入：import-node-cards 命令实现。

把骨架节点卡（node_cards.jsonl，245,976 落位单元聚合的 209 张卡）
+ 参数对象投影（术语表）导入 SQLite 生产索引，
使 query-production 能按节点级召回。

用法：
  agent-kb import-node-cards --db agent-kb.sqlite3 \
      --node-cards docs/ontology/tree_skeleton/llm_landing/node_cards.jsonl \
      --domain-dir domains/obc_dcdc \
      [--vector-embed]  # 同时生成向量索引（默认开启）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_kb.context.context_pack import ContextEvidence, ContextFact  # noqa: E402
from agent_kb.core.documents import DocumentRecord  # noqa: E402
from agent_kb.core.compiler import KnowledgeCompilation  # noqa: E402
from agent_kb.core.evidence import EvidenceBlock  # noqa: E402
from agent_kb.core.source_units import SourceUnit  # noqa: E402
from agent_kb.core.facts import Fact  # noqa: E402
from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.embeddings.providers import HashEmbeddingProvider  # noqa: E402
from agent_kb.pipeline.document_context import CompiledKnowledgeIndex  # noqa: E402
from agent_kb.graph.store import SQLiteGraphStore  # noqa: E402
from agent_kb.projection.models import (
    EvidenceRef,  # noqa: E402
    ObjectProjection,  # noqa: E402
    ObjectRelation,  # noqa: E402
)
from agent_kb.projection.projector import build_terminology_projections  # noqa: E402
from agent_kb.retrieval.cards import RetrievalCard  # noqa: E402
from agent_kb.retrieval.card_builder import build_retrieval_cards  # noqa: E402
from agent_kb.storage.sqlite_store import SQLiteKnowledgeStore  # noqa: E402
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402
from agent_kb.retrieval.vector import SQLiteVectorIndex  # noqa: E402


def build_node_index(
    node_cards_path: Path,
    domain_pack,
    skeleton_relations=None,
    skeleton_nodes=None,
) -> CompiledKnowledgeIndex:
    """从 node_cards.jsonl 构建 CompiledKnowledgeIndex。

    对象投影：参数对象（术语表）+ 骨架节点（node_cards）
    检索卡：参数卡 + 节点卡（search_text 含聚合内容）
    """
    projections: list[ObjectProjection] = build_terminology_projections(domain_pack)
    cards: list[RetrievalCard] = build_retrieval_cards(projections)
    evidence: list[ContextEvidence] = []
    facts: list[ContextFact] = []

    # 节点卡覆盖同 ID 的术语投影（节点卡含聚合内容，检索面更完整）
    node_ids_in_cards: set[str] = set()
    for line in node_cards_path.open(encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        node_ids_in_cards.add(c["node_id"])

    projections = [p for p in projections if p.object_id not in node_ids_in_cards]
    cards = [c for c in cards if c.object_id not in node_ids_in_cards]

    for line in node_cards_path.open(encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        nid = c["node_id"]
        chunk_of = c.get("chunk_of")
        # 子卡不生成对象投影（父节点已有），只生成卡片 + evidence
        if not chunk_of:
            projections.append(
                ObjectProjection(
                    object_id=nid,
                    domain=domain_pack.domain_id,
                    object_type=c["layer"],
                    canonical_name=c["node_name"],
                    description=c.get("content", "")[:500],
                    aliases=list(c.get("aliases", [])),
                    properties={"source": "skeleton_v0.4", "layer": c["layer"],
                                "unit_count": c.get("unit_count", 0),
                                "doc_count": c.get("doc_count", 0)},
                    evidence_refs=[],
                    confidence=1.0,
                    status="active",
                )
            )

        # 节点 evidence：把聚合内容拆成单元级证据（按行/段落）
        content = c.get("content", "")
        ev_ids: list[str] = []
        doc_id = f"doc:node:{nid}"
        seen_snippets: set[str] = set()
        for raw_line in content.splitlines():
            snippet = raw_line.strip()
            if not snippet or len(snippet) < 8 or snippet in seen_snippets:
                continue
            seen_snippets.add(snippet)
            ev_id = f"evd:node:{nid}:{len(ev_ids)}"
            evidence.append(ContextEvidence(
                evidence_id=ev_id,
                document_id=doc_id,
                page_no=None,
                snippet=snippet[:2000],
                confidence=0.9,
            ))
            ev_ids.append(ev_id)
            if len(ev_ids) >= 24:  # 每节点最多 24 条证据（控制索引体积）
                break

        # 节点 fact：term_definition，subject=节点 ID，绑定 evidence（仅父节点）
        if not chunk_of:
            fact_id = f"fact:node:{nid}"
            facts.append(ContextFact(
                fact_id=fact_id,
                fact_type="term_definition",
                subject=nid,
                predicate="defines",
                object_value=c["node_name"],
                qualifiers={"aliases": c.get("aliases", []),
                            "unit_count": c.get("unit_count", 0)},
                evidence_ids=ev_ids,
                confidence=0.9,
            ))
            # 补充 shape fact：按层级/内容给约束、流程、表格类查询提供证据 shape
            # （否则 constraint_lookup/procedure 意图永远缺 shape → 判定 partial）
            layer = c.get("layer", "")
            content = c.get("content", "")
            shape_facts = _shape_facts_for_node(nid, layer, content, c.get("node_name", ""), ev_ids)
            facts.extend(shape_facts)

        cards.append(
            RetrievalCard(
                card_id=f"card:{domain_pack.domain_id}:{nid}",
                domain=domain_pack.domain_id,
                object_id=nid,
                card_type=c["layer"],
                title=c["node_name"] + (f" #{nid.split('#')[-1]}" if chunk_of else ""),
                search_text=" ".join([
                    c["node_name"], c.get("content", "")[:4000],
                    *c.get("aliases", []),
                ]),
                aliases=list(c.get("aliases", [])),
                related_object_ids=[chunk_of] if chunk_of else [],
                evidence_ids=ev_ids,
                answer_shapes=["definition", "general_search"],
                structured_payload={"node": nid,
                                    "unit_count": c.get("unit_count", 0),
                                    "chunk_of": chunk_of},
                confidence=1.0,
            )
        )

    # 空 compilation（节点卡无原始文档编译）
    doc = DocumentRecord(
        document_id="node-cards-import",
        title="Skeleton Node Cards",
        source_type="node_cards",
        mime_type="application/json",
        sha256="0" * 64,
        size_bytes=0,
    )
    compilation = KnowledgeCompilation(
        document=doc,
        evidence_blocks=[],
        source_units=[],
        facts=[],
    )
    # 骨架本体关系：skeleton_v0.x.json 的 relations（R→F→L→P 主链等）转成
    # 证据映射边（ObjectRelation），随索引持久化进 graph_edges，使查询管线
    # 的图通道（BFS, 生产权重 0.85）真正参与召回。
    relations: list[ObjectRelation] = []
    for rel in skeleton_relations or []:
        src_id = str(rel.get("source") or "").strip()
        dst_id = str(rel.get("target") or "").strip()
        rtype = str(rel.get("type") or "").strip() or "related_to"
        if not src_id or not dst_id or src_id == dst_id:
            continue
        refs = [EvidenceRef(evidence_id=str(r))
                for r in (rel.get("evidence_refs") or []) if str(r).strip()]
        conf = 0.75 if not refs else min(0.95, 0.75 + 0.05 * len(refs))
        relations.append(ObjectRelation(
            relation_id=f"rel:{domain_pack.domain_id}:{rtype}:{src_id}:{dst_id}",
            domain=domain_pack.domain_id,
            relation_type=rtype,
            source_object_id=src_id,
            target_object_id=dst_id,
            properties={"category": rel.get("category"),
                        "inverse": rel.get("inverse"),
                        "project_scope": rel.get("project_scope"),
                        "origin": "skeleton"},
            evidence_refs=refs,
            confidence=conf,
            status="materialized",
        ))

    # 结构树包含边（parent -> child）：跨层关系边只覆盖 R/F/L/P 主链，
    # 查询起点常落在无边节点（G 过程层、P-KNOW 知识节点等）。补上结构
    # 树后任何链接节点都有邻域可走（叶子->父->兄弟），图通道才有召回。
    seen_pairs = {(r.source_object_id, r.target_object_id) for r in relations}
    for node in skeleton_nodes or []:
        child = str(node.get("id") or "").strip()
        parent = str(node.get("parent") or "").strip()
        if not child or not parent or parent == child:
            continue
        # 已有同名边则跳过；反向（child->parent 的 instance-of 等）保留，
        # 因为遍历是有向双向的，不重复加只影响 edge_id 唯一性。
        if (parent, child) in seen_pairs:
            continue
        seen_pairs.add((parent, child))
        relations.append(ObjectRelation(
            relation_id=f"rel:{domain_pack.domain_id}:contains:{parent}:{child}",
            domain=domain_pack.domain_id,
            relation_type="contains",
            source_object_id=parent,
            target_object_id=child,
            properties={"category": "structural", "origin": "skeleton_tree"},
            evidence_refs=[],
            confidence=0.9,
            status="materialized",
        ))

    return CompiledKnowledgeIndex(
        compilation=compilation,
        context_facts=facts,
        context_evidence=evidence,
        object_projections=projections,
        retrieval_cards=cards,
        object_relations=relations,
    )


def _shape_facts_for_node(
    nid: str,
    layer: str,
    content: str,
    node_name: str,
    ev_ids: list[str],
) -> list[ContextFact]:
    """按层级/内容补充证据 shape fact。

    - R 层（需求/标准）→ requirement_constraint
    - G 层（过程/方法/验证）→ procedure / test_method
    - L 层（逻辑/策略）→ procedure
    - 内容含表格特征（|、制表符、多列）→ table_row
    让 constraint_lookup / procedure 意图在节点卡上也能覆盖 shape，
    否则判定恒为 partial（缺 parameter_constraint/table_row/procedure shape）。
    """
    out: list[ContextFact] = []
    shape_meta = [
        (("R",), "requirement_constraint", "constrains"),
        (("G",), "procedure", "describes_process"),
    ]
    for layers, shape, predicate in shape_meta:
        if layer in layers:
            out.append(ContextFact(
                fact_id=f"fact:node:{nid}:{shape}",
                fact_type=shape,
                subject=nid,
                predicate=predicate,
                object_value=node_name,
                qualifiers={"layer": layer, "unit_count": 0},
                evidence_ids=ev_ids,
                confidence=0.7,
            ))
    if "|" in content or "\t" in content:
        out.append(ContextFact(
            fact_id=f"fact:node:{nid}:table_row",
            fact_type="table_row",
            subject=nid,
            predicate="contains_structured_row",
            object_value=node_name,
            qualifiers={"layer": layer, "unit_count": 0},
            evidence_ids=ev_ids,
            confidence=0.6,
        ))
    return out


def run(
    *,
    db: Path,
    node_cards: Path,
    domain_dir: Path | None = None,
    no_vector: bool = False,
    embedding_provider=None,
    skeleton: Path | None = None,
) -> dict:
    """Execute the node-card import and return a summary dict."""
    domain_pack = load_domain_pack(domain_dir) if domain_dir else None
    if skeleton is None:
        # 默认自动发现仓库内骨架文件（含本体 relations）
        default_skeleton = (Path(__file__).resolve().parents[3]
                            / "docs" / "ontology" / "tree_skeleton" / "skeleton_v0.6.json")
        if default_skeleton.exists():
            skeleton = default_skeleton
    skeleton_relations = None
    skeleton_nodes = None
    if skeleton is not None:
        skel_data = json.loads(skeleton.read_text(encoding="utf-8"))
        skeleton_relations = skel_data.get("relations", [])
        skeleton_nodes = skel_data.get("nodes", [])
    index = build_node_index(node_cards, domain_pack,
                             skeleton_relations=skeleton_relations,
                             skeleton_nodes=skeleton_nodes)
    summary = {
        "objects": len(index.object_projections),
        "cards": len(index.retrieval_cards),
        "facts": len(index.context_facts),
        "evidence": len(index.context_evidence),
        "relations": len(index.object_relations),
    }
    with SQLiteKnowledgeStore(db) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        # 关闭逐条 FTS 写入，upsert 后一次性批量重建 trigram 索引（快一个量级）
        store._fts_enabled = False
        upsert = store.upsert_index(index)
        summary["upsert"] = upsert
        store._fts_enabled = True
        summary["fts"] = store.rebuild_fts()
        if index.object_relations:
            graph = SQLiteGraphStore(store.connection)
            summary["graph_edges"] = graph.upsert_relations(index.object_relations)
        if not no_vector:
            provider = embedding_provider or HashEmbeddingProvider()
            vector = SQLiteVectorIndex(store.connection, provider=provider)
            vsum = vector.index_view(index)
            summary["vector"] = getattr(vsum, "to_dict", lambda: dict(vsum))()
        summary["schema_version"] = migrator.current_version()
    return summary


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = _parse(argv)
    summary = run(
        db=args.db,
        node_cards=args.node_cards,
        domain_dir=args.domain_dir,
        no_vector=args.no_vector,
        embedding_provider=args.embedding_provider,
        skeleton=args.skeleton,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def _parse(argv: list[str]):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--node-cards", type=Path, required=True,
                        help="node_cards.jsonl 路径")
    parser.add_argument("--domain-dir", type=Path, default=None)
    parser.add_argument("--no-vector", action="store_true",
                        help="跳过向量索引（仅词法+持久化）")
    parser.add_argument("--skeleton", type=Path, default=None,
                        help="骨架 JSON（含 relations）。默认自动使用 "
                             "docs/ontology/tree_skeleton/skeleton_v0.6.json")
    parser.add_argument("--remote-embedding", action="store_true",
                        help="使用远程语义嵌入（AGENT_KB_EMBEDDING_URL 等环境变量），"
                             "未配置时回退 HashEmbeddingProvider")
    args = parser.parse_args(argv)
    if args.remote_embedding:
        from agent_kb.embeddings import RemoteJSONEmbeddingProvider
        args.embedding_provider = RemoteJSONEmbeddingProvider.from_environment()
    else:
        args.embedding_provider = None
    return args


if __name__ == "__main__":
    sys.exit(main())
