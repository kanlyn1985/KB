"""Bridge to the legacy KB1 answer pipeline.

This module is a thin wrapper that lets the new ontology system
ask the legacy ``answer_api.answer_query`` for a prose answer
when the ontology can't help (e.g., free-form "summarize this
section" questions).

The bridge imports ``enterprise_agent_kb.answer_api`` at the
boundary. The new ontology system itself does NOT depend on the
legacy system; only this optional bridge module does. This keeps
the ontology system fully runnable in isolation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# The legacy package lives under src/enterprise_agent_kb. We add
# src/ to sys.path so the bridge can import it. This is the only
# place in the new ontology package that touches the legacy world.
_KB1_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_KB1_SRC) not in sys.path:
    sys.path.insert(0, str(_KB1_SRC))


def legacy_answer(workspace_root: Path, query: str, limit: int = 8) -> dict[str, Any] | None:
    """Call the legacy answer pipeline and return a normalized
    answer dict, or None if it fails.

    The legacy pipeline is allowed to fail (LLM outage, etc.)
    — in that case, the bridge returns None and the caller
    surfaces "no legacy context" to the user.
    """
    try:
        from enterprise_agent_kb.answer_api import answer_query
        return answer_query(workspace_root, query, limit=limit)
    except Exception:
        return None


def legacy_golden_lookup(
    workspace_root: Path, query_keyword: str
) -> list[dict[str, Any]]:
    """Look up golden cases whose query matches a keyword.

    Returns a list of ``{case_id, query, must_hit, source_path}``
    dicts. Used as a lightweight "what does the legacy system
    know about X" probe.
    """
    import sqlite3
    import json
    db_path = workspace_root / "db" / "knowledge.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            SELECT case_id, query, must_hit_json
            FROM golden_cases
            WHERE query LIKE ?
            LIMIT 5
            """,
            (f"%{query_keyword}%",),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            try:
                mh = json.loads(row[2]) if row[2] else []
            except json.JSONDecodeError:
                mh = []
            out.append({
                "case_id": row[0],
                "query": row[1],
                "must_hit": mh,
            })
        return out
    finally:
        conn.close()


def wiki_chunk_answer(
    workspace_root: Path, query: str, limit: int = 8,
    scope_doc_id: str | None = None,
) -> dict[str, Any] | None:
    """Query wiki_chunks_fts in knowledge.db for relevant chunks.

    Args:
        workspace_root: KB workspace path.
        query: Search query (CJK n-grams + non-CJK tokens).
        limit: Max results.
        scope_doc_id: If set, prefer chunks from this document (by doc_id
            or source_standard substring match). Results from other docs
            are still included but ranked lower.

    Returns:
        dict with direct_answer, sources, chunk_count, or None on error.
    """
    import re
    import sqlite3
    db_path = workspace_root / "db" / "knowledge.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Build FTS match expression with CJK n-grams + non-CJK tokens
        normalized = re.sub(r"\s+", " ", query).strip().lower()
        cjk_chars = [ch for ch in normalized if "一" <= ch <= "鿿"]
        cjk_ngrams = []
        for n in (2, 3):
            cjk_ngrams.extend(
                "".join(cjk_chars[i:i + n]) for i in range(len(cjk_chars) - n + 1)
            )
        seen: set[str] = set()
        terms: list[str] = []
        for t in cjk_ngrams:
            if t and t not in seen:
                seen.add(t)
                terms.append(t)

        # Also extract non-CJK tokens (abbreviations, codes like "CP", "V2G",
        # "ISO 14229-1") and include them in the FTS query.
        non_cjk_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9./\-]*[A-Za-z0-9]|[A-Za-z]{2,}", query)
        for t in non_cjk_tokens:
            t = t.lower()
            # FTS5 unicode61 ignores tokens < 3 chars in MATCH expressions
            # unless they're part of a phrase. Use LIKE fallback instead.
            if len(t) >= 3 and t not in seen:
                seen.add(t)
                terms.append(t)

        if not terms:
            terms = [normalized]
        match_expr = " OR ".join(f'"{t}"' for t in terms[:20])

        rows = conn.execute(
            f"""
            SELECT wc.chunk_id, wc.doc_id, wc.source_standard,
                   wc.section_title, wc.body_text
            FROM wiki_chunks_fts fts
            JOIN wiki_chunks wc ON wc.chunk_id = fts.chunk_id
            WHERE wiki_chunks_fts MATCH ?
            ORDER BY bm25(wiki_chunks_fts)
            LIMIT ?
            """,
            (match_expr, limit * 4),
        ).fetchall()

        # FTS5 unicode61 splits CJK into single characters which don't
        # match in MATCH queries. FTS may return many false-positive rows
        # (single CJK chars match everywhere), so we ALWAYS run a CJK
        # LIKE fallback when the query contains CJK characters.
        # Strategy: 2-grams first (more selective), then 1-grams if needed.
        cjk_fallback_rows: list[sqlite3.Row] = []
        if cjk_chars:
            like_c = []
            like_p = []
            # 2-grams: selective matching
            for gram in cjk_ngrams[:10]:
                like_c.append(
                    "(wc.section_title LIKE ? OR wc.body_text LIKE ?)"
                )
                like_p.extend([f"%{gram}%", f"%{gram}%"])
            if like_c:
                cjk_fallback_rows = conn.execute(
                    f"""
                    SELECT wc.chunk_id, wc.doc_id, wc.source_standard,
                           wc.section_title, wc.body_text
                    FROM wiki_chunks wc
                    WHERE {' OR '.join(like_c)}
                    ORDER BY wc.source_standard
                    LIMIT ?
                    """,
                    like_p + [limit * 4],
                ).fetchall()
            # If 2-grams returned too few results, also try 1-grams
            if len(cjk_fallback_rows) < limit:
                like_c1 = []
                like_p1 = []
                for ch in set(cjk_chars):
                    like_c1.append(
                        "(wc.section_title LIKE ? OR wc.body_text LIKE ?)"
                    )
                    like_p1.extend([f"%{ch}%", f"%{ch}%"])
                if like_c1:
                    extra_1gram = conn.execute(
                        f"""
                        SELECT wc.chunk_id, wc.doc_id, wc.source_standard,
                               wc.section_title, wc.body_text
                        FROM wiki_chunks wc
                        WHERE {' OR '.join(like_c1)}
                        ORDER BY wc.source_standard
                        LIMIT ?
                        """,
                        like_p1 + [limit * 2],
                    ).fetchall()
                    # Merge, deduplicate
                    seen_ids = {r["chunk_id"] for r in cjk_fallback_rows}
                    for r in extra_1gram:
                        if r["chunk_id"] not in seen_ids:
                            cjk_fallback_rows.append(r)
                            seen_ids.add(r["chunk_id"])

        # For very short tokens (e.g. "CP", "OBC") that FTS5 ignores,
        # also run a targeted LIKE query for known abbreviations.
        # We match against common CJK compound patterns that contain
        # these abbreviations in meaningful contexts.
        short_tokens = [t for t in non_cjk_tokens if len(t) <= 2 and len(t) >= 2]
        selective: list[str] = []
        general: list[str] = []
        extra_rows: list[sqlite3.Row] = []
        if short_tokens:
            # Known abbreviation → CJK context patterns
            ABBREV_PATTERNS = {
                "cp": ["CP电压", "CP信号", "CP ", " CP", "CP幅值", "+Vcc", "-Vcc",
                       "控制导引", "检测点1", "PWM信号", "状态0", "状态1"],
                "cc": ["CC信号", "连接确认", "检测点3", "CC ", " CC",
                       "CC1", "CC2"],
                "pe": ["PE ", " PE", "保护接地", "PE导体", "PE线"],
                "obc": ["OBC", "车载充电机", "on-board charger"],
                "v2g": ["V2G", "V2X", "充放电", "双向"],
                "uds": ["UDS", "统一诊断服务", "诊断服务", "0x"],
                "can": ["CAN", "CAN总线", "CAN FD"],
                "pwm": ["PWM", "占空比", "pwm信号"],
            }
            patterns = []
            for st in short_tokens:
                st_lower = st.lower()
                if st_lower in ABBREV_PATTERNS:
                    patterns.extend(ABBREV_PATTERNS[st_lower])
                else:
                    patterns.append(st)

            # Order patterns: domain-specific CJK compounds first (most
            # selective), then single-letter/space patterns last.
            selective = []
            general = []
            for pat in patterns[:15]:
                if len(pat) >= 3 and any('一' <= c <= '鿿' for c in pat):
                    selective.append(pat)
                else:
                    general.append(pat)

            like_clauses = []
            like_params = []
            for pat in selective + general:
                like_clauses.append(
                    "(wc.section_title LIKE ? OR wc.body_text LIKE ?)"
                )
                like_params.extend([f"%{pat}%", f"%{pat}%"])

            if like_clauses:
                extra_rows = conn.execute(
                    f"""
                    SELECT wc.chunk_id, wc.doc_id, wc.source_standard,
                           wc.section_title, wc.body_text
                    FROM wiki_chunks wc
                    WHERE {' OR '.join(like_clauses)}
                    ORDER BY wc.source_standard
                    LIMIT ?
                    """,
                    like_params + [limit * 4],
                ).fetchall()

        rows = conn.execute(
            f"""
            SELECT wc.chunk_id, wc.doc_id, wc.source_standard,
                   wc.section_title, wc.body_text
            FROM wiki_chunks_fts fts
            JOIN wiki_chunks wc ON wc.chunk_id = fts.chunk_id
            WHERE wiki_chunks_fts MATCH ?
            ORDER BY bm25(wiki_chunks_fts)
            LIMIT ?
            """,
            (match_expr, limit),
        ).fetchall()

        # Sort LIKE results by relevance: exact value patterns first,
        # then domain-specific CJK compounds, then generic patterns.
        # This ensures "+Vcc" matches outrank "%CP %" noise matches.
        high_priority_patterns = {"+Vcc", "-Vcc", "12.00", "11.40", "12.60"}
        med_priority_patterns = set(selective) if selective else set()
        general_patterns = general if general else []

        def _like_score(row):
            score = 0
            body = (row["body_text"] or "") + " " + (row["section_title"] or "")
            # Scope boost: chunks from the target document get large bonus
            if scope_doc_id:
                src_std = (row["source_standard"] or "")
                if (row["doc_id"] == scope_doc_id or
                    scope_doc_id.upper() in src_std.upper()):
                    score += 500
            for pat in high_priority_patterns:
                if pat in body:
                    score += 100
            for pat in med_priority_patterns:
                if pat in body:
                    score += 10
            for pat in general_patterns:
                if pat in body:
                    score += 1
            # CJK n-gram matches (more selective)
            for gram in cjk_ngrams:
                if gram in body:
                    score += 5
            return -score  # negative for descending sort

        extra_rows.sort(key=_like_score)
        cjk_fallback_rows.sort(key=_like_score)
        all_rows = list(cjk_fallback_rows) + list(extra_rows)
        all_rows.sort(key=_like_score)
        seen_ids: set[str] = set()
        deduped: list[sqlite3.Row] = []
        for r in all_rows:
            cid = r["chunk_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                deduped.append(r)
        all_rows = deduped[:limit]

        if not all_rows:
            return {
                "direct_answer": "No matching wiki chunks found.",
                "sources": [],
                "chunk_count": 0,
            }

        sources = []
        snippets = []
        for row in all_rows:
            snippet = (row["body_text"] or "")[:2000]
            sources.append({
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "source_standard": row["source_standard"] or "",
                "section_title": row["section_title"] or "",
                "snippet": snippet,
            })
            snippets.append(
                f"[{row['source_standard']}] {row['section_title']}\n{snippet}"
            )

        return {
            "direct_answer": "\n\n---\n\n".join(snippets),
            "sources": sources,
            "chunk_count": len(all_rows),
        }
    except Exception:
        return None
    finally:
        conn.close()


def llm_chat(prompt: str, system_prompt: str, max_tokens: int = 500) -> str:
    """Call the LLM via the legacy system's LLMClient.

    This is a bridge wrapper so that ``combined_query.py`` does not
    need to import ``enterprise_agent_kb.infrastructure`` directly,
    preserving the T2 isolation rule.
    """
    from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider
    import os as _os
    import time

    # httpx doesn't support socks proxies — clear all_proxy to avoid errors
    saved = {}
    for key in ("all_proxy", "ALL_PROXY"):
        if key in _os.environ:
            saved[key] = _os.environ.pop(key)

    last_error = None
    response = None
    try:
        for attempt in range(3):
            try:
                client = LLMClient(provider=Provider.CLAUDE, timeout=60.0, max_retries=1)
                response = client.chat(
                    messages=[Message(role="user", content=prompt)],
                    system_prompt=system_prompt,
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(3)
        else:
            raise last_error  # type: ignore[misc]
    finally:
        _os.environ.update(saved)

    return (response.content or "").strip()
