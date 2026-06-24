"""LLM-powered term and parameter extraction for ontology dictionary.

Reads from existing facts/evidence tables in the legacy knowledge.db,
uses LLM to extract domain terms and parameters with high accuracy,
and stores them in the ontology DB.

Usage:
    python scripts/ontology_demo/extract_terms.py

This replaces the regex-based extraction in Phase 7.2.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.attribute_store.schema import ensure_schema
from kb1_ontology.db import connect, default_db_path

# ---- LLM client ---------------------------------------------------

def _call_llm(prompt: str, system_prompt: str, max_tokens: int = 2000) -> str:
    """Call LLM using the project's existing LLMClient infrastructure."""
    import os as _os
    from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider

    # httpx doesn't support socks proxies — clear all_proxy to avoid errors
    saved = {}
    for key in ("all_proxy", "ALL_PROXY"):
        if key in _os.environ:
            saved[key] = _os.environ.pop(key)

    try:
        client = LLMClient(
            provider=Provider.CLAUDE,
            timeout=60.0,
            max_retries=1,
        )

        response = client.chat(
            messages=[Message(role="user", content=prompt)],
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
        )
    finally:
        _os.environ.update(saved)

    if not response.content:
        raise RuntimeError("LLM returned empty content")
    return response.content.strip()


def _extract_json(text: str) -> dict[str, Any] | list[Any]:
    """Extract JSON from LLM response (may be wrapped in markdown)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"[\{\[].*[\}\]]", text, re.S)
    if match:
        text = match.group(0)
    return json.loads(text)


# ---- LLM extraction -----------------------------------------------

_TERM_SYSTEM_PROMPT = """\
You are an automotive systems engineering domain expert. Extract domain-specific
TERMS (concepts, abbreviations) from standard documents.

A valid term MUST meet ALL criteria:
1. Has an abbreviation or symbol form (e.g. V2L, PWM, OBD)
2. Has a clear full English name (e.g. Vehicle-to-Load)
3. Is a domain concept, NOT a parameter value, circuit state, or general word
4. Appears in automotive/charging/diagnostic standards

Exclude:
- Parameter values (U_s = 50 V, R1 = 970 Ω)
- Circuit states (S2, F1, T6-T7)
- Generic words (Unit, Session, Line, Record)
- LaTeX or math expressions
- Numbers or symbols only

Return ONLY a JSON array:
[{"abbreviation": "V2L", "full_name": "Vehicle-to-Load", "chinese": "车辆到负载", "category": "concept"}]

Categories: concept, component, protocol, process"""


_PARAM_SYSTEM_PROMPT = """\
You are an automotive systems engineering domain expert. Extract PARAMETER
definitions from standard documents.

A valid parameter has:
1. A symbol or name (e.g. +Vcc, R1, P2_Server_Timing)
2. A numeric value with unit (e.g. 12.0 V, 50 ms, 1000 Ω)
3. Optionally a min/max range
4. A Chinese description if available

Return ONLY a JSON array:
[{"symbol": "+Vcc", "nominal": 12.0, "unit": "V", "min": 11.4, "max": 12.6, "chinese": "输出高电压"}]"""


def _extract_terms_with_llm(text: str) -> list[dict[str, Any]]:
    """Use LLM to extract domain terms from text."""
    if len(text) < 50:
        return []

    # Truncate to avoid token limits
    prompt = f"Extract all domain terms from this standard document text:\n\n{text[:8000]}"

    try:
        response = _call_llm(prompt, _TERM_SYSTEM_PROMPT, max_tokens=2000)
        result = _extract_json(response)
        if isinstance(result, list):
            return result
    except Exception:
        pass

    return []


def _extract_params_with_llm(text: str) -> list[dict[str, Any]]:
    """Use LLM to extract parameter definitions from text."""
    if len(text) < 50:
        return []

    prompt = f"Extract all parameter definitions (symbol, value, unit, min, max, Chinese description) from this text:\n\n{text[:8000]}"

    try:
        response = _call_llm(prompt, _PARAM_SYSTEM_PROMPT, max_tokens=2000)
        result = _extract_json(response)
        if isinstance(result, list):
            return result
    except Exception:
        pass

    return []


# ---- Database operations ------------------------------------------

def _store_term(conn: sqlite3.Connection, term: dict[str, Any], source_doc_id: str) -> str | None:
    """Store a term in the term table. Returns term_id or None."""
    cur = conn.execute("SELECT MAX(CAST(SUBSTR(term_id, 6) AS INTEGER)) FROM term")
    row = cur.fetchone()
    max_id = row[0] if row and row[0] else 0
    term_id = f"TERM-{max_id + 1:04d}"
    now = datetime.now(UTC).isoformat(timespec="seconds")

    abbreviation = (term.get("abbreviation") or "").strip()
    full_name = (term.get("full_name") or "").strip()
    chinese = (term.get("chinese") or "").strip()
    category = (term.get("category") or "concept").strip()

    if not abbreviation:
        return None

    definition_en = full_name
    definition_zh = chinese

    try:
        conn.execute(
            """INSERT INTO term (term_id, canonical_name, category, definition_zh,
               definition_en, source_standard, confidence, extracted_at, verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (term_id, abbreviation, category, definition_zh or None,
             definition_en or None, source_doc_id, 0.90, now, 1, now),
        )

        aliases = [(term_id, abbreviation, "abbreviation")]
        if full_name:
            aliases.append((term_id, full_name, "full_name"))
        if chinese:
            aliases.append((term_id, chinese, "chinese"))

        for alias in aliases:
            conn.execute(
                "INSERT OR IGNORE INTO term_alias (term_id, alias, alias_type) VALUES (?, ?, ?)",
                alias,
            )

        conn.commit()
        return term_id
    except sqlite3.IntegrityError:
        conn.rollback()
        return None


def _store_param(conn: sqlite3.Connection, param: dict[str, Any], source_doc_id: str) -> str | None:
    """Store a parameter in the param table. Returns param_id or None."""
    cur = conn.execute("SELECT MAX(CAST(SUBSTR(param_id, 7) AS INTEGER)) FROM param")
    row = cur.fetchone()
    max_id = row[0] if row and row[0] else 0
    param_id = f"PARAM-{max_id + 1:04d}"
    now = datetime.now(UTC).isoformat(timespec="seconds")

    symbol = (param.get("symbol") or "").strip()
    chinese = (param.get("chinese") or "").strip()
    unit = (param.get("unit") or "").strip()

    if not symbol:
        return None

    nominal = param.get("nominal")
    vmin = param.get("min")
    vmax = param.get("max")

    try:
        conn.execute(
            """INSERT INTO param (param_id, canonical_name, value_num, value_unit,
               value_min, value_max, definition_zh, source_standard,
               confidence, extracted_at, verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (param_id, symbol,
             float(nominal) if nominal is not None else None,
             unit or None,
             float(vmin) if vmin is not None else None,
             float(vmax) if vmax is not None else None,
             chinese or None, source_doc_id,
             0.90, now, 1, now),
        )

        aliases = [(param_id, symbol, "abbreviation")]
        if chinese:
            aliases.append((param_id, chinese, "chinese"))

        for alias in aliases:
            conn.execute(
                "INSERT OR IGNORE INTO param_alias (param_id, alias, alias_type) VALUES (?, ?, ?)",
                alias,
            )

        conn.commit()
        return param_id
    except (sqlite3.IntegrityError, ValueError):
        conn.rollback()
        return None


# ---- Main extraction ----------------------------------------------

def _get_document_texts(legacy_conn: sqlite3.Connection, doc_id: str | None) -> list[tuple[str, str]]:
    """Get (doc_id, text) pairs for extraction."""
    if doc_id:
        docs = [(doc_id,)]
    else:
        cur = legacy_conn.execute(
            "SELECT doc_id FROM documents WHERE parse_status = 'parsed' ORDER BY doc_id"
        )
        docs = cur.fetchall()

    results: list[tuple[str, str]] = []
    for row in docs:
        did = row[0]
        cur = legacy_conn.execute(
            "SELECT normalized_text FROM evidence WHERE doc_id = ? LIMIT 50",
            (did,),
        )
        texts = [r[0] for r in cur.fetchall() if r[0]]
        combined = "\n".join(texts)
        if combined:
            results.append((did, combined))
    return results


def extract_terms_from_legacy(
    workspace_root: Path,
    doc_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Extract terms using LLM from legacy KB documents."""
    legacy_db = workspace_root / "db" / "knowledge.db"
    if not legacy_db.exists():
        return {"error": "Legacy DB not found"}

    ontology_db = default_db_path(workspace_root)
    ont_conn = connect(ontology_db)
    ensure_schema(ont_conn)

    legacy_conn = sqlite3.connect(str(legacy_db))
    legacy_conn.row_factory = sqlite3.Row

    stats = {"documents": 0, "terms": 0, "params": 0}

    try:
        doc_texts = _get_document_texts(legacy_conn, doc_id)
        for did, text in doc_texts:
            stats["documents"] += 1

            # Extract terms
            for term in _extract_terms_with_llm(text):
                if stats["terms"] >= limit:
                    break
                tid = _store_term(ont_conn, term, did)
                if tid:
                    stats["terms"] += 1

            # Extract params
            for param in _extract_params_with_llm(text):
                if stats["params"] >= limit:
                    break
                pid = _store_param(ont_conn, param, did)
                if pid:
                    stats["params"] += 1

    finally:
        legacy_conn.close()
        ont_conn.close()

    return stats


def main() -> None:
    workspace = ROOT / "knowledge_base"
    print(f"Extracting terms with LLM from: {workspace}")
    print()

    stats = extract_terms_from_legacy(workspace)
    print(stats)
    print()
    print("=" * 50)
    print("✅ LLM term extraction complete")


if __name__ == "__main__":
    main()
