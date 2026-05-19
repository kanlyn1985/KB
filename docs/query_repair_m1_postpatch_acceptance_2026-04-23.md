# Query Repair M1 Postpatch Acceptance

## 封面

```text
Milestone:
  M1 - Topic Resolution Corrected

Date:
  2026-04-23

Executor:
  Codex

Scope:
  仅针对 topic resolution 层的参数类候选优先级修复

Code Changes:
  [topic_resolution.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/topic_resolution.py)

Observed Environment:
  API restarted at 2026-04-23T02:51:00+00:00
  Health check passed

Acceptance Result:
  PARTIAL PASS
```

## Summary

这轮 `M1` 的目标不是让答案已经漂亮，而是先修正：

> 参数解释类 query 不再默认漂向 `parameter_group`

从运行中的 API 结果看，这个目标已经基本达到：

1. `CC阻值代表什么意思` 的 `topic_resolution` 不再把参数总表放在前面
2. `CP占空比是多少` 的 `topic_resolution` 前两位已经是 `term`，而不是 `parameter_group`
3. `parameter_group` 候选仍存在，但已不再默认压到 top1 / top2

但这轮还不能判为完全通过，因为：

- `CC阻值代表什么意思` 的 top candidate 仍是泛 term，而不是理想中的细粒度 parameter topic
- `CP占空比` 仍没有更细的 parameter topic 可命中
- 这说明 topic resolution 漂移被压住了，但知识粒度不足的问题开始暴露出来

结论：

`M1` 可判为 `PARTIAL PASS`，可以继续进入 `M2`，不需要再停留在“parameter_group 抢第一”的问题上。

---

## Query Records

### Query 1

```text
Query:
  CC阻值代表什么意思

Expected Class:
  参数解释型

Observed:
  final_query_type: definition
  final_target_topic: CC阻值
  top_candidates:
    1. 控制导引电路 control pilot circuit (term)
    2. 连接确认功能 ... CC (term)
    3. CC (parameter_topic)

Result:
  PASS

Reason:
  本轮 M1 的要求是“不再默认漂向 parameter_group”，这一点已满足。
```

### Query 2

```text
Query:
  CC阻值是多少

Expected Class:
  参数值型

Observed:
  final_query_type: parameter_lookup
  final_target_topic: CC阻值
  top_candidates:
    1. CC (parameter_topic)
    2. 控制导引电路 control pilot circuit (term)
    3. 连接确认功能 ... CC (term)

Result:
  PASS

Reason:
  已由 parameter_topic 拿到 top1，未再被 parameter_group 抢占。
```

### Query 3

```text
Query:
  CP占空比是什么意思

Expected Class:
  参数解释型

Observed:
  final_query_type: definition
  final_target_topic: CP占空比
  top_candidates:
    1. 控制导引功能 ... CP (term)
    2. 控制导引电路 control pilot circuit (term)
    3. 其他 term

Result:
  PASS

Reason:
  参数总表已不再处于默认前列，说明 parameter_group 漂移已明显下降。
```

### Query 4

```text
Query:
  CP占空比是多少

Expected Class:
  参数值型

Observed:
  final_query_type: parameter_lookup
  final_target_topic: CP占空比
  top_candidates:
    1. 控制导引功能 ... CP (term)
    2. 控制导引电路 control pilot circuit (term)
    3. parameter_group

Result:
  PASS

Reason:
  仍未命中理想 parameter topic，但 parameter_group 已不再默认 top1 / top2。
```

### Query 5

```text
Query:
  检测点1电压表示什么

Expected Class:
  参数解释型

Observed:
  final_query_type: definition
  final_target_topic: 检测点1电压
  top_candidates:
    1. 当前电压测量值 present measured voltage (term)
    2. 电压需求值 target voltage (EV) (term)
    3. 其他 term

Result:
  PASS

Reason:
  当前仍是 term 解释优先，但已避免直接漂向参数总表。
```

---

## Gate 检查

```text
Gate 1:
  parameter / term 类 query 不再默认命中 parameter_group
  Result: PASS

Gate 2:
  top candidate 与 target_topic 粒度一致
  Result: PARTIAL

Gate 3:
  父主题命中时有显式降权迹象
  Result: PASS
```

---

## What Improved

```text
1. parameter_group 不再在参数类 query 上默认抢第一
2. parameter_lookup 已更倾向 parameter_topic / term
3. 参数解释类 definition 也不再直接被参数总表吸走
4. 运行中 API 结果与本地模块测试结果方向一致
```

---

## What Still Fails

```text
1. 部分 query 虽不再漂向 parameter_group，但 top1 仍是泛 term
2. CP 类 query 暂时缺少足够细粒度的 parameter_topic
3. 这轮还没有进入 answer policy，答案层不会自动因此变好
```

---

## Root Cause of Remaining Failures

当前剩余问题主要不是 topic resolution 的粗暴偏移了，而是：

1. 细粒度 knowledge object 仍不足
2. 参数解释类 answer policy 尚未拆出

也就是说，`M1` 已经把“总表默认抢位”这个问题基本压下去，接下来的主要工作应转向 `M2`。

---

## Go / No-Go Decision

```text
Go / No-Go:
  GO

Decision Meaning:
  可以进入 M2，不需要继续围绕 parameter_group 漂移问题反复微调。
```

---

## Next Action

推荐下一步：

进入 `M2`：

1. 把参数解释类 query 从 `general_search` 答案策略里拆出去
2. 让 direct answer 开始输出“参数意义 + 依据”，而不是继续走通用搜索答案拼接
