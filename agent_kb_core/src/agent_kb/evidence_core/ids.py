# -*- coding: utf-8 -*-
"""AKB Canonical ID 工厂（V0.1）。

规则（V0.1_DATABASE_DESIGN §通用约定 / MIGRATION_PLAN §4）：
- 前缀：src_/doc_/evd_/su_/ast_/astt_/prov_（迁移批次：ast_m{batch:03d}_{seq:04d}）
- 禁止 provider id / rowid / external UUID 直接作为 Canonical ID；
- deterministic id 允许：内容寻址 sha256 前 20 hex（evidence 去重用）。
"""
from __future__ import annotations

import hashlib
import uuid


def _short() -> str:
    return uuid.uuid4().hex[:20]


def mint_id(kind: str) -> str:
    prefixes = {
        "source": "src", "document": "doc", "evidence": "evd",
        "semantic_unit": "su", "assertion": "ast", "transition": "astt",
        "provenance": "prov",
    }
    if kind not in prefixes:
        raise ValueError(f"unknown id kind: {kind}")
    return f"{prefixes[kind]}_{_short()}"


def migration_assertion_id(batch: int, seq: int) -> str:
    """迁移批次断言 ID（MIGRATION_PLAN §4：ast_m{批次:03d}_{序号:04d}）。"""
    return f"ast_m{batch:03d}_{seq:04d}"


def content_hash(text: str) -> str:
    """Evidence identity 的确定性哈希（sha256 hex）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()