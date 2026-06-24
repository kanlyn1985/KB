"""Combined query: the one entry point.

Primary path: Decompose the query into structure-matching parts, then match
against the ingestion tables (entity / term / attribute).
Fallback: wiki_chunks then legacy_answer for natural-language context.
"""
from __future__ import annotations

from pathlib import Path

from .db import connect, default_db_path
from .attribute_store.schema import ensure_schema as ensure_attribute_schema
from .entity_manager.schema import ensure_schema as ensure_entity_schema_module
from .relation_registry.schema import ensure_schema as ensure_relation_schema_module
from .decomposer import decompose_query
from .handlers import match_decomposition
from .formatter import format_answer
from .types import Answer, RouteResult


def combined_query(
    workspace_root: Path,
    query: str,
    use_legacy: bool = True,
    use_wiki: bool = True,
    limit: int = 8,
) -> Answer:
    """Run a query against the ontology system.

    Architecture:
      - Ontology: precise (parameters, relations, entities) via
        decompose_query → match_decomposition
      - Wiki chunks: semantic fallback (natural language section content)
      - Legacy answer: optional LLM-powered prose context (slow, off by default)

    Args:
        workspace_root: Path to workspace directory.
        query: User's question.
        use_legacy: If True, also fetch legacy_answer (LLM).
        use_wiki: If True, fetch wiki_chunk_answer context (default True).
        limit: Max results.

    Returns:
        Answer with structured data and display text.
    """
    db_path = default_db_path(workspace_root)
    if not db_path.exists():
        return Answer(query=query, category="free_form",
                      display="Ontology database not found.",
                      warnings=["DB missing"])

    conn = connect(db_path)
    try:
        ensure_entity_schema_module(conn)
        ensure_relation_schema_module(conn)
        ensure_attribute_schema(conn)

        # decompose → match (decomposer has its own LLM+rule fallback)
        decomp = decompose_query(query)
        handler_result = match_decomposition(conn, decomp, query)
        route_result = RouteResult(
            category=decomp.category,
            entity=decomp.entity_anchor,
            target=decomp.target_field,
        )
    finally:
        conn.close()

    # Format
    answer = format_answer(handler_result, route_result)

    # Wiki chunk context — use decomposition result to build better query
    if use_wiki:
        try:
            from .legacy_bridge import wiki_chunk_answer
            # Build a wiki search query enriched with decomposition context
            wiki_query = query
            decomp_parts = []
            if decomp.scope:
                decomp_parts.append(decomp.scope)
            if decomp.tokens:
                decomp_parts.extend(decomp.tokens)
            if decomp_parts:
                wiki_query = " ".join(decomp_parts)
            # Pass scope so chunks from the target document rank higher
            wiki = wiki_chunk_answer(
                workspace_root, wiki_query, limit=limit,
                scope_doc_id=decomp.scope,
            )
            if isinstance(wiki, dict) and wiki.get("chunk_count", 0) == 0 and wiki_query != query:
                wiki = wiki_chunk_answer(workspace_root, query, limit=limit)
            if isinstance(wiki, dict):
                answer.legacy_context = wiki.get("direct_answer", "")
        except Exception:
            answer.warnings.append("Wiki chunk context unavailable")

    # Legacy LLM context (optional)
    if use_legacy and not answer.legacy_context:
        try:
            from .legacy_bridge import legacy_answer
            legacy = legacy_answer(workspace_root, query)
            if isinstance(legacy, dict):
                answer.legacy_context = (answer.legacy_context or "") + "\n" + legacy.get("direct_answer", "")
        except Exception:
            answer.warnings.append("Legacy system unavailable")

    # LLM summary: if we have structured data or wiki context, ask LLM to
    # compose a natural-language answer from the raw results.
    has_structured = bool(answer.structured)
    has_wiki = bool(answer.legacy_context and answer.legacy_context.strip())
    if has_structured or has_wiki:
        try:
            summary = _llm_summarize(query, answer)
            if summary:
                answer.display = summary
        except Exception:
            pass  # summarization is best-effort

    return answer


def _llm_summarize(query: str, answer: Answer) -> str | None:
    """Ask LLM to compose a natural-language answer from raw results."""
    from .legacy_bridge import llm_chat

    structured_text = ""
    if answer.structured:
        if isinstance(answer.structured, list):
            items = []
            for item in answer.structured[:20]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("attribute_name") or ""
                    val = item.get("value") or item.get("value_text") or ""
                    if name and val:
                        items.append(f"{name} = {val}")
                    elif name:
                        items.append(str(name))
                elif isinstance(item, str):
                    items.append(item)
            structured_text = "\n".join(items)
        elif isinstance(answer.structured, dict):
            structured_text = str(answer.structured)[:500]

    wiki_text = (answer.legacy_context or "")[:3000]

    if not structured_text and not wiki_text.strip():
        return None

    prompt = f"""用户查询：{query}

以下是知识库返回的结构化数据和相关文档片段。请用中文整理成一段通顺、简洁的回答。

结构化数据：
{structured_text or "(无)"}

相关文档片段：
{wiki_text[:2500] or "(无)"}

要求：
- 直接回答用户的问题，不要加"根据知识库"等前缀
- 如果数据有重复，只列出一次
- 如果信息不足以完整回答，诚实说明
- 保持简洁，3-5句话"""

    raw = llm_chat(prompt, "你是汽车工程知识库的助手，用中文回答。", max_tokens=600)
    return raw.strip() if raw else None
