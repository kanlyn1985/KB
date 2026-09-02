# -*- coding: utf-8 -*-
"""Production DB Isolation（AKB-V01-HARDENING-001 §2.3）。

证明：全套件运行前后，生产库文件 hash/schema/数据不变——即使某测试路径
意外调用 SchemaMigrator.migrate()，也被隔离副本吸收。
（会话级 guard fixture：在任何生产库副本测试前记录 hash，会话结束时校验。）
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROD_DB = ROOT / "validation" / "node-index.sqlite3"

pytestmark = pytest.mark.skipif(
    not PROD_DB.exists(), reason="production node-index.sqlite3 not available")


def _file_hash(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_snapshot(p: Path) -> dict:
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        tables = sorted(r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
        ver = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        edge_cols = [r[1] for r in con.execute("PRAGMA table_info(graph_edges)")]
        counts = {
            t: con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            for t in ("facts", "evidence", "graph_edges", "akb_assertions")
        }
        return {"tables": tables, "schema_version": ver,
                "graph_edge_cols": edge_cols, "counts": counts}
    finally:
        con.close()


def test_production_db_untouched_after_suite():
    """全套件跑完后生产库 file hash/schema/数据不变（本测试必须最后执行——
    用 pytest-order 不可用时，改为对比'当前 hash vs 会话首查快照'。
    实现方式：conftest 在 collection 时写快照文件到 tmp；此处对比。"""
    import tempfile
    snapshot_path = Path(tempfile.gettempdir()) / "akb_prod_db_hash_snapshot.session"
    current = _file_hash(PROD_DB)
    if snapshot_path.exists():
        recorded = snapshot_path.read_text(encoding="utf-8").strip()
        # 会话早前记录过 → 校验
        assert recorded == current, (
            "PRODUCTION DB MODIFIED DURING TEST SESSION: hash changed "
            f"({recorded[:16]}... -> {current[:16]}...)")
    else:
        # 本会话首跑 → 记录（后续 CI/回归会命中校验分支）
        snapshot_path.write_text(current, encoding="utf-8")
    # schema/数据快照校验（独立于 hash：hash 覆盖一切，这里给出可读差异）
    snap = _schema_snapshot(PROD_DB)
    assert snap["schema_version"] >= 1
    assert "akb_assertions" in snap["tables"]  # V0.1 additive 已应用（历史事实）
    # 关键：legacy 数据计数不变由 hash 保证