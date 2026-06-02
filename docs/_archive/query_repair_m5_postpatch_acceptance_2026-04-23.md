# Query Repair M5 Postpatch Acceptance

## 封面

```text
Milestone:
  M5 - Regression Locked

Date:
  2026-04-23

Executor:
  Codex

Scope:
  将 M0-M4 的关键修复固化为真实测试，并完成一次本地回归运行

Code Changes:
  [test_query_repair_regression.py](E:/AI_Project/opencode_workspace/KB1/tests/test_query_repair_regression.py)

Observed Environment:
  pytest
  workspace: E:/AI_Project/opencode_workspace/KB1

Acceptance Result:
  PASS
```

## Summary

这轮 `M5` 的目标是：

> 把前面 M0-M4 的关键行为固化成可重复执行的真实回归测试，而不是只靠人工口头确认。

本轮已经完成：

1. 新增统一回归测试文件  
   [test_query_repair_regression.py](E:/AI_Project/opencode_workspace/KB1/tests/test_query_repair_regression.py)

2. 覆盖了以下关键能力：
   - rewrite 保留细粒度锚点
   - parameter meaning policy 选路
   - query-context 优先命中新建的 parameter_topic
   - answer-query 对参数解释型问题走 `parameter_meaning`
   - `V2V` definition 走可解释 fallback

3. 实际运行结果：
   - 默认单元测试：`13 passed`
   - 集成回归：`6 passed`

这意味着前面几轮修复已经不再只是一次性的手工验证，而是被测试锁住了。

---

## 执行结果

### 单元层

执行：

```text
pytest -q tests/test_query_rewrite.py tests/test_answer_policy.py tests/test_query_repair_regression.py -m "not integration"
```

结果：

```text
13 passed, 6 deselected
```

### 集成层

执行：

```text
pytest -q tests/test_query_repair_regression.py -m integration
```

结果：

```text
6 passed, 4 deselected
```

---

## 回归覆盖点

### Pack A：Rewrite / Anchor 保真

覆盖：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `V2V的定义是什么`

验证点：

- query_type
- normalized_query
- target_topic
- protected_anchor_terms

### Pack B：Parameter Topic 命中

覆盖：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`

验证点：

- query-context 的 top candidate 是否为 `parameter_topic`

### Pack C：Parameter Meaning Answer

覆盖：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`

验证点：

- `answer_mode == parameter_meaning`
- direct answer 结构合理
- `fallback_reason == ""`

### Pack D：Explainable Fallback

覆盖：

- `什么是V2V`

验证点：

- `answer_mode == definition`
- `fallback_reason == fallback_to_related_concept`
- direct answer 明示“未找到直接定义 + 近似解释”

---

## Gate 检查

```text
Gate 1:
  M0-M4 的关键能力已被自动化测试覆盖
  Result: PASS

Gate 2:
  单元层与集成层均已执行并通过
  Result: PASS

Gate 3:
  回归集可直接复跑，不依赖人工解释
  Result: PASS
```

---

## What Improved

```text
1. 修复结果已被真实测试锁住
2. 参数解释型 query 的行为不再只靠人工手工验证
3. V2V fallback 也已进入集成回归
4. 后续改动如果把 M0-M4 回退，pytest 会直接暴露问题
```

---

## Residual Risks

```text
1. 当前回归仍主要覆盖高频 query，尚未覆盖更广的长尾问法
2. 参数值型 query 还没有独立 answer policy，因此相关测试覆盖仍偏弱
3. topic_entities 与新 parameter_topic 的对齐质量还可以继续增强
```

---

## Final Decision

```text
Milestone Decision:
  M5 PASS

Meaning:
  本轮 M0-M5 已形成完整闭环：
  诊断 -> 策略 -> 实施 -> 验收 -> 回归锁定
```

---

## Next Action

后续如果继续推进，不建议再扩文档。

更合理的方向是：

1. 继续补参数值型 answer policy
2. 扩大长尾 query 回归集
3. 继续补非参数类细粒度知识对象
