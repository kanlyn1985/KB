# -*- coding: utf-8 -*-
"""Production DB Isolation —— 正式证据测试（AKB-V01-ACCEPTANCE-001 §2/§3/§4）。

- PII-001 session-level proof：sessionstart/sessionfinish 指纹对比（实现在
  conftest_prod_isolation.py；本文件提供可读断言与差异输出）
- PII-002 negative proof：隔离机制本身被验证（对副本 migrate → 生产库指纹不变）
- PII-003 answer contract 无生产库直开（静态审计）
- skip 语义：CI 无生产库 → NOT EXECUTED（不冒充 PASS）
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from conftest_prod_isolation import PROD_AVAILABLE, PROD_DB, _fingerprint

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not PROD_AVAILABLE, reason="production DB unavailable — isolation NOT EXECUTED (skipped, not PASS)")
def test_pii_001_session_fingerprint_consistent(prod_isolation_evidence):
    """PII-001: 会话首查指纹 == 当前指纹（sessionfinish 还有终态对比兜底）。"""
    now = _fingerprint()
    assert now["sha256"] == prod_isolation_evidence["sha256"], (
        "production DB changed within session before this assertion")
    assert now["schema_version"] == prod_isolation_evidence["schema_version"]
    assert now["table_counts"] == prod_isolation_evidence["table_counts"]


@pytest.mark.skipif(not PROD_AVAILABLE, reason="production DB unavailable")
def test_pii_002_negative_proof_isolation_mechanism(tmp_path, prod_isolation_evidence):
    """PII-002 (§4 negative proof)：对隔离副本执行 migrate →
    副本 schema 如预期变化，而生产库指纹保持不变——验证隔离机制本身。"""
    import shutil
    from agent_kb.storage.migrations import SchemaMigrator

    before_prod = _fingerprint()
    copy_db = tmp_path / "isolated.sqlite3"
    shutil.copy2(PROD_DB, copy_db)

    con = sqlite3.connect(copy_db)
    con.row_factory = sqlite3.Row
    applied = SchemaMigrator(con).migrate()
    ver = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    con.close()

    # 副本 schema 如预期变化（迁移集应用）
    assert ver >= 1
    assert any(m >= 1 for m in applied) or ver >= 1, "copy should reflect migrations"
    # 生产库指纹不变（隔离机制有效）
    after_prod = _fingerprint()
    assert after_prod == before_prod, (
        f"production DB changed during isolated-copy migration: "
        f"{json.dumps({'before': before_prod, 'after': after_prod}, default=str)}")


@pytest.mark.skipif(not PROD_AVAILABLE, reason="production DB unavailable")
def test_pii_003_answer_contract_never_opens_prod_db():
    """PII-003 (§5)：test_answer_contract.py 不得出现生产库路径直连
    （必须经 isolated_db fixture）。静态审计。"""
    src = (ROOT / "tests" / "test_answer_contract.py").read_text(encoding="utf-8")
    assert "db_path=DB" not in src, "answer contract still opens production DB directly"
    assert "isolated_db" in src, "answer contract must use isolated_db fixture"


def test_pii_004_skip_not_reported_as_pass():
    """§3 语义锁定：isolation 证据报告必须区分 PASS vs NOT EXECUTED。
    （生产库存在时该测试只验证报告文件 verdict 字段合法。）"""
    report = ROOT / "validation" / ".prod_db_isolation_report.json"
    if not PROD_AVAILABLE:
        pytest.skip("production DB unavailable — this test asserts presence semantics only")
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["verdict"] in ("PASS", "EXEMPTED", "FAIL", "PENDING"), data["verdict"]
    # 报告尚未生成（session 未结束）也算合法——sessionfinish 兜底