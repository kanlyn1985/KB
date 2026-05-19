from __future__ import annotations

import json
import re
import unicodedata
from html import unescape
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id
from .knowledge_units import extract_knowledge_units, save_knowledge_units, save_knowledge_units_jsonl


@dataclass(frozen=True)
class FactsBuildResult:
    doc_id: str
    fact_count: int
    fact_types: dict[str, int]
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_text(value: str) -> str:
    value = unescape(str(value or "")).replace("\xa0", " ")
    value = _normalize_ocr_text(value)
    value = re.sub(r"&nbsp;?", " ", value, flags=re.I)
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _clean_text(value)
    return value


def _normalize_ocr_text(value: str) -> str:
    normalized = (
        value.replace("犌", "G")
        .replace("犅", "B")
        .replace("犜", "T")
    )
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = (
        normalized.replace("／", "/")
        .replace("—", "—")
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("‒", "-")
        .replace("–", "-")
        .replace("﹣", "-")
        .replace("－", "-")
    )
    return normalized


STANDARD_CODE_PATTERN = re.compile(
    r"(?:GB/T|GBT|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[.\-—:]\d+)*",
    re.I,
)
PROCESS_BP_PATTERN = re.compile(
    r"\b((?:ACQ|SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM|MLE|SPL)\.\d+)\.BP\d+\b",
    re.I,
)


def _normalize_standard_candidate(match: str) -> str:
    standard_code = _normalize_ocr_text(match).strip()
    standard_code = re.sub(r"(?i)^GBT", "GB/T", standard_code)
    standard_code = re.sub(r"(?i)^GB/T(?=\d)", "GB/T ", standard_code)
    standard_code = re.sub(r"(?i)^GB(?=\d)", "GB ", standard_code)
    standard_code = re.sub(r"(?i)^QC/T(?=\d)", "QC/T ", standard_code)
    standard_code = re.sub(r"(?i)^QC(?=\d)", "QC ", standard_code)
    standard_code = re.sub(r"\s+", " ", standard_code)
    prefix_match = re.match(r"(?i)^(GB/T|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s*(.+)$", standard_code)
    if not prefix_match:
        return standard_code
    prefix = prefix_match.group(1).upper()
    rest = prefix_match.group(2).strip().replace("—", "-").replace(":", "-")
    parts = [part for part in re.split(r"-+", rest) if part]
    if len(parts) >= 2 and re.fullmatch(r"(?:19|20)\d{2}", parts[-1]):
        return f"{prefix} {'-'.join(parts[:-1])}—{parts[-1]}"
    return f"{prefix} {rest}".strip()


def _is_copyright_or_boilerplate_line(line: str) -> bool:
    compact = re.sub(r"\s+", " ", _normalize_ocr_text(line)).strip().lower()
    return bool(
        compact.startswith("©")
        or compact.startswith("(c)")
        or "copyright" in compact
        or "all rights reserved" in compact
        or "iso copyright office" in compact
    )


def _is_valid_standard_candidate(candidate: str, source_line: str) -> bool:
    if not candidate or _is_copyright_or_boilerplate_line(source_line):
        return False
    normalized = candidate.upper().replace("—", "-")
    match = re.match(r"^(GB/T|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s+(.+)$", normalized)
    if not match:
        return False
    prefix, rest = match.group(1), match.group(2).strip()
    if prefix in {"ISO", "IEC"} and re.fullmatch(r"(?:19|20)\d{2}", rest):
        return False
    return len(re.findall(r"\d", rest)) >= 2


def _extract_standard_candidates(text: str, source_filename: str = "") -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    search_texts = [text]
    if source_filename:
        search_texts.append(Path(source_filename).stem)
    for search_text in search_texts:
        lines = _normalize_ocr_text(search_text).splitlines() or [search_text]
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            for match in STANDARD_CODE_PATTERN.findall(line):
                candidate = _normalize_standard_candidate(match)
                if not _is_valid_standard_candidate(candidate, line):
                    continue
                key = candidate.upper()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
    return candidates


def _choose_primary_standard(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    for candidate in candidates:
        if re.search(r"[-—]\d{4}$", candidate):
            return candidate
    return candidates[0]


def _extract_doc_metadata(text: str, source_filename: str = "") -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title_found = False
    for line in lines:
        if line.startswith("# "):
            results.append(("document_title", "title", {"value": line[2:].strip()}))
            title_found = True
            break

    primary_standard = _choose_primary_standard(_extract_standard_candidates(text, source_filename))
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    if not title_found:
        for line in lines:
            compact = re.sub(r"\s+", "", line)
            if not compact:
                continue
            if "国家标准" in compact:
                continue
            if re.search(r"^(ICS|CCS|GB/T|GB|ISO|IEC|\d{4}-\d{2}-\d{2})", compact):
                continue
            if "发布" in line or "实施" in line:
                continue
            if len(compact) < 8:
                continue
            if any(token in line for token in ("电动汽车", "charging", "系统", "部分", "逆变器", "电源", "Road vehicles", "Unified diagnostic", "Specification and requirements")):
                results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", line).strip()}))
                title_found = True
                break

    replace_match = re.search(r"代替\s+([A-Z]{1,4}/?[A-Z]*\s*[\d.\-—]+)", text)
    if replace_match:
        results.append(("document_versioning", "replaces_standard", {"value": replace_match.group(1).strip()}))

    publish_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*发布", text)
    if publish_match:
        results.append(("document_lifecycle", "publication_date", {"value": publish_match.group(1).replace("—", "-")}))

    effective_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*实施", text)
    if effective_match:
        results.append(("document_lifecycle", "effective_date", {"value": effective_match.group(1).replace("—", "-")}))

    return results


def _extract_cover_metadata(text: str, source_filename: str = "") -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    primary_standard = _choose_primary_standard(_extract_standard_candidates(joined, source_filename))
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if len(compact) < 8:
            continue
        if compact.startswith(("ICS", "CCS", "GB/T", "GB", "ISO", "IEC")):
            continue
        if "国家标准" in compact:
            continue
        if "发布" in line or "实施" in line:
            continue
        if any(token in line for token in ("电动汽车", "车载充电机", "charger", "charging", "系统", "部分", "逆变器", "电源", "Road vehicles", "Unified diagnostic", "Specification and requirements")):
            results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", line).strip()}))
            break

    publish_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*发布", joined)
    if publish_match:
        results.append(("document_lifecycle", "publication_date", {"value": publish_match.group(1).replace("—", "-")}))

    effective_match = re.search(r"(\d{4}[-—]\d{2}[-—]\d{2})\s*实施", joined)
    if effective_match:
        results.append(("document_lifecycle", "effective_date", {"value": effective_match.group(1).replace("—", "-")}))

    return results


def _extract_section_headings(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "heading_level": level},
                    )
                )
            continue

        numbered = re.match(r"^(\d+(?:\.\d+){0,4})\s+(.+)$", line)
        if numbered:
            title = numbered.group(2).strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "section_number": numbered.group(1), "heading_level": 0},
                    )
                )
    return results


def _extract_term_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    results.extend(_extract_inline_heading_definitions(text))
    results.extend(_extract_process_attribute_scope_definitions(text))
    results.extend(_extract_process_group_definitions(text))
    looks_like_term_page = (
        text.count("## ") >= 2 and text.count("#### ") >= 2 and re.search(r"####\s*\d+\.\d+\.\d+", text)
    )
    looks_like_numeric_glossary_page = (
        len(
            re.findall(
                r"(?:^|\n)\s*\d+\.\d+\.\d+\s*\n[^\n]{2,80}\n[^\n]{8,}",
                text,
            )
        )
        >= 2
    )
    if (
        "术语和定义" not in text
        and "下列术语和定义适用于本文件" not in text
        and not looks_like_term_page
        and not looks_like_numeric_glossary_page
    ):
        return results

    seen: set[tuple[str, str]] = set()
    lines = text.splitlines()
    current_term: str | None = None
    current_definition_lines: list[str] = []

    def flush_term() -> None:
        nonlocal current_term, current_definition_lines
        if not current_term:
            current_definition_lines = []
            return

        term = _clean_text(current_term)
        definition = _clean_text("\n".join(current_definition_lines))
        if not term or not definition:
            current_term = None
            current_definition_lines = []
            return
        if len(term) > 80 or len(definition) < 12:
            current_term = None
            current_definition_lines = []
            return
        if term.lower() in {"前言", "引言", "目 次", "目次"}:
            current_term = None
            current_definition_lines = []
            return
        if re.match(r"^\d", term):
            current_term = None
            current_definition_lines = []
            return
        blocked_term_tokens = (
            "增加了",
            "更改了",
            "删除了",
            "见",
            "前言",
            "引言",
            "目 次",
            "目次",
            "范围",
            "规范性引用文件",
            "术语和定义",
        )
        if any(token in term for token in blocked_term_tokens):
            current_term = None
            current_definition_lines = []
            return
        if "：" in term or ":" in term:
            current_term = None
            current_definition_lines = []
            return
        if len(term.splitlines()) > 1:
            current_term = None
            current_definition_lines = []
            return
        if re.search(r"[，。；]$", term):
            current_term = None
            current_definition_lines = []
            return
        blocked_definition_tokens = (
            "增加了",
            "更改了",
            "删除了",
            "见2015年版",
            "见第",
            "本文件代替",
            "下列文件中的内容通过",
        )
        if any(token in definition for token in blocked_definition_tokens):
            current_term = None
            current_definition_lines = []
            return
        if "适用于本文件" in definition and len(definition) < 80:
            current_term = None
            current_definition_lines = []
            return
        if definition.count("GB/T") >= 4 and "是" not in definition and "指" not in definition:
            current_term = None
            current_definition_lines = []
            return
        if not _definition_has_publishable_signal(definition):
            current_term = None
            current_definition_lines = []
            return
        key = (term, definition[:100])
        if key in seen:
            current_term = None
            current_definition_lines = []
            return
        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )
        current_term = None
        current_definition_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            flush_term()
            current_term = stripped[3:].strip()
            current_definition_lines = []
            continue

        if stripped.startswith(("### ", "#### ", "# ")):
            flush_term()
            current_term = None
            current_definition_lines = []
            continue

        if current_term is not None:
            current_definition_lines.append(line)

    flush_term()
    results.extend(_extract_markdown_bilingual_terms(text, seen))
    results.extend(_extract_numeric_term_definitions(text, seen))
    return results


def _extract_inline_heading_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return []
    if not re.fullmatch(r"\d+(?:\.\d+){1,4}", lines[0]):
        return []

    term = _clean_definition_term(lines[1])
    definition = _clean_text("\n".join(lines[2:]))
    if not _is_publishable_definition_entry(term, definition):
        return []
    return [
        (
            _definition_fact_type_for_term(term),
            _definition_predicate_for_term(term),
            {"term": term, "definition": definition},
        )
    ]


def _extract_process_attribute_scope_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    normalized = _clean_text(text)
    if "过程属性范围" not in normalized:
        return []
    results: list[tuple[str, str, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    patterns = [
        re.compile(
            r"过程属性名称\s*\n+(?P<term>[^\n]{2,80}?过程属性)\s*\n+过程属性范围\s*\n+(?P<definition>(?P=term)是[:：][^\n]+)",
            re.S,
        ),
        re.compile(r"(?P<term>[\u4e00-\u9fffA-Za-z0-9 ._-]{2,80}?过程属性)是[:：](?P<body>[^\n。]+(?:。)?)"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(normalized):
            term = _clean_definition_term(match.group("term"))
            definition = _clean_text(match.group("definition") if "definition" in match.groupdict() else f"{term}是：{match.group('body')}")
            key = (term, definition[:100])
            if key in seen or not _is_publishable_definition_entry(term, definition):
                continue
            seen.add(key)
            results.append(
                (
                    _definition_fact_type_for_term(term),
                    _definition_predicate_for_term(term),
                    {"term": term, "definition": definition, "definition_label": "过程属性范围"},
                )
            )
    return results


def _extract_process_group_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    normalized = _clean_text(text)
    if "过程组" not in normalized:
        return []
    results: list[tuple[str, str, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    pattern = re.compile(
        r"(?P<term>[\u4e00-\u9fffA-Za-z ]{2,40}过程组)(?:（(?P<code>[A-Z]{2,5})）|\((?P<code_ascii>[A-Z]{2,5})\))?"
        r"(?P<definition>(?:包括|由|是|执行)[^。]{8,220}。)",
        re.S,
    )
    for match in pattern.finditer(normalized):
        term = _clean_definition_term(match.group("term"))
        code = str(match.group("code") or match.group("code_ascii") or "").strip()
        definition = _clean_text(f"{term}{f'（{code}）' if code else ''}{match.group('definition')}")
        key = (term, definition[:100])
        if key in seen or not _is_publishable_definition_entry(term, definition):
            continue
        seen.add(key)
        results.append(
            (
                "concept_definition",
                "defines_concept",
                {"term": f"{term}（{code}）" if code else term, "definition": definition, "concept_type": "process_group"},
            )
        )
    return results


def _extract_markdown_bilingual_terms(
    text: str,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    lines = [line.rstrip() for line in text.splitlines()]

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped.startswith("## "):
            continue
        term_line = stripped[3:].strip()
        if len(term_line) < 4:
            continue
        if not any(token in term_line for token in (":", "；", ";", " to ", "V2")):
            continue

        definition_lines: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                if definition_lines:
                    break
                cursor += 1
                continue
            if candidate.startswith("#") and not candidate.startswith(("### ", "#### ")):
                break
            if re.match(r"^\d+(?:\.\d+){1,4}\b", candidate):
                break
            definition_lines.append(candidate)
            cursor += 1

        definition = _clean_text("\n".join(definition_lines))
        term = _clean_text(term_line)
        if not term or not definition:
            continue
        if len(definition) < 12:
            continue
        if not _definition_has_publishable_signal(definition):
            continue
        key = (term, definition[:100])
        if key in seen:
            continue
        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )

    return results


def _extract_numeric_term_definitions(
    text: str,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    lines = [line.rstrip() for line in text.splitlines()]
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if not re.match(r"^\d+(?:\.\d+){1,4}$", stripped):
            index += 1
            continue

        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            break

        term_line = lines[cursor].strip()
        if (
            term_line.startswith("#")
            or re.match(r"^\d+(?:\.\d+)+", term_line)
            or len(term_line) > 100
        ):
            index = cursor
            continue

        cursor += 1
        definition_lines: list[str] = []
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                if definition_lines:
                    break
                cursor += 1
                continue
            if candidate.startswith("#") or re.match(r"^\d+(?:\.\d+){1,4}\b", candidate):
                break
            definition_lines.append(candidate)
            cursor += 1

        definition = _clean_text("\n".join(definition_lines))
        term = _clean_text(_strip_bilingual_tail(term_line))
        if not term or not definition:
            index = cursor
            continue
        if len(term) > 80 or len(definition) < 12:
            index = cursor
            continue
        if not _definition_has_publishable_signal(definition):
            index = cursor
            continue
        key = (term, definition[:100])
        if key in seen:
            index = cursor
            continue

        seen.add(key)
        results.append(
            (
                "term_definition",
                "defines_term",
                {"term": term, "definition": definition},
            )
        )
        index = cursor

    return results


def _strip_bilingual_tail(value: str) -> str:
    value = value.strip()
    if re.search(r"[\u4e00-\u9fff]", value) and re.search(r"[A-Za-z]", value):
        return re.sub(r"\s{2,}", " ", value)
    match = re.match(r"^(.*?)(?:\s+[A-Za-z][A-Za-z0-9\-()/ ]+)?$", value.strip())
    cleaned = match.group(1).strip() if match else value.strip()
    return re.sub(r"\s{2,}", " ", cleaned)


def _extract_abstract_concepts(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    normalized = _normalize_ocr_text(text)
    if "摘要" not in normalized and "Abstract" not in normalized:
        return results

    concept_patterns = [
        re.compile(
            r"(V2G)\s*\((Vehicle-to-Grid)\)\s*技术.*?作为一种(.+?)[。.]",
            re.S,
        ),
        re.compile(
            r"(Vehicle-to-Grid)\s*\((V2G)\)\s*technology.*?(facilitates.+?\.)",
            re.S | re.I,
        ),
    ]

    for pattern in concept_patterns:
        match = pattern.search(normalized)
        if not match:
            continue
        if match.group(1) == "V2G":
            term = "V2G"
            definition = _clean_text(f"Vehicle-to-Grid (V2G)技术作为一种{match.group(3)}。")
        else:
            term = "V2G"
            definition = _clean_text(match.group(0))
        results.append(
            (
                "concept_definition",
                "defines_concept",
                {"term": term, "definition": definition},
            )
        )
        break

    chinese_v2g_match = re.search(
        r"V2G\s*\((Vehicle-to-Grid)\)\s*技术作为一种创新的能源解决方案，通过实现电动车与电网之间的双向能量交换，(.+?)[。.]",
        normalized,
        re.S,
    )
    if chinese_v2g_match:
        definition = _clean_text(
            "V2G（Vehicle-to-Grid）技术是一种通过实现电动车与电网之间双向能量交换的创新能源解决方案，"
            + chinese_v2g_match.group(2)
            + "。"
        )
        results.insert(
            0,
            (
                "concept_definition",
                "defines_concept",
                {"term": "V2G", "definition": definition},
            ),
        )

    abstract_match = re.search(r"(?:摘\s*要|Abstract)\s*(.+)", normalized, re.S | re.I)
    if abstract_match:
        abstract_text = _clean_text(abstract_match.group(1))
        if len(abstract_text) > 80:
            results.append(
                (
                    "document_abstract",
                    "has_abstract",
                    {"value": abstract_text[:1200]},
                )
            )

    return results


def _extract_document_level_concepts(rows: list[object]) -> list[tuple[object, tuple[str, str, dict[str, object]]]]:
    if not rows:
        return []

    candidate_rows = [row for row in rows if row["page_no"] <= 2]
    combined_text = "\n".join(str(row["normalized_text"] or "") for row in candidate_rows)
    extracted = _extract_abstract_concepts(combined_text)
    if not extracted:
        return []

    anchor_row = candidate_rows[0]
    return [(anchor_row, item) for item in extracted]


def _extract_type_relations(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    normalized = _normalize_ocr_text(text)

    v2x_match = re.search(
        r"V2X.+?包括([^。]+)",
        normalized,
        re.I | re.S,
    )
    if not v2x_match:
        return results

    raw_items = re.split(r"[、,，；;]", v2x_match.group(1))
    cleaned_items: list[str] = []
    for item in raw_items:
        value = re.sub(r"等.*$", "", item).strip()
        if value and value not in cleaned_items:
            cleaned_items.append(value)

    for value in cleaned_items:
        results.append(
            (
                "comparison_relation",
                "includes_type",
                {"subject": "V2X", "item": value},
            )
        )

    return results


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


def _table_parameter_fact_payloads(unit) -> list[dict[str, object]]:
    headers = list(unit.headers or [])
    rows = list(unit.rows or [])
    if not headers or not rows:
        return []

    normalized_headers = [_normalize_header_name(str(header)) for header in headers]
    header_blob = " ".join(normalized_headers)
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
