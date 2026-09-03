# -*- coding: utf-8 -*-
"""CMP-016..019：单证据契约 / Canonical fingerprint / 碰撞抗性 / run 基数。"""
from __future__ import annotations

import hashlib
import json

import pytest

from agent_kb.evidence_core.compilation import (
    SemanticCompiler,
    compilation_fingerprint,
    canonical_json,
)


def test_cmp_016_single_evidence_contract(seeded, compiler):
    """一次 invocation 恰一 Evidence；V0.2 无 batch API 面。"""
    import inspect
    sig = inspect.signature(compiler.compile)
    assert "evidence_id" in sig.parameters
    assert not any(p.startswith("evidence_ids") for p in sig.parameters)
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r.run is not None


def test_cmp_017_canonical_fingerprint_serialization():
    """同四元组两次构造全等；构造顺序无关；无时钟/locale 参与；字节级比较。"""
    fields = {"evidence_id": "ev_1", "compiler_version": "v1",
              "configuration_hash": "cfg", "content_hash": "h"}
    fp1 = compilation_fingerprint(fields["evidence_id"], fields["compiler_version"],
                                  fields["configuration_hash"], fields["content_hash"])
    fp2 = compilation_fingerprint(fields["evidence_id"], fields["compiler_version"],
                                  fields["configuration_hash"], fields["content_hash"])
    assert fp1 == fp2  # deterministic
    # canonical serialization 等价性：构造 dict 直接 dumps 同序
    manual = hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()
    assert fp1 == manual
    # ensure_ascii=False（中文不转义）+ 紧凑分隔符
    assert canonical_json({"k": "中文"}) == '{"k":"中文"}'
    assert " " not in canonical_json({"a": 1, "b": 2})
    # SHA-256 十六进制形态（64 hex chars）
    assert len(fp1) == 64 and all(c in "0123456789abcdef" for c in fp1)


def test_cmp_018_fingerprint_collision_resistance():
    """任一字段变化 → fingerprint 变化；抽样 10^4 组合零碰撞。"""
    base = ("ev_1", "v1", "cfg", "h")
    fp_base = compilation_fingerprint(*base)
    for i, field_vals in enumerate([
            ("ev_2", "v1", "cfg", "h"), ("ev_1", "v2", "cfg", "h"),
            ("ev_1", "v1", "cfg2", "h"), ("ev_1", "v1", "cfg", "h2"),
            ("ev_1x", "v1", "cfg", "h"),  # 仅尾字符变化
            ("ev_1", "v1", "cfg", "hx")]):
        assert compilation_fingerprint(*field_vals) != fp_base, f"collision at variant {i}"
    # 10^4 组合抽样
    seen = set()
    for i in range(10_000):
        fp = compilation_fingerprint(f"ev_{i}", "v1", "cfg", "h")
        assert fp not in seen
        seen.add(fp)


def test_cmp_019_run_evidence_cardinality(db, seeded, compiler):
    """run 行 evidence_ids_json 解析后恰一元素且等于 invocation evidence_id。"""
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    run = compiler.describe_run(r.run.run_id)
    ids = json.loads(run["evidence_ids_json"])
    assert ids == [seeded["evidence_id"]]
    assert len(ids) == 1
    # 无 batch 语义：compile 签名不收列表
    import inspect
    sig = inspect.signature(compiler.compile)
    assert "evidence_ids" not in sig.parameters