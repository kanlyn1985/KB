"""Handlers: query the ontology DB based on RouteResult.

Each handler is a pure function: (conn, RouteResult) -> HandlerResult.
No query parsing, no formatting. Only DB lookup.
"""
from __future__ import annotations

import os


def _ontology_domain() -> str:
    """Return the active ontology domain.

    Default: "OBC". Set ONTOLOGY_DOMAIN env var to override.
    All relation queries in this module are scoped to this domain.
    """
    return os.environ.get("ONTOLOGY_DOMAIN", "OBC")

import re
from typing import Any

from .types import HandlerResult, RouteResult


def _find_entity(conn, name: str) -> str | None:
    """Find entity_id by canonical_name, case-insensitive, with year-stripping."""
    # Exact match
    row = conn.execute(
        "SELECT entity_id FROM entity WHERE LOWER(canonical_name) = LOWER(?)",
        (name,),
    ).fetchone()
    if row:
        return row[0]

    # Strip year suffix and language tags:
    #   "GB/T 18487.1—2023"   -> "GB/T 18487.1"
    #   "ISO 14229-6:2013"    -> "ISO 14229-6"
    #   "ISO 14229-6:2013(E)" -> "ISO 14229-6"
    yearless = re.sub(r"\s*[:：]?[—\-–]\d{4}([A-Z(].*)?$", "", name)
    yearless = re.sub(r"\s*[:：]\d{4}([A-Z(].*)?$", "", yearless)
    if yearless != name:
        row = conn.execute(
            "SELECT entity_id FROM entity WHERE LOWER(canonical_name) = LOWER(?)",
            (yearless,),
        ).fetchone()
        if row:
            return row[0]

    # Try with space normalization
    normalized = re.sub(r"\s+", "", name)
    if normalized != name:
        row = conn.execute(
            "SELECT entity_id FROM entity WHERE LOWER(canonical_name) = LOWER(?)",
            (normalized,),
        ).fetchone()
        if row:
            return row[0]

    return None


def _find_term(conn, name: str) -> dict | None:
    """Find a term by name or alias."""
    row = conn.execute(
        "SELECT term_id, canonical_name, category, definition_zh, definition_en "
        "FROM term WHERE LOWER(canonical_name) = LOWER(?)",
        (name,),
    ).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT t.term_id, t.canonical_name, t.category, t.definition_zh, t.definition_en "
        "FROM term t JOIN term_alias ta ON t.term_id = ta.term_id "
        "WHERE LOWER(ta.alias) = LOWER(?)",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def _find_param(conn, name: str) -> dict | None:
    """Find a parameter by name or alias."""
    row = conn.execute(
        "SELECT param_id, canonical_name, value_num, value_unit, "
        "value_min, value_max, definition_zh, definition_en "
        "FROM param WHERE canonical_name = ?",
        (name,),
    ).fetchone()
    if row:
        return dict(row)

    row = conn.execute(
        "SELECT p.param_id, p.canonical_name, p.value_num, p.value_unit, "
        "p.value_min, p.value_max, p.definition_zh, p.definition_en "
        "FROM param p JOIN param_alias pa ON p.param_id = pa.param_id "
        "WHERE LOWER(pa.alias) = LOWER(?)",
        (name,),
    ).fetchone()
    if row:
        return dict(row)

    # Chinese character overlap match
    if name and any('一' <= c <= '鿿' for c in name):
        chars = [c for c in name if '一' <= c <= '鿿']
        conditions = " AND ".join(["definition_zh LIKE ?" for _ in chars])
        params = [f"%{c}%" for c in chars]
        row = conn.execute(
            f"SELECT param_id, canonical_name, value_num, value_unit, "
            f"value_min, value_max, definition_zh, definition_en "
            f"FROM param WHERE definition_zh IS NOT NULL AND ({conditions}) LIMIT 1",
            params,
        ).fetchone()
        if row:
            return dict(row)

    return None


def _find_service(conn, name: str) -> dict | None:
    """Find a UDS service by hex code (0x10) or service name (DiagnosticSessionControl).

    Used for definition queries like "DiagnosticSessionControl (0x10) 是什么".
    """
    token = name.strip()

    # Hex code: "0x10"
    hex_match = re.fullmatch(r"0x[0-9A-Fa-f]{2}", token)
    if hex_match:
        hex_code = hex_match.group(0).upper()
        row = conn.execute(
            "SELECT subject_id, attribute_name, value_text FROM attribute "
            "WHERE subject_kind='entity' AND attribute_name LIKE 'service_%' "
            "AND UPPER(value_text) = ?",
            (hex_code,),
        ).fetchone()
        if row:
            svc_name = row[1].replace("service_", "")
            return {"service": svc_name, "hex": row[2], "entity_id": row[0]}

    # Service name: "DiagnosticSessionControl" or "CommunicationControl (0x28)"
    bare = re.sub(r"\s*\(0x[0-9A-Fa-f]{2}\)\s*$", "", token)
    if bare:
        row = conn.execute(
            "SELECT subject_id, attribute_name, value_text FROM attribute "
            "WHERE subject_kind='entity' AND attribute_name = ?",
            (f"service_{bare}",),
        ).fetchone()
        if row:
            svc_name = row[1].replace("service_", "")
            return {"service": svc_name, "hex": row[2], "entity_id": row[0]}

    return None


def _looks_like_phrase(text: str) -> bool:
    """True if text is a multi-word phrase or lowercase identifier (not a standard number)."""
    t = text.strip()
    if not t:
        return False
    # Standard numbers like "GB/T 18487.1", "ISO 15118-3", "QC/T 1036" are not phrases
    if re.match(r"^(GB/T|ISO|IEC|QC/T|SAE|JIS)\b", t, re.I):
        return False
    # Multi-word (has a space) or all-lowercase word → treat as phrase
    if " " in t.strip():
        return True
    if t.islower() and t.isalpha():
        return True
    return False


def _find_entity_by_title(conn, phrase: str) -> str | None:
    """Find an entity whose title attribute contains the given phrase (case-insensitive)."""
    token = phrase.strip()
    if not token:
        return None
    # Prefer titles containing the full phrase, then fall back to longest word
    candidates = [token]
    words = [w for w in re.split(r"[\s/]+", token) if len(w) >= 4]
    candidates.extend(words)
    for cand in candidates:
        row = conn.execute(
            "SELECT value_text FROM attribute "
            "WHERE subject_kind='entity' AND attribute_name='title' "
            "AND LOWER(value_text) LIKE ? LIMIT 1",
            (f"%{cand.lower()}%",),
        ).fetchone()
        if row and row[0]:
            return row[0]
    return None


# ---- Handlers ------------------------------------------------------

def handle_definition(conn, route: RouteResult, query: str) -> HandlerResult:
    """Look up a term or entity definition."""
    entity = route.entity or ""

    # Try term table
    if entity:
        term = _find_term(conn, entity)
        if term:
            return HandlerResult(
                data=term,
                data_type="dict",
                source="term",
                query=query,
            )

    # Try entity table (for standard numbers)
    if entity:
        eid = _find_entity(conn, entity)
        if eid:
            row = conn.execute(
                "SELECT value_text FROM attribute "
                "WHERE subject_kind='entity' AND subject_id=? AND attribute_name='title'",
                (eid,),
            ).fetchone()
            if row and row[0]:
                return HandlerResult(
                    data=row[0],
                    data_type="value",
                    source="attribute",
                    query=query,
                )

    # Try UDS service lookup: "0x10" or "DiagnosticSessionControl (0x10)"
    if entity:
        svc = _find_service(conn, entity)
        if svc:
            return HandlerResult(
                data=svc,
                data_type="dict",
                source="service",
                query=query,
            )

    # Try entity by English title substring (e.g. "automotive DC-AC Power Inverter")
    if entity and _looks_like_phrase(entity):
        row = _find_entity_by_title(conn, entity)
        if row:
            return HandlerResult(
                data=row[0],
                data_type="value",
                source="attribute",
                query=query,
            )

    # Try extracting term from query
    for word in re.findall(r"[A-Z][A-Za-z0-9\-/]{1,20}", query):
        term = _find_term(conn, word)
        if term:
            return HandlerResult(
                data=term,
                data_type="dict",
                source="term",
                query=query,
            )

    # Try entity from query
    for word in re.findall(r"[A-Z][A-Za-z0-9\-/]{2,20}", query):
        eid = _find_entity(conn, word)
        if eid:
            row = conn.execute(
                "SELECT value_text FROM attribute "
                "WHERE subject_kind='entity' AND subject_id=? AND attribute_name='title'",
                (eid,),
            ).fetchone()
            if row and row[0]:
                return HandlerResult(
                    data=row[0],
                    data_type="value",
                    source="attribute",
                    query=query,
                )

    return HandlerResult(data=None, data_type="value", source="", query=query)


def handle_parameter(conn, route: RouteResult, query: str) -> HandlerResult:
    """Look up a parameter value or list of attributes."""
    entity = route.entity
    target = route.target

    # If entity is given, search its attributes
    if entity:
        eid = _find_entity(conn, entity)
        if eid is None:
            return HandlerResult(data=None, data_type="value", source="", query=query)

        all_attrs = conn.execute(
            "SELECT * FROM attribute "
            "WHERE subject_kind='entity' AND subject_id=?",
            (eid,),
        ).fetchall()

        # Detect list query pattern
        is_list_query = bool(re.search(r"有哪些|哪些|所有|全部|什么.*源", query))

        if is_list_query:
            # Score and filter attributes by keyword overlap
            chinese_words = re.findall(r"[一-鿿]{2,8}", query)
            matches = []
            for row in all_attrs:
                attr_name = row["attribute_name"] or ""
                if attr_name in ("title",) or attr_name.startswith("service_"):
                    continue
                score = sum(
                    len([c for c in word if c in attr_name])
                    for word in chinese_words
                ) if chinese_words else 1
                if score >= 2 or not chinese_words:
                    display = attr_name
                    if row["value_text"]:
                        display += f" = {row['value_text']}"
                    elif row["value_num"] is not None and row["value_unit"]:
                        display += f" = {row['value_num']} {row['value_unit']}"
                    matches.append(display)
            if matches:
                return HandlerResult(data=matches, data_type="list", source="attribute", query=query)
            return HandlerResult(data=None, data_type="list", source="", query=query)

        # Single value: keyword scoring
        chinese_words = re.findall(r"[一-鿿]{2,8}", query + (target or ""))

        # English/CamelCase identifier path: match an attribute whose name (or its
        # service_ tail) contains a query identifier token.
        #   "P3Client_max"                          → attribute "P3Client_max"
        #   "verifyModeTransitionWithFixedParameter"→ service_verifyModeTransitionWithFixedParameter
        eng_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", query + (target or ""))
        if eng_tokens:
            best_eng_score = 0
            best_eng_row = None
            for row in all_attrs:
                attr_name = (row["attribute_name"] or "").strip()
                if not attr_name or attr_name == "title":
                    continue
                hay = attr_name[len("service_"):] if attr_name.startswith("service_") else attr_name
                score = sum(len(tok) for tok in eng_tokens if tok.lower() in hay.lower())
                if score > best_eng_score:
                    best_eng_score = score
                    best_eng_row = row
            if best_eng_row and best_eng_score >= 5:
                d = dict(best_eng_row)
                return HandlerResult(
                    data={"value": d.get("value_num"), "unit": d.get("value_unit"),
                          "text": d.get("value_text")},
                    data_type="value",
                    source="attribute",
                    query=query,
                )

        best_score = 0
        best_row = None
        for row in all_attrs:
            attr_name = row["attribute_name"] or ""
            if attr_name in ("title",) or attr_name.startswith("service_"):
                continue
            score = sum(
                len([c for c in word if c in attr_name])
                for word in chinese_words
            )
            if score > best_score:
                best_score = score
                best_row = row

        if best_row and best_score >= 2:
            d = dict(best_row)
            return HandlerResult(
                data={"value": d.get("value_num"), "unit": d.get("value_unit"),
                      "text": d.get("value_text")},
                data_type="value",
                source="attribute",
                query=query,
            )

        return HandlerResult(data=None, data_type="value", source="", query=query)

    # No entity: try param table
    if target:
        param = _find_param(conn, target)
        if param:
            return HandlerResult(data=param, data_type="dict", source="param", query=query)

    # Try Chinese keywords in param table
    for word in re.findall(r"[一-鿿]{2,8}", query):
        param = _find_param(conn, word)
        if param:
            return HandlerResult(data=param, data_type="dict", source="param", query=query)

    # Try uppercase symbols in param table
    for word in sorted(re.findall(r"[+\-]?[A-Z][A-Za-z0-9_+\-]{0,20}", query), key=len, reverse=True):
        if len(word) < 2:
            continue
        param = _find_param(conn, word)
        if param:
            return HandlerResult(data=param, data_type="dict", source="param", query=query)

    return HandlerResult(data=None, data_type="value", source="", query=query)


def handle_reference(conn, route: RouteResult, query: str) -> HandlerResult:
    """Look up reference relations for an entity."""
    entity = route.entity
    if not entity:
        return HandlerResult(data=None, data_type="list", source="", query=query)

    eid = _find_entity(conn, entity)
    if eid is None:
        return HandlerResult(data=None, data_type="list", source="", query=query)

    direction = "incoming" if re.search(
        r"哪些.{0,3}引用|谁.{0,3}引用|who.*ref|被.*引用|what standards reference", query, re.I,
    ) else "outgoing"

    from .relation_registry import relations_of
    rels = relations_of(conn, src_id=eid, direction=direction, relation_name="references", domain=_ontology_domain())

    names = []
    for r in rels:
        target_id = r.dst_id if direction == "outgoing" else r.src_id
        cur = conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id=?",
            (target_id,),
        ).fetchone()
        if cur:
            names.append(cur[0])

    return HandlerResult(
        data=names,
        data_type="list",
        source="relation",
        query=query,
    )


def handle_service(conn, route: RouteResult, query: str) -> HandlerResult:
    """Look up UDS services."""
    # Hex code lookup
    hex_match = re.search(r"0x[0-9A-Fa-f]{2}", query)
    if hex_match:
        hex_code = hex_match.group(0).upper()
        rows = conn.execute(
            "SELECT a.subject_id, a.attribute_name, a.value_text "
            "FROM attribute a "
            "WHERE a.subject_kind='entity' AND a.attribute_name LIKE 'service_%' "
            "AND UPPER(a.value_text) = ? ORDER BY a.subject_id",
            (hex_code,),
        ).fetchall()
        if rows:
            services = []
            for row in rows:
                ename = conn.execute(
                    "SELECT canonical_name FROM entity WHERE entity_id=?", (row[0],)
                ).fetchone()
                sname = row[1].replace("service_", "")
                services.append(f"{ename[0] if ename else row[0]}: {sname} = {row[2]}")
            return HandlerResult(data=services, data_type="list", source="attribute", query=query)

    # Entity-specific services
    entity = route.entity
    if entity:
        eid = _find_entity(conn, entity)
        if eid:
            rows = conn.execute(
                "SELECT attribute_name, value_text FROM attribute "
                "WHERE subject_kind='entity' AND subject_id=? "
                "AND attribute_name LIKE 'service_%' ORDER BY attribute_name",
                (eid,),
            ).fetchall()
            if rows:
                services = [f"{r[0].replace('service_', '')}: {r[1]}" for r in rows]
                return HandlerResult(data=services, data_type="list", source="attribute", query=query)

    # All services
    rows = conn.execute(
        "SELECT a.subject_id, a.attribute_name, a.value_text "
        "FROM attribute a WHERE a.subject_kind='entity' "
        "AND a.attribute_name LIKE 'service_%' ORDER BY a.subject_id, a.attribute_name"
    ).fetchall()
    if rows:
        services = []
        for row in rows:
            ename = conn.execute(
                "SELECT canonical_name FROM entity WHERE entity_id=?", (row[0],)
            ).fetchone()
            sname = row[1].replace("service_", "")
            services.append(f"{ename[0] if ename else row[0]}: {sname} = {row[2]}")
        return HandlerResult(data=services, data_type="list", source="attribute", query=query)

    return HandlerResult(data=None, data_type="list", source="", query=query)


def handle_traversal(conn, route: RouteResult, query: str) -> HandlerResult:
    """Look up multi-hop traversal from an entity."""
    entity = route.entity
    if not entity:
        return HandlerResult(data=None, data_type="path_list", source="", query=query)

    eid = _find_entity(conn, entity)
    if eid is None:
        return HandlerResult(data=None, data_type="path_list", source="", query=query)

    hops = 3 if re.search(r"3\s*跳|3-hop|3 hop", query, re.I) else 2

    from .relation_registry import traverse_relations
    paths = traverse_relations(conn, start_id=eid, max_hops=hops, relation_name="references", domain=_ontology_domain())

    out = []
    for p in paths:
        names = [conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id=?", (r.dst_id,)
        ).fetchone() for r in p]
        names = [n[0] for n in names if n]
        if names:
            out.append(" → ".join(names))

    return HandlerResult(data=out, data_type="path_list", source="relation", query=query)


# ---- Decomposition-based matcher ----------------------------------
#
# This is the structure-aware path: a QueryDecomposition is matched directly
# against the ingestion tables (entity / term / term_alias / attribute),
# rather than classified into a category and handed to a category handler.
# It exists alongside the legacy category handlers so the two can be A/B'd.


def _resolve_anchor(conn, anchor: str | None) -> str | None:
    if not anchor:
        return None
    return _find_entity(conn, anchor)


def _match_terms_by_tokens(conn, tokens: tuple[str, ...]) -> list[dict]:
    """Find terms whose canonical_name or alias contains any concept token."""
    if not tokens:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for tok in tokens:
        rows = conn.execute(
            "SELECT DISTINCT t.term_id, t.canonical_name, t.definition_zh, t.definition_en "
            "FROM term t "
            "WHERE LOWER(t.canonical_name) LIKE LOWER(?) "
            "   OR LOWER(t.definition_zh) LIKE LOWER(?) "
            "   OR LOWER(t.definition_en) LIKE LOWER(?)",
            (f"%{tok}%", f"%{tok}%", f"%{tok}%"),
        ).fetchall()
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            out.append(dict(r))
    if not out:
        for tok in tokens:
            rows = conn.execute(
                "SELECT DISTINCT t.term_id, t.canonical_name, t.definition_zh, t.definition_en "
                "FROM term t JOIN term_alias ta ON t.term_id = ta.term_id "
                "WHERE LOWER(ta.alias) LIKE LOWER(?)",
                (f"%{tok}%",),
            ).fetchall()
            for r in rows:
                if r[0] in seen:
                    continue
                seen.add(r[0])
                out.append(dict(r))
    return out


def _match_attributes_by_tokens(
    conn, tokens: tuple[str, ...], entity_id: str | None,
    *, include_services: bool = False,
) -> list[dict]:
    """Find attributes whose name or value contains a concept token.

    Scoped to entity_id when given, else global. By default skips title and
    service_* attributes (those are the service-artifact path); set
    include_services=True when target_artifact=service. Falls back to shorter
    CJK substrings when a full token doesn't match (唤醒源 → 唤醒).
    """
    if not tokens:
        return []

    def _run(tok_list: tuple[str, ...]) -> list[dict]:
        base = (
            "SELECT attribute_name, value_text, value_num, value_unit, subject_id "
            "FROM attribute WHERE subject_kind='entity' "
            "AND attribute_name NOT IN ('title') "
        )
        if not include_services:
            base += "AND attribute_name NOT LIKE 'service_%' "
        params: list = []
        clauses: list[str] = []
        for tok in tok_list:
            clauses.append("(lower(attribute_name) LIKE lower(?) OR lower(COALESCE(value_text,'')) LIKE lower(?))")
            params.extend([f"%{tok}%", f"%{tok}%"])
        sql = base + " AND (" + " OR ".join(clauses) + ")"
        if entity_id:
            sql += " AND subject_id=?"
            params.append(entity_id)
        sql += " ORDER BY attribute_name LIMIT 50"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    rows = _run(tokens)
    if rows:
        return rows

    # Substring fallback for CJK tokens: try progressively shorter prefixes.
    # CJK has no word boundaries, so "电子锁策略" should still match "电子锁解锁超时".
    for tok in tokens:
        if not (any("一" <= c <= "鿿" for c in tok) and len(tok) >= 3):
            continue
        tried: set[str] = set()
        for end in range(len(tok) - 1, 1, -1):
            short = tok[:end]
            if short in tried:
                continue
            tried.add(short)
            rows = _run((short,))
            if rows:
                return rows
    return []


def match_decomposition(conn, decomp, query: str) -> HandlerResult:
    """Match a QueryDecomposition against the ingestion tables.

    Dispatch is on (target_artifact, operation) — each branch is a direct
    query against the artifact's table/column family, with no special-casing:
      lookup     → return the single best-matching artifact row
      enumerate  → return all matching artifact rows (scoped to decomp.scope)
    """
    tokens = decomp.tokens
    eid = _resolve_anchor(conn, decomp.scope)
    artifact = decomp.target_artifact
    operation = decomp.operation

    # ---- service -------------------------------------------------------
    if artifact == "service":
        if operation == "lookup":
            for tok in tokens:
                svc = _find_service(conn, tok)
                if svc:
                    return HandlerResult(data=svc, data_type="dict", source="service", query=query)
            # lookup by name substring (e.g. "DiagnosticSession")
            svcs = _match_attributes_by_tokens(conn, tokens, eid, include_services=True)
            return _attr_rows_result(svcs, query)
        # enumerate: list every service_*, scoped to entity if given
        sql = ("SELECT attribute_name, value_text, value_num, value_unit, subject_id "
               "FROM attribute WHERE subject_kind='entity' "
               "AND attribute_name LIKE 'service_%'")
        params: list = []
        if eid:
            sql += " AND subject_id=?"
            params.append(eid)
        sql += " ORDER BY subject_id, attribute_name LIMIT 200"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return _attr_rows_result(rows, query, source="attribute")

    # ---- term -----------------------------------------------------------
    if artifact == "term":
        terms = _match_terms_by_tokens(conn, tokens)
        if operation == "lookup" or len(terms) <= 1:
            return HandlerResult(
                data=terms[0] if terms else None, data_type="dict",
                source="term" if terms else "", query=query,
            )
        # enumerate: list all matching terms
        payload = [{"type": "term", "name": t.get("canonical_name"),
                    "definition_zh": t.get("definition_zh"),
                    "definition_en": t.get("definition_en")} for t in terms]
        return HandlerResult(data=payload, data_type="list", source="term", query=query)

    # ---- relation -------------------------------------------------------
    if artifact == "relation":
        if not decomp.scope:
            return HandlerResult(data=None, data_type="list", source="", query=query)
        route = RouteResult(category="reference", entity=decomp.scope, target=None)
        if operation == "lookup":
            return handle_reference(conn, route, query)
        # enumerate: multi-hop traversal
        hops = 3 if re.search(r"3\s*跳|3-hop|3 hop", query, re.I) else 2
        return _traversal_result(conn, decomp.scope, hops, query)

    # ---- entity ---------------------------------------------------------
    if artifact == "entity":
        if not decomp.scope and tokens:
            # lookup entity by token in title
            row = _find_entity_by_title(conn, tokens[0]) if _looks_like_phrase(tokens[0]) else None
            return HandlerResult(data=row, data_type="value",
                                 source="attribute" if row else "", query=query)
        if eid:
            title = conn.execute(
                "SELECT value_text FROM attribute "
                "WHERE subject_kind='entity' AND subject_id=? AND attribute_name='title'",
                (eid,),
            ).fetchone()
            return HandlerResult(
                data=title[0] if title and title[0] else None, data_type="value",
                source="attribute" if title and title[0] else "", query=query,
            )
        return HandlerResult(data=None, data_type="value", source="", query=query)

    # ---- param ----------------------------------------------------------
    if artifact == "param":
        if not tokens:
            return HandlerResult(data=None, data_type="value", source="", query=query)
        param = _find_param(conn, tokens[0])
        return HandlerResult(data=param, data_type="dict",
                             source="param" if param else "", query=query)

    # ---- attribute (default) -------------------------------------------
    attrs = _match_attributes_by_tokens(conn, tokens, eid)
    # If scoped search found nothing but tokens exist, widen to global
    if not attrs and tokens and eid:
        attrs = _match_attributes_by_tokens(conn, tokens, None)
    # If still nothing, try matching a term (concept-without-entity queries)
    if not attrs and not eid and tokens:
        terms = _match_terms_by_tokens(conn, tokens)
        if terms:
            if operation == "lookup" or len(terms) <= 1:
                return HandlerResult(data=terms[0], data_type="dict", source="term", query=query)
            payload = [{"type": "term", "name": t.get("canonical_name"),
                        "definition_zh": t.get("definition_zh"),
                        "definition_en": t.get("definition_en")} for t in terms]
            return HandlerResult(data=payload, data_type="list", source="term", query=query)
    return _attr_rows_result(attrs, query)


def _attr_rows_result(rows: list[dict], query: str, *, source: str = "attribute") -> HandlerResult:
    """Render attribute rows uniformly as a list payload (or empty)."""
    if not rows:
        return HandlerResult(data=None, data_type="value", source="", query=query)
    payload: list[dict] = []
    for a in rows[:30]:
        name = a.get("attribute_name") or a.get("name")
        if name and name.startswith("service_"):
            name = name[len("service_"):]
        val = a.get("value_text")
        if val is None and a.get("value_num") is not None:
            val = f"{a['value_num']} {a.get('value_unit') or ''}".strip()
        payload.append({"type": "service" if (a.get("attribute_name") or "").startswith("service_") else "attribute",
                        "name": name, "value": val})
    return HandlerResult(data=payload, data_type="list", source=source, query=query)


def _traversal_result(conn, scope_entity: str, hops: int, query: str) -> HandlerResult:
    eid = _find_entity(conn, scope_entity)
    if eid is None:
        return HandlerResult(data=None, data_type="path_list", source="", query=query)
    from .relation_registry import traverse_relations
    paths = traverse_relations(conn, start_id=eid, max_hops=hops,
                               relation_name="references", domain=_ontology_domain())
    out: list[str] = []
    for p in paths:
        names = [conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id=?", (r.dst_id,)
        ).fetchone() for r in p]
        names = [n[0] for n in names if n]
        if names:
            out.append(" → ".join(names))
    return HandlerResult(data=out, data_type="path_list", source="relation", query=query)
