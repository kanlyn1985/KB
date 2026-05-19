from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ParseViewCandidate:
    doc_id: str
    page_no: int
    view_type: str
    parser_name: str
    parser_version: str | None
    text: str
    structure: dict[str, Any]
    quality: dict[str, Any]
    status: str = "candidate"
    page_payload: dict[str, object] | None = None


@dataclass(frozen=True)
class PageParseSelection:
    doc_id: str
    page_no: int
    selected_view_id: str
    selected_reason: str
    fallback_chain: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fallback_chain"] = list(self.fallback_chain)
        return payload


def sync_parse_views_for_pages(
    connection: sqlite3.Connection,
    *,
    doc_id: str,
    parser_engine: str,
    parsed_pages: list[dict[str, object]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    candidates, selections, _ = prepare_parse_view_selection(
        doc_id=doc_id,
        primary_parser_engine=parser_engine,
        primary_pages=parsed_pages,
        extra_views=[],
    )
    return sync_parse_view_candidates(
        connection,
        doc_id=doc_id,
        candidates=candidates,
        selections=selections,
        generated_at=generated_at,
    )


def prepare_parse_view_selection(
    *,
    doc_id: str,
    primary_parser_engine: str,
    primary_pages: list[dict[str, object]],
    extra_views: list[tuple[str, list[dict[str, object]]]] | None = None,
) -> tuple[list[ParseViewCandidate], dict[int, PageParseSelection], list[dict[str, object]]]:
    candidates = [
        _candidate_from_page(doc_id=doc_id, parser_engine=primary_parser_engine, page_payload=page)
        for page in primary_pages
    ]
    for parser_engine, pages in extra_views or []:
        candidates.extend(
            _candidate_from_page(doc_id=doc_id, parser_engine=parser_engine, page_payload=page)
            for page in pages
        )
    selections = select_best_views(candidates)
    selected_pages = materialize_selected_pages(
        candidates=candidates,
        selections=selections,
        fallback_pages=primary_pages,
    )
    return candidates, selections, selected_pages


def materialize_selected_pages(
    *,
    candidates: list[ParseViewCandidate],
    selections: dict[int, PageParseSelection],
    fallback_pages: list[dict[str, object]],
) -> list[dict[str, object]]:
    candidates_by_view_id = {_view_id(candidate): candidate for candidate in candidates}
    fallback_by_page = {int(page["page_no"]): page for page in fallback_pages}
    selected_pages: list[dict[str, object]] = []
    for page_no in sorted(fallback_by_page):
        selection = selections.get(page_no)
        candidate = candidates_by_view_id.get(selection.selected_view_id) if selection else None
        source_page = candidate.page_payload if candidate and candidate.page_payload else fallback_by_page[page_no]
        page_copy = _copy_page_payload(source_page)
        if candidate:
            page_copy["selected_parse_view"] = {
                "view_id": _view_id(candidate),
                "view_type": candidate.view_type,
                "parser_name": candidate.parser_name,
                "selected_reason": selection.selected_reason if selection else "",
            }
        selected_pages.append(page_copy)
    return selected_pages


def sync_parse_view_candidates(
    connection: sqlite3.Connection,
    *,
    doc_id: str,
    candidates: list[ParseViewCandidate],
    selections: dict[int, PageParseSelection],
    generated_at: str | None = None,
) -> dict[str, Any]:
    ensure_parse_view_tables(connection)
    now = generated_at or _utc_now()

    connection.execute("DELETE FROM page_parse_selection WHERE doc_id = ?", (doc_id,))
    connection.execute("DELETE FROM parse_views WHERE doc_id = ?", (doc_id,))
    for candidate in candidates:
        view_id = _view_id(candidate)
        status = "selected" if selections.get(candidate.page_no, None) and selections[candidate.page_no].selected_view_id == view_id else candidate.status
        connection.execute(
            """
            INSERT INTO parse_views (
                view_id, doc_id, page_no, view_type, parser_name, parser_version,
                text, structure_json, quality_json, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                view_id,
                candidate.doc_id,
                candidate.page_no,
                candidate.view_type,
                candidate.parser_name,
                candidate.parser_version,
                candidate.text,
                json.dumps(candidate.structure, ensure_ascii=False),
                json.dumps(candidate.quality, ensure_ascii=False),
                status,
                now,
                now,
            ),
        )
    for selection in selections.values():
        connection.execute(
            """
            INSERT INTO page_parse_selection (
                doc_id, page_no, selected_view_id, selected_reason,
                fallback_chain_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selection.doc_id,
                selection.page_no,
                selection.selected_view_id,
                selection.selected_reason,
                json.dumps(selection.fallback_chain, ensure_ascii=False),
                now,
                now,
            ),
        )
    return summarize_parse_view_selection(connection, doc_id)


def select_best_views(candidates: list[ParseViewCandidate]) -> dict[int, PageParseSelection]:
    grouped: dict[int, list[ParseViewCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.page_no, []).append(candidate)

    selections: dict[int, PageParseSelection] = {}
    for page_no, page_candidates in grouped.items():
        ordered = sorted(page_candidates, key=_candidate_sort_key, reverse=True)
        best = ordered[0]
        score = float(best.quality.get("score") or 0.0)
        structure_score = float(best.quality.get("structure_quality_score") or 0.0)
        reason = (
            f"highest_score:{score:.3f}; "
            f"structure:{structure_score:.3f}; "
            f"view_type={best.view_type}; parser={best.parser_name}"
        )
        fallback_chain = [
            f"{candidate.view_type}:{candidate.status}:score={float(candidate.quality.get('score') or 0.0):.3f}"
            for candidate in ordered
        ]
        selections[page_no] = PageParseSelection(
            doc_id=best.doc_id,
            page_no=page_no,
            selected_view_id=_view_id(best),
            selected_reason=reason,
            fallback_chain=fallback_chain,
        )
    return selections


def score_parse_view(*, text: str, block_count: int, view_type: str) -> dict[str, Any]:
    cleaned = text.strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    total_chars = len(cleaned)
    readability = text_readability_metrics(cleaned)
    semantic_ratio = float(readability["semantic_ratio"])
    symbol_ratio = float(readability["symbol_ratio"])
    unreadable_ratio = float(readability["unreadable_ratio"])
    readability_score = float(readability["readability_score"])
    heading_count = len(re.findall(r"(?m)^(#{1,6}\s|\d+(?:\.\d+){0,5}\s+\S+)", cleaned))
    table_signal_count = cleaned.lower().count("<table") + cleaned.count("|")
    list_signal_count = len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)]|[a-zA-Z][.)])\s+", cleaned))
    table_metrics = _table_metrics(cleaned, lines)
    clause_metrics = _clause_metrics(cleaned)
    noise_metrics = _noise_metrics(lines)
    continuation_signal_count = _continuation_signal_count(cleaned)
    noise_penalty = min(
        0.85,
        symbol_ratio * 0.55
        + unreadable_ratio * 0.8
        + noise_metrics["header_footer_noise_ratio"] * 0.18
        + noise_metrics["duplicate_line_ratio"] * 0.14
        + float(readability["singleton_token_ratio"]) * 0.18,
    )
    density_score = min(1.0, total_chars / 800.0)
    raw_structure_score = max(
        0.0,
        min(
            1.0,
            (heading_count * 0.08)
            + (table_signal_count * 0.025)
            + (list_signal_count * 0.035)
            + (table_metrics["table_density"] * 0.22)
            + (min(1.0, table_metrics["row_column_signal_count"] / 12.0) * 0.14)
            + (clause_metrics["clause_continuity_score"] * 0.18)
            + (min(1.0, continuation_signal_count / 3.0) * 0.08)
            - (noise_metrics["header_footer_noise_ratio"] * 0.12)
            - (noise_metrics["duplicate_line_ratio"] * 0.14),
        ),
    )
    noise_damping = max(
        0.1,
        1.0
        - noise_metrics["header_footer_noise_ratio"] * 0.75
        - noise_metrics["duplicate_line_ratio"] * 0.55,
    )
    structure_score = raw_structure_score * max(0.25, readability_score) * noise_damping
    block_score = min(1.0, block_count / 8.0)
    view_bonus = 0.03 if view_type == "html" else 0.02 if view_type == "ocr_html" else 0.0
    score = max(
        0.0,
        min(
            1.0,
            density_score * 0.15
            + readability_score * 0.22
            + structure_score * 0.5
            + block_score * 0.07
            + view_bonus
            - noise_penalty,
        ),
    )
    risk_flags: list[str] = []
    if total_chars == 0:
        risk_flags.append("no_text")
    if total_chars < 80:
        risk_flags.append("low_text_density")
    if symbol_ratio > 0.38:
        risk_flags.append("symbol_noise")
    if unreadable_ratio > 0.08:
        risk_flags.append("unreadable_text")
    if readability_score < 0.35 and total_chars > 200:
        risk_flags.append("low_readability")
    if noise_metrics["header_footer_noise_ratio"] > 0.35:
        risk_flags.append("header_footer_noise")
    if noise_metrics["duplicate_line_ratio"] > 0.35:
        risk_flags.append("duplicate_lines")
    if table_metrics["table_density"] > 0.18 and table_metrics["row_column_signal_count"] < 2:
        risk_flags.append("weak_table_structure")
    return {
        "score": round(score, 6),
        "total_chars": total_chars,
        "block_count": block_count,
        "semantic_ratio": round(semantic_ratio, 6),
        "symbol_ratio": round(symbol_ratio, 6),
        "unreadable_ratio": round(unreadable_ratio, 6),
        "singleton_token_ratio": round(float(readability["singleton_token_ratio"]), 6),
        "language_run_count": int(readability["language_run_count"]),
        "readability_score": round(readability_score, 6),
        "heading_count": heading_count,
        "table_signal_count": table_signal_count,
        "list_signal_count": list_signal_count,
        "table_density": round(table_metrics["table_density"], 6),
        "row_column_signal_count": table_metrics["row_column_signal_count"],
        "clause_number_count": clause_metrics["clause_number_count"],
        "clause_continuity_score": round(clause_metrics["clause_continuity_score"], 6),
        "header_footer_noise_ratio": round(noise_metrics["header_footer_noise_ratio"], 6),
        "duplicate_line_ratio": round(noise_metrics["duplicate_line_ratio"], 6),
        "structure_noise_damping": round(noise_damping, 6),
        "continuation_signal_count": continuation_signal_count,
        "structure_quality_score": round(structure_score, 6),
        "risk_flags": risk_flags,
    }


def text_readability_metrics(text: str) -> dict[str, float | int]:
    counted_chars = 0
    semantic_chars = 0
    symbol_chars = 0
    unreadable_chars = 0
    for ch in text:
        if ch.isspace():
            continue
        counted_chars += 1
        if re.match(r"[A-Za-z0-9\u4e00-\u9fff]", ch):
            semantic_chars += 1
            continue
        symbol_chars += 1
        if _is_unreadable_glyph(ch):
            unreadable_chars += 1

    non_space = max(1, counted_chars)
    semantic_ratio = semantic_chars / non_space
    symbol_ratio = symbol_chars / non_space
    unreadable_ratio = unreadable_chars / non_space
    singleton_token_ratio = _singleton_token_ratio(text)
    language_run_count = _language_run_count(text)
    language_density = min(1.0, language_run_count / max(len(text) / 120.0, 1.0)) if text else 0.0
    penalty = min(0.9, symbol_ratio * 0.55 + unreadable_ratio * 3.0 + singleton_token_ratio * 0.22)
    readability_score = max(0.0, min(1.0, semantic_ratio * 0.55 + language_density * 0.45 - penalty))
    return {
        "counted_chars": counted_chars,
        "semantic_ratio": semantic_ratio,
        "symbol_ratio": symbol_ratio,
        "unreadable_ratio": unreadable_ratio,
        "singleton_token_ratio": singleton_token_ratio,
        "language_run_count": language_run_count,
        "readability_score": readability_score,
    }


def _is_unreadable_glyph(ch: str) -> bool:
    codepoint = ord(ch)
    if codepoint < 32 or 127 <= codepoint <= 159:
        return True
    if ch == "\ufffd":
        return True
    category = unicodedata.category(ch)
    if category in {"Co", "Cs", "Cn"}:
        return True
    name = unicodedata.name(ch, "")
    if "MATHEMATICAL" in name:
        return True
    if codepoint >= 128 and not ("\u4e00" <= ch <= "\u9fff") and category[0] in {"L", "M", "S"}:
        return True
    return False


def _singleton_token_ratio(text: str) -> float:
    tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text)
    if not tokens:
        return 1.0
    singleton_count = sum(1 for token in tokens if len(token) == 1)
    return singleton_count / len(tokens)


def _language_run_count(text: str) -> int:
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    latin_words = [
        token
        for token in re.findall(r"[A-Za-z]{3,}", text)
        if re.search(r"[aeiouAEIOU]", token)
    ]
    return len(cjk_runs) + len(latin_words)


def summarize_parse_view_selection(connection: sqlite3.Connection, doc_id: str) -> dict[str, Any]:
    ensure_parse_view_tables(connection)
    view_rows = connection.execute(
        """
        SELECT view_type, status, count(*) AS count
        FROM parse_views
        WHERE doc_id = ?
        GROUP BY view_type, status
        ORDER BY view_type, status
        """,
        (doc_id,),
    ).fetchall()
    selection_count = connection.execute(
        "SELECT count(*) AS count FROM page_parse_selection WHERE doc_id = ?",
        (doc_id,),
    ).fetchone()["count"]
    selected_by_type = connection.execute(
        """
        SELECT pv.view_type, count(*) AS count
        FROM page_parse_selection s
        JOIN parse_views pv ON pv.view_id = s.selected_view_id
        WHERE s.doc_id = ?
        GROUP BY pv.view_type
        ORDER BY pv.view_type
        """,
        (doc_id,),
    ).fetchall()
    return {
        "view_count": sum(int(row["count"] or 0) for row in view_rows),
        "selection_count": int(selection_count or 0),
        "views_by_type_status": {
            f"{row['view_type']}:{row['status']}": int(row["count"] or 0)
            for row in view_rows
        },
        "selected_by_type": {
            str(row["view_type"]): int(row["count"] or 0)
            for row in selected_by_type
        },
    }


def list_parse_view_pages(
    connection: sqlite3.Connection,
    doc_id: str,
    *,
    page_no: int | None = None,
    text_limit: int = 1200,
) -> dict[str, Any]:
    ensure_parse_view_tables(connection)
    params: list[object] = [doc_id]
    page_filter = ""
    if page_no is not None:
        page_filter = " AND pv.page_no = ?"
        params.append(page_no)
    rows = connection.execute(
        f"""
        SELECT
            pv.view_id,
            pv.doc_id,
            pv.page_no,
            pv.view_type,
            pv.parser_name,
            pv.parser_version,
            pv.text,
            pv.structure_json,
            pv.quality_json,
            pv.status,
            s.selected_view_id,
            s.selected_reason,
            s.fallback_chain_json
        FROM parse_views pv
        LEFT JOIN page_parse_selection s
            ON s.doc_id = pv.doc_id AND s.page_no = pv.page_no
        WHERE pv.doc_id = ?{page_filter}
        ORDER BY pv.page_no ASC, pv.status = 'selected' DESC, pv.view_type ASC
        """,
        params,
    ).fetchall()

    pages: dict[int, dict[str, Any]] = {}
    for row in rows:
        current_page_no = int(row["page_no"])
        page = pages.setdefault(
            current_page_no,
            {
                "doc_id": doc_id,
                "page_no": current_page_no,
                "selected_view_id": row["selected_view_id"],
                "selected_reason": row["selected_reason"] or "",
                "fallback_chain": _loads_json_list(row["fallback_chain_json"]),
                "candidates": [],
            },
        )
        quality = _loads_json_dict(row["quality_json"])
        structure = _loads_json_dict(row["structure_json"])
        page["candidates"].append(
            {
                "view_id": row["view_id"],
                "view_type": row["view_type"],
                "parser_name": row["parser_name"],
                "parser_version": row["parser_version"],
                "status": row["status"],
                "selected": row["view_id"] == row["selected_view_id"],
                "quality": quality,
                "structure": structure,
                "text_preview": _preview_text(row["text"] or "", text_limit),
            }
        )

    page_items = list(pages.values())
    for page in page_items:
        page["candidates"].sort(
            key=lambda item: (
                1 if item["selected"] else 0,
                float(item.get("quality", {}).get("score") or 0.0),
            ),
            reverse=True,
        )

    return {
        "doc_id": doc_id,
        "page_count": len(page_items),
        "text_limit": text_limit,
        "pages": page_items,
        "summary": summarize_parse_view_selection(connection, doc_id),
    }


def ensure_parse_view_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS parse_views (
            view_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            view_type TEXT NOT NULL,
            parser_name TEXT NOT NULL,
            parser_version TEXT,
            text TEXT,
            structure_json TEXT NOT NULL DEFAULT '{}',
            quality_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_parse_selection (
            doc_id TEXT NOT NULL,
            page_no INTEGER NOT NULL,
            selected_view_id TEXT NOT NULL,
            selected_reason TEXT NOT NULL,
            fallback_chain_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, page_no)
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_parse_views_doc_page ON parse_views(doc_id, page_no)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_parse_views_doc_status ON parse_views(doc_id, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_page_parse_selection_doc_id ON page_parse_selection(doc_id)")


def _candidate_from_page(*, doc_id: str, parser_engine: str, page_payload: dict[str, object]) -> ParseViewCandidate:
    page_no = int(page_payload["page_no"])
    blocks = list(page_payload.get("blocks", []))
    text_parts = [str(block.get("text") or "").strip() for block in blocks if isinstance(block, dict)]
    text = "\n\n".join(part for part in text_parts if part)
    view_type = _view_type_for_parser(parser_engine, blocks)
    structure = {
        "block_count": len(blocks),
        "block_types": [
            str(block.get("block_type") or "unknown")
            for block in blocks
            if isinstance(block, dict)
        ],
        "page_status": page_payload.get("page_status"),
        "risk_level": page_payload.get("risk_level"),
    }
    quality = score_parse_view(text=text, block_count=len(blocks), view_type=view_type)
    status = "candidate" if text.strip() else "unavailable"
    return ParseViewCandidate(
        doc_id=doc_id,
        page_no=page_no,
        view_type=view_type,
        parser_name=parser_engine,
        parser_version=None,
        text=text,
        structure=structure,
        quality=quality,
        status=status,
        page_payload=_copy_page_payload(page_payload),
    )


def _view_id(candidate: ParseViewCandidate) -> str:
    return f"PV-{candidate.doc_id}-{candidate.page_no:04d}-{candidate.view_type}"


def _copy_page_payload(page_payload: dict[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(page_payload, ensure_ascii=False))


def _candidate_sort_key(candidate: ParseViewCandidate) -> tuple[float, int]:
    status_weight = 1 if candidate.status == "candidate" else 0
    return (float(candidate.quality.get("score") or 0.0), status_weight)


def _view_type_for_parser(parser_engine: str, blocks: list[object]) -> str:
    engine = parser_engine.lower()
    block_types = {
        str(block.get("block_type") or "").lower()
        for block in blocks
        if isinstance(block, dict)
    }
    if "html" in engine or "table_html" in block_types:
        return "html"
    if "minimax" in engine or "paddlevl" in engine or "ocr" in engine or "ocr_markdown" in block_types:
        return "ocr_html"
    return "native_text"


def _table_metrics(text: str, lines: list[str]) -> dict[str, Any]:
    html_table_count = len(re.findall(r"<\s*table\b", text, flags=re.IGNORECASE))
    html_row_count = len(re.findall(r"<\s*tr\b", text, flags=re.IGNORECASE))
    html_cell_count = len(re.findall(r"<\s*t[dh]\b", text, flags=re.IGNORECASE))
    pipe_rows = [line for line in lines if line.count("|") >= 2]
    aligned_rows = [
        line
        for line in lines
        if len(re.findall(r"\s{2,}", line)) >= 2 and len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", line)) >= 6
    ]
    row_column_signal_count = html_row_count + len(pipe_rows) + len(aligned_rows)
    table_chars = sum(len(line) for line in pipe_rows + aligned_rows) + html_cell_count * 8 + html_table_count * 24
    total_chars = max(1, len(text.strip()))
    return {
        "table_density": min(1.0, table_chars / total_chars),
        "row_column_signal_count": row_column_signal_count,
    }


def _clause_metrics(text: str) -> dict[str, Any]:
    clause_matches = re.findall(r"(?m)^\s*(\d+(?:\.\d+){0,5})(?:\s+|[.)、])", text)
    normalized: list[tuple[int, ...]] = []
    for item in clause_matches:
        try:
            normalized.append(tuple(int(part) for part in item.split(".") if part != ""))
        except ValueError:
            continue
    if len(normalized) < 2:
        continuity = 1.0 if normalized else 0.0
    else:
        adjacent = 0
        for prev, current in zip(normalized, normalized[1:]):
            if _is_clause_continuation(prev, current):
                adjacent += 1
        continuity = adjacent / max(1, len(normalized) - 1)
    return {
        "clause_number_count": len(normalized),
        "clause_continuity_score": continuity,
    }


def _is_clause_continuation(prev: tuple[int, ...], current: tuple[int, ...]) -> bool:
    if current == prev:
        return True
    if len(current) == len(prev) and current[:-1] == prev[:-1] and current[-1] >= prev[-1]:
        return True
    if len(current) == len(prev) + 1 and current[:-1] == prev:
        return True
    if len(current) < len(prev) and current[0] >= prev[0]:
        return True
    return False


def _noise_metrics(lines: list[str]) -> dict[str, float]:
    if not lines:
        return {"header_footer_noise_ratio": 0.0, "duplicate_line_ratio": 0.0}
    normalized_lines = [re.sub(r"\s+", " ", line).strip().lower() for line in lines]
    duplicate_count = len(normalized_lines) - len(set(normalized_lines))
    header_footer_count = sum(1 for line in normalized_lines if _looks_like_header_footer_noise(line))
    return {
        "header_footer_noise_ratio": header_footer_count / len(lines),
        "duplicate_line_ratio": duplicate_count / len(lines),
    }


def _looks_like_header_footer_noise(line: str) -> bool:
    if len(line) <= 3:
        return True
    if re.fullmatch(r"(?:page|第)?\s*\d+\s*(?:页|/\s*\d+)?", line):
        return True
    if re.search(r"\bdoi\s*:\s*10\.\d{4,9}/", line):
        return True
    if re.search(r"\b(?:copyright|all rights reserved|published online|received:|accepted:)\b", line):
        return True
    if re.search(r"^\s*(?:iso|iec|gb/t|qc/t)\s*[\d-]+", line) and len(line) < 40:
        return True
    if re.search(r"^\s*\d+\s*(?:智能电网|smart grid|road vehicles)\s*$", line):
        return True
    return False


def _continuation_signal_count(text: str) -> int:
    patterns = [
        r"（续）",
        r"\(continued\)",
        r"\bcontinued\b",
        r"续表",
        r"表\s*\S+\s*续",
        r"^\s*(?:continued|cont\.)\s*$",
    ]
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE)) for pattern in patterns)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _loads_json_dict(value: object) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _loads_json_list(value: object) -> list[Any]:
    if not value:
        return []
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _preview_text(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if limit <= 0 or len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"
