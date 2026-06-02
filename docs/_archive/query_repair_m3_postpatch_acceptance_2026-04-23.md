# Query Repair M3 Postpatch Acceptance

## 封面

```text
Milestone:
  M3 - Explainable Fallback

Date:
  2026-04-23

Executor:
  Codex

Scope:
  为无精确定义对象的 definition query 增加显式 fallback_reason 与近似解释模板

Code Changes:
  [answer_api.py](E:/AI_Project\\opencode_workspace\\KB1\\src\\enterprise_agent_kb\\answer_api.py)

Observed Environment:
  API restarted at 2026-04-23T03:45:07+00:00
  Health check passed

Acceptance Result:
  PASS
```

## Summary

这轮 `M3` 的目标是：

> 当知识库里没有精确定义对象时，系统不再空答或静默漂移，而是显式给出近似解释。

从运行结果看，这个目标已经达成：

1. `什么是V2V`
2. `V2V的定义是什么`

这两类 query 现在都返回：

- `answer_mode = definition`
- `fallback_reason = fallback_to_related_concept`
- direct answer 明确说明：
  - 没找到 `V2V` 的直接定义
  - 当前最近的相关概念是 `V2X`
  - 以下内容是近似解释，不是精确定义

这正是 `M3` 设计要求的“可解释退化”。

---

## Gate 检查

```text
Gate 1:
  无精确对象时，响应包含 fallback_reason
  Result: PASS

Gate 2:
  使用父概念替代时，明确标注近似解释
  Result: PASS

Gate 3:
  不再出现静默漂移
  Result: PASS
```

---

## Query Records

### Query 1

```text
Query:
  什么是V2V

Observed:
  answer_mode: definition
  fallback_reason: fallback_to_related_concept
  direct_answer:
    知识库中未找到 V2V 的直接定义。
    当前最接近的相关概念是 电动汽车充放电双向互动 vehicle to X: V2X：...
    以下内容为近似解释，不是 V2V 的精确定义。

Result:
  PASS
```

### Query 2

```text
Query:
  V2V的定义是什么

Observed:
  answer_mode: definition
  fallback_reason: fallback_to_related_concept
  direct_answer:
    知识库中未找到 V2V 的直接定义。
    当前最接近的相关概念是 电动汽车充放电双向互动 vehicle to X: V2X：...
    以下内容为近似解释，不是 V2V 的精确定义。

Result:
  PASS
```

---

## What Improved

```text
1. 定义型空答已具备显式 fallback_reason
2. 近似解释模板已落地
3. V2V 不再静默漂移或直接空答
4. fallback 行为开始可观察、可归因
```

---

## What Still Fails

```text
1. 当前近似解释只覆盖了 related concept fallback，还没覆盖更多 fallback 类别
2. topic_resolution 本身对 V2V 的候选排序仍然不理想，fallback 依赖额外 related-term 搜索
3. 高频缺对象问题最终仍需要 M4 的知识补齐
```

---

## Root Cause of Remaining Failures

当前剩余问题已经不再是“fallback 不可解释”，而是：

1. 知识对象本身缺失
2. topic resolution 对这类缺失对象的候选还不够稳

也就是说，`M3` 的主任务已经完成，剩余压力转移到了 `M4`。

---

## Go / No-Go Decision

```text
Go / No-Go:
  GO

Decision Meaning:
  可以进入 M4，不需要继续围绕“V2V 是否静默漂移”反复微调。
```

---

## Next Action

推荐下一步：

进入 `M4`：

1. 为高频缺失对象补 term / parameter topic / definition fact / wiki page
2. 优先补：
   - V2V
   - CC阻值
   - CP占空比
   - 检测点电压
