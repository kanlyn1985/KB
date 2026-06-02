"""Fact payload construction and main orchestrator.

Extracted from `facts._impl` to isolate the fact payload construction
(definition, procedure transition, two-column parameter, table parameter,
timing, parameter scope, knowledge-unit dispatcher), the evidence-chain
and metadata-fact persistence, the public `build_facts_for_document`
orchestrator, and the `FactsBuildResult` value class.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import AppPaths
from ..db import connect
from ..ids import next_prefixed_id
from ..knowledge_units import extract_knowledge_units, save_knowledge_units, save_knowledge_units_jsonl
from ._extract_cover import (
    _clean_text,
    _extract_cover_metadata,
    _extract_doc_metadata,
    _extract_section_headings,
    _sanitize_payload,
    _utc_now,
)
from ._extract_terms import (
    _extract_document_level_concepts,
    _extract_numeric_term_definitions,
    _extract_term_definitions,
)
from ._extract_process import _extract_type_relations

@dataclass(frozen=True)
class FactsBuildResult:
    doc_id: str
    fact_count: int
    fact_types: dict[str, int]
    export_path: Path
def _confidence(base: float, evidence_confidence: float) -> float:
    return round(max(0.1, min(1.0, (base + evidence_confidence) / 2)), 3)


def _knowledge_unit_fact_payloads(
    workspace_root: Path,
    doc_id: str,
) -> list[dict[str, object]]:
    cleaned_doc_ir_path = AppPaths.from_root(workspace_root).normalized / f"{doc_id}.cleaned_doc_ir.json"
    if not cleaned_doc_ir_path.exists():
        return []

    bundle = extract_knowledge_units(cleaned_doc_ir_path)
    save_knowledge_units(bundle, AppPaths.from_root(workspace_root).normalized / f"{doc_id}.knowledge_units.json")
    save_knowledge_units_jsonl(bundle, AppPaths.from_root(workspace_root).normalized / f"{doc_id}.kb.jsonl")

    payloads: list[dict[str, object]] = []
    for unit in bundle.units:
        if unit.type == "definition":
            payloads.extend(_definition_fact_payloads(unit))
        elif unit.type == "requirement":
            title = _unit_canonical_title(unit)
            payloads.append(
                {
                    "fact_type": "requirement",
                    "predicate": "states_requirement",
                    "payload": {
                        "title": title,
                        "content": unit.content,
                        "subject": unit.subject,
                        "topic": unit.topic,
                        "scope_type": unit.scope_type,
                        "condition": unit.condition,
                        "threshold": unit.threshold,
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.82,
                }
            )
            if unit.threshold:
                payloads.append(
                    {
                        "fact_type": "threshold",
                        "predicate": "has_threshold",
                        "payload": {
                            "title": unit.title,
                            "subject": unit.subject,
                            "topic": unit.topic,
                            "scope_type": unit.scope_type,
                            "value": unit.threshold,
                        },
                        "page_no": unit.page,
                        "base_confidence": 0.8,
                    }
                )
        elif unit.type == "table_requirement":
            # Skip index/catalog tables (e.g. standard number listings)
            if str(getattr(unit, "scope_type", "") or "") == "index":
                continue
            headers = list(getattr(unit, "headers", None) or [])
            header_blob = " ".join(str(h) for h in headers)
            if "序号" in header_blob and "标准编号" in header_blob:
                continue
            title = _unit_canonical_title(unit)
            table_title = _unit_canonical_table_title(unit)
            payloads.append(
                {
                    "fact_type": "table_requirement",
                    "predicate": "has_table_requirement",
                    "payload": {
                        "title": title,
                        "table_title": table_title,
                        "table_no": unit.table_no,
                        "headers": unit.headers,
                        "rows": unit.rows[:20] if unit.rows else [],
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.78,
                }
            )
            payloads.extend(_table_parameter_fact_payloads(unit))
            payloads.extend(_timing_fact_payloads(unit))
        elif unit.type == "procedure":
            process_title = _unit_canonical_title(unit) or _process_title_for_procedure_unit(unit)
            payloads.append(
                {
                    "fact_type": "process_fact",
                    "predicate": "describes_process",
                    "payload": {
                        "title": process_title,
                        "process_name": process_title,
                        "step_text": unit.content,
                        "section": unit.section,
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.79,
                }
            )
            payloads.extend(_procedure_transition_payloads(unit, process_title))
    return payloads


def _definition_fact_payloads(unit) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    title = _clean_definition_term(_unit_canonical_title(unit) or str(unit.title or ""))
    content = _clean_text(str(unit.content or ""))
    if _is_publishable_definition_entry(title, content):
        seen.add((title, content[:120]))
        payloads.append(
            {
                "fact_type": _definition_fact_type_for_term(title),
                "predicate": _definition_predicate_for_term(title),
                "payload": {
                    "term": title,
                    "definition": content,
                },
                "page_no": unit.page,
                "base_confidence": 0.8 if str(unit.section or "").startswith("3") else 0.76,
            }
        )

    for fact_type, predicate, payload in _extract_numeric_term_definitions(content, seen):
        payloads.append(
            {
                "fact_type": fact_type,
                "predicate": predicate,
                "payload": payload,
                "page_no": unit.page,
                "base_confidence": 0.78,
            }
        )

    return payloads


def _clean_definition_term(value: str) -> str:
    text = _clean_text(value)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^\d+(?:\.\d+){0,8}\s*", "", text)
    text = re.sub(r"^(?:图|表)\s*[A-Z]?\d+(?:\.\d+)*\s*", "", text)
    text = re.sub(r"^(?:附录|附 录)\s*[A-Z]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ：:;；-")
    return text[:120]


def _is_publishable_definition_entry(term: str, definition: str) -> bool:
    if not term or not definition:
        return False
    if len(term) > 50 or len(definition) < 12:
        return False
    if term[0] in {".", ",", "，", "。", ";", "；", "-", "—", "*"}:
        return False
    if any(token in term for token in ("前言", "引言", "规范性引用文件", "术语和定义")):
        return False
    if term in {"范围", "适用范围", "过程评估模型范围"} or re.fullmatch(r"条款\s*\d+(?:\.\d+)*[,“”\"'\s]*.*范围.*", term):
        return False
    if any(token in term for token in ("原理图", "示意图", "状态转换", "时序", "参数", "图 ", "表 ")):
        return False
    if any(token in term for token in ("。", "，", ";", "；")):
        return False
    if re.match(r"^(?:图|表|附录|附 录)", term):
        return False
    if re.search(r"[，。；]$", term):
        return False
    if term.count(" ") > 8:
        return False
    if term.count("——") > 0:
        return False
    if any(token in definition for token in ("增加了", "更改了", "删除了", "见2015年版")):
        return False
    if not _definition_has_publishable_signal(definition):
        return len(definition) >= 40
    return True


def _definition_has_publishable_signal(definition: str) -> bool:
    text = _clean_text(definition)
    if any(token in text for token in ("是", "指", "用于", "能够", "将", "利用", "通过", "为", "作为", "参与", "实现", "装置", "电路", "系统", "功能", "过程", "时间段")):
        return True
    lowered = text.lower()
    english_patterns = [
        r"\bfunction\s+that\b",
        r"\bdata\s+that\b",
        r"\bsoftware\s+which\b",
        r"\bpart\s+of\b",
        r"\barea\s+of\b",
        r"\bset\s+of\b",
        r"\bsystem\s+that\b",
        r"\bmechanism\s+for\b",
        r"\bsimple\s+type\s+with\b",
        r"\bone\s+or\s+more\b",
        r"\bnumerical\s+common\s+identifier\b",
        r"\belectronic\s+control\s+unit\b",
        r"\bopen\s+systems\s+interconnection\b",
        r"\binformation\s+exchange\s+initiated\b",
    ]
    return any(re.search(pattern, lowered) for pattern in english_patterns)


def _definition_fact_type_for_term(term: str) -> str:
    upper = term.upper().strip()
    if re.fullmatch(r"[A-Z][A-Z0-9/\-]{1,}", upper) or upper.startswith("V2"):
        return "concept_definition"
    return "term_definition"


def _definition_predicate_for_term(term: str) -> str:
    if _definition_fact_type_for_term(term) == "concept_definition":
        return "defines_concept"
    return "defines_term"


def _unit_canonical_title(unit) -> str:
    return str(getattr(unit, "canonical_title", None) or getattr(unit, "title", "") or "").strip()


def _unit_canonical_table_title(unit) -> str | None:
    value = getattr(unit, "canonical_table_title", None)
    if value:
        return str(value).strip()
    value = getattr(unit, "table_title", None)
    return str(value).strip() if value else None


def _procedure_transition_payloads(unit, process_title: str) -> list[dict[str, object]]:
    """Extract transition_facts from procedure content with enumerated steps."""
    content = str(getattr(unit, "content", "") or "")
    if not content:
        return []

    payloads: list[dict[str, object]] = []

    # Path 1: markdown table rows as steps (e.g. | 测试项目 | 性能要求 |)
    table_rows = _extract_table_step_rows(content)
    if table_rows:
        for i, row_text in enumerate(table_rows):
            if not row_text or len(row_text) < 4:
                continue
            payloads.append(
                {
                    "fact_type": "transition_fact",
                    "predicate": "has_transition",
                    "payload": {
                        "title": process_title,
                        "table_title": None,
                        "section": getattr(unit, "section", None),
                        "sequence": str(i + 1),
                        "state": "",
                        "condition": "",
                        "action": row_text[:300],
                        "time_constraint": "",
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.74,
                }
            )
        return payloads

    # Path 2: enumerated step markers: a) b) c), 1. 2. 3., or numbered sub-sections
    # Also include the unit title as context so steps mentioned in title are captured
    full_text = str(getattr(unit, "title", "") or "") + "\n" + content
    step_pattern = re.compile(r"(?:^|\n)\s*(?:([a-z])\s*[).）]|[①-⑳]|(\d+(?:\.\d+)?)\s*[.．)）])\s*", re.I)
    splits = list(step_pattern.finditer(full_text))
    if len(splits) < 2:
        return []
    for i, match in enumerate(splits):
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(full_text)
        step_text = full_text[start:end].strip()
        if not step_text or len(step_text) < 8:
            continue
        step_label = match.group(1) or match.group(2) or str(i + 1)
        payloads.append(
            {
                "fact_type": "transition_fact",
                "predicate": "has_transition",
                "payload": {
                    "title": process_title,
                    "table_title": None,
                    "section": getattr(unit, "section", None),
                    "sequence": step_label,
                    "state": "",
                    "condition": "",
                    "action": step_text[:300],
                    "time_constraint": "",
                },
                "page_no": unit.page,
                "base_confidence": 0.76,
            }
        )
    return payloads


def _extract_table_step_rows(content: str) -> list[str]:
    """Extract step-like rows from markdown tables in procedure content."""
    rows: list[str] = []
    lines = content.splitlines()
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if stripped.replace("|", "").replace("-", "").replace(":", "").replace(" ", "") == "":
                # separator row
                in_table = True
                continue
            if not in_table:
                in_table = True
                continue  # skip header row
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            row_text = " / ".join(c for c in cells if c)
            if row_text and len(row_text) >= 4:
                rows.append(row_text)
        else:
            if in_table:
                break  # end of table
    return rows


def _process_title_for_procedure_unit(unit) -> str:
    title = _clean_process_payload_title(_unit_canonical_title(unit))
    content = str(getattr(unit, "content", "") or "")
    process_code = _process_code_from_text(content)
    if process_code and _is_low_quality_process_payload_title(title):
        return f"{process_code} 基本实践"
    if title:
        return title
    if process_code:
        return f"{process_code} 基本实践"
    section = str(getattr(unit, "section", "") or "").strip()
    return section if section else "过程事实"


def _process_title_for_table_unit(unit) -> tuple[str, str]:
    table_title = _clean_process_payload_title(_unit_canonical_table_title(unit) or "")
    title = _clean_process_payload_title(_unit_canonical_title(unit))
    if _is_low_quality_process_payload_title(title) and table_title:
        title = table_title
    return title, table_title


def _clean_process_payload_title(value: str) -> str:
    text = _clean_text(str(value or ""))
    text = re.sub(r"^\*+|\*+$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return "" if _is_low_quality_process_payload_title(text) else text


def _is_low_quality_process_payload_title(value: str) -> bool:
    text = str(value or "").strip()
    compact = re.sub(r"\s+", "", text).upper()
    if not compact:
        return True
    if compact in {
        "PUBLIC",
        "BASEPRACTICES",
        "基本实践",
        "VDAQMC",
        "AUTOMOTIVESPICE",
        "AUTOMOTIVESPICE®",
    }:
        return True
    if re.fullmatch(r"\d{1,4}PUBLIC", compact):
        return True
    if re.fullmatch(r"\d{1,4}", compact):
        return True
    if "VDAQMC" in compact and len(compact) <= 80:
        return True
    return False


def _process_code_from_text(value: str) -> str:
    match = PROCESS_BP_PATTERN.search(str(value or ""))
    return match.group(1).upper() if match else ""


def _two_column_parameter_payloads(unit, rows: list) -> list[dict[str, object]]:
    """Extract parameter_value facts from 2-column key-value parameter tables.

    Handles tables like: 输出特性 | 参数  where col-0 is the parameter name
    and col-1 is the value description.
    """
    payloads: list[dict[str, object]] = []
    for row in rows:
        if len(row) < 2:
            continue
        param_name = str(row[0]).strip()
        param_value = str(row[1]).strip()
        if not param_name or not param_value:
            continue
        if param_name in {"参数", "输出特性", "项目"}:
            continue
        payloads.append(
            {
                "fact_type": "parameter_value",
                "predicate": "has_parameter_value",
                "payload": {
                    "table_title": unit.table_title,
                    "table_no": unit.table_no,
                    "parameter": param_name,
                    "value_description": param_value,
                    **_parameter_scope_fields(
                        title=unit.title,
                        table_title=unit.table_title,
                        object_name=param_name,
                        parameter=param_name,
                        symbol="",
                        state="",
                    ),
                },
                "page_no": unit.page,
                "base_confidence": 0.74,
            }
        )
    return payloads


def _table_parameter_fact_payloads(unit) -> list[dict[str, object]]:
    headers = list(unit.headers or [])
    rows = list(unit.rows or [])
    if not headers or not rows:
        return []

    normalized_headers = [_normalize_header_name(str(header)) for header in headers]
    header_blob = " ".join(normalized_headers)

    # 2-column key-value parameter tables (e.g. "输出特性 | 参数")
    if len(headers) == 2 and len(rows) >= 2:
        title_blob = f"{unit.title or ''} {unit.table_title or ''}"
        if "参数" in header_blob and any(kw in title_blob + header_blob for kw in ("参数", "特性", "规格", "输出", "性能")):
            return _two_column_parameter_payloads(unit, rows)

    if not any(token in header_blob for token in ("参数", "符号", "标称值", "单位", "最大值", "最小值", "电路版本")):
        return []

    column_map = {name: idx for idx, name in enumerate(normalized_headers)}
    object_idx = column_map.get("对象")
    parameter_idx = column_map.get("参数", 0)
    symbol_idx = column_map.get("符号", 1 if len(headers) > 1 else 0)
    unit_idx = column_map.get("单位")
    nominal_idx = column_map.get("标称值")
    max_idx = column_map.get("最大值")
    min_idx = column_map.get("最小值")
    state_idx = column_map.get("状态")
    if state_idx is None:
        state_idx = column_map.get("电路版本")

    payloads: list[dict[str, object]] = []
    last_object = ""
    for row in rows:
        if len(row) < 3:
            continue
        object_name = _row_value(row, object_idx)
        if object_name:
            last_object = object_name
        parameter = _row_value(row, parameter_idx)
        symbol = _row_value(row, symbol_idx)
        unit_name = _normalize_unit(_row_value(row, unit_idx))
        nominal = _row_value(row, nominal_idx)
        max_value = _row_value(row, max_idx)
        min_value = _row_value(row, min_idx)
        state = _row_value(row, state_idx)

        if not parameter and not symbol:
            continue
        if parameter in {"最小值", "标称值", "最大值"}:
            continue

        payloads.append(
            {
                "fact_type": "parameter_value",
                "predicate": "has_parameter_value",
                "payload": {
                    "table_title": unit.table_title,
                    "table_no": unit.table_no,
                    "object": object_name or last_object,
                    "parameter": parameter,
                    "symbol": symbol,
                    "unit": unit_name,
                    "nominal_value": nominal,
                    "max_value": max_value,
                    "min_value": min_value,
                    "state": state,
                    **_parameter_scope_fields(
                        title=unit.title,
                        table_title=unit.table_title,
                        object_name=object_name or last_object,
                        parameter=parameter,
                        symbol=symbol,
                        state=state,
                    ),
                },
                "page_no": unit.page,
                "base_confidence": 0.76,
            }
        )
    return payloads


def _normalize_header_name(value: str) -> str:
    text = re.sub(r"\s+", "", value)
    text = re.sub(r"\$[^$]+\$", "", text)
    text = text.replace("^a", "").replace("^b", "").replace("^c", "")
    text = re.sub(r"[ᵃᵇᶜᵈᵉᶠᵍ]", "", text)
    if "参数" in text:
        return "参数"
    if "时序" in text:
        return "时序"
    if "控制时序说明" in text:
        return "控制时序说明"
    if "符号" in text:
        return "符号"
    if "单位" in text:
        return "单位"
    if "标称值" in text:
        return "标称值"
    if "最大值" in text:
        return "最大值"
    if "最小值" in text:
        return "最小值"
    if "电路版本" in text:
        return "电路版本"
    if "状态" in text:
        return "状态"
    if "对象" in text:
        return "对象"
    return text


def _row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row) or index < 0:
        return ""
    return str(row[index]).strip()


def _normalize_unit(value: str) -> str:
    unit = value.replace("\\Omega", "Ω").replace("Omega", "Ω").replace("ohm", "Ω")
    unit = unit.replace("\\mu", "μ")
    unit = re.sub(r"\s+", "", unit)
    return unit


def _timing_fact_payloads(unit) -> list[dict[str, object]]:
    headers = [str(item or "") for item in (unit.headers or [])]
    rows = list(unit.rows or [])
    if not headers or not rows:
        return []

    header_blob = " ".join(headers)
    title_blob = f"{unit.title or ''} {unit.table_title or ''}"
    if not any(token in header_blob + title_blob for token in ("时序", "状态", "条件", "时间", "控制时序")):
        return []

    payloads: list[dict[str, object]] = []
    title, table_title = _process_title_for_table_unit(unit)
    normalized_headers = [_normalize_header_name(header) for header in headers]
    column_map = {name: idx for idx, name in enumerate(normalized_headers)}

    sequence_idx = column_map.get("时序", 0)
    state_idx = column_map.get("状态")
    condition_idx = column_map.get("条件")
    time_idx = column_map.get("时间")
    action_idx = column_map.get("控制时序说明")
    if action_idx is None and len(headers) == 2:
        action_idx = 1

    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        sequence = _row_value(row, sequence_idx)
        state = _row_value(row, state_idx)
        condition = _row_value(row, condition_idx)
        time_value = _row_value(row, time_idx)
        action = _row_value(row, action_idx)
        combined = " ".join(part for part in [sequence, state, condition, action, time_value] if part).strip()
        if not combined:
            continue

        payloads.append(
            {
                "fact_type": "process_fact",
                "predicate": "describes_process",
                "payload": {
                    "title": title,
                    "table_title": table_title,
                    "section": unit.section,
                    "sequence": sequence,
                    "state": state,
                    "condition": condition,
                    "action": action or combined,
                    "time_constraint": time_value,
                },
                "page_no": unit.page,
                "base_confidence": 0.8,
            }
        )

        if state or condition or time_value:
            payloads.append(
                {
                    "fact_type": "transition_fact",
                    "predicate": "has_transition",
                    "payload": {
                        "title": title,
                        "table_title": table_title,
                        "section": unit.section,
                        "sequence": sequence,
                        "state": state,
                        "condition": condition,
                        "action": action,
                        "time_constraint": time_value,
                    },
                    "page_no": unit.page,
                    "base_confidence": 0.78,
                }
            )
    return payloads


def _parameter_scope_fields(
    *,
    title: str | None,
    table_title: str | None,
    object_name: str,
    parameter: str,
    symbol: str,
    state: str,
) -> dict[str, object]:
    table_haystack = " ".join(part for part in [title or "", table_title or ""] if part).upper()
    row_haystack = " ".join(part for part in [object_name, parameter, symbol, state] if part).upper()
    tags: list[str] = []
    row_tags: list[str] = []
    table_tags: list[str] = []

    def add(tag: str, *, row_only: bool = False, table_only: bool = False) -> None:
        if tag not in tags:
            tags.append(tag)
        if row_only and tag not in row_tags:
            row_tags.append(tag)
        if table_only and tag not in table_tags:
            table_tags.append(tag)

    for token in ("CC1", "CC2", "CP", "R1", "R2", "R3", "R4", "R4C", "R4C'", "RV", "RV'"):
        if token in row_haystack:
            add(token, row_only=True)
        elif token in table_haystack:
            add(token, table_only=True)
    for token in ("控制导引", "检测点1", "检测点2", "检测点3", "车辆插头", "车辆插座", "充电机", "电动汽车"):
        if token in row_haystack:
            add(token, row_only=True)
        elif token in table_haystack:
            add(token, table_only=True)

    loop_scope = "general"
    if "CC1" in row_tags or "CC2" in row_tags:
        loop_scope = "cc"
    elif "CC1" in tags or "CC2" in tags:
        loop_scope = "cc"
    elif "CP" in row_tags or "CP" in tags:
        loop_scope = "cp"

    detection_points: list[str] = []
    for token in ("检测点1", "检测点2", "检测点3"):
        if token in row_tags or token in table_tags:
            detection_points.append(token)

    interface_scope: list[str] = []
    for token in ("车辆插头", "车辆插座", "充电机", "电动汽车"):
        if token in row_tags or token in table_tags:
            interface_scope.append(token)

    scope_confidence = "row" if row_tags else "table" if table_tags else "none"

    return {
        "focus_tags": tags,
        "row_focus_tags": row_tags,
        "table_focus_tags": table_tags,
        "loop_scope": loop_scope,
        "detection_points": detection_points,
        "interface_scope": interface_scope,
        "scope_confidence": scope_confidence,
        "source_caption": (table_title or title or "").strip(),
    }
def _ensure_evidence_chains(connection, doc_id: str) -> int:
    """Ensure every fact has at least one source_unit_fact_map entry. Returns count of fixed facts."""
    unlinked = connection.execute(
        """
        SELECT f.fact_id, f.qualifiers_json
        FROM facts f
        LEFT JOIN source_unit_fact_map m ON f.fact_id = m.fact_id
        WHERE f.source_doc_id = ? AND m.fact_id IS NULL
        """,
        (doc_id,),
    ).fetchall()

    if not unlinked:
        return 0

    # Pre-load source_units by page_no for this document
    su_by_page: dict[int, str] = {}
    default_su: str | None = None
    for row in connection.execute(
        "SELECT unit_id, page_no FROM source_units WHERE doc_id = ? AND status != 'rejected' ORDER BY page_no",
        (doc_id,),
    ):
        if default_su is None:
            default_su = row["unit_id"]
        if row["page_no"] not in su_by_page:
            su_by_page[row["page_no"]] = row["unit_id"]

    fixed = 0
    for row in unlinked:
        page_no = 0
        try:
            q = json.loads(row["qualifiers_json"] or "{}")
            page_no = int(q.get("page_no", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            # Malformed qualifiers; fall back to the default page_no=0 lookup.
            pass

        unit_id = su_by_page.get(page_no) or default_su
        if unit_id:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO source_unit_fact_map (doc_id, unit_id, fact_id) VALUES (?, ?, ?)",
                (doc_id, unit_id, row["fact_id"]),
            )
            if cursor.rowcount > 0:
                fixed += 1

    return fixed


def _insert_metadata_facts(connection, doc_id: str, metadata: dict, missing_types: set[str]) -> int:
    """Insert metadata facts for the specified missing types. Returns count of inserted facts."""
    now = _utc_now()

    type_map = {
        "document_title": ("document_title", "title", metadata.get("title", "")),
        "document_standard": ("document_standard", "standard_code", metadata.get("standard_id", "")),
        "document_lifecycle": ("document_lifecycle", "publication_date", metadata.get("publication_date", "")),
        "document_abstract": ("document_abstract", "has_abstract", metadata.get("abstract", "")),
    }

    inserted = 0
    for mt in missing_types:
        if mt not in type_map:
            continue
        fact_type, predicate, value = type_map[mt]
        if not value:
            continue

        fact_id = next_prefixed_id(connection, "fact", "FACT")

        connection.execute(
            """INSERT INTO facts
               (fact_id, source_doc_id, fact_type, predicate, object_value,
                confidence, fact_status, qualifiers_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fact_id, doc_id, fact_type, predicate,
                json.dumps({"value": value}, ensure_ascii=False),
                0.85, "active",
                json.dumps({"page_no": 1, "auto_repaired": True}, ensure_ascii=False),
                now, now,
            ),
        )

        # Create source_unit_fact_map link
        su = connection.execute(
            "SELECT unit_id FROM source_units WHERE doc_id = ? AND page_no = 1 AND status != 'rejected' LIMIT 1",
            (doc_id,),
        ).fetchone()
        if su:
            connection.execute(
                "INSERT OR IGNORE INTO source_unit_fact_map (doc_id, unit_id, fact_id) VALUES (?, ?, ?)",
                (doc_id, su["unit_id"], fact_id),
            )

        inserted += 1

    return inserted
def build_facts_for_document(workspace_root: Path, doc_id: str) -> FactsBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        rows = connection.execute(
            """
            SELECT evidence_id, page_no, confidence, risk_level, normalized_text
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        document_row = connection.execute(
            "SELECT source_filename FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        source_filename = str(document_row["source_filename"] or "") if document_row else ""

        connection.execute(
            "DELETE FROM fact_evidence_map WHERE fact_id IN (SELECT fact_id FROM facts WHERE source_doc_id = ?)",
            (doc_id,),
        )
        # When facts are rebuilt with new IDs, the source_unit_fact_map links
        # to old fact IDs become stale. Clean them up so that knowledge contracts
        # don't silently pass on broken traceability chains.
        connection.execute(
            "DELETE FROM source_unit_fact_map WHERE doc_id = ?",
            (doc_id,),
        )
        connection.execute("DELETE FROM facts WHERE source_doc_id = ?", (doc_id,))

        exported: list[dict[str, object]] = []
        fact_types: dict[str, int] = {}
        seen_facts: set[str] = set()

        metadata_candidates: list[tuple[object, list[tuple[str, str, dict[str, object]]]]] = []
        page_payloads: list[tuple[object, list[tuple[str, str, dict[str, object]]]]] = []

        for row in rows:
            text = row["normalized_text"] or ""
            metadata_items: list[tuple[str, str, dict[str, object]]] = []
            if row["page_no"] == 1:
                metadata_items.extend(_extract_cover_metadata(text, source_filename))
            if row["page_no"] <= 3:
                metadata_items.extend(_extract_doc_metadata(text, source_filename))
                if metadata_items:
                    metadata_candidates.append((row, metadata_items))

            extracted: list[tuple[str, str, dict[str, object]]] = []
            extracted.extend(_extract_section_headings(text))
            extracted.extend(_extract_term_definitions(text))
            extracted.extend(_extract_type_relations(text))
            page_payloads.append((row, extracted))

        chosen_metadata: list[tuple[object, tuple[str, str, dict[str, object]]]] = []
        metadata_seen: set[tuple[str, str]] = set()
        for row, items in metadata_candidates:
            for fact_type, predicate, payload in items:
                key = (fact_type, predicate)
                if key in metadata_seen:
                    continue
                metadata_seen.add(key)
                chosen_metadata.append((row, (fact_type, predicate, payload)))

        for row, item in _extract_document_level_concepts(rows):
            fact_type, predicate, payload = item
            key = (fact_type, predicate)
            if key in metadata_seen:
                continue
            metadata_seen.add(key)
            chosen_metadata.append((row, item))

        for row, (fact_type, predicate, payload) in chosen_metadata:
            payload = _sanitize_payload(payload)
            dedupe_key = json.dumps([fact_type, predicate, payload], ensure_ascii=False, sort_keys=True)
            if dedupe_key in seen_facts:
                continue
            seen_facts.add(dedupe_key)

            fact_id = next_prefixed_id(connection, "fact", "FACT")
            object_value = json.dumps(payload, ensure_ascii=False)
            confidence = _confidence(0.9, float(row["confidence"]))

            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, fact_type, subject_entity_id, predicate, object_value,
                    object_entity_id, qualifiers_json, confidence, fact_status,
                    source_doc_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    fact_type,
                    None,
                    predicate,
                    object_value,
                    None,
                    json.dumps(
                        {
                            "page_no": row["page_no"],
                            "risk_level": row["risk_level"],
                        },
                        ensure_ascii=False,
                    ),
                    confidence,
                    "ready",
                    doc_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                VALUES (?, ?, ?)
                """,
                (fact_id, row["evidence_id"], "direct"),
            )

            fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
            exported.append(
                {
                    "fact_id": fact_id,
                    "fact_type": fact_type,
                    "predicate": predicate,
                    "object": payload,
                    "page_no": row["page_no"],
                    "evidence_id": row["evidence_id"],
                    "confidence": confidence,
                }
            )

        for row, extracted in page_payloads:
            for fact_type, predicate, payload in extracted:
                payload = _sanitize_payload(payload)
                dedupe_key = json.dumps([fact_type, predicate, payload], ensure_ascii=False, sort_keys=True)
                if dedupe_key in seen_facts:
                    continue
                seen_facts.add(dedupe_key)

                fact_id = next_prefixed_id(connection, "fact", "FACT")
                object_value = json.dumps(payload, ensure_ascii=False)
                confidence = _confidence(
                    0.9 if fact_type not in {"term_definition", "concept_definition"} else 0.8,
                    float(row["confidence"]),
                )

                connection.execute(
                    """
                    INSERT INTO facts (
                        fact_id, fact_type, subject_entity_id, predicate, object_value,
                        object_entity_id, qualifiers_json, confidence, fact_status,
                        source_doc_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact_id,
                        fact_type,
                        None,
                        predicate,
                        object_value,
                        None,
                        json.dumps(
                            {
                                "page_no": row["page_no"],
                                "risk_level": row["risk_level"],
                            },
                            ensure_ascii=False,
                        ),
                        confidence,
                        "ready",
                        doc_id,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                    VALUES (?, ?, ?)
                    """,
                    (fact_id, row["evidence_id"], "direct"),
                )

                fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
                exported.append(
                    {
                        "fact_id": fact_id,
                        "fact_type": fact_type,
                        "predicate": predicate,
                        "object": payload,
                        "page_no": row["page_no"],
                        "evidence_id": row["evidence_id"],
                        "confidence": confidence,
                    }
                )

        export_path = paths.facts / f"{doc_id}.facts.json"
        row_by_page = {int(row["page_no"]): row for row in rows}
        for item in _knowledge_unit_fact_payloads(workspace_root, doc_id):
            item = {**item, "payload": _sanitize_payload(item["payload"])}
            row = row_by_page.get(int(item["page_no"])) or _nearest_evidence_row(rows, int(item["page_no"]))
            if row is None:
                continue
            dedupe_key = json.dumps(
                [item["fact_type"], item["predicate"], item["payload"]],
                ensure_ascii=False,
                sort_keys=True,
            )
            if dedupe_key in seen_facts:
                continue
            seen_facts.add(dedupe_key)

            fact_id = next_prefixed_id(connection, "fact", "FACT")
            object_value = json.dumps(item["payload"], ensure_ascii=False)
            confidence = _confidence(float(item["base_confidence"]), float(row["confidence"]))

            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, fact_type, subject_entity_id, predicate, object_value,
                    object_entity_id, qualifiers_json, confidence, fact_status,
                    source_doc_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    item["fact_type"],
                    None,
                    item["predicate"],
                    object_value,
                    None,
                    json.dumps(
                        {
                            "page_no": row["page_no"],
                            "risk_level": row["risk_level"],
                        },
                        ensure_ascii=False,
                    ),
                    confidence,
                    "ready",
                    doc_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                VALUES (?, ?, ?)
                """,
                (fact_id, row["evidence_id"], "derived"),
            )
            fact_types[item["fact_type"]] = fact_types.get(item["fact_type"], 0) + 1
            exported.append(
                {
                    "fact_id": fact_id,
                    "fact_type": item["fact_type"],
                    "predicate": item["predicate"],
                    "object": item["payload"],
                    "page_no": row["page_no"],
                    "evidence_id": row["evidence_id"],
                    "confidence": confidence,
                }
            )

        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "fact_count": len(exported),
                    "fact_types": fact_types,
                    "items": exported,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Ensure every fact has a source_unit_fact_map entry
        _ensure_evidence_chains(connection, doc_id)

        connection.commit()
        return FactsBuildResult(
            doc_id=doc_id,
            fact_count=len(exported),
            fact_types=fact_types,
            export_path=export_path,
        )
    finally:
        connection.close()
def _nearest_evidence_row(rows: list[object], page_no: int):
    if not rows:
        return None
    return min(rows, key=lambda row: abs(int(row["page_no"]) - page_no))
