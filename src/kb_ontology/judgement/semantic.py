"""LLM semantic judgement — only when rules mark needs_semantic (ADR-0003)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from kb_ontology.judgement.models import AnswerStrategy, Judgement
from kb_ontology.llm.llm_client import LLMChatClient, LLMClientError
from kb_ontology.query.frame import QueryResult

_logger = logging.getLogger(__name__)

_VALID_STRATEGIES: frozenset[str] = frozenset(
    {
        "answer_with_evidence",
        "answer_with_caveat",
        "clarify_ambiguity",
        "report_knowledge_gap",
        "refuse_insufficient",
    }
)

_SYSTEM = """你是知识库判断器，不是答案生成器。根据查询结果做语义判断，只输出 JSON：
{
  "evidence_quality": "good|weak|poor",
  "knowledge_gaps": ["..."],
  "recommended_strategy": "answer_with_evidence|answer_with_caveat|clarify_ambiguity|report_knowledge_gap|refuse_insufficient",
  "notes": ["简短理由"],
  "status_override": "sufficient|partial|insufficient|null"
}
不要编造结果中不存在的实体或属性。"""


def _summarize_result(result: QueryResult, limit: int = 8) -> str:
    lines = [
        f"intent={result.intent}",
        f"empty_reason={result.empty_reason}",
        f"warnings={result.warnings[:5]}",
        f"hit_count={len(result.hits)}",
    ]
    for h in result.hits[:limit]:
        ent = h.entity or {}
        attrs = ", ".join(
            f"{a.get('name')}={a.get('value')}"
            for a in (h.attributes or [])[:6]
            if isinstance(a, dict)
        )
        lines.append(
            f"- entity class={ent.get('class')} name={ent.get('canonical_name')} attrs=[{attrs}]"
        )
    if result.related:
        lines.append(f"related_edges={len(result.related)}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def refine_with_llm(
    result: QueryResult,
    base: Judgement,
    client: LLMChatClient,
) -> Judgement:
    """Augment a rule Judgement with LLM semantic notes. Never raises."""
    user = (
        f"用户问题：{result.frame.original_query}\n"
        f"规则判断：status={base.status} score={base.score} "
        f"missing={base.missing_requirements} ambiguities={base.ambiguities}\n"
        f"策略初判：{base.recommended_strategy}\n"
        f"查询结果摘要：\n{_summarize_result(result)}\n"
        "请输出 JSON。"
    )
    try:
        resp = client.chat(user, system_prompt=_SYSTEM, temperature=0.0, max_tokens=600)
    except LLMClientError as exc:
        _logger.warning("semantic judgement LLM failed: %s", exc)
        return Judgement(
            status=base.status,
            score=base.score,
            needs_semantic=base.needs_semantic,
            has_target=base.has_target,
            hit_count=base.hit_count,
            evidence_count=base.evidence_count,
            attribute_count=base.attribute_count,
            relation_count=base.relation_count,
            missing_requirements=list(base.missing_requirements),
            conflicts=list(base.conflicts),
            ambiguities=list(base.ambiguities),
            knowledge_gaps=list(base.knowledge_gaps),
            reasons=list(base.reasons) + [f"semantic_llm_failed:{type(exc).__name__}"],
            recommended_strategy=base.recommended_strategy,
            used_llm=False,
            semantic_notes=["llm_unavailable"],
            meta={**dict(base.meta), "semantic_error": str(exc)[:200]},
        )

    data = _extract_json(resp.content) or {}
    gaps = list(base.knowledge_gaps)
    raw_gaps = data.get("knowledge_gaps") or []
    if isinstance(raw_gaps, list):
        for g in raw_gaps:
            g_s = str(g).strip()
            if g_s and g_s not in gaps:
                gaps.append(g_s)

    strategy = str(data.get("recommended_strategy") or base.recommended_strategy)
    if strategy not in _VALID_STRATEGIES:
        strategy = base.recommended_strategy

    notes: list[str] = []
    quality = data.get("evidence_quality")
    if quality:
        notes.append(f"evidence_quality:{quality}")
    raw_notes = data.get("notes") or []
    if isinstance(raw_notes, list):
        notes.extend(str(n) for n in raw_notes if str(n).strip())
    elif isinstance(raw_notes, str) and raw_notes.strip():
        notes.append(raw_notes.strip())

    status = base.status
    override = data.get("status_override")
    if override in ("sufficient", "partial", "insufficient"):
        # Do not let LLM upgrade insufficient→sufficient without hits.
        if override == "sufficient" and base.hit_count == 0:
            notes.append("ignored_status_override_no_hits")
        elif override == "sufficient" and base.status == "insufficient":
            status = "partial"  # cap upgrade
            notes.append("capped_status_override_to_partial")
        else:
            status = override  # type: ignore[assignment]

    score = base.score
    if status == "sufficient":
        score = max(score, 0.75)
    elif status == "insufficient":
        score = min(score, 0.39)

    return Judgement(
        status=status,  # type: ignore[arg-type]
        score=round(score, 4),
        needs_semantic=False,  # semantic pass done
        has_target=base.has_target,
        hit_count=base.hit_count,
        evidence_count=base.evidence_count,
        attribute_count=base.attribute_count,
        relation_count=base.relation_count,
        missing_requirements=list(base.missing_requirements),
        conflicts=list(base.conflicts),
        ambiguities=list(base.ambiguities),
        knowledge_gaps=gaps,
        reasons=list(base.reasons),
        recommended_strategy=strategy,  # type: ignore[arg-type]
        used_llm=True,
        semantic_notes=notes,
        meta={**dict(base.meta), "evidence_quality": quality},
    )
