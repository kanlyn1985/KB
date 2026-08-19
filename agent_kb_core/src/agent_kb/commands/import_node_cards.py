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
from agent_kb.projection.models import ObjectProjection  # noqa: E402
from agent_kb.projection.projector import build_terminology_projections  # noqa: E402
from agent_kb.retrieval.cards import RetrievalCard  # noqa: E402
from agent_kb.retrieval.card_builder import build_retrieval_cards  # noqa: E402
from agent_kb.storage.sqlite_store import SQLiteKnowledgeStore  # noqa: E402
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402
from agent_kb.retrieval.vector import SQLiteVectorIndex  # noqa: E402


def build_node_index(
    node_cards_path: Path,
    domain_pack,
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
    return CompiledKnowledgeIndex(
        compilation=compilation,
        context_facts=facts,
        context_evidence=evidence,
        object_projections=projections,
        retrieval_cards=cards,
    )


def run(
    *,
    db: Path,
    node_cards: Path,
    domain_dir: Path | None = None,
    no_vector: bool = False,
) -> dict:
    """Execute the node-card import and return a summary dict."""
    domain_pack = load_domain_pack(domain_dir) if domain_dir else None
    index = build_node_index(node_cards, domain_pack)
    summary = {
        "objects": len(index.object_projections),
        "cards": len(index.retrieval_cards),
        "facts": len(index.context_facts),
        "evidence": len(index.context_evidence),
    }
    with SQLiteKnowledgeStore(db) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        upsert = store.upsert_index(index)
        summary["upsert"] = upsert
        if not no_vector:
            provider = HashEmbeddingProvider()
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
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
