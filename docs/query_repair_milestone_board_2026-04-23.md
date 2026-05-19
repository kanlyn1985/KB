# Query Repair Milestone Board

## 用途

这份文档不是再做分析，而是把查询修复工作转成可推进、可汇报、可验收的里程碑看板。

适用场景：

- 开工前对齐范围
- 迭代中跟踪进度
- 每个阶段做完成判断
- 避免继续扩散成无边界讨论

关联文档：

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)
- [query_repair_task_breakdown_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_task_breakdown_2026-04-23.md)
- [query_repair_phase0_execution_spec_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_phase0_execution_spec_2026-04-23.md)
- [query_repair_master_plan_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_master_plan_2026-04-23.md)

---

## 总目标

把 KB1 当前查询链从“经常围绕错误主题工作”推进到：

1. 上游理解稳定
2. 中游对象定位准确
3. 下游答案策略匹配问题类型
4. 无精确对象时退化可解释
5. 高频问题不依赖 fallback

---

## 里程碑总览

| 里程碑 | 名称 | 核心目标 | 状态 |
|---|---|---|---|
| M0 | Query Understanding Stabilized | 不再把问题在 rewrite 阶段理解错 | Pending |
| M1 | Topic Resolution Corrected | 不再默认漂向大表/父主题 | Pending |
| M2 | Answer Policy Split | 参数解释型不再走 general_search | Pending |
| M3 | Explainable Fallback | 无精确对象时显式近似解释 | Pending |
| M4 | Knowledge Object Enrichment | 高频细粒度对象直接命中 | Pending |
| M5 | Regression Locked | 类错误回归集固化，可持续验收 | Pending |

---

## M0：Query Understanding Stabilized

### 目标

让 query 的最终理解对象稳定，不再出现：

- `query_type` 正确但 `target_topic` 仍然错误
- `CC阻值` 被压成 `CC`
- `CP占空比` 被压成 `CP`
- 解释型问法掉进 `general_search`

### 范围

- semantic parser 输出约束
- rewrite 两阶段重构
- 解释型问法规则补齐
- 限定词保护机制
- 最小调试字段输出

### 完成定义

以下 query 通过：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `什么是V2V`

必须同时满足：

1. `final_query_type` 与问题意图一致
2. `final_target_topic` 不再是裸缩写或粗主题
3. `protected_anchor_terms` 非空
4. `rewrite_override_applied` 可观测
5. 不出现 `undefined` / 高置信 `no_answer_candidate`

### 失败判据

任意一个 query 仍满足以下任一条件，则 M0 不能算完成：

- `target_topic = CC / CP / V2V 技术` 这类粗主题
- `must_terms` 丢失限定词
- `general_search` 误接定义/解释问题

### 风险

- 规则过强导致 general_search 被误拉成 definition
- 限定词保护过强导致召回面变窄

### 依赖

- 无外部依赖，可直接开工

---

## M1：Topic Resolution Corrected

### 目标

让系统在 query 已经理解正确后，不再优先命中大表和父主题。

### 范围

- `topic_resolution.py`
- `query_api.py` 中 topic object / wiki 注入偏好
- ranking / candidate scoring

### 完成定义

以下 query 通过：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `CC阻值是多少`

必须满足：

1. top candidate 不再默认是 `parameter_group`
2. 细粒度 parameter topic / term 优先于参数总表
3. coarse parent 命中被显式降权

### 失败判据

以下现象仍存在则 M1 未完成：

- 参数解释 query 的 top1 仍是总参数表
- 细对象存在时仍优先命中父对象

### 风险

- 若细粒度对象本身稀缺，topic resolution 调整后可能暴露更多知识缺口

### 依赖

- M0 完成

---

## M2：Answer Policy Split

### 目标

把“参数解释型问题”从 `general_search` 中拆出去，建立专用回答策略。

### 范围

- `answer_policy.py`
- `answer_api.py`

### 完成定义

以下 query 通过：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `绝缘电阻是什么意思`

必须满足：

1. `answer_policy != general_search`
2. direct answer 的主结构是“意义/定义 + 依据”
3. 不再直接把大表内容当最终答案

### 失败判据

以下任一存在则 M2 未完成：

- `parameter_lookup -> general_search` 仍然保留
- direct answer 还是整表堆叠
- facts 命中了，answer 仍然空答

### 风险

- policy 拆分后，需要明确参数意义型和参数值型的边界

### 依赖

- M0 必须完成
- M1 建议完成

---

## M3：Explainable Fallback

### 目标

没有精确对象时，系统退化得可解释，不再静默漂移。

### 范围

- `answer_api.py`
- fallback reason / fallback template

### 完成定义

以下 query 通过：

- `什么是V2V`
- `V2V的定义是什么`

必须满足：

1. 如果没有直接定义，必须明确说明
2. 如果 fallback 到父概念，必须明确标记“近似解释”
3. 响应中存在 `fallback_reason`

### 失败判据

以下现象仍出现则 M3 未完成：

- 静默用 V2X 回答 V2V
- 直接空答但不说明原因

### 风险

- fallback 过于频繁会掩盖知识建模问题

### 依赖

- M0 完成
- M2 建议完成

---

## M4：Knowledge Object Enrichment

### 目标

把高频细粒度对象补进知识体系，让系统从“可退化”走到“可直接命中”。

### 范围

- `facts.py`
- `entities.py`
- `wiki_compiler.py`

### 优先补齐对象

- `V2V`
- `CC阻值`
- `CP占空比`
- `检测点电压`

### 完成定义

这些 query 的结果不再依赖父主题 fallback。

### 失败判据

若 query 仍主要依赖：

- parent concept fallback
- parameter group fallback

则 M4 未完成。

### 风险

- 如果知识补齐无规范，容易出现对象粒度混乱

### 依赖

- M0 完成
- M1 / M2 至少完成其一

---

## M5：Regression Locked

### 目标

把这类问题固化成回归集，防止后续改动再次退化。

### 范围

- regression query packs
- debug field assertions
- acceptance baselines

### 回归包

#### Pack A：限定词丢失型

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c'是什么意思`

#### Pack B：参数值型

- `CC阻值是多少`
- `CP占空比是多少`

#### Pack C：别名漂移型

- `什么是V2V`
- `V2V的定义是什么`
- `车车通信是什么`

#### Pack D：标准定义型

- `什么是控制导引电路`
- `V2G的定义是什么`

### 完成定义

每个回归 query 都有：

1. 期望 `query_type`
2. 期望 `target_topic`
3. 期望 top candidate 行为
4. 期望 answer policy
5. 期望 fallback 行为

### 依赖

- M0-M3 至少基本完成

---

## 当前推荐推进顺序

### 第一优先级

- M0

### 第二优先级

- M1
- M2

### 第三优先级

- M3

### 第四优先级

- M4
- M5

---

## 当前不应做的事

1. 不应先大规模补 synonym
2. 不应先调 rerank 当主要修法
3. 不应先改 UI 来掩盖错答
4. 不应为单个 query 写 patch
5. 不应在 M0 完成前启动大规模知识补齐

---

## 推荐周节奏

### 第 1 周

- 完成 M0
- 出最小观测字段

### 第 2 周

- 完成 M1
- 完成 M2

### 第 3 周

- 完成 M3
- 选取第一批高频对象做 M4

### 第 4 周

- 完成 M5
- 锁住回归集

---

## 管理层判断标准

如果只看一个指标，不看准确率，建议看：

> “细粒度 query 的 `target_topic` 是否已经稳定正确”

因为一旦这个指标还是错的，后面所有答对都不可持续。

---

## 最终一句话

这个项目当前最需要的不是“把答案写得更像答案”，而是：

> 让系统在最上游先认准它到底在回答哪个知识对象。
