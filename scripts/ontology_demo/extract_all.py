"""One-shot LLM extraction: extract ALL structured knowledge from a document.

Reads PDF raw text independently of the pipeline, uses a single LLM call
per document to extract entities, attributes, relations, terms, services,
and parameters. Stores everything in the ontology DB.

Usage:
    python scripts/ontology_demo/extract_all.py --doc-id DOC-000016
    python scripts/ontology_demo/extract_all.py --all
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider


_EXTRACT_SYSTEM_PROMPT = """\
You are a knowledge extraction expert for automotive engineering standards.
Read the document content and extract ALL structured knowledge.

Return a JSON object with these keys:

1. "entities": ALL standard/document identifiers found in the document,
   INCLUDING those only mentioned in normative references.
   [{"name": "GB/T 18487.4", "title_zh": "电动汽车传导充放电系统 第4部分", "title_en": "EV conductive charging system Part 4"}]
   IMPORTANT: Provide title_zh and title_en for EVERY entity.

2. "attributes": parameter values with standard number, parameter name, value, unit.
   For each parameter, provide MULTIPLE name variants.
   [{"entity": "GB/T 18487.4", "param": "额定交流电压", "aliases": ["交流电压", "额定电压", "输出电压"], "value": 250, "unit": "V", "min": 220, "max": 280}]
   IMPORTANT: Use Chinese parameter names whenever possible.
   IMPORTANT: Provide aliases — shorter or alternative names users might use to query this parameter.

3. "relations": which standards this document references (from normative references section).
   [{"src": "GB/T 18487.4", "relation": "references", "dst": "GB/T 18487.1"}]
   IMPORTANT: The 'dst' entity does NOT need to exist in the current document — it will be created automatically.
   [{"src": "GB/T 18487.4", "relation": "references", "dst": "GB/T 18487.1"}]

4. "terms": abbreviations and concepts. Each term may have a Chinese name AND an
   English name (both must be queryable). Put the Chinese term as "chinese",
   the English term as "english", and any abbreviation as "abbreviation".
   If there is a separate full English name (not just the abbreviation expansion),
   add it to "other_names". Example:
   [{"chinese": "保护门", "english": "shutter", "abbreviation": "", "other_names": [], "category": "component"}]
   [{"abbreviation": "V2L", "chinese": "车辆到负载", "english": "Vehicle-to-Load", "other_names": [], "category": "concept"}]
   IMPORTANT: Extract EVERY defined term in the terminology chapter, including
   bilingual pairs like "保护门 shutter", "激活信号 enable signal",
   "电压滞回功能 voltage hysteresis" — set chinese=保护门, english=shutter.

5. "services": UDS diagnostic services with hex codes.
   [{"entity": "ISO 14229-1", "name": "DiagnosticSessionControl", "hex": "0x10"}]

6. "params_dict": parameter name to value mappings (separate from attributes for broader coverage).
   [{"entity": "ISO 14229-3", "name": "P2_Server_Timing", "value": 50, "unit": "ms"}]

Rules:
- entity names MUST use consistent format: "GB/T XXXXX.X", "ISO XXXXX-X", "IEC XXXXX-X"
- Strip year suffixes from entity names (e.g. "GB/T 18487.4—2025" → "GB/T 18487.4")
- Extract ALL parameters, terms, and references — do not skip any
- For value fields, use numbers (not strings) when possible
- If a section does not apply, return an empty array

Return ONLY the JSON object, nothing else."""


def _call_llm_extract(text: str) -> dict[str, Any]:
    """Call LLM to extract all structured knowledge from document text."""
    import os as _os, time
    saved = {k: _os.environ.pop(k, None) for k in ("all_proxy", "ALL_PROXY")}

    for attempt in range(3):
        try:
            client = LLMClient(provider=Provider.CLAUDE, timeout=120.0, max_retries=1)
            response = client.chat(
                messages=[Message(role="user", content=text)],
                system_prompt=_EXTRACT_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=8000,
            )
            break
        except Exception:
            if attempt == 2:
                for k, v in saved.items():
                    if v is not None: _os.environ[k] = v
                return {}
            time.sleep(10)

    for k, v in saved.items():
        if v is not None: _os.environ[k] = v

    content = (response.content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _get_document_text(workspace_root: Path, doc_id: str) -> str:
    """Get raw text from document evidence."""
    db_path = AppPaths.from_root(workspace_root).db_file
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT page_no, raw_text FROM evidence "
            "WHERE doc_id = ? ORDER BY page_no",
            (doc_id,),
        ).fetchall()
        texts = [r[1] or "" for r in rows]
        return "\n".join(texts)
    finally:
        conn.close()


def _store_extracted(ont_conn: sqlite3.Connection, data: dict[str, Any], doc_id: str) -> dict[str, int]:
    """Store all extracted knowledge in the ontology DB."""
    from kb1_ontology.entity_manager import find_or_create_entity
    from kb1_ontology.attribute_store import set_attribute, VALUE_TYPE_NUMBER, VALUE_TYPE_STRING
    from kb1_ontology.class_registry import ensure_schema as ensure_cls, seed_core_classes

    ont_conn.row_factory = sqlite3.Row
    ensure_cls(ont_conn)
    seed_core_classes(ont_conn)

    from kb1_ontology.entity_manager.schema import ensure_schema as ensure_ent
    ensure_ent(ont_conn)

    from kb1_ontology.relation_registry.schema import ensure_schema as ensure_rel
    ensure_rel(ont_conn)

    from kb1_ontology.attribute_store.schema import ensure_schema as ensure_attr
    ensure_attr(ont_conn)

    stats = {"entities": 0, "attributes": 0, "relations": 0, "terms": 0, "services": 0, "params": 0, "terms_stored": 0, "params_stored": 0}

    # Store entities — also store title as attribute
    for e in data.get("entities", []):
        name = (e.get("name") or "").strip()
        if not name:
            continue
        try:
            ent, created = find_or_create_entity(ont_conn, name, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.commit()
            if created:
                stats["entities"] += 1
            # Store title as attribute so definition queries work
            title_zh = (e.get("title_zh") or "").strip()
            title_en = (e.get("title_en") or "").strip()
            if title_zh or title_en:
                title_text = f"{title_zh} / {title_en}" if title_zh and title_en else (title_zh or title_en)
                try:
                    set_attribute(ont_conn, "entity", ent.entity_id, "title",
                                  value_text=title_text, value_type=VALUE_TYPE_STRING)
                except Exception:
                    pass  # title may already exist
        except Exception as ex:
            print(f"    entity fail: {name}: {ex}")
            ont_conn.rollback()

    # Store attributes — also store aliases for better searchability
    for a in data.get("attributes", []):
        entity_name = (a.get("entity") or "").strip()
        param_name = (a.get("param") or "").strip()
        if not entity_name or not param_name:
            continue
        try:
            ent, _ = find_or_create_entity(ont_conn, entity_name, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.commit()
            value = a.get("value")
            unit = (a.get("unit") or "").strip()
            text = f"{value} {unit}".strip() if value is not None else None
            set_attribute(ont_conn, "entity", ent.entity_id, param_name,
                          value_text=text, value_type=VALUE_TYPE_NUMBER)
            stats["attributes"] += 1

            # Store parameter aliases for fuzzy matching
            aliases = a.get("aliases", [])
            for alias in aliases:
                if alias and alias != param_name:
                    try:
                        ont_conn.execute(
                            "INSERT OR IGNORE INTO param_alias (param_id, alias, alias_type) "
                            "SELECT param_id, ?, 'chinese' FROM param WHERE canonical_name = ?",
                            (alias, param_name)
                        )
                    except Exception:
                        pass  # may not exist in param table yet
        except Exception as ex:
            print(f"    attr fail: {entity_name}.{param_name}: {ex}")
            ont_conn.rollback()

    # Store relations — also create entities for targets
    for r in data.get("relations", []):
        src_name = (r.get("src") or "").strip()
        dst_name = (r.get("dst") or "").strip()
        if not src_name or not dst_name:
            continue
        try:
            src, _ = find_or_create_entity(ont_conn, src_name, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.commit()
            # Also create destination entity so reference/traversal queries work
            dst, dst_created = find_or_create_entity(ont_conn, dst_name, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.commit()
            if dst_created:
                stats["entities"] += 1
                # If no title exists, set a minimal one from the standard number
                existing = ont_conn.execute(
                    "SELECT 1 FROM attribute WHERE subject_kind='entity' AND subject_id=? AND attribute_name='title'",
                    (dst.entity_id,),
                ).fetchone()
                if not existing:
                    try:
                        set_attribute(ont_conn, "entity", dst.entity_id, "title",
                                      value_text=dst_name, value_type=VALUE_TYPE_STRING)
                    except Exception:
                        pass
            ont_conn.execute(
                "INSERT OR IGNORE INTO relation (relation_name, src_kind, src_id, dst_kind, dst_id, domain, confidence, created_at) VALUES ('references', 'entity', ?, 'entity', ?, 'OBC', 0.9, ?)",
                (src.entity_id, dst.entity_id, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            stats["relations"] += 1
        except Exception as ex:
            print(f"    rel fail: {src_name}->{dst_name}: {ex}")
            ont_conn.rollback()

    # Store terms — idempotent on canonical_name (case-insensitive).
    # canonical_name = abbreviation if present, else chinese name.
    # Both chinese and english names become queryable aliases.
    for t in data.get("terms", []):
        abbr = (t.get("abbreviation") or "").strip()
        zh = (t.get("chinese") or "").strip()
        en = (t.get("english") or "").strip()
        other_names = [n.strip() for n in (t.get("other_names") or []) if n and n.strip()]
        cat = (t.get("category") or "concept").strip()
        if cat not in ("concept", "component", "protocol", "process"):
            cat = "concept"
        canonical = abbr or zh or en
        if not canonical:
            continue
        stats["terms"] += 1
        try:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            # Find existing term by any of its names (case-insensitive)
            names = [n for n in [canonical, zh, en, *other_names] if n]
            placeholders = ",".join("LOWER(?)" for _ in names)
            existing = ont_conn.execute(
                f"SELECT t.term_id, t.definition_zh, t.definition_en "
                f"FROM term t LEFT JOIN term_alias ta ON t.term_id = ta.term_id "
                f"WHERE LOWER(t.canonical_name) IN ({placeholders}) "
                f"OR LOWER(ta.alias) IN ({placeholders}) "
                f"LIMIT 1",
                (*names, *names),
            ).fetchone()
            if existing:
                tid = existing[0]
                ont_conn.execute(
                    "UPDATE term SET "
                    "definition_zh = COALESCE(definition_zh, ?), "
                    "definition_en = COALESCE(definition_en, ?) "
                    "WHERE term_id = ? AND (definition_zh IS NULL OR definition_en IS NULL)",
                    (zh or None, en or None, tid),
                )
            else:
                cur = ont_conn.execute("SELECT MAX(CAST(SUBSTR(term_id, 6) AS INTEGER)) FROM term")
                row = cur.fetchone()
                max_id = row[0] if row and row[0] else 0
                tid = f"TERM-{max_id + 1:04d}"
                ont_conn.execute(
                    "INSERT INTO term (term_id, canonical_name, category, definition_zh, definition_en, source_standard, confidence, extracted_at, verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tid, canonical, cat, zh or None, en or None, doc_id, 0.9, now, 1, now),
                )
                stats["terms_stored"] += 1
            # Register every name as a queryable alias
            alias_pairs = []
            if abbr:
                alias_pairs.append((abbr, "abbreviation"))
            if zh:
                alias_pairs.append((zh, "chinese"))
            if en:
                alias_pairs.append((en, "english"))
            for nm in other_names:
                alias_pairs.append((nm, "other"))
            for alias, atype in alias_pairs:
                ont_conn.execute(
                    "INSERT OR IGNORE INTO term_alias (term_id, alias, alias_type) VALUES (?, ?, ?)",
                    (tid, alias, atype),
                )
        except Exception as ex:
            print(f"    term fail: {canonical}: {ex}")
            ont_conn.rollback()

    # Store services
    for s in data.get("services", []):
        entity_name = (s.get("entity") or "").strip()
        svc_name = (s.get("name") or "").strip()
        svc_hex = (s.get("hex") or "").strip()
        if not entity_name or not svc_name:
            continue
        try:
            ent, _ = find_or_create_entity(ont_conn, entity_name, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.commit()
            set_attribute(ont_conn, "entity", ent.entity_id, f"service_{svc_name}",
                          value_text=svc_hex, value_type=VALUE_TYPE_STRING)
            stats["services"] += 1
        except Exception:
            ont_conn.rollback()

    # Store params dict — idempotent on canonical_name (case-insensitive)
    for p in data.get("params_dict", []):
        entity_name = (p.get("entity") or "").strip()
        name = (p.get("name") or "").strip()
        value = p.get("value")
        unit = (p.get("unit") or "").strip()
        if not entity_name or not name:
            continue
        stats["params"] += 1
        try:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            existing = ont_conn.execute(
                "SELECT param_id FROM param WHERE LOWER(canonical_name) = LOWER(?)",
                (name,),
            ).fetchone()
            if existing:
                # Backfill value if missing
                ont_conn.execute(
                    "UPDATE param SET value_num = COALESCE(value_num, ?), "
                    "value_unit = COALESCE(value_unit, ?) WHERE param_id = ? AND value_num IS NULL",
                    (float(value) if value is not None else None, unit or None, existing[0]),
                )
            else:
                cur = ont_conn.execute("SELECT MAX(CAST(SUBSTR(param_id, 7) AS INTEGER)) FROM param")
                row = cur.fetchone()
                max_id = row[0] if row and row[0] else 0
                pid = f"PARAM-{max_id + 1:04d}"
                ont_conn.execute(
                    "INSERT INTO param (param_id, canonical_name, value_num, value_unit, source_standard, confidence, extracted_at, verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, name, float(value) if value is not None else None, unit or None, doc_id, 0.9, now, 1, now),
                )
                stats["params_stored"] += 1
        except Exception:
            ont_conn.rollback()

    ont_conn.commit()
    return stats


def _chunk_text(text: str, max_chars: int = 8000) -> list[str]:
    """Split text into page-boundary-aware chunks that fit LLM context.

    No artificial chunk count cap — long documents must be read in full,
    otherwise terminology/reference chapters (often near the front) and
    later sections are silently skipped.
    """
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        # Prefer breaking at a paragraph boundary near the limit
        if end < n:
            break_point = text.rfind("\n\n", start + max_chars // 2, end)
            if break_point > start:
                end = break_point
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end <= start:  # safety against infinite loop
            end = start + 1
        start = end
    return chunks


def extract_document(workspace_root: Path, ontology_db_path: Path, doc_id: str) -> dict[str, Any]:
    """Extract all structured knowledge from one document, processing in chunks."""
    print(f"Reading: {doc_id}")
    text = _get_document_text(workspace_root, doc_id)

    if not text:
        return {"doc_id": doc_id, "error": "No text"}

    print(f"  Text: {len(text)} chars")

    chunks = _chunk_text(text, max_chars=8000)
    print(f"  Chunks: {len(chunks)} ({sum(len(c) for c in chunks)} chars total)")

    all_data: dict[str, list] = {
        "entities": [], "attributes": [], "relations": [],
        "terms": [], "services": [], "params_dict": [],
    }

    seen_entities: set = set()
    seen_terms: set = set()

    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...", end=" ", flush=True)
        data = _call_llm_extract(chunk)
        if data:
            n = sum(len(data.get(k, [])) for k in all_data)
            print(f"got {n} items")
            for key in all_data:
                items = data.get(key, [])
                if key == "entities":
                    items = [e for e in items if e.get("name") not in seen_entities]
                    seen_entities.update(e.get("name", "") for e in items)
                elif key == "terms":
                    items = [t for t in items if t.get("abbreviation") not in seen_terms]
                    seen_terms.update(t.get("abbreviation", "") for t in items)
                all_data[key].extend(items)
        else:
            print("empty")
            continue

    # Show summary
    for key in all_data:
        if all_data[key]:
            print(f"  Total {key}: {len(all_data[key])}")

    # Store
    ont_conn = sqlite3.connect(str(ontology_db_path))
    stats = _store_extracted(ont_conn, all_data, doc_id)
    ont_conn.close()

    print(f"  Stored: entities={stats['entities']} attrs={stats['attributes']} rels={stats['relations']} terms={stats['terms_stored']} svcs={stats['services']} params={stats['params_stored']}")
    return {"doc_id": doc_id, **stats}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", help="Single document ID")
    parser.add_argument("--all", action="store_true", help="All documents")
    parser.add_argument("--workspace", default="knowledge_base")
    args = parser.parse_args()

    workspace = ROOT / args.workspace
    ontology_db = workspace / "ontology" / "ontology.db"

    if args.all:
        db_path = AppPaths.from_root(workspace).db_file
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        docs = conn.execute("SELECT doc_id FROM documents WHERE parse_status = 'parsed' ORDER BY doc_id").fetchall()
        conn.close()

        total = {"entities": 0, "attributes": 0, "relations": 0, "terms_stored": 0, "services": 0, "params_stored": 0}
        for doc in docs:
            r = extract_document(workspace, ontology_db, doc["doc_id"])
            for k in total:
                total[k] += r.get(k, 0)

        print(f"\n{'='*50}")
        print(f"Total stored: {total}")
    elif args.doc_id:
        r = extract_document(workspace, ontology_db, args.doc_id)
        print(r)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
