# WP6: Guard warning 并入 Answer Warnings

> Sprint 3 WP6。Sprint 2 已有 ontology guard post-check，遗留项是 warning 还没有
> 自然并入 answer warnings。Sprint 3 把它作为可观测输出接入，但仍不得改写 answer text。
> 日期：2026-06-26

## 1. 范围

将 ontology guard post-check 的 findings 并入 answer payload 的 `warnings` 数组，
作为可观测输出。**不得改写 answer text，不得改 fact adjudication，answer_changed_by_ontology
保持 false。**

## 2. 改动

`answer_api.py` `_compose_final_answer`：在 guard 模式 post_check 产出 findings 后，
把每个 finding 作为结构化 warning 追加到 `warnings` 数组：

```python
warnings.append({
    "source": "ontology_guard",
    "type": "relation_unknown|relation_conflict|entity_type_mismatch",
    "severity": "info|warning",
    "message": "...",
    "changed_answer": False,
})
```

符合 Sprint 3 指南的 warning envelope 格式。已有的字符串 warnings（如质量状态警告）
保留，结构化 guard warnings 与之并存。

## 3. 验证

### 3.1 guard 模式真实查询
- `什么是控制导引电路？` guard 模式：ontology_post_check_status=completed，
  ontology_post_checks=[]（因为所有实体共享一个 class，post_check 无 finding），
  warnings 仅含已有字符串警告，无 ontology_guard warning（正确：无 finding 则无 warning）。
  answer_changed_by_ontology=False，direct_answer 不变。

### 3.2 合并路径单测（monkeypatch 合成 finding）
- monkeypatch `_ontology_post_check` 返回合成 entity_type_mismatch finding
- 验证：warnings 数组含 1 个 source=ontology_guard 的结构化 warning
- type/severity/message 正确，changed_answer=False
- answer_changed_by_ontology=False，direct_answer 含「控制导引电路」不变
- ontology_post_checks[0].type == entity_type_mismatch（finding 同时在两处可观测）

## 4. 边界合规

- ✅ warnings 是可观测输出，不改写 answer text
- ✅ answer_changed_by_ontology = false（全程）
- ✅ 不绕过 evidence_judge（guard 只观察不裁决）
- ✅ 无 finding 时不产生 warning（避免噪声）
- ✅ 已有字符串 warnings 保留，不破坏现有调用方

## 5. 测试

- tests/test_ontology_adapter.py::TestAnswerQueryGuardWiring：+1 WP6 合并测试
  （3 tests total: off skipped, guard no-mutation, WP6 finding merged）
- fast suite 全量回归：见提交时验证

## 6. 当前限制

由于 ontology.db 单 class（所有 364 实体共享 CLS-OBC-STANDARD），post_check 在
真实查询上几乎不产生 finding（与 WP5 A/B 结论一致）。合并机制结构正确，待
ontology.db class 多样化后会自然产生更多 guard warnings。

## 7. 交付物

- `src/enterprise_agent_kb/answer_api.py`：guard findings 并入 warnings
- `tests/test_ontology_adapter.py`：+1 WP6 测试
- 本报告：`docs/dev/sprint3-answer-quality/wp6_guard_warning_merge_report.md`
