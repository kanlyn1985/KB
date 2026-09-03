# -*- coding: utf-8 -*-
"""Production DB Isolation —— session-level proof（AKB-V01-ACCEPTANCE-001 §2）。

机制（真实 session 级）：
- pytest_sessionstart：记录生产库指纹（SHA-256/schema version/关键表计数/graph_edges 列/size+mtime）
- 整个 session 运行
- pytest_sessionfinish：重读指纹，逐项对比；任何变化 → 输出 before/after 差异并使会话失败
- 豁免清单：.prod_db_isolation_exemptions.json（仅当架构负责人批准的合法写入，如 --apply 回填）——
  默认不存在；存在时在报告输出中显式声明"exempted"，不允许 silent pass。
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROD_DB = ROOT / "validation" / "node-index.sqlite3"
PROD_AVAILABLE = PROD_DB.exists()

CRITICAL_TABLES = ("facts", "evidence", "graph_edges", "retrieval_cards", "akb_assertions")


def _fingerprint() -> dict:
    stat = PROD_DB.stat()
    h = hashlib.sha256()
    with open(PROD_DB, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    con = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    try:
        version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        counts = {t: con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                  for t in CRITICAL_TABLES if con.execute(
                      "SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()}
        edge_cols = [r[1] for r in con.execute("PRAGMA table_info(graph_edges)")]
    finally:
        con.close()
    return {"sha256": h.hexdigest(), "size": stat.st_size, "mtime": stat.st_mtime,
            "schema_version": version, "table_counts": counts, "graph_edges_cols": edge_cols}


def _write_report(report: dict, verdict: str) -> Path:
    out = Path(os.environ.get("PROD_ISOLATION_REPORT",
                              str(ROOT / "validation" / ".prod_db_isolation_report.json")))
    out.write_text(json.dumps({"verdict": verdict, **report}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


if PROD_AVAILABLE:

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(session):
        before = _fingerprint()
        setattr(session, "prod_isolation_before", before)
        report_path = _write_report({"phase": "sessionstart", "before": before}, "PENDING")
        print(f"\n[prod-isolation] BEFORE fingerprint recorded -> {report_path.name} "
              f"(sha256={before['sha256'][:16]}..., schema_version={before['schema_version']})")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(session, exitstatus):
        before = getattr(session, "prod_isolation_before", None)
        if before is None:  # sessionstart 未跑（异常收集等）——现场补拍
            before = _fingerprint()
        after = _fingerprint()
        diff = {}
        for key in before:
            if before[key] != after[key]:
                diff[key] = {"before": before[key], "after": after[key]}
        exempt = ROOT / "validation" / ".prod_db_isolation_exemptions.json"
        verdict = "PASS" if not diff else ("EXEMPTED" if exempt.exists() else "FAIL")
        report_path = _write_report({"phase": "sessionfinish",
                                     "before": before, "after": after, "diff": diff}, verdict)
        print(f"\n[prod-isolation] AFTER fingerprint compared -> {report_path.name}")
        if diff:
            print(f"[prod-isolation] DIFF: {json.dumps(diff, indent=1, default=str)}")
        print(f"[prod-isolation] VERDICT = {verdict}")
        if verdict == "FAIL":
            session.prod_isolation_failed = True
            raise RuntimeError(
                f"PRODUCTION DB MODIFIED DURING PYTEST SESSION: {diff}")

    @pytest.fixture(scope="session")
    def prod_isolation_evidence(request):
        """供测试读取会话首查指纹（negative proof 对比用）。"""
        before = getattr(request.session, "prod_isolation_before", None)
        if before is None:  # fixture 首用时 sessionstart 已必跑；兜底现场补拍
            before = _fingerprint()
            setattr(request.session, "prod_isolation_before", before)
        return before

    @pytest.fixture(scope="session")
    def prod_db_path():
        return PROD_DB

else:

    @pytest.fixture(scope="session")
    def prod_isolation_evidence():
        pytest.skip("production node-index.sqlite3 not available — isolation NOT EXECUTED")

    @pytest.fixture(scope="session")
    def prod_db_path():
        pytest.skip("production node-index.sqlite3 not available")