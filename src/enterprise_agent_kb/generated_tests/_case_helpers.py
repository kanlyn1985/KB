"""Pure helper functions for case construction and rendering.

Extracted from `generated_tests._impl` to isolate dependency-free
utilities (string normalization, JSON safety, regex helpers,
markdown stripping, identifier sanitization) from the test-case
orchestration logic.
"""
from __future__ import annotations

import html
import json
import re

def _count_by_key(items: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
def _strip_markdown_bold(text: str) -> str:
    stripped = re.sub(r"\*\*([^*]{1,300})\*\*", r"\1", text)
    stripped = re.sub(r"\*([^*]{1,100})\*", r"\1", stripped)
    return stripped.strip()
def _contains_locally(local_corpus: str, expected: str) -> bool:
    if not expected:
        return False
    return _normalize_compare(expected) in _normalize_compare(local_corpus)
def _unique_matches(pattern: str, text: str, *, flags: int = 0) -> list[str]:
    return _unique_values(match.group(0).strip() for match in re.finditer(pattern, text, flags))
def _unique_values(values) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped
def _strip_html(text: str) -> str:
    stripped = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    stripped = re.sub(r"<style.*?</style>", " ", stripped, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return html.unescape(stripped)
def _safe_json(value: object) -> object:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
def _normalize_compare(value: str) -> str:
    text = value.lower()
    text = text.replace("—", "-").replace("／", "/")
    text = re.sub(r"\s+", "", text)
    return text
def _safe_identifier(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "generated"
