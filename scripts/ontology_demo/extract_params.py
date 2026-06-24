"""LLM-powered parameter extraction for ontology dictionary.

Reads from parameter_value and threshold facts in the legacy knowledge.db,
uses LLM to extract structured parameter values, and stores them in the
ontology DB ``param`` table.

Usage:
    python scripts/ontology_demo/extract_params.py
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.attribute_store.schema import ensure_schema
from kb1_ontology.db import connect, default_db_path


def _store_param(conn: sqlite3.Connection, param: dict[str, Any], source_doc_id: str) -> str | None:
    """Store a parameter in the param table. Returns param_id or None."""
    symbol = (param.get("symbol") or param.get("canonical_name") or "").strip()
    if not symbol:
        return None

    cur = conn.execute("SELECT MAX(CAST(SUBSTR(param_id, 7) AS INTEGER)) FROM param")
    row = cur.fetchone()
    max_id = row[0] if row and row[0] else 0
    param_id = f"PARAM-{max_id + 1:04d}"
    now = datetime.now(UTC).isoformat(timespec="seconds")

    unit = (param.get("unit") or param.get("value_unit") or "").strip()
    chinese = (param.get("chinese") or param.get("definition_zh") or "").strip()
    nominal = param.get("nominal") or param.get("value_num")
    vmin = param.get("min") or param.get("value_min")
    vmax = param.get("max") or param.get("value_max")

    try:
        conn.execute(
            """INSERT OR REPLACE INTO param (param_id, canonical_name, value_num, value_unit,
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
        conn.commit()
        return param_id
    except (sqlite3.IntegrityError, ValueError):
        conn.rollback()
        return None


def extract_params_from_legacy(
    workspace_root: Path,
    doc_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Extract parameters from legacy KB facts using LLM."""
    legacy_db = workspace_root / "db" / "knowledge.db"
    if not legacy_db.exists():
        return {"error": "Legacy DB not found"}

    ontology_db = default_db_path(workspace_root)
    ont_conn = connect(ontology_db)
    ensure_schema(ont_conn)

    legacy_conn = sqlite3.connect(str(legacy_db))
    legacy_conn.row_factory = sqlite3.Row

    stats = {"from_parameter_values": 0, "from_thresholds": 0, "total": 0}

    try:
        # Extract from parameter_value facts (already structured JSON)
        if doc_id:
            rows = legacy_conn.execute(
                "SELECT object_value, source_doc_id FROM facts "
                "WHERE fact_type = 'parameter_value' AND source_doc_id = ?",
                (doc_id,),
            ).fetchall()
        else:
            rows = legacy_conn.execute(
                "SELECT object_value, source_doc_id FROM facts "
                "WHERE fact_type = 'parameter_value'"
            ).fetchall()

        for row in rows:
            try:
                obj = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue

            symbol = (obj.get("symbol") or obj.get("parameter") or "").strip()
            if not symbol:
                continue

            try:
                nominal = float(obj["nominal_value"]) if obj.get("nominal_value") else None
            except (ValueError, TypeError):
                nominal = None
            try:
                vmin = float(obj["min_value"]) if obj.get("min_value") else None
            except (ValueError, TypeError):
                vmin = None
            try:
                vmax = float(obj["max_value"]) if obj.get("max_value") else None
            except (ValueError, TypeError):
                vmax = None

            param = {
                "symbol": symbol,
                "chinese": (obj.get("parameter") or "").strip(),
                "unit": (obj.get("unit") or "").strip(),
                "nominal": nominal,
                "min": vmin,
                "max": vmax,
            }
            pid = _store_param(ont_conn, param, row[1])
            if pid:
                stats["from_parameter_values"] += 1
                stats["total"] += 1

        # Extract from threshold facts
        if doc_id:
            rows = legacy_conn.execute(
                "SELECT predicate, object_value, source_doc_id FROM facts "
                "WHERE fact_type = 'threshold' AND source_doc_id = ?",
                (doc_id,),
            ).fetchall()
        else:
            rows = legacy_conn.execute(
                "SELECT predicate, object_value, source_doc_id FROM facts "
                "WHERE fact_type = 'threshold'"
            ).fetchall()

        import re
        for row in rows:
            predicate = row[0] or ""
            value_text = row[1] or ""
            doc = row[2]

            match = re.search(r"([\d.]+)\s*(ms|V|A|Hz|kHz|MHz|s|min|h|°C|Ω)", value_text)
            if not match:
                continue

            try:
                num = float(match.group(1))
            except ValueError:
                continue

            param = {
                "symbol": predicate[:60],
                "nominal": num,
                "unit": match.group(2),
            }
            pid = _store_param(ont_conn, param, doc)
            if pid:
                stats["from_thresholds"] += 1
                stats["total"] += 1

    finally:
        legacy_conn.close()
        ont_conn.close()

    return stats


def main() -> None:
    workspace = ROOT / "knowledge_base"
    print(f"Extracting params from legacy KB at: {workspace}")
    print()
    stats = extract_params_from_legacy(workspace)
    print(stats)
    print()
    print("=" * 50)
    print("✅ Parameter extraction complete")


if __name__ == "__main__":
    main()