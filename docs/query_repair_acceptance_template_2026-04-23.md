# Query Repair Acceptance Template

## 用途

这份模板用于在每个里程碑完成后，统一记录：

1. 测了什么
2. 哪些 query 通过
3. 哪些 query 失败
4. 失败属于哪一类错误
5. 下一步应该进入哪个里程碑或回退哪个模块

这份模板的目的不是替代回归测试，而是形成一套**面向里程碑的验收记录格式**。

关联文档：

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)
- [query_repair_task_breakdown_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_task_breakdown_2026-04-23.md)
- [query_repair_phase0_execution_spec_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_phase0_execution_spec_2026-04-23.md)
- [query_repair_master_plan_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_master_plan_2026-04-23.md)
- [query_repair_milestone_board_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_milestone_board_2026-04-23.md)

---

## 一、验收记录封面模板

```text
Milestone:
Date:
Executor:
Scope:
Code / Config Changes:
Observed Environment:
Acceptance Result:
  PASS / PARTIAL PASS / FAIL

Summary:
  用 3-5 句话概述本次验收结论
```

建议说明：

- `Milestone`: 例如 `M0`, `M1`, `M2`
- `Scope`: 本轮实际进入验收的模块范围
- `Code / Config Changes`: 可列文件名或 PR 范围
- `Observed Environment`: 例如本地库版本、索引版本、DB 版本、是否重建 facts/wiki

---

## 二、单 query 验收模板

每条 query 建议用同一结构记录。

```text
Query:
Expected Class:
Expected Query Type:
Expected Target Topic:
Expected Retrieval Behavior:
Expected Answer Behavior:

Observed:
  final_query_type:
  final_normalized_query:
  final_target_topic:
  protected_anchor_terms:
  rewrite_override_applied:
  topic_resolution_top_candidates:
  retrieval_channels:
  answer_policy:
  fallback_reason:
  direct_answer_summary:

Result:
  PASS / FAIL

Failure Class:
  限定词丢失型 / 别名漂移型 / 类型判定错位型 / 主题锚点粗化型 /
  召回通道错配型 / 答案策略错配型 / 知识建模缺口型 / 未分类

Notes:
  记录一句话判断：问题首发层在哪里，是否已比上一轮改善
```

---

## 三、里程碑级通过判定模板

每个 milestone 不能靠“主观觉得差不多”通过，建议用下面结构。

```text
Milestone Gate:
  Gate 1:
  Gate 2:
  Gate 3:
  Gate 4:

Gate Result:
  全通过 / 有条件通过 / 不通过

Blocking Issues:
  列出阻塞项

Carry-over Issues:
  列出允许带入下一里程碑的问题
```

---

## 四、M0 验收模板

### M0 目标

`Query Understanding Stabilized`

### M0 必过 Gate

```text
Gate 1:
  解释型问法不再错误落入 general_search

Gate 2:
  target_topic 不再退化为裸缩写或粗主题

Gate 3:
  protected_anchor_terms 可观测且对限定词有效

Gate 4:
  rewrite_override_applied 发生时，target_topic 已同步纠正
```

### M0 建议验收包

```text
Pack A:
  CC阻值代表什么意思
  CP占空比是什么意思
  检测点1电压表示什么
  R4c'是什么意思

Pack B:
  什么是V2V
  V2V的定义是什么
  什么是控制导引电路
```

### M0 通过标准

建议：

- Pack A 至少 `80%` 通过
- Pack B 至少 `80%` 通过
- 不允许存在：
  - `target_topic = undefined`
  - 高置信 `no_answer_candidate`
  - 裸缩写 target_topic 仍大面积出现

### M0 允许带入下一阶段的问题

允许：

- 答案还不够漂亮
- topic resolution 还偏父主题
- parameter answer 还不够解释型

不允许：

- query 还在最上游被理解错

---

## 五、M1 验收模板

### M1 目标

`Topic Resolution Corrected`

### M1 必过 Gate

```text
Gate 1:
  parameter / term 类 query 不再默认命中 parameter_group

Gate 2:
  top candidate 与 target_topic 粒度一致

Gate 3:
  父主题命中时有显式降权迹象
```

### M1 建议验收包

```text
CC阻值代表什么意思
CP占空比是什么意思
CC阻值是多少
CP占空比是多少
```

### M1 通过标准

- 参数解释 query 的 top1 不再默认是大表
- 若细粒度对象存在，应稳定优先命中

### M1 允许带入下一阶段的问题

允许：

- direct answer 仍不够好

不允许：

- topic resolution 仍主要围绕父主题工作

---

## 六、M2 验收模板

### M2 目标

`Answer Policy Split`

### M2 必过 Gate

```text
Gate 1:
  parameter explanation query 不再走 general_search

Gate 2:
  direct answer 结构符合参数解释问题预期

Gate 3:
  facts 已命中时，不再返回“没有足够的结构化结果”
```

### M2 建议验收包

```text
CC阻值代表什么意思
CP占空比是什么意思
绝缘电阻是什么意思
```

### M2 通过标准

- `answer_policy != general_search`
- direct answer 以解释性输出为主，而不是证据堆叠

### M2 允许带入下一阶段的问题

允许：

- 缺少精确对象时仍需 fallback

不允许：

- 参数解释问题还按通用搜索回答

---

## 七、M3 验收模板

### M3 目标

`Explainable Fallback`

### M3 必过 Gate

```text
Gate 1:
  无精确对象时，响应包含 fallback_reason

Gate 2:
  使用父概念替代时，明确标注近似解释

Gate 3:
  不再出现静默漂移
```

### M3 建议验收包

```text
什么是V2V
V2V的定义是什么
车车通信是什么
```

### M3 通过标准

- fallback 可见、可解释、可归因

---

## 八、M4 验收模板

### M4 目标

`Knowledge Object Enrichment`

### M4 必过 Gate

```text
Gate 1:
  高频 query 不再依赖 parent fallback

Gate 2:
  term / parameter topic / definition fact 已补齐

Gate 3:
  wiki page 与 entity 粒度一致
```

### M4 建议验收包

```text
什么是V2V
CC阻值代表什么意思
CP占空比是什么意思
检测点1电压表示什么
```

### M4 通过标准

- 高频细粒度 query 的直接命中率明显提升

---

## 九、里程碑验收结果模板

每次验收后，建议输出如下总结：

```text
Milestone Result:
  PASS / PARTIAL PASS / FAIL

What Improved:
  列出 3-5 项本轮明确改善的现象

What Still Fails:
  列出 3-5 项仍失败的问题

Root Cause of Remaining Failures:
  说明剩余失败主要集中在哪一层

Go / No-Go Decision:
  是否进入下一里程碑

Next Action:
  下一轮改动重点
```

---

## 十、失败归因模板

如果某个 query 没通过，不建议只写“失败”，建议用下面模板：

```text
Query:

Primary Failure Layer:
  semantic parse / rewrite / topic resolution / retrieval / answer policy / knowledge gap

Failure Mechanism:
  用一句话描述错误是怎样产生的

Is This New or Known:
  new / known / regressed

Should Block Milestone:
  yes / no

Reason:
  为什么它会阻塞或不阻塞当前里程碑
```

---

## 十一、建议的验收节奏

### 开发中验收

每完成一个模块改动，就跑对应的最小 query 包。

### 合并前验收

至少跑当前 milestone 的完整 query 包。

### 里程碑完成验收

必须形成一份正式记录，按本模板存档。

---

## 十二、建议的存档方式

建议每个里程碑单独产出：

- `query_repair_m0_acceptance_YYYY-MM-DD.md`
- `query_repair_m1_acceptance_YYYY-MM-DD.md`
- `query_repair_m2_acceptance_YYYY-MM-DD.md`

内容按本模板填写。

这样后面回看时能快速看出：

- 哪一轮解决了什么
- 哪些问题是在后续重新回归的

---

## 十三、最终建议

如果下一步准备进入代码实施，建议：

1. 先以这份模板为准建立 `M0` 验收记录文件
2. 再开始 `Phase 0` 代码改动
3. 每改完一个模块就即时填一次验收记录，不要等全部做完再统一回忆

这样能避免两种常见问题：

- 改完很多，但说不清具体改善了什么
- 某个修复导致旧问题回归，却在最后才发现
