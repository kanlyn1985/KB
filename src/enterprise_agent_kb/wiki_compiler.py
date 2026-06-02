from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .entities import _is_low_quality_process_name


@dataclass(frozen=True)
class WikiBuildResult:
    doc_id: str
    page_count: int
    export_paths: list[Path]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "-", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    value = value[:96].strip("-")
    return value or "page"


def _slugify_with_hash(value: str) -> str:
    base = _slugify(value)
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()[:8]
    if len(base) > 84:
        base = base[:84].strip("-")
    return f"{base}-{digest}".strip("-")


def _load_payload(value: str) -> dict[str, object]:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def _find_entity_id_by_name(connection, canonical_name: str, entity_type: str) -> str | None:
    row = connection.execute(
        """
        SELECT entity_id
        FROM entities
        WHERE canonical_name = ? AND entity_type = ?
          AND entity_status = 'ready'
        LIMIT 1
        """,
        (canonical_name, entity_type),
    ).fetchone()
    if row:
        return row["entity_id"]

    normalized = _clean_heading_topic(canonical_name)
    if normalized and normalized != canonical_name:
        row = connection.execute(
            """
            SELECT entity_id
            FROM entities
            WHERE canonical_name = ? AND entity_type = ?
              AND entity_status = 'ready'
            LIMIT 1
            """,
            (normalized, entity_type),
        ).fetchone()
        if row:
            return row["entity_id"]

    rows = connection.execute(
        """
        SELECT entity_id, canonical_name
        FROM entities
        WHERE entity_type = ?
          AND entity_status = 'ready'
        """,
        (entity_type,),
    ).fetchall()
    for candidate in rows:
        candidate_name = str(candidate["canonical_name"] or "").strip()
        if normalized and candidate_name == normalized:
            return candidate["entity_id"]
        if normalized and normalized in candidate_name:
            return candidate["entity_id"]
        if candidate_name and candidate_name in canonical_name:
            return candidate["entity_id"]
    return None


def _term_is_publishable(name: str, description: str | None) -> bool:
    if not name or len(name) > 50:
        return False
    if description and len(description) > 800:
        return False
    if re.match(r"^\d", name):
        return False
    if ":" in name or "：" in name:
        return False
    if re.search(r"[，。；]$", name):
        return False
    blocked_tokens = (
        "增加了",
        "更改了",
        "删除了",
        "见",
        "目 次",
        "前言",
        "引言",
        "范围",
        "规范性引用文件",
        "术语和定义",
    )
    if any(token in name for token in blocked_tokens):
        return False
    if description:
        blocked_desc_tokens = ("增加了", "更改了", "删除了", "见2015年版", "下列文件中的内容通过")
        if any(token in description for token in blocked_desc_tokens):
            return False
    return True


def _build_document_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", ""]
    metadata_lines: list[str] = []
    sections: list[str] = []

    for row in facts:
        payload = _load_payload(row["object_value"])
        if row["fact_type"] == "document_title":
            metadata_lines.append(f"- 标题: {payload.get('value', '')}")
        elif row["fact_type"] == "document_standard":
            metadata_lines.append(f"- 标准号: {payload.get('value', '')}")
        elif row["fact_type"] == "document_versioning":
            metadata_lines.append(f"- 代替: {payload.get('value', '')}")
        elif row["fact_type"] == "document_lifecycle":
            label = "发布日期" if row["predicate"] == "publication_date" else "实施日期"
            metadata_lines.append(f"- {label}: {payload.get('value', '')}")
        elif row["fact_type"] == "section_heading":
            title = payload.get("title")
            if title:
                sections.append(str(title))

    lines.append("## 概览")
    lines.extend(metadata_lines or ["- 暂无结构化元信息"])
    lines.append("")
    if sections:
        lines.append("## 章节")
        lines.extend(f"- {title}" for title in sections[:50])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_standard_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", "", "## 关联事实"]
    for row in facts:
        subject_name = row["subject_name"] or row["source_doc_id"]
        lines.append(f"- {subject_name}: {row['predicate']}")
    lines.append("")
    return "\n".join(lines)


def _build_term_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", ""]
    definition_added = False
    for row in facts:
        if row["fact_type"] == "term_definition":
            payload = _load_payload(row["object_value"])
            definition = str(payload.get("definition", "")).strip()
            if definition:
                lines.append("## 定义")
                lines.append(definition)
                lines.append("")
                definition_added = True
                break
    if not definition_added and entity["description"]:
        lines.append("## 定义")
        lines.append(str(entity["description"]).strip())
        lines.append("")
    return "\n".join(lines)


def _build_parameter_topic_page(entity: sqlite3.Row, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {entity['canonical_name']}", "", "## 参数主题"]
    if entity["description"]:
        lines.append(str(entity["description"]).strip())
        lines.append("")
    related_tables: list[str] = []
    for row in facts:
        payload = _load_payload(row["object_value"])
        if row["fact_type"] == "parameter_value":
            for key in ("table_title", "source_caption"):
                value = str(payload.get(key) or "").strip()
                if value and value not in related_tables:
                    related_tables.append(value)
    if related_tables:
        lines.append("## 相关参数表")
        lines.extend(f"- {item}" for item in related_tables[:12])
        lines.append("")
    return "\n".join(lines)


def _build_process_wiki_page(title: str, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {title}", "", "## 过程概览"]
    rendered: list[str] = []
    for row in facts[:8]:
        payload = _load_payload(row["object_value"])
        action = str(payload.get("action") or payload.get("step_text") or "").strip()
        state = str(payload.get("state") or "").strip()
        condition = str(payload.get("condition") or "").strip()
        time_constraint = str(payload.get("time_constraint") or "").strip()
        piece = " / ".join(part for part in [state, condition, action, time_constraint] if part)
        if piece and piece not in rendered:
            rendered.append(piece)
    lines.extend(f"- {item}" for item in rendered[:8])
    if not rendered:
        lines.append("- 暂无过程摘要")
    lines.append("")
    return "\n".join(lines)


def _build_parameter_group_wiki_page(title: str, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {title}", "", "## 参数组"]
    rendered: list[str] = []
    for row in facts[:12]:
        payload = _load_payload(row["object_value"])
        parameter = str(payload.get("parameter") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        nominal = str(payload.get("nominal_value") or "").strip()
        unit = str(payload.get("unit") or "").strip()
        piece = parameter or symbol
        if symbol:
            piece += f"（{symbol}）"
        if nominal:
            piece += f" = {nominal}"
            if unit:
                piece += unit
        if piece and piece not in rendered:
            rendered.append(piece)
    lines.extend(f"- {item}" for item in rendered[:12])
    if not rendered:
        lines.append("- 暂无参数摘要")
    lines.append("")
    return "\n".join(lines)


def _build_constraint_wiki_page(title: str, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {title}", "", "## 约束与要求"]
    rendered: list[str] = []
    for row in facts[:10]:
        payload = _load_payload(row["object_value"])
        subject = str(payload.get("subject") or "").strip()
        condition = str(payload.get("condition") or "").strip()
        threshold = str(payload.get("threshold") or payload.get("value") or "").strip()
        content = str(payload.get("content") or "").strip()
        piece = " / ".join(part for part in [subject, condition, threshold or content] if part)
        if piece and piece not in rendered:
            rendered.append(piece)
    lines.extend(f"- {item}" for item in rendered[:10])
    if not rendered:
        lines.append("- 暂无约束摘要")
    lines.append("")
    return "\n".join(lines)


def _build_comparison_wiki_page(title: str, facts: list[sqlite3.Row]) -> str:
    lines = [f"# {title}", "", "## 比较与类型"]
    rendered: list[str] = []
    for row in facts[:12]:
        payload = _load_payload(row["object_value"])
        subject = str(payload.get("subject") or "").strip()
        item = str(payload.get("item") or "").strip()
        if item:
            piece = f"{subject} -> {item}" if subject else item
            if piece not in rendered:
                rendered.append(piece)
    lines.extend(f"- {item}" for item in rendered[:12])
    if not rendered:
        lines.append("- 暂无比较摘要")
    lines.append("")
    return "\n".join(lines)


def _clean_heading_topic(title: str) -> str:
    text = re.sub(r"^\d+(?:\.\d+){0,8}\s*", "", title).strip()
    text = text.replace("#", "").strip()
    return text


def _mark_doc_wiki_pages_stale(connection, doc_id: str, now: str) -> None:
    connection.execute(
        """
        UPDATE wiki_pages
        SET trust_status = 'stale',
            updated_at = ?
        WHERE source_doc_ids_json LIKE ?
        """,
        (now, f'%"{doc_id}"%'),
    )


def _render_and_persist_entity_page(
    *,
    connection: sqlite3.Connection,
    entity: sqlite3.Row,
    doc_id: str,
    paths: AppPaths,
    now: str,
) -> list[Path]:
    """Render markdown for one entity and persist both the file and the row.

    Returns the (single-element) list of file paths written, or an empty list
    if the entity was filtered out (e.g. an unpublishable term).
    """
    if entity["entity_type"] == "term" and not _term_is_publishable(
        str(entity["canonical_name"]),
        str(entity["description"] or ""),
    ):
        return []

    fact_rows = connection.execute(
        """
        SELECT
            f.fact_id,
            f.fact_type,
            f.predicate,
            f.object_value,
            f.source_doc_id,
            s.canonical_name AS subject_name
        FROM facts f
        LEFT JOIN entities s ON f.subject_entity_id = s.entity_id
        WHERE f.source_doc_id = ?
          AND (f.subject_entity_id = ? OR f.object_entity_id = ?)
        ORDER BY f.fact_id
        """,
        (doc_id, entity["entity_id"], entity["entity_id"]),
    ).fetchall()

    content, page_type, subdir = _render_entity_content(entity, fact_rows)
    target_dir = paths.wiki / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify_with_hash(
        f"{entity['entity_type']}-{entity['entity_id']}-{entity['canonical_name']}"
    )
    file_path = target_dir / f"{slug}.md"
    file_path.write_text(content, encoding="utf-8")

    _persist_wiki_page_row(
        connection=connection,
        entity=entity,
        doc_id=doc_id,
        page_type=page_type,
        slug=slug,
        file_path=file_path,
        fact_rows=fact_rows,
        now=now,
    )
    return [file_path]


def _render_entity_content(
    entity: sqlite3.Row,
    fact_rows: list[sqlite3.Row],
) -> tuple[str, str, str]:
    """Pick the right builder for the entity type and return (markdown, page_type, subdir).

    Centralizes the per-type dispatch so the persistence layer doesn't have
    to know about the type taxonomy.
    """
    entity_type = entity["entity_type"]
    name = str(entity["canonical_name"])
    if entity_type == "document":
        return _build_document_page(entity, fact_rows), "document", "documents"
    if entity_type == "standard":
        return _build_standard_page(entity, fact_rows), "standard", "standards"
    if entity_type == "parameter_topic":
        return _build_parameter_topic_page(entity, fact_rows), "parameter", "parameter_topics"
    if entity_type == "parameter_group":
        return _build_parameter_group_wiki_page(name, fact_rows), "parameter_group", "parameter_groups"
    if entity_type == "process":
        return _build_process_wiki_page(name, fact_rows), "process", "processes"
    if entity_type == "constraint_topic":
        return _build_constraint_wiki_page(name, fact_rows), "constraint", "constraints"
    if entity_type == "comparison_topic":
        return _build_comparison_wiki_page(name, fact_rows), "comparison", "comparisons"
    return _build_term_page(entity, fact_rows), "term", "terms"


def _persist_wiki_page_row(
    *,
    connection: sqlite3.Connection,
    entity: sqlite3.Row,
    doc_id: str,
    page_type: str,
    slug: str,
    file_path: Path,
    fact_rows: list[sqlite3.Row],
    now: str,
) -> None:
    """Upsert a wiki_pages row for the rendered entity."""
    wiki_page_id = f"WPAGE-{entity['entity_id'].split('-', 1)[1]}"
    source_fact_ids = [row["fact_id"] for row in fact_rows]
    connection.execute(
        """
        INSERT INTO wiki_pages (
            page_id, page_type, title, slug, entity_id, source_fact_ids_json,
            source_doc_ids_json, trust_status, file_path, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id) DO UPDATE SET
            page_type = excluded.page_type,
            title = excluded.title,
            slug = excluded.slug,
            entity_id = excluded.entity_id,
            source_fact_ids_json = excluded.source_fact_ids_json,
            source_doc_ids_json = excluded.source_doc_ids_json,
            trust_status = excluded.trust_status,
            file_path = excluded.file_path,
            updated_at = excluded.updated_at
        """,
        (
            wiki_page_id,
            page_type,
            entity["canonical_name"],
            slug,
            entity["entity_id"],
            json.dumps(source_fact_ids, ensure_ascii=False),
            json.dumps([doc_id], ensure_ascii=False),
            "reviewed" if entity["entity_type"] != "term" else "draft",
            str(file_path),
            now,
        ),
    )


def build_wiki_for_document(workspace_root: Path, doc_id: str) -> WikiBuildResult:
    """Compile wiki pages for *doc_id*: render per-entity markdown, persist
    to disk and the `wiki_pages` table, and delete any stale pages left from
    a previous build.
    """
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        _mark_doc_wiki_pages_stale(connection, doc_id, now)

        entity_rows = connection.execute(
            """
            SELECT DISTINCT e.entity_id, e.canonical_name, e.entity_type, e.description, e.source_confidence
            FROM entities e
            JOIN facts f
              ON f.subject_entity_id = e.entity_id OR f.object_entity_id = e.entity_id
            WHERE f.source_doc_id = ?
              AND e.entity_status = 'ready'
            ORDER BY e.entity_type, e.canonical_name
            """,
            (doc_id,),
        ).fetchall()

        export_paths: list[Path] = []

        for entity in entity_rows:
            export_paths.extend(
                _render_and_persist_entity_page(
                    connection=connection,
                    entity=entity,
                    doc_id=doc_id,
                    paths=paths,
                    now=now,
                )
            )

        extra_pages = _build_extra_wiki_pages(connection, doc_id, paths, now)
        export_paths.extend(extra_pages)
        _delete_stale_doc_wiki_pages(connection, doc_id)

        connection.commit()
        return WikiBuildResult(
            doc_id=doc_id,
            page_count=len(export_paths),
            export_paths=export_paths,
        )
    finally:
        connection.close()


def _delete_stale_doc_wiki_pages(connection, doc_id: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM wiki_pages
        WHERE source_doc_ids_json LIKE ?
          AND trust_status = 'stale'
        """,
        (f'%"{doc_id}"%',),
    )
    return max(int(cursor.rowcount or 0), 0)


def _build_extra_wiki_pages(connection, doc_id: str, paths: AppPaths, now: str) -> list[Path]:
    export_paths: list[Path] = []

    process_rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('process_fact', 'transition_fact')
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    process_groups: dict[str, list[sqlite3.Row]] = {}
    for row in process_rows:
        payload = _load_payload(row["object_value"])
        title = str(payload.get("table_title") or payload.get("title") or payload.get("process_name") or "").strip()
        if title and not _is_low_quality_process_name(title):
            process_groups.setdefault(title, []).append(row)

    for title, grouped_rows in process_groups.items():
        slug = _slugify(f"process-{doc_id}-{title}")
        file_path = paths.wiki / "processes" / f"{slug}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_build_process_wiki_page(title, grouped_rows), encoding="utf-8")
        export_paths.append(file_path)
        connection.execute(
            """
            INSERT INTO wiki_pages (
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
                page_type = excluded.page_type,
                title = excluded.title,
                slug = excluded.slug,
                entity_id = excluded.entity_id,
                source_fact_ids_json = excluded.source_fact_ids_json,
                source_doc_ids_json = excluded.source_doc_ids_json,
                trust_status = excluded.trust_status,
                file_path = excluded.file_path,
                updated_at = excluded.updated_at
            """,
            (
                f"WPROC-{doc_id}-{slug}",
                "process",
                title,
                slug,
                None,
                json.dumps([row["fact_id"] for row in grouped_rows], ensure_ascii=False),
                json.dumps([doc_id], ensure_ascii=False),
                "draft",
                str(file_path),
                now,
            ),
        )

    parameter_rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('parameter_value', 'table_requirement')
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    parameter_groups: dict[str, list[sqlite3.Row]] = {}
    for row in parameter_rows:
        payload = _load_payload(row["object_value"])
        title = str(payload.get("table_title") or payload.get("title") or payload.get("source_caption") or "").strip()
        if title and "参数" in title:
            parameter_groups.setdefault(title, []).append(row)

    for title, grouped_rows in parameter_groups.items():
        slug = _slugify(f"parameter-{doc_id}-{title}")
        file_path = paths.wiki / "parameter_groups" / f"{slug}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_build_parameter_group_wiki_page(title, grouped_rows), encoding="utf-8")
        export_paths.append(file_path)
        connection.execute(
            """
            INSERT INTO wiki_pages (
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
                page_type = excluded.page_type,
                title = excluded.title,
                slug = excluded.slug,
                entity_id = excluded.entity_id,
                source_fact_ids_json = excluded.source_fact_ids_json,
                source_doc_ids_json = excluded.source_doc_ids_json,
                trust_status = excluded.trust_status,
                file_path = excluded.file_path,
                updated_at = excluded.updated_at
            """,
            (
                f"WPAR-{doc_id}-{slug}",
                "parameter_group",
                title,
                slug,
                None,
                json.dumps([row["fact_id"] for row in grouped_rows], ensure_ascii=False),
                json.dumps([doc_id], ensure_ascii=False),
                "draft",
                str(file_path),
                now,
            ),
        )

    constraint_rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('requirement', 'threshold')
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    constraint_groups: dict[str, list[sqlite3.Row]] = {}
    for row in constraint_rows:
        payload = _load_payload(row["object_value"])
        title = str(payload.get("subject") or payload.get("title") or "").strip()
        if title and len(title) <= 80 and "目次" not in title and "目 次" not in title:
            constraint_groups.setdefault(title, []).append(row)

    for title, grouped_rows in list(constraint_groups.items())[:24]:
        slug = _slugify_with_hash(f"constraint-{doc_id}-{title}")
        file_path = paths.wiki / "constraints" / f"{slug}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_build_constraint_wiki_page(title, grouped_rows), encoding="utf-8")
        export_paths.append(file_path)
        entity_id = _find_entity_id_by_name(connection, title, "constraint_topic")
        connection.execute(
            """
            INSERT INTO wiki_pages (
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
                page_type = excluded.page_type,
                title = excluded.title,
                slug = excluded.slug,
                entity_id = excluded.entity_id,
                source_fact_ids_json = excluded.source_fact_ids_json,
                source_doc_ids_json = excluded.source_doc_ids_json,
                trust_status = excluded.trust_status,
                file_path = excluded.file_path,
                updated_at = excluded.updated_at
            """,
            (
                f"WCON-{doc_id}-{slug}",
                "constraint",
                title,
                slug,
                entity_id,
                json.dumps([row["fact_id"] for row in grouped_rows], ensure_ascii=False),
                json.dumps([doc_id], ensure_ascii=False),
                "draft",
                str(file_path),
                now,
            ),
        )

    heading_rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type = 'section_heading'
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    for row in heading_rows:
        payload = _load_payload(row["object_value"])
        raw_title = str(payload.get("title") or "").strip()
        topic_title = _clean_heading_topic(raw_title)
        if not topic_title or len(topic_title) > 24:
            continue
        if any(token in topic_title for token in ("前言", "引言", "范围", "术语和定义", "规范性引用文件")):
            continue
        if not any(token in topic_title for token in ("急停", "停机", "锁止", "保护", "维修", "使用条件", "标识", "说明")):
            continue
        slug = _slugify_with_hash(f"constraint-topic-{doc_id}-{topic_title}")
        file_path = paths.wiki / "constraints" / f"{slug}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"# {topic_title}\n\n## 主题\n- 来自章节标题：{raw_title}\n", encoding="utf-8")
        export_paths.append(file_path)
        entity_id = _find_entity_id_by_name(connection, topic_title, "constraint_topic")
        connection.execute(
            """
            INSERT INTO wiki_pages (
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
                page_type = excluded.page_type,
                title = excluded.title,
                slug = excluded.slug,
                entity_id = excluded.entity_id,
                source_fact_ids_json = excluded.source_fact_ids_json,
                source_doc_ids_json = excluded.source_doc_ids_json,
                trust_status = excluded.trust_status,
                file_path = excluded.file_path,
                updated_at = excluded.updated_at
            """,
            (
                f"WCONTOP-{doc_id}-{slug}",
                "constraint",
                topic_title,
                slug,
                entity_id,
                json.dumps([row["fact_id"]], ensure_ascii=False),
                json.dumps([doc_id], ensure_ascii=False),
                "draft",
                str(file_path),
                now,
            ),
        )

    comparison_rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type = 'comparison_relation'
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    comparison_groups: dict[str, list[sqlite3.Row]] = {}
    for row in comparison_rows:
        payload = _load_payload(row["object_value"])
        title = str(payload.get("subject") or "").strip()
        if title:
            comparison_groups.setdefault(title, []).append(row)

    for title, grouped_rows in comparison_groups.items():
        slug = _slugify_with_hash(f"comparison-{doc_id}-{title}")
        file_path = paths.wiki / "comparisons" / f"{slug}.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_build_comparison_wiki_page(title, grouped_rows), encoding="utf-8")
        export_paths.append(file_path)
        entity_id = _find_entity_id_by_name(connection, title, "comparison_topic")
        connection.execute(
            """
            INSERT INTO wiki_pages (
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
                page_type = excluded.page_type,
                title = excluded.title,
                slug = excluded.slug,
                source_fact_ids_json = excluded.source_fact_ids_json,
                source_doc_ids_json = excluded.source_doc_ids_json,
                trust_status = excluded.trust_status,
                file_path = excluded.file_path,
                updated_at = excluded.updated_at
            """,
            (
                f"WCMP-{doc_id}-{slug}",
                "comparison",
                title,
                slug,
                entity_id,
                json.dumps([row["fact_id"] for row in grouped_rows], ensure_ascii=False),
                json.dumps([doc_id], ensure_ascii=False),
                "draft",
                str(file_path),
                now,
            ),
        )

    return export_paths
