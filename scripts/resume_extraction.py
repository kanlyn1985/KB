#!/usr/bin/env python3
"""Resume ontology extraction for remaining documents (DOC-000006 onwards).

Usage:
  .venv-paddle/bin/python scripts/resume_extraction.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for k in ("all_proxy", "ALL_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(k, None)


_EXTRACT_PROMPT = """\
You are a knowledge extraction expert for automotive engineering standards.
Read this document section and extract structured knowledge.

Return a JSON object with:

1. "attributes": parameter values found in this section.
   [{"entity": "GB/T 18487.1", "param": "额定交流电压", "aliases": ["交流电压"],
     "value": 220, "unit": "V"}]

2. "relations": standards referenced in this section ONLY if both endpoints
   are real standard codes (GB/T x, ISO x, IEC x, NB/T x, DL/T x, QC/T x,
   SAE x, IEEE x) or real product names (V2G, CCU, OBC, AutomotiveSPICE,
   AUTOSAR). Never use section headings as entities.
   [{"src": "GB/T 18487.1", "relation": "references", "dst": "GB 50057"}]
   Allowed relations: "references", "is-a", "part-of", "implements", "depends-on"

3. "params_dict": parameter name→value mappings.
   [{"entity": "ISO 14229-3", "name": "P2_Server_Timing", "value": 50, "unit": "ms"}]

4. "terms": abbreviations and concepts.
   [{"chinese": "保护门", "english": "shutter", "abbreviation": "", "category": "component"}]

Rules:
- Strip year suffixes (e.g. "GB/T 18487.1—2023" → "GB/T 18487.1")
- Never create entities for section numbers or appendix labels
- Return ONLY the JSON object, nothing else."""


def _call_llm(text: str, max_retries: int = 3) -> dict[str, Any]:
    from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider

    for attempt in range(max_retries):
        try:
            client = LLMClient(provider=Provider.CLAUDE, timeout=120.0, max_retries=1)
            response = client.chat(
                messages=[Message(role="user", content=text)],
                system_prompt=_EXTRACT_PROMPT,
                temperature=0.0,
                max_tokens=6000,
            )
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
        except Exception:
            if attempt == max_retries - 1:
                return {}
            time.sleep(5)
    return {}


def _clean_name(name: str) -> str:
    return name.strip()


def _is_bad_name(name: str) -> bool:
    n = name.strip()
    if not n:
        return True
    if re.match(r"^[0-9]+(\.[0-9]+)*\s+\S", n):
        return True
    if re.match(r"^附录\s*[A-Z0-9]?$", n):
        return True
    if n in ("范围", "规范性引用文件", "术语和定义", "附录"):
        return True
    return False


def _store(ont_conn, data, doc_id, chunk_id):
    from kb1_ontology.entity_manager import find_or_create_entity
    from kb1_ontology.attribute_store import set_attribute, VALUE_TYPE_NUMBER, VALUE_TYPE_STRING

    now = datetime.now(UTC).isoformat(timespec="seconds")
    stats = {"attrs": 0, "rels": 0, "params": 0}

    def _chunk_link(eid):
        row = ont_conn.execute(
            "SELECT wiki_chunk_ids_json FROM entity WHERE entity_id = ?", (eid,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row[0] or "[]")
        if chunk_id not in existing:
            existing.append(chunk_id)
            ont_conn.execute(
                "UPDATE entity SET wiki_chunk_ids_json = ? WHERE entity_id = ?",
                (json.dumps(existing), eid),
            )

    for a in data.get("attributes", []):
        ename = _clean_name(a.get("entity") or "")
        pname = _clean_name(a.get("param") or "")
        if not ename or not pname or _is_bad_name(ename):
            continue
        try:
            ent, _ = find_or_create_entity(ont_conn, ename, class_id="CLS-OBC-STANDARD", domain="OBC")
            value = a.get("value")
            unit = (a.get("unit") or "").strip()
            text = f"{value} {unit}".strip() if value is not None else None
            set_attribute(ont_conn, "entity", ent.entity_id, pname, value_text=text, value_type=VALUE_TYPE_NUMBER)
            stats["attrs"] += 1
            _chunk_link(ent.entity_id)
        except Exception:
            pass

    for r in data.get("relations", []):
        sn = _clean_name(r.get("src") or "")
        dn = _clean_name(r.get("dst") or "")
        rn = (r.get("relation") or "references").strip()
        if not sn or not dn:
            continue
        if _is_bad_name(sn) or _is_bad_name(dn):
            continue
        if rn not in ("references", "is-a", "part-of", "implements", "depends-on"):
            rn = "references"
        try:
            src, _ = find_or_create_entity(ont_conn, sn, class_id="CLS-OBC-STANDARD", domain="OBC")
            dst, _ = find_or_create_entity(ont_conn, dn, class_id="CLS-OBC-STANDARD", domain="OBC")
            ont_conn.execute(
                "INSERT OR IGNORE INTO relation (relation_name, src_kind, src_id, dst_kind, dst_id, domain, confidence, created_at) VALUES (?,'entity',?,'entity',?,'OBC',0.9,?)",
                (rn, src.entity_id, dst.entity_id, now),
            )
            stats["rels"] += 1
            _chunk_link(src.entity_id)
            _chunk_link(dst.entity_id)
        except Exception:
            pass

    for p in data.get("params_dict", []):
        ename = _clean_name(p.get("entity") or "")
        pname = _clean_name(p.get("name") or "")
        if not ename or not pname or _is_bad_name(ename):
            continue
        try:
            ent, _ = find_or_create_entity(ont_conn, ename, class_id="CLS-OBC-STANDARD", domain="OBC")
            value = p.get("value")
            unit = (p.get("unit") or "").strip()
            text = f"{value} {unit}".strip() if value is not None else None
            set_attribute(ont_conn, "entity", ent.entity_id, pname, value_text=text, value_type=VALUE_TYPE_NUMBER)
            stats["params"] += 1
            _chunk_link(ent.entity_id)
        except Exception:
            pass

    ont_conn.commit()
    return stats


def extract_one(ont_conn, knowledge_db, doc_id):
    conn = sqlite3.connect(str(knowledge_db))
    conn.row_factory = sqlite3.Row
    chunks = [
        dict(r) for r in conn.execute(
            "SELECT chunk_id, doc_id, source_standard, section_title, body_text FROM wiki_chunks WHERE doc_id = ? AND length(body_text) > 50 ORDER BY chunk_id",
            (doc_id,),
        ).fetchall()
    ]
    conn.close()

    if not chunks:
        return

    print(f"\n[{doc_id}] {len(chunks)} chunks", flush=True)
    total = {"attrs": 0, "rels": 0, "params": 0}

    for i, c in enumerate(chunks):
        sec = c.get("section_title", "")[:25]
        text = c.get("body_text", "")
        print(f"  [{i+1}/{len(chunks)}] {sec!r} ({len(text)} chars)...", end=" ", flush=True)
        if len(text) < 50:
            print("skip")
            continue
        data = _call_llm(text)
        if not data:
            print("empty")
            continue
        s = _store(ont_conn, data, doc_id, c["chunk_id"])
        for k in total:
            total[k] += s.get(k, 0)
        print(f"attrs={s['attrs']} rels={s['rels']} params={s['params']}")

    print(f"  TOTAL: {total}")


def main():
    knowledge_db = ROOT / "knowledge_base" / "db" / "knowledge.db"
    ontology_db = ROOT / "knowledge_base" / "ontology" / "ontology.db"

    done = {"DOC-000002", "DOC-000003", "DOC-000004", "DOC-000005"}
    conn = sqlite3.connect(str(knowledge_db))
    conn.row_factory = sqlite3.Row
    remaining = [
        r["doc_id"]
        for r in conn.execute("SELECT DISTINCT doc_id FROM wiki_chunks ORDER BY doc_id")
        if r["doc_id"] not in done
    ]
    conn.close()

    print(f"Remaining: {len(remaining)} documents", flush=True)

    ont_conn = sqlite3.connect(str(ontology_db))
    ont_conn.row_factory = sqlite3.Row
    try:
        from kb1_ontology.class_registry import ensure_schema as ensure_cls
        from kb1_ontology.entity_manager.schema import ensure_schema as ensure_ent
        from kb1_ontology.relation_registry.schema import ensure_schema as ensure_rel
        from kb1_ontology.attribute_store.schema import ensure_schema as ensure_attr
        ensure_cls(ont_conn)
        ensure_ent(ont_conn)
        ensure_rel(ont_conn)
        ensure_attr(ont_conn)

        grand = {"attrs": 0, "rels": 0, "params": 0}
        for doc_id in remaining:
            extract_one(ont_conn, knowledge_db, doc_id)
            for k in grand:
                grand[k] += grand.get(k, 0)

        print(f"\n{'='*50}")
        print(f"GRAND TOTAL: {grand}")
    finally:
        ont_conn.close()


if __name__ == "__main__":
    main()
