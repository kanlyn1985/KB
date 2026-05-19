from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .answer_api import answer_query
from .query_api import build_query_context
from .retrieval import search_knowledge_base


@dataclass(frozen=True)
class AgentRunResult:
    query: str
    plan: list[dict[str, object]]
    tool_results: list[dict[str, object]]
    final_answer: dict[str, object]


def tool_search(workspace_root: Path, query: str, limit: int = 8) -> dict[str, object]:
    return {
        "tool": "search",
        "query": query,
        "results": search_knowledge_base(workspace_root, query, limit=limit),
    }


def tool_query_context(workspace_root: Path, query: str, limit: int = 8) -> dict[str, object]:
    return {
        "tool": "query-context",
        "query": query,
        "result": build_query_context(workspace_root, query, limit=limit),
    }


def tool_answer_query(workspace_root: Path, query: str, limit: int = 8) -> dict[str, object]:
    return {
        "tool": "answer-query",
        "query": query,
        "result": answer_query(workspace_root, query, limit=limit),
    }


def run_agent_query(workspace_root: Path, query: str, limit: int = 8) -> AgentRunResult:
    plan = _build_plan(query)
    tool_results: list[dict[str, object]] = []

    primary_context = tool_query_context(workspace_root, query, limit=limit)
    tool_results.append(primary_context)

    expanded_queries = _derive_followup_queries(primary_context["result"], original_query=query)
    secondary_contexts: list[dict[str, object]] = []
    for expanded_query in expanded_queries[:2]:
        result = tool_query_context(workspace_root, expanded_query, limit=limit)
        tool_results.append(result)
        secondary_contexts.append(result)

    merged_answer = _merge_answers(
        primary=tool_answer_query(workspace_root, query, limit=limit)["result"],
        secondary=[
            tool_answer_query(workspace_root, expanded_query, limit=limit)["result"]
            for expanded_query in expanded_queries[:2]
        ],
    )

    return AgentRunResult(
        query=query,
        plan=plan,
        tool_results=tool_results,
        final_answer=merged_answer,
    )


def _build_plan(query: str) -> list[dict[str, object]]:
    plan = [
        {
            "step": "primary_retrieval",
            "description": "Run structured retrieval on the user query.",
        }
    ]
    if _looks_like_standard_query(query):
        plan.append(
            {
                "step": "standard_expansion",
                "description": "Expand around matched standard entities and version relations.",
            }
        )
    if _looks_like_definition_query(query):
        plan.append(
            {
                "step": "term_expansion",
                "description": "Prefer term-definition and related evidence over generic section hits.",
            }
        )
    plan.append(
        {
            "step": "answer_synthesis",
            "description": "Merge retrieval results into an explainable answer.",
        }
    )
    return plan


def _looks_like_standard_query(query: str) -> bool:
    return bool(re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC)\b", query, re.I))


def _looks_like_definition_query(query: str) -> bool:
    markers = ("什么是", "定义", "含义", "是什么")
    return any(marker in query for marker in markers)


def _derive_followup_queries(context: dict[str, object], original_query: str) -> list[str]:
    followups: list[str] = []
    is_definition = _looks_like_definition_query(original_query)

    for entity in context.get("entities", []):
        entity_type = entity.get("entity_type")
        name = str(entity.get("canonical_name", "")).strip()
        if not name:
            continue
        if entity_type == "standard":
            followups.append(name)
        elif entity_type == "term" and is_definition:
            followups.append(name)

    for fact in context.get("facts", []):
        payload = fact.get("object_value")
        if fact.get("fact_type") == "term_definition" and isinstance(payload, dict):
            term = str(payload.get("term", "")).strip()
            if term:
                followups.append(term)
        elif is_definition and fact.get("fact_type") == "section_heading" and isinstance(payload, dict):
            title = str(payload.get("title", "")).strip()
            if title:
                followups.append(title)
                primary = re.split(r"\s{2,}|(?<![A-Za-z]) [A-Za-z].*$", title, maxsplit=1)[0].strip()
                if primary and primary != title:
                    followups.append(primary)
                chinese_only = re.sub(r"[A-Za-z0-9;:/().\-—_ ]+", "", title).strip()
                if len(chinese_only) >= 2:
                    followups.append(chinese_only)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in followups:
        if item not in seen and item != original_query:
            seen.add(item)
            deduped.append(item)
    return deduped


def _merge_answers(primary: dict[str, object], secondary: list[dict[str, object]]) -> dict[str, object]:
    direct_answer = primary.get("direct_answer")
    summary = list(primary.get("summary", []))
    facts = list(primary.get("supporting_facts", []))
    evidence = list(primary.get("supporting_evidence", []))
    warnings = list(primary.get("warnings", []))
    wiki_pages = list(primary.get("related_wiki_pages", []))
    graph_edges = list(primary.get("related_graph_edges", []))

    seen_fact_ids = {item.get("fact_id") for item in facts}
    seen_evidence_ids = {item.get("evidence_id") for item in evidence}
    seen_wiki_ids = {item.get("page_id") for item in wiki_pages}
    seen_edge_ids = {item.get("edge_id") for item in graph_edges}
    seen_summary = set(summary)
    seen_warnings = set(warnings)

    for answer in secondary:
        if direct_answer == "没有找到足够的结构化结果。" and answer.get("direct_answer"):
            direct_answer = answer.get("direct_answer")
        for line in answer.get("summary", []):
            if line not in seen_summary:
                seen_summary.add(line)
                summary.append(line)
        for item in answer.get("supporting_facts", []):
            if item.get("fact_id") not in seen_fact_ids:
                seen_fact_ids.add(item.get("fact_id"))
                facts.append(item)
        for item in answer.get("supporting_evidence", []):
            if item.get("evidence_id") not in seen_evidence_ids:
                seen_evidence_ids.add(item.get("evidence_id"))
                evidence.append(item)
        for item in answer.get("related_wiki_pages", []):
            if item.get("page_id") not in seen_wiki_ids:
                seen_wiki_ids.add(item.get("page_id"))
                wiki_pages.append(item)
        for item in answer.get("related_graph_edges", []):
            if item.get("edge_id") not in seen_edge_ids:
                seen_edge_ids.add(item.get("edge_id"))
                graph_edges.append(item)
        for line in answer.get("warnings", []):
            if line not in seen_warnings:
                seen_warnings.add(line)
                warnings.append(line)

    return {
        "query": primary.get("query"),
        "direct_answer": direct_answer,
        "summary": summary[:8],
        "supporting_facts": facts[:5],
        "supporting_evidence": evidence[:3],
        "related_graph_edges": graph_edges[:6],
        "related_wiki_pages": wiki_pages[:4],
        "warnings": warnings,
    }
