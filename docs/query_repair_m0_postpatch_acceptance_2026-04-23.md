# Query Repair M0 Postpatch Acceptance

## 封面

```text
Milestone:
  M0 - Query Understanding Stabilized

Date:
  2026-04-23

Executor:
  Codex

Scope:
  Phase 0 上游理解链路修复后的第一次复验

Code / Config Changes:
  [query_semantic_parser.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_semantic_parser.py)
  [query_rewrite.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_rewrite.py)
  [query_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_api.py)
  [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

Observed Environment:
  API restarted at 2026-04-23T02:35:37+00:00
  Health check passed

Acceptance Result:
  PARTIAL PASS
```

## Summary

这轮修复已经明显改善了 `M0` 的核心问题：

1. 解释型问法不再大面积掉进 `general_search`
2. `CC阻值 / CP占空比 / 检测点1电压 / V2V` 这类 query 已能保留细粒度 topic anchor
3. `rewrite` 输出已显式带出 `protected_anchor_terms / rewrite_override_applied / semantic_quality_flags`
4. `query-context` 和 `answer-query` 已暴露 `debug_query`

但 `M0` 还不能判定为完全通过，原因是：

- 参数解释类 query 目前被稳定归入 `definition`，而不是更清晰的参数解释内部模式
- 还没有证明所有“semantic 错、rule 修正”的场景都能稳定触发并正确重建 topic anchor

结论：

当前状态已经从 `FAIL` 提升到 `PARTIAL PASS`，可以进入下一轮 `M0` 收尾或直接推进 `M1` 预备。

---

## Gate 检查

```text
Gate 1:
  解释型问法不再错误落入 general_search
  Result: PASS

Gate 2:
  target_topic 不再退化为裸缩写或粗主题
  Result: PASS

Gate 3:
  protected_anchor_terms 可观测且对限定词有效
  Result: PASS

Gate 4:
  rewrite_override_applied 发生时，target_topic 已同步纠正
  Result: PARTIAL
```

---

## Query Records

### Query 1

```text
Query:
  CC阻值代表什么意思

Observed:
  final_query_type: definition
  final_normalized_query: CC阻值
  final_target_topic: CC阻值
  protected_anchor_terms: [CC阻值, CC]
  semantic_quality_flags: []

Result:
  PASS

Notes:
  已不再退化为 CC，也不再落入 general_search。
```

### Query 2

```text
Query:
  CP占空比是什么意思

Observed:
  final_query_type: definition
  final_normalized_query: CP占空比
  final_target_topic: CP占空比
  protected_anchor_terms: [CP占空比, CP]

Result:
  PASS

Notes:
  已保留参数限定词，占空比没有再丢失。
```

### Query 3

```text
Query:
  检测点1电压表示什么

Observed:
  final_query_type: definition
  final_normalized_query: 检测点1电压
  final_target_topic: 检测点1电压
  protected_anchor_terms: [检测点1电压]

Result:
  PASS

Notes:
  已不再落入 no_answer_candidate。
```

### Query 4

```text
Query:
  什么是V2V

Observed:
  final_query_type: definition
  final_normalized_query: V2V
  final_target_topic: V2V
  protected_anchor_terms: [V2V]

Result:
  PASS

Notes:
  已从 general_search 拉回 definition。
```

### Query 5

```text
Query:
  V2V的定义是什么

Observed:
  final_query_type: definition
  final_normalized_query: V2V
  final_target_topic: V2V
  protected_anchor_terms: [V2V]

Result:
  PASS

Notes:
  显式定义型问法已稳定进入 definition。
```

### Query 6

```text
Query:
  什么是控制导引电路

Observed:
  final_query_type: definition
  final_normalized_query: 控制导引电路
  final_target_topic: 控制导引电路
  protected_anchor_terms: []

Result:
  PASS

Notes:
  标准定义型问法已恢复到正常 definition 轨道。
```

---

## What Improved

```text
1. 解释型问法归类明显改善
2. target_topic 保真度显著提升
3. 细粒度限定词已能被保护
4. semantic parser 的 placeholder topic 已被抑制
5. API 返回中已有最小调试字段
```

---

## What Still Fails

```text
1. 参数解释型问法当前仍统一落在 definition，而未拆为更明确的参数解释内部模式
2. rewrite_override_applied 的覆盖场景还需要更强的回归证明
3. 当前只是“理解链路变对”，还没有解决 topic resolution / answer policy 的下游问题
```

---

## Root Cause of Remaining Failures

当前剩余问题已不再主要集中在最上游 semantic/rewrite，
而是开始转向：

1. query type 细分粒度不足
2. 下游 topic resolution 和 answer policy 尚未同步升级

这说明 `M0` 的核心方向基本正确，下一阶段应开始进入 `M1 / M2`。

---

## Go / No-Go Decision

```text
Go / No-Go:
  GO for moving forward

Decision Meaning:
  可以继续推进到下一轮实现，不需要停留在纯 M0 讨论阶段。
```

---

## Next Action

推荐下一步：

1. 继续收尾 M0：
   明确参数解释型与一般 definition 的边界

2. 或直接进入 M1：
   修 topic resolution，使参数解释类 query 不再优先漂向 parameter_group
