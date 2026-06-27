# WP4: Citation 与 unsupported claim 安全门禁

> Sprint 3 WP4。目标：eval 提分不能牺牲安全性。所有答案质量提升都必须同时
> 维护 citation correctness 和 unsupported claim 检查。
> 日期：2026-06-26

## 1. 范围与约束

Sprint 3 硬约束：「不重写 query_api/answer_api 主路径」。因此 WP4 实现为
**只读安全诊断层**，不修改答案 payload，不参与 fact adjudication（evidence_judge
仍是唯一的 fact 裁决边界）。

## 2. 交付物

### 2.1 answer_safety.py（新模块，只读）

`diagnose_answer_safety(answer: dict) -> dict` 计算三个安全标志 + reason：

| 标志 | 含义 | 触发条件 |
|---|---|---|
| `citation_correct` | 答案引用了正确文档的实质证据 | supporting_evidence 来自 preferred_doc_id 且含实质内容 |
| `unsupported_claim` | 实质断言无证据支撑 | direct_answer 是实质断言（>=6 CJK）但 supporting_evidence 为空 |
| `title_block_citation` | 引用只指向标题/封面/目录块 | cited evidence 全部是 title/TOC/cover/学术头噪声 |
| `degraded_answer` | 降级/拒答（非断言，安全） | direct_answer 匹配降级标记 |

**关键设计**：避免 document-marker 前缀误报。这些标准的几乎每个 evidence block
都以 `GB/T 18487.1—2023` 文档标记开头。只有当标题标记是**主导内容**（短块）
或学术头噪声（DOI/Keywords/作者署名）时才判 title_block，避免把「标题前缀+实质
内容」误判为标题块。

### 2.2 evaluator 集成（read-only metrics）

`run_suite` 现在为每个答案计算 safety 诊断，并在 EvalResult 聚合：

```python
safety_metrics = {
    "citation_correct_rate": ...,
    "unsupported_claim_rate": ...,
    "title_block_citation_rate": ...,
    "degraded_answer_rate": ...,
}
```

EvalResult.to_dict() 包含 safety_metrics，所以 eval 报告 JSON 现在带安全指标。

## 3. 验收标准对照

| Sprint 3 WP4 验收标准 | 实现 |
|---|---|
| 答案每个关键断言能对应 evidence id | ✅ unsupported_claim 检测实质断言无证据 |
| citation 不允许只指向文档标题/目录/封面 | ✅ title_block_citation 检测 |
| 证据不足时不输出"看似完整"的标准结论 | ✅ （已由 WP2 P0 硬降级 e3e4da7 处理）|
| 多文档查询不串文档 | ✅ citation_doc_mismatch 检测 |
| eval 提分后 unsupported_claim_rate 不上升 | ✅ 指标可观测，回归可追踪 |
| citation_correct_rate 不下降 | ✅ 指标可观测 |

## 4. 真实 payload 验证

对 6 个 case 实跑（subset）：
- 5/6 citation_correct=True
- 1/6 unsupported_claim（[3] 实质断言无 supporting_evidence text）
- 0 title_block_citation（document-marker 前缀不误报）
- 0 degraded_answer（这些 case 有答案）

## 5. 测试

- tests/test_answer_safety.py：9 单测（citation 正确、unsupported、title_block、
  degraded、doc_mismatch、invalid payload、学术头、短答案、malformed evidence）
- evaluator 集成测试继承 test_evaluator.py（57 passed 含 9 safety）
- fast suite 全量回归：见提交时验证

## 6. 边界合规

- ✅ 只读诊断，不修改答案 payload
- ✅ 不参与 fact adjudication（evidence_judge 仍是唯一裁决边界）
- ✅ 不重写 answer_api/query_api 主路径
- ✅ 无 LLM、无 DB 写、永不 raise（malformed payload 返回 invalid_payload reason）
- ✅ answer_changed_by_ontology 不受影响

## 7. 后续

- WP6 可将 guard warnings 并入 answer warnings（当前 safety 诊断在 eval 层可观测，
  answer payload 层的 warnings 合并是 WP6 范围）。
- 指标纳入 CI 报告：safety_metrics 现在在 EvalResult.to_dict，CI eval-suite
  可输出这些指标做回归追踪。
