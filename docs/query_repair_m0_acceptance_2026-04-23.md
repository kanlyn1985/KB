# Query Repair M0 Acceptance

## 封面

```text
Milestone:
  M0 - Query Understanding Stabilized

Date:
  2026-04-23

Executor:
  Codex

Scope:
  基于当前代码状态，对 M0 的上游理解链路做基线验收，不包含任何修复代码

Code / Config Changes:
  无功能修复代码
  仅生成基线快照：
  [query_repair_m0_baseline_snapshot_2026-04-23.json](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_m0_baseline_snapshot_2026-04-23.json)

Observed Environment:
  本地开发环境
  工作区: E:/AI_Project/opencode_workspace/KB1
  API: http://127.0.0.1:8000

Acceptance Result:
  FAIL
```

## Summary

当前系统尚未达到 `M0` 完成标准。  
主要失败不是召回层，而是最上游 query understanding 仍明显失真：

1. 解释型问法仍会落入 `general_search`
2. 细粒度限定词仍然会被压粗
3. `target_topic` 仍会出现“未知实体 / 未知主题”这类无效锚点
4. 参数解释型问题与参数值型问题还没有被稳定区分

结论：

`M0` 目前不能通过，必须先进入 `rewrite consistency + 解释型问法覆盖 + 限定词保护` 的实施阶段。

---

## M0 Gate 检查

```text
Gate 1:
  解释型问法不再错误落入 general_search
  Result: FAIL

Gate 2:
  target_topic 不再退化为裸缩写或粗主题
  Result: FAIL

Gate 3:
  protected_anchor_terms 可观测且对限定词有效
  Result: FAIL

Gate 4:
  rewrite_override_applied 发生时，target_topic 已同步纠正
  Result: FAIL
```

---

## Query Records

### Query 1

```text
Query:
  CC阻值代表什么意思

Expected Class:
  限定词丢失型 / 参数解释型

Expected Query Type:
  definition 或 parameter_meaning（至少不能是 general_search）

Expected Target Topic:
  CC阻值

Observed:
  final_query_type: general_search
  final_normalized_query: CC
  final_target_topic: 未知实体
  protected_anchor_terms: 不可见
  rewrite_override_applied: 不可见

Result:
  FAIL

Failure Class:
  限定词丢失型 + 类型判定错位型 + 主题锚点粗化型

Notes:
  用户问的是细粒度参数语义，但系统把问题压成了粗主题，并且还出现了无效 target_topic。
```

### Query 2

```text
Query:
  CP占空比是什么意思

Expected Class:
  参数解释型

Expected Query Type:
  parameter_lookup / parameter_meaning

Expected Target Topic:
  CP占空比

Observed:
  final_query_type: parameter_lookup
  final_normalized_query: CP
  final_target_topic: CP
  protected_anchor_terms: 不可见

Result:
  FAIL

Failure Class:
  主题锚点粗化型

Notes:
  类型方向是对的，但主题只保留了 CP，限定词“占空比”丢失，属于典型半修正状态。
```

### Query 3

```text
Query:
  检测点1电压表示什么

Expected Class:
  参数解释型

Expected Query Type:
  parameter_lookup / parameter_meaning

Expected Target Topic:
  检测点1电压

Observed:
  final_query_type: no_answer_candidate
  final_normalized_query: 原问题未被有效抽象
  final_target_topic: 原问题碎片化保留

Result:
  FAIL

Failure Class:
  类型判定错位型 + semantic 输出质量问题

Notes:
  这是 M0 的明显阻塞项，说明解释型问法与检测点类参数对象都没有被正确纳入理解链路。
```

### Query 4

```text
Query:
  什么是V2V

Expected Class:
  别名漂移型 / 定义型

Expected Query Type:
  definition

Expected Target Topic:
  V2V

Observed:
  final_query_type: general_search
  final_normalized_query: V2V
  final_target_topic: V2V

Result:
  FAIL

Failure Class:
  类型判定错位型

Notes:
  主题本身没有完全错，但意图仍错误归入 general_search，后续链路天然会走偏。
```

### Query 5

```text
Query:
  V2V的定义是什么

Expected Class:
  定义型

Expected Query Type:
  definition

Expected Target Topic:
  V2V

Observed:
  final_query_type: general_search
  final_normalized_query: V2V
  final_target_topic: V2V

Result:
  FAIL

Failure Class:
  类型判定错位型

Notes:
  连显式包含“定义是什么”的问法都没有稳定进入 definition，说明解释型规则覆盖明显不足。
```

### Query 6

```text
Query:
  什么是控制导引电路

Expected Class:
  标准定义型

Expected Query Type:
  definition

Expected Target Topic:
  控制导引电路

Observed:
  final_query_type: general_search
  final_target_topic: 未知主题

Result:
  FAIL

Failure Class:
  类型判定错位型 + semantic 输出质量问题

Notes:
  连最标准的定义型问法都未稳定进入 definition，说明上游 query understanding 仍不可靠。
```

---

## What Improved

```text
本轮是基线验收，不存在“修复后改善项”。
当前的价值在于把失败现象固化成了可比较的基准面。
```

---

## What Still Fails

```text
1. 解释型问法仍然大面积落入 general_search
2. target_topic 仍然可能退化成裸缩写
3. target_topic 仍可能出现“未知实体 / 未知主题”
4. 参数解释 query 没有稳定保留限定词
5. 检测点类 query 仍可能掉入 no_answer_candidate
```

---

## Root Cause of Remaining Failures

剩余失败主要集中在最上游两层：

1. semantic parse
2. rewrite

更具体地说，是：

- 解释型问法识别不足
- query_type 与 topic anchor 不一致
- 限定词保护缺失
- 坏输出缺乏质量约束

---

## Go / No-Go Decision

```text
Go / No-Go:
  NO-GO for M0 completion

Reason:
  当前 M0 的四个 gate 全部未通过，不能进入“里程碑已完成”状态。
  但可以进入 M0 实施阶段。
```

---

## Next Action

下一步必须进入代码实施，而不是继续扩写文档。

推荐顺序：

1. 执行 `rewrite` 两阶段重构
2. 补解释型问法规则
3. 加限定词保护机制
4. 增加最小观测字段

只有完成这四项后，才应再次做 `M0` 验收。
