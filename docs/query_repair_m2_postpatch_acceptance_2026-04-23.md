# Query Repair M2 Postpatch Acceptance

## 封面

```text
Milestone:
  M2 - Answer Policy Split

Date:
  2026-04-23

Executor:
  Codex

Scope:
  将参数解释型 query 从 general_search / 普通 definition 中拆出

Code Changes:
  [answer_policy.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_policy.py)
  [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

Observed Environment:
  API restarted at 2026-04-23T03:15:51+00:00
  Health check passed

Acceptance Result:
  PARTIAL PASS
```

## Summary

这轮 `M2` 的核心目标是：

> 参数解释型 query 不再走 `general_search`，并开始输出“参数意义 + 依据”的直接答案。

从运行结果看，这个目标已经基本达成：

1. `CC阻值代表什么意思` 的 `answer_mode` 已变为 `parameter_meaning`
2. `CP占空比是什么意思` 的 `answer_mode` 已变为 `parameter_meaning`
3. `CC阻值` 的 direct answer 已不再输出错误的电压符号和值
4. 参数解释型答案开始稳定输出“它表示什么 + 依据来自哪里”

但这轮仍然不能判为完全通过，因为：

- `CP占空比` 的解释虽然方向对，但仍偏粗
- 参数值型 query（如 `CC阻值是多少`）仍未纳入单独策略，继续走 `general_search`
- 这说明参数解释型 policy 已拆出，但“参数值型”和“参数解释型”的策略分裂还没完整完成

结论：

`M2` 可以判为 `PARTIAL PASS`，已经可以进入 `M3`，但未来还应补一个“parameter value answer policy”。

---

## Gate 检查

```text
Gate 1:
  parameter explanation query 不再走 general_search
  Result: PASS

Gate 2:
  direct answer 结构符合参数解释问题预期
  Result: PASS

Gate 3:
  facts 已命中时，不再返回“没有足够的结构化结果”
  Result: PASS
```

---

## Query Records

### Query 1

```text
Query:
  CC阻值代表什么意思

Observed:
  answer_mode: parameter_meaning
  direct_answer:
    CC阻值 表示 连接确认回路中的等效电阻参数，用于反映车辆接口连接状态。依据来自 A.2 充电控制导引电路。

Result:
  PASS

Notes:
  已摆脱 general_search，也不再输出误导性的电压符号和值。
```

### Query 2

```text
Query:
  CP占空比是什么意思

Observed:
  answer_mode: parameter_meaning
  direct_answer:
    CP占空比（符号 Dco） 表示 控制导引 PWM 信号中的占空比参数，用于表达供电设备可用电流或控制状态。相关值为标称值 ——，范围 max +0.5% / min -0.5%。依据来自 表 A.1 控制导引电路的参数。

Result:
  PASS

Notes:
  虽然表述仍偏工程摘要风格，但已经属于“参数意义解释”，而不是泛搜索拼接。
```

### Query 3

```text
Query:
  CC阻值是多少

Observed:
  answer_mode: general_search

Result:
  FAIL (expected for current milestone boundary)

Failure Class:
  答案策略未拆分完全

Notes:
  当前 M2 的范围只覆盖 parameter meaning，不覆盖 parameter value lookup。
```

---

## What Improved

```text
1. 参数解释型 query 已经从 general_search 中拆出
2. answer_mode 已明确可观测为 parameter_meaning
3. direct answer 开始采用“参数意义 + 依据”的格式
4. CC阻值 的错误值拼接已被去掉
```

---

## What Still Fails

```text
1. 参数值型 query 仍未拆成独立策略
2. CP占空比 的解释还偏粗，后续可继续优化
3. parameter meaning 仍依赖上游 topic/fact 质量，知识粒度不足时会变得保守
```

---

## Root Cause of Remaining Failures

当前剩余问题已不再是 answer policy 没拆，而是：

1. 参数值型策略缺失
2. 更细粒度的 parameter topic / fact 仍不足

也就是说，`M2` 的主任务已完成，剩下的是下一层优化问题。

---

## Go / No-Go Decision

```text
Go / No-Go:
  GO

Decision Meaning:
  可以进入 M3，不需要继续围绕“参数解释型是否还在走 general_search”重复打转。
```

---

## Next Action

推荐下一步：

进入 `M3`：

1. 为无精确对象的问题补 `fallback_reason`
2. 建立“近似解释”模板
3. 解决像 `V2V` 这类 query 的静默漂移问题
