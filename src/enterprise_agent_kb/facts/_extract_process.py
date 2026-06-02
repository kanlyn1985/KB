"""Process extraction: attribute scopes, groups, and type relations.

Extracted from `facts._impl` to isolate the process-attribute,
process-group, and entity-type-relation extraction from the
cover, term, and fact-payload concerns.
"""
from __future__ import annotations

import re

from ._extract_cover import _clean_text, _normalize_ocr_text

def _extract_process_attribute_scope_definitions(text: str) -> list[tuple[str, str, dict[str, object]]]:
    from ._fact_payloads import (  # local import: avoids import cycle
        _clean_definition_term,
        _definition_fact_type_for_term,
        _definition_predicate_for_term,
        _is_publishable_definition_entry,
    )
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
    from ._fact_payloads import (  # local import: avoids import cycle
        _clean_definition_term,
        _is_publishable_definition_entry,
    )
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
