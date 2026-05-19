from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


PROCESS_CODE_PATTERN = r"(?:ACQ|SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM|MLE|SPL)\.\d+"


@dataclass(frozen=True)
class EntitiesBuildResult:
    doc_id: str
    entity_count: int
    entity_types: dict[str, int]
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _extract_payload(row) -> dict[str, object]:
    try:
        return json.loads(row["object_value"] or "{}")
    except json.JSONDecodeError:
        return {}


def _build_process_code_index(fact_rows) -> dict[str, str]:
    process_by_code: dict[str, str] = {}
    for row in fact_rows:
        if row["fact_type"] != "table_requirement":
            continue
        payload = _extract_payload(row)
        title = str(payload.get("table_title") or payload.get("title") or "").strip()
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        blob = json.dumps(payload, ensure_ascii=False)
        codes = [
            match.group(1).upper()
            for match in re.finditer(rf"\b({PROCESS_CODE_PATTERN})\b", blob, re.I)
        ]
        if not codes:
            continue
        process_name = _process_name_from_table_rows(rows)
        if not process_name and "过程参考模型" not in title and "Process reference model" not in title:
            process_name = _title_without_page_noise(title)
        for code in codes:
            if not process_name:
                continue
            canonical = _canonical_process_name(code, process_name, title)
            existing = process_by_code.get(code)
            if existing is None or _process_name_quality(canonical) > _process_name_quality(existing):
                process_by_code[code] = canonical
    return process_by_code


def _process_name_from_table_rows(rows: list[object]) -> str:
    for index, row in enumerate(rows):
        cells = [str(cell).strip() for cell in row] if isinstance(row, list) else [str(row).strip()]
        if not cells:
            continue
        if len(cells) >= 2 and re.search(r"^(过程名称|Process name)$", cells[0], re.I) and cells[1]:
            return cells[1]
        if len(cells) == 1 and re.search(r"^(过程名称|Process name)$", cells[0], re.I):
            for next_row in rows[index + 1 : index + 3]:
                next_cells = [str(cell).strip() for cell in next_row] if isinstance(next_row, list) else [str(next_row).strip()]
                if next_cells and next_cells[0]:
                    return next_cells[0]
    return ""


def _canonical_process_name(code: str, process_name: str, title: str = "") -> str:
    cleaned_name = _title_without_page_noise(process_name)
    cleaned_title = _title_without_page_noise(title)
    if cleaned_title and code.upper() in cleaned_title.upper() and cleaned_name and cleaned_name in cleaned_title:
        return cleaned_title
    if cleaned_name:
        return f"{code.upper()} {cleaned_name}"
    return cleaned_title or code.upper()


def _title_without_page_noise(value: str) -> str:
    text = str(value or "").strip()
    compact = re.sub(r"\s+", "", text).upper()
    if _is_low_quality_process_name(text):
        return ""
    return text


def _is_low_quality_process_name(value: str) -> bool:
    text = str(value or "").strip()
    compact = re.sub(r"\s+", "", text).upper()
    if not compact:
        return True
    if compact in {
        "PUBLIC",
        "BASEPRACTICES",
        "BASICPRACTICES",
        "OUTPUTINFORMATIONITEMS",
        "TABLEREQUIREMENT",
        "TABLE_REQUIREMENT",
        "VDAQMC",
        "AUTOMOTIVESPICE",
    }:
        return True
    if text in {
        "基本实践",
        "输出信息项",
        "过程名称",
        "过程目的",
        "过程成果",
        "通用实践",
    }:
        return True
    if re.fullmatch(r"\d+PUBLIC", compact or ""):
        return True
    if text.startswith("--- Page"):
        return True
    if len(text) > 160:
        return True
    return False


def _process_name_quality(value: str) -> int:
    score = 0
    if re.search(rf"\b{PROCESS_CODE_PATTERN}\b", value, re.I):
        score += 4
    if re.search(r"[\u4e00-\u9fff]", value):
        score += 3
    if re.search(r"(过程|Process|验证|设计|集成|需求|管理)", value, re.I):
        score += 2
    if "过程参考模型" in value or "Process reference model" in value:
        score -= 4
    if _title_without_page_noise(value) != value:
        score -= 5
    return score


def _process_code_from_payload(payload: dict[str, object]) -> str:
    blob = json.dumps(payload, ensure_ascii=False)
    match = re.search(rf"\b({PROCESS_CODE_PATTERN})\.BP\d+\b", blob, re.I)
    if match:
        return match.group(1).upper()
    match = re.search(rf"\b({PROCESS_CODE_PATTERN})\b", blob, re.I)
    return match.group(1).upper() if match else ""


PROCESS_ALIAS_STOPWORDS = {
    "Process name",
    "Process purpose",
    "Process outcomes",
    "Base Practices",
    "Output Information Items",
    "过程名称",
    "过程目的",
    "过程成果",
    "基本实践",
    "输出信息项",
    "通用实践",
}


def _process_aliases_from_payload(payload: dict[str, object], canonical_name: str, process_code: str = "") -> list[str]:
    aliases: list[str] = []
    for key in ("table_title", "title", "process_name"):
        value = _clean_process_title_alias(str(payload.get(key) or ""), canonical_name, process_code)
        if value:
            aliases.append(value)
    step_text = str(payload.get("step_text") or payload.get("action") or "").strip()
    if step_text:
        aliases.extend(_process_activity_aliases(step_text, process_code=process_code, allow_bare_bp=True))
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    for row in rows:
        cells = [str(cell).strip() for cell in row] if isinstance(row, list) else [str(row).strip()]
        for cell in cells:
            # Table rows are noisier than process facts. Only trust rows that carry
            # the full process code, otherwise a continued/misaligned table can
            # leak BP aliases from the previous process into the current entity.
            aliases.extend(_process_activity_aliases(cell, process_code=process_code, allow_bare_bp=False))
    return _unique_strings([alias for alias in aliases if _is_process_alias_candidate(alias, canonical_name)])


def _clean_process_title_alias(value: str, canonical_name: str, process_code: str = "") -> str:
    text = _title_without_page_noise(str(value or "").strip())
    if not text or text == canonical_name:
        return ""
    if text in PROCESS_ALIAS_STOPWORDS:
        return ""
    if re.fullmatch(r"[A-Z]{2,4}", text):
        return ""
    if process_code and process_code.upper() in text.upper():
        return text
    if re.search(rf"\b{PROCESS_CODE_PATTERN}\b", text, re.I):
        return text
    if re.search(r"(Requirements|Architecture|Design|Verification|Validation|Management|需求|架构|设计|验证|确认|管理|集成)", text, re.I):
        return text
    return ""


def _process_names_for_fact_rows(fact_rows, process_code_index: dict[str, str]) -> set[str]:
    names: set[str] = set()
    for row in fact_rows:
        if row["fact_type"] not in {"process_fact", "transition_fact", "table_requirement"}:
            continue
        payload = _extract_payload(row)
        process_code = _process_code_from_payload(payload)
        if process_code and process_code in process_code_index:
            names.add(process_code_index[process_code])
    return names


def _reset_process_aliases(connection, process_names: set[str]) -> None:
    for process_name in process_names:
        connection.execute(
            """
            UPDATE entities
            SET alias_json = ?
            WHERE entity_type = 'process'
              AND canonical_name = ?
            """,
            (json.dumps([], ensure_ascii=False), process_name),
        )


def _sanitize_process_aliases(connection) -> int:
    rows = connection.execute(
        """
        SELECT entity_id, canonical_name, alias_json
        FROM entities
        WHERE entity_type = 'process'
          AND alias_json IS NOT NULL
          AND alias_json != ''
          AND alias_json != '[]'
        """
    ).fetchall()
    updated = 0
    for row in rows:
        try:
            aliases = json.loads(row["alias_json"] or "[]")
        except json.JSONDecodeError:
            aliases = []
        if not isinstance(aliases, list):
            aliases = []
        cleaned = _unique_strings(
            [
                str(alias).strip()
                for alias in aliases
                if _is_process_alias_candidate(str(alias), str(row["canonical_name"] or ""))
            ]
        )
        if cleaned != aliases:
            connection.execute(
                "UPDATE entities SET alias_json = ? WHERE entity_id = ?",
                (json.dumps(cleaned, ensure_ascii=False), row["entity_id"]),
            )
            updated += 1
    return updated


def _mark_unlinked_reference_process_entities_stale(connection, now: str) -> int:
    cursor = connection.execute(
        """
        UPDATE entities
        SET entity_status = 'stale',
            updated_at = ?
        WHERE entity_type = 'process'
          AND entity_status != 'stale'
          AND (
              canonical_name LIKE '%过程参考模型%'
              OR canonical_name LIKE '%Process reference model%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM facts
              WHERE facts.object_entity_id = entities.entity_id
                 OR facts.subject_entity_id = entities.entity_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges
              WHERE graph_edges.src_entity_id = entities.entity_id
                 OR graph_edges.dst_entity_id = entities.entity_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM wiki_pages
              WHERE wiki_pages.entity_id = entities.entity_id
          )
        """,
        (now,),
    )
    return int(cursor.rowcount or 0)


def _quarantine_low_quality_process_entities(connection, now: str) -> int:
    rows = connection.execute(
        """
        SELECT e.entity_id, e.canonical_name
        FROM entities e
        WHERE e.entity_type = 'process'
          AND e.entity_status != 'stale'
        """
    ).fetchall()
    stale_ids = [
        str(row["entity_id"])
        for row in rows
        if _is_low_quality_process_name(str(row["canonical_name"] or ""))
    ]
    if not stale_ids:
        return 0
    placeholders = ",".join("?" for _ in stale_ids)
    connection.execute(
        f"""
        UPDATE facts
        SET object_entity_id = CASE WHEN object_entity_id IN ({placeholders}) THEN NULL ELSE object_entity_id END,
            subject_entity_id = CASE WHEN subject_entity_id IN ({placeholders}) THEN NULL ELSE subject_entity_id END
        WHERE object_entity_id IN ({placeholders})
           OR subject_entity_id IN ({placeholders})
        """,
        [*stale_ids, *stale_ids, *stale_ids, *stale_ids],
    )
    connection.execute(
        f"""
        DELETE FROM graph_edges
        WHERE src_entity_id IN ({placeholders})
           OR dst_entity_id IN ({placeholders})
        """,
        [*stale_ids, *stale_ids],
    )
    connection.execute(
        f"""
        UPDATE entities
        SET entity_status = 'stale',
            updated_at = ?
        WHERE entity_id IN ({placeholders})
        """,
        [now, *stale_ids],
    )
    return len(stale_ids)


def _reject_low_quality_process_entity(connection, canonical_name: str, now: str) -> None:
    if not _is_low_quality_process_name(canonical_name):
        return
    row = connection.execute(
        """
        SELECT entity_id
        FROM entities
        WHERE entity_type = 'process'
          AND canonical_name = ?
        LIMIT 1
        """,
        (canonical_name,),
    ).fetchone()
    if not row:
        return
    entity_id = str(row["entity_id"])
    connection.execute(
        """
        UPDATE facts
        SET object_entity_id = CASE WHEN object_entity_id = ? THEN NULL ELSE object_entity_id END,
            subject_entity_id = CASE WHEN subject_entity_id = ? THEN NULL ELSE subject_entity_id END
        WHERE object_entity_id = ?
           OR subject_entity_id = ?
        """,
        (entity_id, entity_id, entity_id, entity_id),
    )
    connection.execute(
        """
        DELETE FROM graph_edges
        WHERE src_entity_id = ?
           OR dst_entity_id = ?
        """,
        (entity_id, entity_id),
    )
    connection.execute(
        """
        UPDATE entities
        SET entity_status = 'stale',
            updated_at = ?
        WHERE entity_id = ?
        """,
        (now, entity_id),
    )


def _process_activity_aliases(text: str, process_code: str = "", allow_bare_bp: bool = True) -> list[str]:
    aliases: list[str] = []
    cleaned = re.sub(r"<[^>]+>", " ", str(text or ""))
    cleaned = re.sub(r"[*_`#]+", "", cleaned)
    if process_code and re.search(r"\b[A-Z]{2,4}\.\d+\.BP\d+\b", cleaned, re.I):
        allowed_prefix = re.escape(process_code.upper())
        if not re.search(rf"\b{allowed_prefix}\.BP\d+\b", cleaned.upper()):
            return []
    bp_prefix = (
        rf"\b{PROCESS_CODE_PATTERN}\.BP\d+\s*[:：]\s*"
        if not allow_bare_bp
        else rf"(?:\b{PROCESS_CODE_PATTERN}\.BP\d+\s*[:：]\s*|\bBP\d+\s*[:：]\s*)?"
    )
    for match in re.finditer(
        bp_prefix + r"([^。.;；\n]+)",
        cleaned,
        re.I,
    ):
        phrase = match.group(1).strip()
        phrase = re.sub(r"^\s*(?:BP\d+\s*[:：]\s*)", "", phrase, flags=re.I).strip()
        if not _is_process_activity_phrase(phrase):
            continue
        aliases.append(phrase)
        aliases.extend(_activity_phrase_variants(phrase))
        break
    return _unique_strings(aliases)


def _is_process_activity_phrase(phrase: str) -> bool:
    text = str(phrase or "").strip(" ：:，,。.")
    if not text or len(text) < 3 or len(text) > 90:
        return False
    if text in PROCESS_ALIAS_STOPWORDS:
        return False
    if re.fullmatch(r"[A-Z]{2,4}", text):
        return False
    if re.match(r"^(?:Note|注)\s*\d*", text, re.I):
        return False
    if re.match(r"^\d+\)", text):
        return False
    if re.match(r"^\d{2}-\d{2}\b", text):
        return False
    if "|" in text or "PUBLIC" in text:
        return False
    return bool(
        re.search(
            r"(分析|定义|选择|执行|集成|总结|沟通|确保|建立|验证|确认|管理|记录|跟踪|指定|"
            r"Analyze|Define|Specify|Select|Perform|Integrate|Ensure|Communicate|Summarize|Verify|Validate|Manage|Track|Identify|Establish)",
            text,
            re.I,
        )
    )


def _is_process_alias_candidate(alias: str, canonical_name: str) -> bool:
    text = str(alias or "").strip(" ：:，,。.")
    if not text or text == canonical_name:
        return False
    if text in PROCESS_ALIAS_STOPWORDS:
        return False
    if len(text) > 90:
        return False
    if re.fullmatch(r"[A-Z]{2,4}", text):
        return False
    if "|" in text or "PUBLIC" in text:
        return False
    if re.match(r"^\d+\)", text):
        return False
    if re.match(r"^\d{2}-\d{2}\b", text):
        return False
    if text.lower().startswith(("note ", "注 ")):
        return False
    return True


def _activity_phrase_variants(phrase: str) -> list[str]:
    variants: list[str] = []
    text = str(phrase or "").strip()
    verb_object = re.match(r"^(分析|定义|选择|执行|集成|总结|沟通|确保|建立)(.+)$", text)
    if verb_object:
        obj = verb_object.group(2).strip(" ：:，,。.")
        verb = verb_object.group(1)
        if obj:
            variants.append(f"{obj}{verb}")
            if obj.endswith("架构") and verb == "分析":
                variants.append(f"{obj}分析")
    lower = text.lower()
    if "analyze software architecture" in lower:
        variants.extend(["分析软件架构", "软件架构分析"])
    if "software architecture" in lower and "analy" in lower:
        variants.append("软件架构分析")
    return variants


def _find_existing_entity_id(connection, canonical_name: str, entity_type: str) -> str | None:
    row = connection.execute(
        """
        SELECT entity_id
        FROM entities
        WHERE canonical_name = ? AND entity_type = ?
        LIMIT 1
        """,
        (canonical_name, entity_type),
    ).fetchone()
    return row["entity_id"] if row else None


def _find_parameter_group_entity_id(connection, payload: dict[str, object]) -> str | None:
    candidates = [
        str(payload.get("table_title") or "").strip(),
        str(payload.get("source_caption") or "").strip(),
        str(payload.get("title") or "").strip(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        entity_id = _find_existing_entity_id(connection, candidate, "parameter_group")
        if entity_id:
            return entity_id
        row = connection.execute(
            """
            SELECT entity_id
            FROM entities
            WHERE entity_type = 'parameter_group'
              AND (canonical_name LIKE ? OR ? LIKE '%' || canonical_name || '%')
            LIMIT 1
            """,
            (f"%{candidate}%", candidate),
        ).fetchone()
        if row:
            return row["entity_id"]
    return None


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _derive_parameter_topics(payload: dict[str, object]) -> list[str]:
    specific_topics: list[str] = []
    generic_topics: list[str] = []
    loop_scope = str(payload.get("loop_scope") or "").strip().lower()
    parameter = str(payload.get("parameter") or "").strip()
    symbol = str(payload.get("symbol") or "").strip().upper()
    unit = str(payload.get("unit") or "").strip().upper()
    if loop_scope:
        generic_topics.append(loop_scope.upper())

    for item in payload.get("detection_points") or []:
        text = str(item or "").strip()
        if text:
            generic_topics.append(text)

    focus_tags = [str(item or "").strip() for item in payload.get("focus_tags") or []]
    row_focus_tags = [str(item or "").strip() for item in payload.get("row_focus_tags") or []]
    table_focus_tags = [str(item or "").strip() for item in payload.get("table_focus_tags") or []]
    all_tags = _unique_strings([*focus_tags, *row_focus_tags, *table_focus_tags])

    for candidate in all_tags:
        upper = candidate.upper()
        if upper in {"CC1", "CC2"} and "CC" not in generic_topics:
            generic_topics.append("CC")
        elif upper == "CP" and "CP" not in generic_topics:
            generic_topics.append("CP")
        elif "检测点" in candidate and candidate not in generic_topics:
            generic_topics.append(candidate)
        elif candidate in {"控制导引", "控制导引电路"} and candidate not in generic_topics:
            generic_topics.append(candidate)

    table_title = str(payload.get("table_title") or "").strip()
    source_caption = str(payload.get("source_caption") or "").strip()
    title_blob = f"{table_title} {source_caption}"
    if "控制导引" in title_blob and "控制导引" not in generic_topics:
        generic_topics.append("控制导引")
    if "锁止装置" in title_blob and "锁止装置" not in generic_topics:
        generic_topics.append("锁止装置")

    if loop_scope == "cc" and (unit == "Ω" or symbol.startswith("R") or any(token in parameter for token in ("电阻", "阻值"))):
        specific_topics.append("CC阻值")
    if ((loop_scope == "cp") or "CP" in all_tags or "控制导引" in title_blob) and ("占空比" in parameter or symbol.startswith("D") or "DUTY" in parameter.upper()):
        specific_topics.append("CP占空比")
    if unit == "V":
        for point in payload.get("detection_points") or []:
            text = str(point or "").strip()
            if text:
                suffix = text if text.endswith("电压") else f"{text}电压"
                specific_topics.append(suffix)

    return _unique_strings([*specific_topics, *generic_topics])


def _parameter_topic_description(topic: str) -> str:
    mapping = {
        "CC": "Parameter topic CC",
        "CP": "Parameter topic CP",
        "CC阻值": "连接确认回路中的等效电阻参数主题。",
        "CP占空比": "控制导引 PWM 信号中的占空比参数主题。",
    }
    if topic in mapping:
        return mapping[topic]
    if "检测点" in topic and topic.endswith("电压"):
        return f"{topic} 参数主题。"
    return f"Parameter topic {topic}"


def _merge_aliases(existing_alias_json: str | None, new_aliases: list[str] | None) -> str:
    aliases: list[str] = []
    if existing_alias_json:
        try:
            loaded = json.loads(existing_alias_json)
            if isinstance(loaded, list):
                aliases.extend(str(item).strip() for item in loaded if str(item).strip())
        except json.JSONDecodeError:
            pass
    for alias in new_aliases or []:
        text = str(alias or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return json.dumps(aliases[:80], ensure_ascii=False)


def _ensure_entity(
    connection,
    canonical_name: str,
    entity_type: str,
    description: str | None,
    confidence: float,
    now: str,
    aliases: list[str] | None = None,
) -> str:
    if entity_type == "process" and _is_low_quality_process_name(canonical_name):
        _reject_low_quality_process_entity(connection, canonical_name, now)
        return ""

    existing_row = connection.execute(
        """
        SELECT entity_id, alias_json
        FROM entities
        WHERE canonical_name = ? AND entity_type = ?
        LIMIT 1
        """,
        (canonical_name, entity_type),
    ).fetchone()
    if existing_row:
        existing_id = existing_row["entity_id"]
        connection.execute(
            """
            UPDATE entities
            SET description = COALESCE(description, ?),
                alias_json = ?,
                source_confidence = MAX(COALESCE(source_confidence, 0), ?),
                entity_status = 'ready',
                updated_at = ?
            WHERE entity_id = ?
            """,
            (description, _merge_aliases(existing_row["alias_json"], aliases), confidence, now, existing_id),
        )
        return existing_id

    entity_id = next_prefixed_id(connection, "entity", "ENT")
    connection.execute(
        """
        INSERT INTO entities (
            entity_id, canonical_name, entity_type, alias_json, description,
            source_confidence, entity_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            canonical_name,
            entity_type,
            _merge_aliases(None, aliases),
            description,
            confidence,
            "ready",
            now,
            now,
        ),
    )
    return entity_id


def build_entities_for_document(workspace_root: Path, doc_id: str) -> EntitiesBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        doc_row = connection.execute(
            """
            SELECT source_filename
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if doc_row is None:
            raise ValueError(f"document not found: {doc_id}")

        fact_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        process_code_index = _build_process_code_index(fact_rows)
        _sanitize_process_aliases(connection)
        _mark_unlinked_reference_process_entities_stale(connection, now)
        _quarantine_low_quality_process_entities(connection, now)
        _reset_process_aliases(connection, _process_names_for_fact_rows(fact_rows, process_code_index))

        doc_entity_name = f"{doc_id}:{doc_row['source_filename']}"
        doc_entity_id = _ensure_entity(
            connection,
            canonical_name=doc_entity_name,
            entity_type="document",
            description=f"Source document {doc_row['source_filename']}",
            confidence=1.0,
            now=now,
        )

        entity_ids_for_export: dict[str, tuple[str, str, str | None, float]] = {
            doc_entity_id: (doc_entity_name, "document", f"Source document {doc_row['source_filename']}", 1.0)
        }

        for row in fact_rows:
            payload = _extract_payload(row)
            fact_id = row["fact_id"]
            confidence = float(row["confidence"] or 0.8)

            connection.execute(
                "UPDATE facts SET subject_entity_id = ? WHERE fact_id = ?",
                (doc_entity_id, fact_id),
            )

            if row["fact_type"] == "document_standard":
                value = str(payload.get("value", "")).strip()
                if value:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=value,
                        entity_type="standard",
                        description="Standard code referenced by document",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (value, "standard", "Standard code referenced by document", confidence)

            elif row["fact_type"] == "document_versioning":
                value = str(payload.get("value", "")).strip()
                if value:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=value,
                        entity_type="standard",
                        description="Superseded or referenced standard",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (value, "standard", "Superseded or referenced standard", confidence)

            elif row["fact_type"] in {"term_definition", "concept_definition"}:
                term = str(payload.get("term", "")).strip()
                definition = str(payload.get("definition", "")).strip()
                if term:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=term,
                        entity_type="term",
                        description=definition or None,
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        """
                        UPDATE facts
                        SET subject_entity_id = ?, object_entity_id = NULL
                        WHERE fact_id = ?
                        """,
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (term, "term", definition or None, confidence)

            elif row["fact_type"] in {"process_fact", "transition_fact"}:
                process_code = _process_code_from_payload(payload)
                process_name = process_code_index.get(process_code, "") if process_code else ""
                if not process_name:
                    process_name = _title_without_page_noise(
                        str(
                            payload.get("table_title")
                            or payload.get("title")
                            or payload.get("process_name")
                            or ""
                        ).strip()
                    )
                if process_name:
                    process_aliases = _process_aliases_from_payload(payload, process_name, process_code)
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=process_name,
                        entity_type="process",
                        description=f"Process knowledge object {process_code}".strip(),
                        confidence=confidence,
                        now=now,
                        aliases=process_aliases,
                    )
                    if entity_id:
                        connection.execute(
                            "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                            (entity_id, fact_id),
                        )
                        entity_ids_for_export[entity_id] = (process_name, "process", f"Process knowledge object {process_code}".strip(), confidence)
                    else:
                        connection.execute(
                            "UPDATE facts SET object_entity_id = NULL WHERE fact_id = ?",
                            (fact_id,),
                        )
                else:
                    connection.execute(
                        "UPDATE facts SET object_entity_id = NULL WHERE fact_id = ?",
                        (fact_id,),
                    )

            elif row["fact_type"] == "table_requirement":
                table_title = str(payload.get("table_title") or payload.get("title") or "").strip()
                process_code = _process_code_from_payload(payload)
                if process_code and process_code in process_code_index:
                    process_name = process_code_index[process_code]
                    process_aliases = _process_aliases_from_payload(payload, process_name, process_code)
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=process_name,
                        entity_type="process",
                        description=f"Process knowledge object {process_code}",
                        confidence=confidence,
                        now=now,
                        aliases=process_aliases,
                    )
                    if entity_id:
                        connection.execute(
                            "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                            (entity_id, fact_id),
                        )
                        entity_ids_for_export[entity_id] = (process_name, "process", f"Process knowledge object {process_code}", confidence)
                    else:
                        connection.execute(
                            "UPDATE facts SET object_entity_id = NULL WHERE fact_id = ?",
                            (fact_id,),
                        )
                if table_title and "参数" in table_title:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=table_title,
                        entity_type="parameter_group",
                        description="Parameter group derived from table",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (table_title, "parameter_group", "Parameter group derived from table", confidence)

            elif row["fact_type"] == "parameter_value":
                topics = _derive_parameter_topics(payload)
                group_entity_id = _find_parameter_group_entity_id(connection, payload)
                if topics:
                    primary_topic = topics[0]
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=primary_topic,
                        entity_type="parameter_topic",
                        description=_parameter_topic_description(primary_topic),
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET subject_entity_id = COALESCE(?, subject_entity_id), object_entity_id = ? WHERE fact_id = ?",
                        (group_entity_id, entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (primary_topic, "parameter_topic", _parameter_topic_description(primary_topic), confidence)
                elif group_entity_id:
                    connection.execute(
                        "UPDATE facts SET subject_entity_id = ? WHERE fact_id = ?",
                        (group_entity_id, fact_id),
                    )

            elif row["fact_type"] in {"requirement", "threshold"}:
                topic = str(payload.get("topic") or payload.get("subject") or "").strip()
                scope_type = str(payload.get("scope_type") or "").strip()
                if topic and scope_type not in {"index", "preface", "overview"}:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=topic,
                        entity_type="constraint_topic",
                        description=f"Constraint topic {topic}",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (topic, "constraint_topic", f"Constraint topic {topic}", confidence)

            elif row["fact_type"] == "comparison_relation":
                subject = str(payload.get("subject") or "").strip()
                if subject:
                    entity_id = _ensure_entity(
                        connection,
                        canonical_name=subject,
                        entity_type="comparison_topic",
                        description=f"Comparison topic {subject}",
                        confidence=confidence,
                        now=now,
                    )
                    connection.execute(
                        "UPDATE facts SET object_entity_id = ? WHERE fact_id = ?",
                        (entity_id, fact_id),
                    )
                    entity_ids_for_export[entity_id] = (subject, "comparison_topic", f"Comparison topic {subject}", confidence)

        export_items = [
            {
                "entity_id": entity_id,
                "canonical_name": values[0],
                "entity_type": values[1],
                "description": values[2],
                "source_confidence": values[3],
            }
            for entity_id, values in sorted(entity_ids_for_export.items())
        ]

        _quarantine_low_quality_process_entities(connection, now)

        entity_types: dict[str, int] = {}
        for item in export_items:
            entity_types[item["entity_type"]] = entity_types.get(item["entity_type"], 0) + 1

        export_path = paths.facts / f"{doc_id}.entities.json"
        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "entity_count": len(export_items),
                    "entity_types": entity_types,
                    "items": export_items,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        connection.commit()
        return EntitiesBuildResult(
            doc_id=doc_id,
            entity_count=len(export_items),
            entity_types=entity_types,
            export_path=export_path,
        )
    finally:
        connection.close()
