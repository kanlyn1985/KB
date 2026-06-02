"""Term/definition extraction.

Extracted from `facts._impl` to isolate the term-definition,
inline-heading, bilingual, numeric, and abstract-concept extraction
from the cover/metadata and process concerns.
"""
from __future__ import annotations

import re

from ._extract_cover import _clean_text, _normalize_ocr_text
from ._extract_process import (
    _extract_process_attribute_scope_definitions,
    _extract_process_group_definitions,
)


def _extract_term_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    from ._fact_payloads import _definition_has_publishable_signal  # local import: avoids cycle
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
def _extract_markdown_bilingual_terms(
    text: str,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, object]]]:
    from ._fact_payloads import _definition_has_publishable_signal  # local import: avoids cycle
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
    from ._fact_payloads import _definition_has_publishable_signal  # local import: avoids cycle
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

    abstract_match = re.search(r"(?:摘\s*要|概\s*述|范\s*围|Abstract|Scope)\s*(.+)", normalized, re.S | re.I)
    if abstract_match:
        abstract_text = _clean_text(abstract_match.group(1))
        if len(abstract_text) > 40:
            results.append(
                (
                    "document_abstract",
                    "has_abstract",
                    {"value": abstract_text[:1200]},
                )
            )

    # Standards often use 前言/Foreword instead of Abstract — extract the first
    # paragraph after the heading as a summary substitute.
    if not any(r[1] == "has_abstract" for r in results):
        foreword_match = re.search(
            r"(?:^|\n)\s*#{0,3}\s*(?:前\s*言|Foreword|Introduction)\s*\n(.+?)(?:\n\s*\n|\n#{1,3}\s)",
            normalized,
            re.S | re.I,
        )
        if foreword_match:
            abstract_text = _clean_text(foreword_match.group(1))
            if len(abstract_text) > 40:
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

    candidate_rows = [row for row in rows if row["page_no"] <= 10]
    combined_text = "\n".join(str(row["normalized_text"] or "") for row in candidate_rows)
    extracted = _extract_abstract_concepts(combined_text)
    if not extracted:
        return []

    anchor_row = candidate_rows[0]
    return [(anchor_row, item) for item in extracted]
