from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeUnit:
    id: str
    type: str
    title: str
    content: str
    section: str | None
    page: int
    subject: str | None = None
    topic: str | None = None
    scope_type: str | None = None
    condition: str | None = None
    threshold: str | None = None
    table_title: str | None = None
    table_no: str | None = None
    headers: list[str] | None = None
    rows: list[list[str]] | None = None
    canonical_title: str | None = None
    canonical_table_title: str | None = None
    canonical_process_code: str | None = None
    content_role: str | None = None
    quality_flags: list[str] | None = None


@dataclass(frozen=True)
class KnowledgeUnitBundle:
    doc_id: str
    unit_count: int
    units: list[KnowledgeUnit]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def extract_knowledge_units(cleaned_doc_ir_path: Path) -> KnowledgeUnitBundle:
    payload = json.loads(cleaned_doc_ir_path.read_text(encoding="utf-8"))
    doc_id = str(payload["doc_id"])
    units: list[KnowledgeUnit] = []
    current_heading = ""
    current_section = None

    for page in payload.get("pages", []):
        page_no = int(page["page_no"])
        blocks = page.get("blocks", [])
        index = 0
        while index < len(blocks):
            block = blocks[index]
            block_type = str(block.get("type", "paragraph"))
            text = str(block.get("text") or "").strip()
            if not text:
                index += 1
                continue

            if block_type == "heading":
                current_heading = _strip_heading_marks(text)
                current_section = _extract_section_number(current_heading)
                index += 1
                continue

            if _looks_like_definition_term(blocks, index):
                unit = _definition_unit(doc_id, blocks, index, current_section, page_no)
                if unit:
                    units.append(unit)
                    index += 2
                    continue

            procedure = _procedure_unit(doc_id, blocks, index, current_heading, current_section, page_no)
            if procedure:
                units.append(procedure)
                index += 1
                continue

            if block_type == "table" or _looks_like_markdown_table(text):
                title = current_heading or f"page_{page_no}_table"
                table_title = _infer_table_title(blocks, index, current_heading)
                table_no = _extract_table_no(table_title or title)
                if _looks_like_markdown_table(text):
                    headers, rows = _parse_markdown_table(text)
                else:
                    headers, rows = _parse_html_table(text)
                units.append(
                    _knowledge_unit(
                        id=f"{doc_id}_table_{page_no}_{index+1}",
                        type="table_requirement",
                        title=title,
                        content=text,
                        section=current_section,
                        page=page_no,
                        table_title=table_title,
                        table_no=table_no,
                        headers=headers,
                        rows=rows,
                    )
                )
                index += 1
                continue

            if _looks_like_requirement(text):
                title = current_heading or f"page_{page_no}_requirement"
                subject, condition, threshold = _parse_requirement_fields(title, text)
                topic = _infer_requirement_topic(title, subject, current_heading)
                scope_type = _infer_requirement_scope_type(title, text, current_section)
                units.append(
                    _knowledge_unit(
                        id=f"{doc_id}_requirement_{page_no}_{index+1}",
                        type="requirement",
                        title=title,
                        content=text,
                        section=current_section,
                        page=page_no,
                        subject=subject,
                        topic=topic,
                        scope_type=scope_type,
                        condition=condition,
                        threshold=threshold,
                    )
                )

            index += 1

    return KnowledgeUnitBundle(doc_id=doc_id, unit_count=len(units), units=units)


def _knowledge_unit(**kwargs: object) -> KnowledgeUnit:
    normalized = _normalize_unit_metadata(
        unit_type=str(kwargs.get("type") or ""),
        title=str(kwargs.get("title") or ""),
        content=str(kwargs.get("content") or ""),
        table_title=str(kwargs.get("table_title") or "") or None,
        section=str(kwargs.get("section") or "") or None,
        scope_type=str(kwargs.get("scope_type") or "") or None,
        headers=kwargs.get("headers") if isinstance(kwargs.get("headers"), list) else None,
    )
    return KnowledgeUnit(
        **kwargs,
        canonical_title=normalized["canonical_title"],
        canonical_table_title=normalized["canonical_table_title"],
        canonical_process_code=normalized["canonical_process_code"],
        content_role=normalized["content_role"],
        quality_flags=normalized["quality_flags"],
    )


def _normalize_unit_metadata(
    *,
    unit_type: str,
    title: str,
    content: str,
    table_title: str | None = None,
    section: str | None = None,
    scope_type: str | None = None,
    headers: list[object] | None = None,
) -> dict[str, object]:
    flags: list[str] = []
    raw_title = _clean_unit_title(title)
    raw_table_title = _clean_unit_title(table_title or "")
    title_is_noise = _is_layout_noise_title(raw_title)
    table_title_is_noise = _is_layout_noise_title(raw_table_title)
    if title_is_noise:
        flags.append("layout_title_noise")
    if table_title and table_title_is_noise:
        flags.append("layout_table_title_noise")

    process_code = _process_code_from_text(content)
    if process_code:
        flags.append("process_code_extracted")

    canonical_title = "" if title_is_noise else raw_title
    canonical_table_title = "" if table_title_is_noise else raw_table_title
    content_role = unit_type

    if unit_type == "procedure":
        content_role = "process_practice" if process_code else "procedure"
        if process_code and not canonical_title:
            canonical_title = f"{process_code} 基本实践"
            flags.append("canonical_title_from_process_code")
    elif unit_type == "table_requirement":
        header_blob = " ".join(str(item or "") for item in (headers or []))
        if any(token in f"{canonical_table_title} {canonical_title} {header_blob}" for token in ("时序", "状态", "条件", "时间", "控制时序")):
            content_role = "timing_table"
        elif "参数" in f"{canonical_table_title} {canonical_title} {header_blob}":
            content_role = "parameter_table"
        else:
            content_role = "table_requirement"
        if not canonical_title and canonical_table_title:
            canonical_title = canonical_table_title
            flags.append("canonical_title_from_table_title")
    elif unit_type == "requirement":
        content_role = scope_type or "requirement"
    elif unit_type == "definition":
        content_role = "definition"

    if not canonical_title:
        canonical_title = section or unit_type
        flags.append("canonical_title_fallback")

    return {
        "canonical_title": canonical_title,
        "canonical_table_title": canonical_table_title or None,
        "canonical_process_code": process_code or None,
        "content_role": content_role,
        "quality_flags": flags,
    }


PROCESS_BP_PATTERN = re.compile(
    r"\b((?:ACQ|SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM|MLE|SPL)\.\d+)\.BP\d+\b",
    re.I,
)


def _process_code_from_text(value: str) -> str:
    match = PROCESS_BP_PATTERN.search(str(value or ""))
    return match.group(1).upper() if match else ""


def _clean_unit_title(value: str) -> str:
    text = _strip_inline_markup(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[.。:：;；,，、\-–—•·]+\s*(?=(?:[A-Z]{2,4}|PA\s*\d|\d))", "", text, flags=re.I).strip()
    return text


def _is_layout_noise_title(value: str) -> bool:
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


def save_knowledge_units(bundle: KnowledgeUnitBundle, output_path: Path) -> Path:
    output_path.write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def save_knowledge_units_jsonl(bundle: KnowledgeUnitBundle, output_path: Path) -> Path:
    lines = [json.dumps(asdict(unit), ensure_ascii=False) for unit in bundle.units]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _looks_like_definition_term(blocks: list[dict[str, object]], index: int) -> bool:
    if index + 1 >= len(blocks):
        return False
    current = str(blocks[index].get("text") or "").strip()
    nxt = str(blocks[index + 1].get("text") or "").strip()
    if not current or not nxt:
        return False
    if current.startswith("#"):
        return False
    if _looks_like_caption_or_note(current) or _looks_like_process_practice(current):
        return False
    if _looks_like_section_heading_label(current):
        return False
    if not _looks_like_definition_label(current):
        return False
    if _looks_like_caption_or_note(nxt) or _looks_like_process_practice(nxt):
        return False
    if len(current) > 120:
        return False
    if _looks_like_reference_line(current):
        return False
    if _looks_like_reference_line(nxt):
        return False
    if current.startswith("<div") or current.startswith("<table"):
        return False
    if re.fullmatch(r"\d+\.\d+", current):
        return False
    if not any(ch.isalpha() for ch in current) and not re.search(r"[\u4e00-\u9fff]", current):
        return False
    if len(nxt) < 12:
        return False
    return any(token in nxt for token in ("是", "指", "用于", "能够", "通过", "作为", "实现"))


def _looks_like_definition_label(text: str) -> bool:
    compact = _strip_inline_markup(text)
    if len(compact) > 80:
        return False
    if _is_layout_noise_title(compact):
        return False
    if any(token in compact for token in ("。", "；", ";", "：", ":")):
        return False
    if compact.startswith(("——", "-", "•", "*")):
        return False
    if re.match(r"^[a-z]\)", compact, re.I):
        return False
    if any(token in compact for token in ("应", "不应", "不得", "宜", "可采用", "可通过")):
        return False
    return True


def _looks_like_section_heading_label(text: str) -> bool:
    raw = _strip_inline_markup(text)
    if raw.startswith("."):
        return True
    compact = raw.lstrip(". ").strip()
    if re.match(r"^\d+(?:\.\d+){0,5}\.?\s+\S+", compact):
        return True
    if re.match(r"^[A-Z]{1,5}\.\d+(?:\.\d+)*\.?\s+\S+", compact):
        return True
    return False


def _looks_like_caption_or_note(text: str) -> bool:
    compact = _strip_inline_markup(text)
    if re.match(r"^(?:表|图)\s*(?:[A-Z]\s*\.?\s*)?\d+(?:\.\d+)*(?:[—\-:：\s]|$)", compact):
        return True
    if re.match(r"^注\s*\d*\s*[:：]", compact):
        return True
    return False


def _looks_like_process_practice(text: str) -> bool:
    compact = _strip_inline_markup(text)
    return bool(
        re.match(
            r"^[A-Z]{2,5}\.\d+\.(?:BP|GP|PA)\d+(?::|：|\s|$)",
            compact,
            re.I,
        )
    )


def _strip_inline_markup(text: str) -> str:
    compact = text.replace("**", "").replace("__", "").strip()
    compact = compact.strip("*`_ ")
    return compact


def _definition_unit(
    doc_id: str,
    blocks: list[dict[str, object]],
    index: int,
    current_section: str | None,
    page_no: int,
) -> KnowledgeUnit | None:
    term = str(blocks[index].get("text") or "").strip()
    definition = str(blocks[index + 1].get("text") or "").strip()
    if not term or not definition:
        return None
    return _knowledge_unit(
        id=f"{doc_id}_definition_{page_no}_{index+1}",
        type="definition",
        title=term,
        content=definition,
        section=current_section,
        page=page_no,
    )


def _procedure_unit(
    doc_id: str,
    blocks: list[dict[str, object]],
    index: int,
    current_heading: str,
    current_section: str | None,
    page_no: int,
) -> KnowledgeUnit | None:
    text = str(blocks[index].get("text") or "").strip()
    if not text:
        return None
    if not _looks_like_procedure(text, current_heading, current_section):
        return None
    title = current_heading or f"page_{page_no}_procedure"
    return _knowledge_unit(
        id=f"{doc_id}_procedure_{page_no}_{index+1}",
        type="procedure",
        title=title,
        content=text,
        section=current_section,
        page=page_no,
    )


def _looks_like_requirement(text: str) -> bool:
    return any(token in text for token in ("应", "不应", "不得", "不超过", "不小于", "应符合", "应满足"))


def _parse_requirement_fields(title: str, text: str) -> tuple[str | None, str | None, str | None]:
    subject = _extract_requirement_subject(title, text)
    condition = _extract_requirement_condition(text)
    threshold = _extract_requirement_threshold(text)
    return subject, condition, threshold


def _infer_requirement_topic(title: str, subject: str | None, current_heading: str) -> str | None:
    candidates = [subject, title, current_heading]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        text = re.sub(r"^\d+(?:\.\d+){0,8}\s*", "", text)
        text = text.replace("（规范性）", "").replace("(规范性)", "")
        text = text.replace("（资料性）", "").replace("(资料性)", "")
        text = text.split("。", 1)[0].split("：", 1)[0].strip()
        if text:
            return text[:120]
    return None


def _infer_requirement_scope_type(title: str, text: str, current_section: str | None) -> str:
    heading = f"{title} {text[:120]}"
    if any(token in heading for token in ("目次", "目 次")):
        return "index"
    if any(token in heading for token in ("前言", "前    言", "引言")):
        return "preface"
    if re.search(r"^\s*1\s*范围", title) or "适用于" in text or "本文件规定了" in text:
        return "overview"
    if current_section and any(current_section.startswith(prefix) for prefix in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")):
        return "appendix_rule"
    if any(token in heading for token in ("要求", "应", "不应", "不得", "保护", "锁止", "急停", "停机")):
        return "normative_requirement"
    return "general_requirement"


def _extract_requirement_subject(title: str, text: str) -> str | None:
    for candidate in [title, text]:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^\d+(?:\.\d+){0,5}\s*", "", cleaned)
        cleaned = cleaned.split("。", 1)[0].split("：", 1)[0].strip()
        if cleaned:
            return cleaned[:120]
    return None


def _extract_requirement_condition(text: str) -> str | None:
    patterns = [
        r"(在[^。；，]{4,80}?(?:情况下|条件下|状态下))",
        r"(当[^。；，]{4,80}?(?:时|后))",
        r"(对于[^。；，]{4,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _extract_requirement_threshold(text: str) -> str | None:
    patterns = [
        r"(不超过[^。；，]{1,40})",
        r"(不小于[^。；，]{1,40})",
        r"(小于或等于[^。；，]{1,40})",
        r"(大于或等于[^。；，]{1,40})",
        r"(应符合[^。；，]{1,60})",
        r"(应满足[^。；，]{1,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    percent_match = re.search(r"(±?\s*\d+(?:\.\d+)?\s*%|±?\s*\d+(?:\.\d+)?\s*Hz|±?\s*\d+(?:\.\d+)?\s*s|±?\s*\d+(?:\.\d+)?\s*mA)", text)
    if percent_match:
        return percent_match.group(1).strip()
    return None


def _looks_like_procedure(text: str, current_heading: str, current_section: str | None) -> bool:
    heading = current_heading or ""
    if any(token in heading for token in ("前言", "规范性引用文件", "范围", "术语和定义", "要求", "检验规则", "标志、包装、运输和贮存")):
        return False
    if _looks_like_process_practice(text):
        return True
    if _looks_like_caption_or_note(text) or text.startswith("关键词") or _looks_like_reference_line(text):
        return False

    in_test_chapter = current_section == "5" or (current_section or "").startswith("5.")
    heading_is_test = any(token in heading for token in ("试验", "试验方法", "试验条件", "检查", "步骤"))
    action_like = any(token in text for token in ("按照", "测量", "施加", "连接", "进行试验", "检查", "测试", "记录", "固定", "调节", "使用"))

    if heading_is_test and action_like:
        return True
    if in_test_chapter and action_like:
        return True
    return False


def _looks_like_reference_line(text: str) -> bool:
    if re.match(r"^(GB/T|GB|ISO|IEC|QC/T|JB/T|SJ/T)\s*[\d.]+", text, re.I):
        return True
    return False


def _infer_table_title(blocks: list[dict[str, object]], index: int, current_heading: str) -> str | None:
    if index > 0:
        prev_text = str(blocks[index - 1].get("text") or "").strip()
        cleaned_prev = _clean_html_cell(prev_text)
        if "表" in cleaned_prev:
            return cleaned_prev
    return current_heading or None


def _extract_table_no(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"表\s*(\d+)", value)
    if match:
        return match.group(1)
    return None


def _parse_html_table(html_text: str) -> tuple[list[str], list[list[str]]]:
    html_text = unescape(html_text)
    row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.I | re.S)
    rows: list[list[str]] = []
    for row_html in row_matches:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
        cleaned_cells = [_clean_html_cell(cell) for cell in cells]
        if cleaned_cells:
            rows.append(cleaned_cells)
    if not rows:
        return [], []
    headers = rows[0]
    data_rows = rows[1:]
    return headers, data_rows


def _looks_like_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    if not lines[0].startswith("|"):
        return False
    separator_line = next((line for line in lines[1:3] if line.startswith("|")), "")
    return bool(re.search(r"\|\s*:?-{3,}", separator_line))


def _parse_markdown_table(markdown_text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in markdown_text.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|")]
    if len(table_lines) < 2:
        return [], []

    def split_row(row: str) -> list[str]:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        return [_clean_markdown_cell(cell) for cell in cells]

    header_row = split_row(table_lines[0])
    data_rows: list[list[str]] = []
    for row in table_lines[1:]:
        if re.fullmatch(r"\|?[\s:\-|]+\|?", row):
            continue
        parsed = split_row(row)
        if parsed:
            data_rows.append(parsed)
    return header_row, data_rows


def _clean_html_cell(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_markdown_cell(value: str) -> str:
    text = value.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("\\|", "|")
    text = _clean_html_cell(text)
    return text


def _strip_heading_marks(text: str) -> str:
    stripped = text.strip()
    return stripped.lstrip("#").strip()


def _extract_section_number(text: str) -> str | None:
    match = re.match(r"^(\d+(?:\.\d+){0,5})\b", text)
    return match.group(1) if match else None
