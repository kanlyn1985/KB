"""Formatter: convert HandlerResult into human-readable Answer."""
from __future__ import annotations

from .types import Answer, HandlerResult, RouteResult


def format_answer(handler_result: HandlerResult, route: RouteResult) -> Answer:
    """Format a HandlerResult into a user-facing Answer."""

    data = handler_result.data
    data_type = handler_result.data_type
    source = handler_result.source
    query = handler_result.query
    category = route.category

    if data is None:
        display = _no_answer_text(category, query)
        return Answer(
            query=query, category=category,
            display=display, source=source,
            warnings=["No structured answer found"],
        )

    if data_type == "dict":
        display = _format_dict(data)
    elif data_type == "list":
        display = _format_list(data)
    elif data_type == "path_list":
        display = _format_path_list(data)
    elif data_type == "value":
        display = _format_value(data)
    else:
        display = str(data)

    return Answer(
        query=query,
        category=category,
        structured=data,
        display=display,
        source=source,
    )


def _format_dict(d: dict) -> str:
    if "term" in d or "canonical_name" in d:
        name = d.get("term") or d.get("canonical_name", "")
        zh = d.get("definition_zh", "") or ""
        en = d.get("definition_en", "") or ""
        parts = [name]
        if zh: parts.append(zh)
        if en: parts.append(en)
        return " — ".join(parts)

    if "value" in d and d["value"] is not None:
        val = str(d["value"])
        unit = str(d.get("unit", ""))
        return f"{val} {unit}".strip()

    return str(d)


def _format_list(items: list) -> str:
    if not items:
        return "No matching items found."
    lines: list[str] = []
    seen: set[tuple] = set()
    for item in items:
        if isinstance(item, dict):
            key = _dedup_key(item)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  • {_format_list_item(item)}")
        else:
            if item not in seen:
                seen.add((str(item),))
                lines.append(f"  • {item}")
    return "\n".join(lines)


def _dedup_key(item: dict) -> tuple:
    """Extract a deduplication key from a dict item.

    For typed attribute items ({type, name, value}), deduplicate by value.
    Same value with different alias names → keep only the first occurrence.
    """
    # Typed payload: {"type": "attribute", "name": "...", "value": "..."}
    if "type" in item and "name" in item:
        val = str(item.get("value") or "").strip()
        return (val,)  # dedup by value only
    # Raw attribute row: {"attribute_name": ..., "value_text": ...}
    name = (item.get("attribute_name") or "").strip()
    val = (item.get("value_text") or str(item.get("value_num", ""))).strip()
    return (name, val)


def _format_list_item(d: dict) -> str:
    """Render one attribute/term/typed dict as a compact line."""
    # Typed behavior payload: {"type": "term"/"attribute", "name": ..., "value": ...}
    if "type" in d and "name" in d:
        val = d.get("value")
        if d.get("type") == "term":
            zh = d.get("definition_zh") or ""
            en = d.get("definition_en") or ""
            parts = [d["name"]]
            if zh:
                parts.append(zh)
            if en:
                parts.append(en)
            return " — ".join(parts)
        if val is not None:
            return f"{d['name']} = {val}"
        return str(d["name"])
    # Raw attribute row: {"attribute_name": ..., "value_text": ..., "value_num": ...}
    name = d.get("attribute_name") or d.get("canonical_name") or ""
    if d.get("value_text"):
        return f"{name} = {d['value_text']}"
    if d.get("value_num") is not None:
        unit = d.get("value_unit") or ""
        return f"{name} = {d['value_num']} {unit}".strip()
    return str(name)


def _format_path_list(paths: list) -> str:
    if not paths:
        return "No reachable standards found."
    return "\n".join(f"  • {p}" for p in paths)


def _format_value(v: dict) -> str:
    """Format a single value dict."""
    if isinstance(v, dict):
        val = v.get("value") or v.get("text")
        unit = v.get("unit", "")
        if val is not None and unit:
            return f"{val} {unit}"
        if val is not None:
            return str(val)
    return str(v)


def _no_answer_text(category: str, query: str) -> str:
    return f"No structured answer available. Try rephrasing your question."
