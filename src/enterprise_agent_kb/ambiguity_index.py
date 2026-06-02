from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .logging_config import get_logger

_logger = get_logger(__name__)


@dataclass
class Sense:
    label: str
    entity_id: str
    fact_ids: list[str]
    context_terms: list[str]
    example_query: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])")
_TERM_SEMICOLON_ACRONYM_RE = re.compile(r";\s*([A-Z]{2,6})\s*$")
_PAREN_ACRONYM_RE = re.compile(r"[（(]\s*([A-Z]{2,6})\s*[)）]")


def build_ambiguity_index(connection: sqlite3.Connection) -> dict[str, list[Sense]]:
    senses: dict[str, list[Sense]] = {}
    _index_from_term_definitions(connection, senses)
    _index_from_entities(connection, senses)
    _deduplicate(senses)
    return senses


def save_ambiguity_index(index: dict[str, list[Sense]], path: str | Path) -> None:
    data = {
        acronym: [s.to_dict() for s in sense_list]
        for acronym, sense_list in index.items()
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_ambiguity_index(path: str | Path) -> dict[str, list[Sense]]:
    p = Path(path)
    if not p.exists():
        _logger.warning("ambiguity index file not found at %s; proceeding without disambiguation", p)
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    index: dict[str, list[Sense]] = {}
    for acronym, sense_dicts in data.items():
        index[acronym] = [
            Sense(
                label=s.get("label", ""),
                entity_id=s.get("entity_id", ""),
                fact_ids=s.get("fact_ids", []),
                context_terms=s.get("context_terms", []),
                example_query=s.get("example_query", ""),
                confidence=s.get("confidence", 0.0),
            )
            for s in sense_dicts
        ]
    return index


def _index_from_term_definitions(connection: sqlite3.Connection, senses: dict[str, list[Sense]]) -> None:
    rows = connection.execute(
        "SELECT fact_id, object_value, source_doc_id FROM facts "
        "WHERE fact_type IN ('term_definition', 'concept_definition')"
    ).fetchall()

    for fact_id, object_value, doc_id in rows:
        if not object_value:
            continue
        try:
            d = json.loads(object_value) if isinstance(object_value, str) else object_value
        except (json.JSONDecodeError, TypeError):
            continue
        term = str(d.get("term", "")).strip()
        definition = str(d.get("definition", "")).strip()
        if not term:
            continue

        acronym = _extract_acronym_from_term(term)
        if not acronym:
            acronym = _extract_acronym_from_paren(definition)
        if not acronym:
            continue

        clean_label = re.sub(r"\s*[;；]\s*[A-Z]{2,6}\s*$", "", term).strip()
        clean_label = re.sub(r"\s*\*+\s*", "", clean_label).strip()
        if not clean_label:
            clean_label = term

        context = _extract_context_terms(term, definition)
        example = f"{clean_label}是什么意思"

        sense = Sense(
            label=clean_label,
            entity_id="",
            fact_ids=[fact_id],
            context_terms=context,
            example_query=example,
            confidence=0.9,
        )
        senses.setdefault(acronym, []).append(sense)


def _index_from_entities(connection: sqlite3.Connection, senses: dict[str, list[Sense]]) -> None:
    rows = connection.execute(
        "SELECT entity_id, canonical_name, entity_type, alias_json, description FROM entities"
    ).fetchall()

    for entity_id, canonical_name, entity_type, alias_json, description in rows:
        if not canonical_name:
            continue
        names_to_check = [canonical_name]
        if alias_json:
            try:
                aliases = json.loads(alias_json) if isinstance(alias_json, str) else alias_json
            except (json.JSONDecodeError, TypeError):
                aliases = []
            names_to_check.extend(str(a) for a in (aliases or []))

        for name in names_to_check:
            m = re.match(r"^([A-Z]{2,6})$", name.strip())
            if not m:
                continue
            acronym = m.group(1)
            if acronym in senses:
                for s in senses[acronym]:
                    if not s.entity_id:
                        s.entity_id = entity_id
            else:
                clean_label = canonical_name
                context = _extract_context_terms(canonical_name, description or "")
                sense = Sense(
                    label=clean_label,
                    entity_id=entity_id,
                    fact_ids=[],
                    context_terms=context,
                    example_query=f"{clean_label}是什么意思",
                    confidence=0.7,
                )
                senses.setdefault(acronym, []).append(sense)


def _extract_acronym_from_term(term: str) -> str | None:
    m = _TERM_SEMICOLON_ACRONYM_RE.search(term)
    if m:
        return m.group(1)
    return None


def _extract_acronym_from_paren(definition: str) -> str | None:
    m = _PAREN_ACRONYM_RE.search(definition)
    if m:
        return m.group(1)
    return None


def _extract_context_terms(term: str, definition: str) -> list[str]:
    text = f"{term} {definition}"
    cjk_words = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    return list(dict.fromkeys(cjk_words))[:10]


def _deduplicate(senses: dict[str, list[Sense]]) -> None:
    for acronym in list(senses):
        seen_labels: set[str] = set()
        unique: list[Sense] = []
        for s in senses[acronym]:
            normalized = re.sub(r"\s+", "", s.label.lower())
            if normalized not in seen_labels:
                seen_labels.add(normalized)
                unique.append(s)
        senses[acronym] = unique
        if len(senses[acronym]) <= 1:
            del senses[acronym]
