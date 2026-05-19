# Query Repair M4 Postpatch Acceptance

## 封面

```text
Milestone:
  M4 - Knowledge Object Enrichment

Date:
  2026-04-23

Executor:
  Codex

Scope:
  为高频参数类问题补细粒度 parameter_topic 与 wiki page

Code Changes:
  [entities.py](E:/AI_Project\\opencode_workspace\\KB1\\src\\enterprise_agent_kb\\entities.py)

Data Rebuild:
  DOC-000002
  DOC-000003

Observed Environment:
  运行期 DB: E:/AI_Project/opencode_workspace/KB1/knowledge_base/db/knowledge.db
  API 在线

Acceptance Result:
  PASS
```

## Summary

这轮 `M4` 的目标不是调回答模板，而是补足：

> 高频参数类 query 缺少细粒度知识对象，只能围着父主题或参数总表兜圈子。

本轮已经完成：

1. `CC阻值`
2. `CP占空比`
3. `检测点1电压`

这些对象的 `parameter_topic` 构建与对应 wiki page 生成。

从数据库与运行期 `query-context` 验证看：

- 这些对象已经真实进入 `entities` 与 `wiki_pages`
- `query-context` 的 `topic_resolution` 已能直接把它们排到 top1

这意味着 `M4` 的核心目标已经达成：

> 高频参数问题开始具备“直接命中细粒度对象”的能力，不再完全依赖 fallback。

---

## 数据验证

### 新增 parameter_topic

在 `knowledge_base/db/knowledge.db` 中确认存在：

- `CC阻值`
- `CP占空比`
- `检测点1电压`
- `检测点3电压`

并生成了对应的 `parameter_topics/*.md` wiki 页面。

---

## Query Records

### Query 1

```text
Query:
  CC阻值代表什么意思

Observed:
  topic_resolution top1:
    CC阻值 (parameter_topic)

  answer_mode:
    parameter_meaning

  direct_answer:
    CC阻值 表示 连接确认回路中的等效电阻参数，用于反映车辆接口连接状态。依据来自 A.2 充电控制导引电路。

Result:
  PASS
```

### Query 2

```text
Query:
  CP占空比是什么意思

Observed:
  topic_resolution top1:
    CP占空比 (parameter_topic)

  answer_mode:
    parameter_meaning

  direct_answer:
    CP占空比（符号 Dco） 表示 控制导引 PWM 信号中的占空比参数，用于表达供电设备可用电流或控制状态。相关值为标称值 ——，范围 max +0.5% / min -0.5%。依据来自 表 A.1 控制导引电路的参数。

Result:
  PASS
```

### Query 3

```text
Query:
  检测点1电压表示什么

Observed:
  topic_resolution top1:
    检测点1电压 (parameter_topic)

  answer_mode:
    parameter_meaning

  direct_answer:
    检测点1电压（符号 U1a） 表示 控制导引回路中的检测点电压参数，用于判断当前连接或控制状态。相关值为标称值 12V，范围 max 12.8 / min 11.2。依据来自 B.3.1 充电控制导引电路。

Result:
  PASS
```

---

## Gate 检查

```text
Gate 1:
  高频 query 不再依赖 parent fallback
  Result: PASS

Gate 2:
  term / parameter topic / wiki page 已补齐
  Result: PASS

Gate 3:
  wiki page 与 entity 粒度一致
  Result: PASS
```

---

## What Improved

```text
1. 高频参数解释 query 已能直接命中细粒度 parameter_topic
2. parameter_group 不再是唯一可用对象
3. wiki 层已经为这些对象生成独立页面
4. answer 层开始建立在更细粒度知识对象上工作
```

---

## What Still Fails

```text
1. V2V 这类术语缺口仍然依赖 M3 fallback，而未形成直接对象
2. 参数值型 query 仍可继续拆出更细的 answer policy
3. topic_entities 对新 parameter_topic 的对齐还可进一步优化
```

---

## Root Cause of Remaining Failures

当前剩余问题已经不再是“高频参数对象缺失”，而是：

1. 非参数术语对象（如 V2V）仍未显式建模
2. 回归体系尚未正式固化

也就是说，`M4` 已完成，下一步应进入 `M5`。

---

## Go / No-Go Decision

```text
Go / No-Go:
  GO

Decision Meaning:
  可以进入 M5，不需要继续停留在“高频参数对象缺失”的补齐阶段。
```

---

## Next Action

推荐下一步：

进入 `M5`：

1. 固化类错误回归包
2. 建立 M0-M4 的统一验收快照
3. 确保未来改动不会把这轮修复回退掉
