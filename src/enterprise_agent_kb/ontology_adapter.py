"""Ontology shadow / guard adapter (Sprint 2 WP3/WP4).

A minimal, read-only bridge from the ``kb1_ontology`` system into the main
``enterprise_agent_kb`` query/answer pipeline.

Hard constraints (see .codestable/features/2026-06-25-ontology-shadow-guard-adapter):
  * The ontology is a CONSTRAINT / VALIDATION / RECALL-AID layer only.
  * It MUST NOT generate facts, rewrite answer text, bypass
    ``evidence_judge``, or act as a source of truth.
  * Adapter outputs are named ``signal`` / ``constraint`` / ``check`` /
    ``validation`` — never ``evidence`` / ``fact`` / ``source_truth``.
  * ``changed_retrieval`` and ``changed_answer`` are ALWAYS ``False`` in
    Sprint 2.
  * No LLM calls. Entity detection is rule/lookup based against the
    ontology DB only.

Mode selection: environment variable ``KB1_ONTOLOGY_MODE`` ∈ {off, shadow,
guard} (default ``off``). ``off`` short-circuits with an empty signal and
zero overhead.
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

OntologyMode = Literal["off", "shadow", "guard"]

DEFAULT_MODE: OntologyMode = "off"
_MODE_ENV = "KB1_ONTOLOGY_MODE"
_VALID_MODES = {"off", "shadow", "guard"}


def get_ontology_mode(env: dict[str, str] | None = None) -> OntologyMode:
    """Read the active ontology mode from the environment (default off)."""
    raw = (env or os.environ).get(_MODE_ENV, DEFAULT_MODE)
    value = str(raw or "").strip().lower()
    if value not in _VALID_MODES:
        return DEFAULT_MODE
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class EntityConstraint:
    """A mention in the query mapped to an ontology class."""

    mention: str
    class_id: str | None
    class_name: str | None
    confidence: float


@dataclass(frozen=True)
class RelationCheck:
    """Whether a relation between query entities is consistent."""

    relation: str
    status: str  # "consistent" | "unknown" | "conflict"
    note: str


@dataclass(frozen=True)
class AnswerPostCheck:
    """A consistency warning produced in guard mode (never mutates the answer)."""

    type: str
    severity: str  # "info" | "warning"
    message: str


@dataclass(frozen=True)
class OntologySignal:
    """Read-only ontology signals attached to a query / answer context.

    ``changed_retrieval`` and ``changed_answer`` are intentionally always
    ``False`` in Sprint 2: the adapter observes and reports, it never mutates
    retrieval ordering, candidate sets, or the final answer.
    """

    mode: OntologyMode
    query_entities: list[EntityConstraint] = field(default_factory=list)
    relation_checks: list[RelationCheck] = field(default_factory=list)
    post_checks: list[AnswerPostCheck] = field(default_factory=list)
    changed_retrieval: bool = False
    changed_answer: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "query_entities": [
                {
                    "mention": e.mention,
                    "class_id": e.class_id,
                    "class_name": e.class_name,
                    "confidence": e.confidence,
                }
                for e in self.query_entities
            ],
            "relation_checks": [
                {"relation": r.relation, "status": r.status, "note": r.note}
                for r in self.relation_checks
            ],
            "post_checks": [
                {"type": p.type, "severity": p.severity, "message": p.message}
                for p in self.post_checks
            ],
            "changed_retrieval": self.changed_retrieval,
            "changed_answer": self.changed_answer,
            "errors": list(self.errors),
        }


def _ontology_db_path(workspace_root: Path) -> Path:
    return workspace_root / "ontology" / "ontology.db"


def _load_entity_index(connection: sqlite3.Connection) -> list[tuple[str, str | None, str | None, float]]:
    """Load (name, class_id, class_name, confidence) lookup rows from the ontology DB.

    Each canonical name / alias becomes a matchable surface. Canonical names
    score higher than aliases.
    """
    rows: list[tuple[str, str | None, str | None, float]] = []
    class_name_by_id: dict[str, str] = {}
    try:
        for row in connection.execute("SELECT class_id, class_name FROM class_def").fetchall():
            class_name_by_id[str(row["class_id"])] = str(row["class_name"])
    except sqlite3.DatabaseError:
        pass

    def _add(name: str, class_id: str | None, confidence: float) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        rows.append((cleaned, class_id, class_name_by_id.get(class_id) if class_id else None, confidence))

    try:
        for row in connection.execute(
            "SELECT canonical_name, class_id FROM entity"
        ).fetchall():
            _add(str(row["canonical_name"]), str(row["class_id"] or "") or None, 0.95)
    except sqlite3.DatabaseError:
        pass
    try:
        for row in connection.execute(
            "SELECT canonical_name, aliases_json, class_id FROM term"
        ).fetchall():
            _add(str(row["canonical_name"]), str(row["class_id"] or "") or None, 0.9)
            aliases = _parse_aliases(str(row["aliases_json"] or ""))
            for alias in aliases:
                _add(alias, str(row["class_id"] or "") or None, 0.7)
    except sqlite3.DatabaseError:
        pass
    # Also load entity aliases_json for broader recall.
    try:
        for row in connection.execute("SELECT canonical_name, aliases_json, class_id FROM entity").fetchall():
            aliases = _parse_aliases(str(row["aliases_json"] or ""))
            for alias in aliases:
                _add(alias, str(row["class_id"] or "") or None, 0.7)
    except sqlite3.DatabaseError:
        pass
    return rows


def _parse_aliases(aliases_json: str) -> list[str]:
    import json

    if not aliases_json or aliases_json == "[]":
        return []
    try:
        data = json.loads(aliases_json)
    except (ValueError, TypeError):
        return []
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    return []


def _detect_entities(
    query: str, index: list[tuple[str, str | None, str | None, float]]
) -> list[EntityConstraint]:
    """Match query text against the ontology entity/term index (rule-based, no LLM)."""
    query_norm = query
    # Build a case-insensitive lookup keyed by surface name.
    seen_mentions: set[str] = set()
    constraints: list[EntityConstraint] = []
    # Prefer longer / higher-confidence surfaces first.
    ordered = sorted(index, key=lambda row: (-len(row[0]), -row[3]))
    for surface, class_id, class_name, confidence in ordered:
        if len(surface) < 2:
            continue
        if re.search(re.escape(surface), query_norm, re.IGNORECASE):
            key = surface.lower()
            if key in seen_mentions:
                continue
            seen_mentions.add(key)
            constraints.append(
                EntityConstraint(
                    mention=surface,
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                )
            )
    # Deduplicate nested surfaces: drop a mention that is a strict substring
    # of a longer mention sharing the same class (e.g. 'ISO 14229-1' supersedes
    # 'ISO 14229' and 'ISO'). Keeps the most specific entity mention.
    deduped: list[EntityConstraint] = []
    for ent in constraints:
        nested = False
        for other in constraints:
            if other is ent:
                continue
            if other.class_id != ent.class_id:
                continue
            if ent.mention.lower() in other.mention.lower() and len(other.mention) > len(ent.mention):
                nested = True
                break
        if not nested:
            deduped.append(ent)
    return deduped[:12]


def _relation_checks_for(
    connection: sqlite3.Connection, entities: list[EntityConstraint]
) -> list[RelationCheck]:
    """Inspect known relations among the detected entities (read-only).

    No OWL/RDF reasoning — only reports whether a known relation exists
    between the mentioned entity classes.
    """
    if not entities:
        return []
    class_ids = {e.class_id for e in entities if e.class_id}
    if len(class_ids) < 2:
        return []
    relation_names: list[str] = []
    try:
        for row in connection.execute("SELECT relation_name FROM relation_def").fetchall():
            relation_names.append(str(row["relation_name"]))
    except sqlite3.DatabaseError:
        relation_names = []
    checks: list[RelationCheck] = []
    # Look for any stored relation whose endpoints fall within the detected classes.
    try:
        placeholders = ",".join("?" for _ in class_ids)
        params: list[object] = list(class_ids)
        rows = connection.execute(
            f"""
            SELECT r.relation_name AS relation_name, COUNT(*) AS n
            FROM relation r
            JOIN entity e1 ON e1.entity_id = r.source_entity_id
            JOIN entity e2 ON e2.entity_id = r.target_entity_id
            WHERE e1.class_id IN ({placeholders}) AND e2.class_id IN ({placeholders})
            GROUP BY r.relation_name
            """,
            (*params, *params),
        ).fetchall()
        found = {str(row["relation_name"]): int(row["n"]) for row in rows}
    except sqlite3.DatabaseError:
        found = {}
    for name in relation_names:
        n = found.get(name, 0)
        checks.append(
            RelationCheck(
                relation=name,
                status="consistent" if n else "unknown",
                note=f"{n} stored instance(s) among detected entities" if n else "no stored instance among detected entities",
            )
        )
    return checks


def analyze(
    query: str,
    workspace_root: Path,
    mode: OntologyMode | None = None,
) -> OntologySignal:
    """Produce a read-only ontology signal for ``query``.

    Never raises: any DB / schema problem is captured in ``signal.errors``
    and an empty signal is returned so the main pipeline is never blocked.
    """
    active_mode = mode if mode is not None else get_ontology_mode()
    if active_mode == "off" or not query:
        return OntologySignal(mode=active_mode)

    db_path = _ontology_db_path(workspace_root)
    if not db_path.exists():
        return OntologySignal(mode=active_mode, errors=[f"ontology db not found: {db_path}"])

    errors: list[str] = []
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return OntologySignal(mode=active_mode, errors=[f"ontology db open failed: {exc}"])

    try:
        index = _load_entity_index(connection)
        entities = _detect_entities(query, index)
        relation_checks = _relation_checks_for(connection, entities)
    except sqlite3.Error as exc:
        errors.append(f"ontology read failed: {exc}")
        entities = []
        relation_checks = []
    finally:
        connection.close()

    return OntologySignal(
        mode=active_mode,
        query_entities=entities,
        relation_checks=relation_checks,
        errors=errors,
    )


def post_check(
    query: str,
    direct_answer: str,
    signal: OntologySignal,
    workspace_root: Path | None = None,
) -> list[AnswerPostCheck]:
    """Guard-mode consistency audit of a generated answer (WP4).

    Returns warnings only; it MUST NOT mutate the answer. ``changed_answer``
    stays ``False``. An answer that mentions an ontology entity which has no
    known relation to any query entity is flagged as a soft warning.

    ``workspace_root`` (optional) lets the audit detect entities in the
    answer text against the full ontology index. When omitted, only entities
    already present in ``signal.query_entities`` are considered.
    """
    if not direct_answer or signal.mode == "off":
        return []
    checks: list[AnswerPostCheck] = []
    query_entity_classes = {e.class_id for e in signal.query_entities if e.class_id}
    query_mentions = {e.mention.lower() for e in signal.query_entities}
    if not query_entity_classes:
        return []
    # Detect entities in the answer text. Prefer the full ontology index when a
    # workspace is available; otherwise fall back to the signal's entities.
    answer_index: list[tuple[str, str | None, str | None, float]]
    if workspace_root is not None:
        db_path = _ontology_db_path(workspace_root)
        if db_path.exists():
            try:
                connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                connection.row_factory = sqlite3.Row
                try:
                    answer_index = _load_entity_index(connection)
                finally:
                    connection.close()
            except sqlite3.Error:
                answer_index = _entity_index_from_signal(signal)
        else:
            answer_index = _entity_index_from_signal(signal)
    else:
        answer_index = _entity_index_from_signal(signal)
    answer_entities = _detect_entities(direct_answer, answer_index)
    if not answer_entities:
        return []
    # Flag answer entities whose class is not among the query's detected classes
    # and which were not also detected in the query.
    for ent in answer_entities:
        if ent.mention.lower() in query_mentions:
            continue
        if ent.class_id in query_entity_classes:
            continue
        checks.append(
            AnswerPostCheck(
                type="ontology_entity_not_in_query_scope",
                severity="warning",
                message=(
                    f"Answer mentions '{ent.mention}' (class {ent.class_name or ent.class_id}) "
                    "which was not part of the detected query entities; verify it is "
                    "supported by evidence rather than an unrelated ontology association."
                ),
            )
        )
    return checks


def _entity_index_from_signal(signal: OntologySignal) -> list[tuple[str, str | None, str | None, float]]:
    return [
        (e.mention, e.class_id, e.class_name, e.confidence)
        for e in signal.query_entities
    ]


# ── Sprint 3 WP5: shadow A/B projected retrieval filtering ──────────────


def project_retrieval_filtering(
    query: str,
    candidates: list[dict[str, object]],
    workspace_root: Path,
) -> dict[str, object]:
    """Project which retrieval candidates ontology type constraints WOULD filter.

    Sprint 3 WP5 shadow A/B. This NEVER actually filters — it only records what
    *would* be dropped if entity-type-mismatch filtering were enabled, so an A/B
    report can measure ``evidence_loss_rate`` and ``false_positive_filter_cases``
    before any decision to guard-ize in Sprint 4.

    A candidate is *projected-filtered* only when:
      1. The query has at least one entity with a known class, AND
      2. The candidate text mentions an ontology entity of a DIFFERENT class, AND
      3. The candidate text does NOT mention any entity of the query's class.

    This is conservative: a candidate is dropped only when it is *exclusively*
    about a different-class entity, never when it also mentions the query class.
    It can never delete the only evidence because it only flags candidates that
    are about a different class entirely.
    """
    result: dict[str, object] = {
        "enabled": False,
        "query_class_ids": [],
        "candidates_total": len(candidates),
        "candidates_would_drop": [],
        "evidence_loss_cases": [],
        "false_positive_filter_cases": [],
        "safe_filter_candidates": [],
        "reason": "",
    }
    if not candidates:
        result["reason"] = "no_candidates"
        return result

    signal = analyze(query, workspace_root, mode="shadow")
    query_class_ids = {
        e.class_id for e in signal.query_entities if e.class_id
    }
    result["query_class_ids"] = sorted(query_class_ids)

    # If the query has no entity class, or the ontology has only one class
    # (no class diversity), projected filtering cannot help — nothing is dropped.
    if not query_class_ids:
        result["reason"] = "query_has_no_known_entity_class"
        return result

    # Load the full entity index to detect which entities each candidate mentions.
    db_path = _ontology_db_path(workspace_root)
    if not db_path.exists():
        result["reason"] = f"ontology db not found: {db_path}"
        return result
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        index = _load_entity_index(connection)
        connection.close()
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        result["reason"] = f"ontology read failed: {exc}"
        return result

    # Group entity surfaces by class.
    surfaces_by_class: dict[str | None, list[str]] = {}
    for surface, class_id, _class_name, _confidence in index:
        if len(surface) < 2:
            continue
        surfaces_by_class.setdefault(class_id, []).append(surface)
    distinct_classes = {c for c in surfaces_by_class if c is not None}
    if len(distinct_classes) <= 1:
        # Single-class ontology: type-mismatch filtering is structurally a no-op.
        result["reason"] = (
            "single_class_ontology_no_diversity: type-mismatch filtering cannot "
            "distinguish candidates when all entities share one class"
        )
        return result

    result["enabled"] = True
    query_surfaces = set()
    for cid in query_class_ids:
        for s in surfaces_by_class.get(cid, []):
            query_surfaces.add(s.lower())

    for cand in candidates:
        cid = cand.get("evidence_id") or cand.get("fact_id") or cand.get("id") or "?"
        text = str(
            cand.get("snippet")
            or cand.get("normalized_text")
            or cand.get("text")
            or cand.get("object_value")
            or ""
        )
        text_low = text.lower()
        mentions_query_class = any(s in text_low for s in query_surfaces)
        mentions_other_class = False
        for other_cid, surfaces in surfaces_by_class.items():
            if other_cid in query_class_ids or other_cid is None:
                continue
            if any(s.lower() in text_low for s in surfaces):
                mentions_other_class = True
                break
        if mentions_other_class and not mentions_query_class:
            drop = {"id": cid, "reason": "type_mismatch_other_class_only"}
            result["candidates_would_drop"].append(drop)
            result["safe_filter_candidates"].append(cid)
        else:
            result["evidence_loss_cases"].append(cid) if (
                mentions_query_class is False and mentions_other_class is False
            ) else None
    result["reason"] = "projected"
    return result
