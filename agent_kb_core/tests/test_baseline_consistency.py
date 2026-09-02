# -*- coding: utf-8 -*-
"""基线一致性检查 —— 兼容层。

断言本体已按任务书 AKB-P0-BASELINE-CLEANUP-001 §10 指定文件名拆分：
- test_requirement_id_consistency.py（SRS/RTM 需求 ID 唯一 + 映射完整）
- test_invariant_registry_consistency.py（Registry 唯一 + 全仓引用一致）

本文件仅保留一个 smoke test 防止拆分文件被意外删除/清空（不再 re-import 断言函数，
避免 pytest 重复收集）。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_split_consistency_files_exist() -> None:
    assert (ROOT / "agent_kb_core" / "tests" / "test_requirement_id_consistency.py").is_file()
    assert (ROOT / "agent_kb_core" / "tests" / "test_invariant_registry_consistency.py").is_file()
