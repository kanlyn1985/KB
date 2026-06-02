from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .retrieval import search_knowledge_base


DISSATISFACTION_CATEGORIES = {
    "incomplete_answer": "答案不完整",
    "inaccurate_answer": "答案不准确",
    "retrieval_miss": "检索不到相关信息",
    "irrelevant_answer": "答案与问题不相关",
    "missing_evidence": "缺少依据事实",
    "unclear_term": "术语解释不清",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _next_feedback_id(connection) -> str:
    row = connection.execute(
        "SELECT feedback_id FROM answer_feedback ORDER BY feedback_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return "FB-000001"
    last_id = row["feedback_id"]
    num = int(re.search(r"\d+", last_id).group()) + 1
    return f"FB-{num:06d}"


def submit_feedback(
    workspace_root: Path,
    *,
    query: str,
    direct_answer: str,
    answer_mode: str | None = None,
    preferred_doc_id: str | None = None,
    confidence_score: float | None = None,
    satisfaction: str,
    categories: list[str] | None = None,
    user_comment: str | None = None,
) -> dict[str, object]:
    """Record user feedback on an answer. If unsatisfied, trigger automatic reflection."""
    if satisfaction not in ("satisfied", "unsatisfied"):
        raise ValueError(f"satisfaction must be 'satisfied' or 'unsatisfied', got '{satisfaction}'")
    if categories is None:
        categories = []
    for cat in categories:
        if cat not in DISSATISFACTION_CATEGORIES:
            raise ValueError(f"unknown category '{cat}', must be one of {list(DISSATISFACTION_CATEGORIES)}")

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        feedback_id = _next_feedback_id(connection)
        connection.execute(
            """
            INSERT INTO answer_feedback
                (feedback_id, query, direct_answer, answer_mode, preferred_doc_id,
                 confidence_score, satisfaction, categories_json, user_comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                query,
                direct_answer,
                answer_mode,
                preferred_doc_id,
                confidence_score,
                satisfaction,
                json.dumps(categories, ensure_ascii=False),
                user_comment,
                _utc_now(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    reflection = None
    if satisfaction == "unsatisfied" and categories:
        reflection = _reflect_on_feedback(workspace_root, feedback_id)

    return {
        "feedback_id": feedback_id,
        "satisfaction": satisfaction,
        "reflection": reflection,
    }


def _reflect_on_feedback(workspace_root: Path, feedback_id: str) -> dict[str, object]:
    """Analyze an unsatisfied feedback record and produce a diagnostic reflection."""
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            "SELECT * FROM answer_feedback WHERE feedback_id = ?",
            (feedback_id,),
        ).fetchone()
        if row is None:
            return {"diagnosis": [], "suggested_actions": []}

        query = row["query"]
        categories = json.loads(row["categories_json"] or "[]")
        answer_mode = row["answer_mode"]
        preferred_doc_id = row["preferred_doc_id"]
        confidence_score = row["confidence_score"]

        diagnosis: list[dict[str, str]] = []
        suggested_actions: list[dict[str, str]] = []

        for cat in categories:
            if cat == "retrieval_miss":
                try:
                    hits = search_knowledge_base(workspace_root, query, limit=5)
                    hit_count = len(hits)
                except (ValueError, OSError, RuntimeError):
                    hit_count = 0
                if hit_count == 0:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "fact_extraction_gap",
                        "detail": f"查询 '{query}' 检索到 0 条结果，知识库可能未覆盖此内容",
                    })
                    suggested_actions.append({
                        "action": "rebuild_coverage",
                        "doc_id": preferred_doc_id or "",
                        "reason": "检索空结果，需重建覆盖以刷新 fact/evidence 链路",
                    })
                else:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "retrieval_quality_low",
                        "detail": f"检索到 {hit_count} 条结果但未命中关键信息，排序或相关度有问题",
                    })
                    suggested_actions.append({
                        "action": "auto_activate_golden",
                        "doc_id": preferred_doc_id or "",
                        "reason": "补充 golden case 以验证和改进检索排序",
                    })

            elif cat == "incomplete_answer":
                if preferred_doc_id:
                    fact_count = connection.execute(
                        "SELECT COUNT(*) as cnt FROM facts WHERE source_doc_id = ?",
                        (preferred_doc_id,),
                    ).fetchone()["cnt"]
                    su_count = connection.execute(
                        "SELECT COUNT(*) as cnt FROM source_units WHERE doc_id = ?",
                        (preferred_doc_id,),
                    ).fetchone()["cnt"]
                    coverage_rate = fact_count / max(su_count, 1)
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "knowledge_extraction_incomplete",
                        "detail": f"文档 {preferred_doc_id} 有 {su_count} 个源单元但只有 {fact_count} 条事实，覆盖率 {coverage_rate:.1%}",
                    })
                    suggested_actions.append({
                        "action": "rebuild_coverage",
                        "doc_id": preferred_doc_id,
                        "reason": f"fact 覆盖率仅 {coverage_rate:.1%}，需重建知识提取",
                    })
                else:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "knowledge_extraction_incomplete",
                        "detail": "答案不完整，但未指定文档，无法量化覆盖情况",
                    })

            elif cat == "inaccurate_answer":
                if confidence_score is not None and confidence_score < 0.5:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "low_confidence_facts",
                        "detail": f"答案置信度仅 {confidence_score:.2f}，低于 0.5 阈值，事实质量不足",
                    })
                    suggested_actions.append({
                        "action": "auto_activate_golden",
                        "doc_id": preferred_doc_id or "",
                        "reason": "低置信度答案需要 golden case 验证事实准确性",
                    })
                else:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "fact_linkage_error",
                        "detail": "答案内容与事实不符，可能是事实链接或组合逻辑出错",
                    })

            elif cat == "irrelevant_answer":
                diagnosis.append({
                    "category": cat,
                    "root_cause": "query_routing_mismatch",
                    "detail": f"问题被路由为 '{answer_mode}' 模式，可能分类错误导致答非所问",
                })
                suggested_actions.append({
                    "action": "rebuild_coverage",
                    "doc_id": preferred_doc_id or "",
                    "reason": "query routing 错误，需检查 answer_mode 分配逻辑",
                })

            elif cat == "missing_evidence":
                if preferred_doc_id:
                    linked = connection.execute(
                        """
                        SELECT COUNT(*) as cnt FROM source_unit_fact_map
                        WHERE doc_id = ?
                        """,
                        (preferred_doc_id,),
                    ).fetchone()["cnt"]
                    total_facts = connection.execute(
                        "SELECT COUNT(*) as cnt FROM facts WHERE source_doc_id = ?",
                        (preferred_doc_id,),
                    ).fetchone()["cnt"]
                    broken = total_facts - linked
                    if broken > 0:
                        diagnosis.append({
                            "category": cat,
                            "root_cause": "broken_evidence_chain",
                            "detail": f"文档 {preferred_doc_id} 有 {total_facts} 条事实，仅 {linked} 条有 source_unit 链路，{broken} 条断裂",
                        })
                        suggested_actions.append({
                            "action": "rebuild_coverage",
                            "doc_id": preferred_doc_id,
                            "reason": f"{broken} 条事实缺少证据链路，需重建覆盖",
                        })
                    else:
                        diagnosis.append({
                            "category": cat,
                            "root_cause": "evidence_shape_gap",
                            "detail": "所有事实有链路但证据维度不完整，缺少必要证据类型",
                        })
                else:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "missing_evidence_chain",
                        "detail": "缺少依据事实，但未指定文档无法定位具体链路断裂",
                    })

            elif cat == "unclear_term":
                if preferred_doc_id:
                    term_count = connection.execute(
                        """
                        SELECT COUNT(*) as cnt FROM entities
                        WHERE entity_id LIKE ? AND entity_type = 'term_definition'
                        """,
                        (f"{preferred_doc_id}:%",),
                    ).fetchone()["cnt"]
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "term_definition_gap",
                        "detail": f"文档 {preferred_doc_id} 仅定义了 {term_count} 个术语，术语覆盖不足",
                    })
                    suggested_actions.append({
                        "action": "rebuild_coverage",
                        "doc_id": preferred_doc_id,
                        "reason": "术语定义不足，需增强 entity 提取",
                    })
                else:
                    diagnosis.append({
                        "category": cat,
                        "root_cause": "term_definition_gap",
                        "detail": "术语解释不清，术语定义覆盖不足",
                    })

        reflection = {
            "diagnosis": diagnosis,
            "suggested_actions": suggested_actions,
            "analyzed_at": _utc_now(),
        }

        connection.execute(
            "UPDATE answer_feedback SET reflection_json = ? WHERE feedback_id = ?",
            (json.dumps(reflection, ensure_ascii=False), feedback_id),
        )
        connection.commit()
        return reflection
    finally:
        connection.close()


def reflect_on_feedback(workspace_root: Path, feedback_id: str) -> dict[str, object]:
    """Public API: trigger or re-trigger reflection on a feedback record."""
    return _reflect_on_feedback(workspace_root, feedback_id)


def list_answer_feedback(
    workspace_root: Path,
    *,
    satisfaction: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List answer feedback records, optionally filtered by satisfaction."""
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        if satisfaction:
            rows = connection.execute(
                """
                SELECT feedback_id, query, satisfaction, categories_json,
                       answer_mode, preferred_doc_id, confidence_score, created_at
                FROM answer_feedback
                WHERE satisfaction = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (satisfaction, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT feedback_id, query, satisfaction, categories_json,
                       answer_mode, preferred_doc_id, confidence_score, created_at
                FROM answer_feedback
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "feedback_id": r["feedback_id"],
                "query": r["query"],
                "satisfaction": r["satisfaction"],
                "categories": json.loads(r["categories_json"] or "[]"),
                "answer_mode": r["answer_mode"],
                "preferred_doc_id": r["preferred_doc_id"],
                "confidence_score": r["confidence_score"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        connection.close()


def get_feedback_detail(
    workspace_root: Path,
    feedback_id: str,
) -> dict[str, object] | None:
    """Get full feedback record including reflection."""
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            "SELECT * FROM answer_feedback WHERE feedback_id = ?",
            (feedback_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "feedback_id": row["feedback_id"],
            "query": row["query"],
            "direct_answer": row["direct_answer"],
            "answer_mode": row["answer_mode"],
            "preferred_doc_id": row["preferred_doc_id"],
            "confidence_score": row["confidence_score"],
            "satisfaction": row["satisfaction"],
            "categories": json.loads(row["categories_json"] or "[]"),
            "user_comment": row["user_comment"],
            "reflection": json.loads(row["reflection_json"] or "null"),
            "created_at": row["created_at"],
        }
    finally:
        connection.close()