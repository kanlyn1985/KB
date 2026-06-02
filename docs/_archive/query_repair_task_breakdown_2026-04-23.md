# Query Repair Task Breakdown

## 文档定位

这份清单承接两份上游文档：

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)

目标是把“修复策略”进一步拆成：

1. 具体改哪些文件
2. 每个文件承担什么变更职责
3. 每个任务的输入/输出边界是什么
4. 改完用哪些 query 验收

这份清单仍然不写代码，只定义实施任务。

---

## 一、总实施原则

### 原则 1：先修一致性，再修精度

先保证：

- `query_type`
- `normalized_query`
- `target_topic`
- `must_terms`

之间是相互一致的。

如果这一层不一致，后面所有检索与答案优化都只是围绕错主题做增强。

### 原则 2：按“类错误”组织任务，不按单 query 组织任务

任务组织单位应是：

- 限定词丢失型
- 别名漂移型
- 参数解释型
- fallback 近似解释型

而不是：

- 修 `CC阻值`
- 修 `V2V`

### 原则 3：每个任务都要有“可观测性输出”

任何模块改动，只要影响 query 理解链路，都必须同步定义：

- 新增什么 debug 字段
- 如何看出这次修复是否生效

---

## 二、Phase 0 任务拆解

Phase 0 的目标是止血：

> 消除“类型对了、主题还错着”的半修正状态。

---

### Task 0.1

文件：

- [query_rewrite.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_rewrite.py)

任务名称：

- Rewrite 两阶段重构

当前问题：

- semantic parse 产出的 `normalized_query / target_topic` 会直接进入最终 rewrite
- 即使规则纠正了 `query_type`，topic anchor 不会跟着纠正

需要改的点：

1. 拆成两个显式阶段：
   - intent selection
   - anchor reconstruction
2. 增加“最终意图决定最终 topic anchor”的约束
3. 若规则 override 了 query type，必须触发 anchor rebuild

输入：

- original query
- semantic parser output
- rule-based intent detection result

输出：

- final query_type
- final normalized_query
- final target_topic
- final must_terms
- final should_terms
- rewrite_override_applied

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`

验收标准：

- `normalized_query` 不再退化成裸缩写
- `target_topic` 保留限定词
- `must_terms` 中保留细粒度锚点

---

### Task 0.2

文件：

- [query_rewrite.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_rewrite.py)

任务名称：

- 定义解释型问法规则补齐

当前问题：

- `_normalize_query()` 和 `_detect_query_type()` 对“代表什么意思/表示什么/指什么/含义是什么”覆盖不足

需要改的点：

1. 补充解释型问法正则集合
2. 区分“定义型问法”和“参数解释型问法”
3. 让解释型问法不再默认掉入 `general_search`

输入：

- original query

输出：

- 更稳定的 rule_query_type
- 更合理的 normalized_query

验收 query：

- `CC阻值代表什么意思`
- `V2V的定义是什么`
- `CP占空比表示什么`
- `绝缘电阻含义是什么`

验收标准：

- 这些问法不能落入 `general_search`

---

### Task 0.3

文件：

- [query_rewrite.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_rewrite.py)

任务名称：

- 限定词保护机制

当前问题：

- `CC阻值`、`CP占空比`、`检测点1电压` 这类结构会在 rewrite 时被压粗

需要改的点：

1. 定义保护锚点抽取器
2. 把保护锚点直接写入 `must_terms`
3. 对保护锚点建立“不可退化”约束

建议保护模式：

- 缩写 + 参数词
- 缩写 + 数值属性
- 检测点 + 编号 + 属性
- 参数符号 + 下标 / 撇号

输出：

- protected_anchor_terms

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c'是什么意思`

验收标准：

- `protected_anchor_terms` 非空
- target_topic 中体现被保护锚点

---

### Task 0.4

文件：

- [query_semantic_parser.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_semantic_parser.py)

任务名称：

- Semantic parser 输出质量约束

当前问题：

- semantic parser 会产出高置信但明显错误的结果
- 会产出 `target_topic = undefined`
- 会把 query_type 判成 `no_answer_candidate`

需要改的点：

1. 收紧 system prompt 对解释型 query 的要求
2. 增加低质量输出过滤
3. 对明显坏输出做兜底降级

建议增加的坏输出规则：

- `target_topic` 为空或 `undefined`
- `normalized_query` 只剩缩写，但原 query 含限定词
- `must_terms` 为空且 confidence 高

输出：

- semantic_quality_flags

验收 query：

- `CC阻值代表什么意思`
- `什么是V2V`
- `CP占空比是什么意思`

验收标准：

- 不再出现 `undefined`
- 不再高置信输出 `no_answer_candidate`

---

## 三、Phase 1 任务拆解

Phase 1 的目标是链路纠偏：

> 让 query 已经识别对之后，topic resolution / retrieval / answer policy 真正走对路径。

---

### Task 1.1

文件：

- [topic_resolution.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/topic_resolution.py)

任务名称：

- Parameter 类候选优先级重排

当前问题：

- `parameter_lookup` 容易优先命中 `parameter_group`
- 结果被大表吸走

需要改的点：

1. 明确定义 `parameter_topic > term > parameter_group`
2. 为完整命中保护锚点的候选增加 bonus
3. 为仅命中父主题的大对象增加 penalty

输入：

- final rewritten query
- protected anchor terms

输出：

- ranked candidate_entities
- candidate_score_breakdown

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`

验收标准：

- top candidate 不应默认是参数总表

---

### Task 1.2

文件：

- [retrieval_router.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/retrieval_router.py)

任务名称：

- 参数解释型 routing 拆分

当前问题：

- `parameter_lookup` 语义过宽
- 参数解释类和参数值类共用一条 routing

需要改的点：

1. 定义内部细分 query mode：
   - parameter_meaning
   - parameter_value_lookup
2. 为参数解释型定义新的 channel priority
3. 避免 document 成为首通道

输出：

- retrieval_mode
- retrieval_channels

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `绝缘电阻是什么意思`

验收标准：

- 首通道应优先 facts/wiki，而非 document

---

### Task 1.3

文件：

- [query_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_api.py)

任务名称：

- direct wiki/fact 注入偏好修正

当前问题：

- 对参数解释型 query，当前直注逻辑更容易引大而泛的 wiki/item

需要改的点：

1. 让 parameter explanation 优先注入 parameter topic / term wiki
2. 降低 parameter group 的默认注入优先级
3. 保留 coarse object 作为 fallback，不作主入口

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`

验收标准：

- 直接注入的 wiki 不应默认是总参数表页

---

### Task 1.4

文件：

- [answer_policy.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_policy.py)
- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

任务名称：

- 参数解释型 answer policy 新增

当前问题：

- `parameter_lookup -> general_search`

需要改的点：

1. 新增 policy：
   - parameter_meaning
   - parameter_value
2. 定义 parameter meaning 的 direct answer builder
3. 定义 parameter meaning 的 fallback 顺序

输出：

- answer_policy
- answer_builder_path

验收 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`

验收标准：

- 不能直接返回整表片段
- 应输出“参数意义 + 依据”形式答案

---

## 四、Phase 2 任务拆解

Phase 2 的目标是可解释退化：

> 当库里没有精确对象时，系统要显式说明自己在做近似解释。

---

### Task 2.1

文件：

- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

任务名称：

- fallback reason 标准化

需要改的点：

定义统一 fallback reason：

- missing_exact_term
- fallback_to_parent_concept
- fallback_to_parameter_group
- fallback_to_evidence_only

输出：

- fallback_reason
- fallback_level

验收 query：

- `什么是V2V`
- `V2V的定义是什么`

验收标准：

- 若不是精确命中，响应中必须可见 fallback 原因

---

### Task 2.2

文件：

- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)

任务名称：

- 近似解释模板

需要改的点：

为“上位概念替代”设计统一回答模板：

```text
知识库中未找到 X 的直接定义。
当前最接近的相关概念是 Y。
以下内容是近似解释，不是 X 的精确定义。
```

验收 query：

- `什么是V2V`

验收标准：

- 不允许静默用 V2X 解释 V2V

---

## 五、Phase 3 任务拆解

Phase 3 的目标是补知识对象。

---

### Task 3.1

文件：

- [facts.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/facts.py)
- [entities.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/entities.py)
- [wiki_compiler.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/wiki_compiler.py)

任务名称：

- 细粒度参数/术语对象补齐

优先对象：

- V2V
- CC阻值
- CP占空比
- 检测点电压

需要改的点：

1. 补 definition/meaning 类 fact
2. 补细粒度 entity
3. 补独立 wiki page

验收标准：

- 这些 query 不再只能 fallback 到父主题

---

## 六、回归任务清单

### 回归包 A：限定词丢失型

query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c'是什么意思`

检查字段：

- query_type
- target_topic
- must_terms
- protected_anchor_terms
- top candidate entities
- answer_policy
- direct_answer

---

### 回归包 B：参数值型

query：

- `CC阻值是多少`
- `CP占空比是多少`

检查字段：

- query_type
- target_topic
- selected facts
- direct_answer

---

### 回归包 C：别名漂移型

query：

- `什么是V2V`
- `V2V的定义是什么`
- `车车通信是什么`

检查字段：

- topic_resolution candidates
- fallback_reason
- direct_answer

---

### 回归包 D：定义型

query：

- `什么是控制导引电路`
- `V2G的定义是什么`

检查字段：

- answer_policy 是否为 definition
- direct_answer 是否优先 term_definition / concept_definition

---

## 七、每个任务必须增加的观测字段

不管哪个模块改动，最终至少应能看到：

- final_query_type
- final_normalized_query
- final_target_topic
- protected_anchor_terms
- rewrite_override_applied
- semantic_quality_flags
- topic_resolution_top_candidates
- retrieval_mode
- retrieval_channels
- answer_policy
- fallback_reason

这组字段是以后排查同类错误的最低配置。

---

## 八、实施优先级

### P0

- Task 0.1 Rewrite 两阶段重构
- Task 0.2 解释型问法规则补齐
- Task 0.3 限定词保护机制
- Task 0.4 semantic 输出质量约束

### P1

- Task 1.1 parameter topic resolution 优先级重排
- Task 1.2 参数解释 routing 拆分
- Task 1.4 参数解释 answer policy

### P2

- Task 1.3 wiki/fact 注入偏好修正
- Task 2.1 fallback reason 标准化
- Task 2.2 近似解释模板

### P3

- Task 3.1 细粒度知识对象补齐

---

## 九、建议的执行节奏

### Sprint 1

目标：

- 消除 anchor 丢失

交付：

- Rewrite 一致性修复
- 解释型问法覆盖
- 最小观测字段

### Sprint 2

目标：

- 让参数解释型问句真正答对

交付：

- parameter meaning routing
- parameter meaning answer policy
- topic resolution 优先级修正

### Sprint 3

目标：

- 让没有精确对象的问题也能“解释地退化”

交付：

- fallback reason
- 近似解释模板

### Sprint 4

目标：

- 提升稳定性，不再依赖 fallback

交付：

- 细粒度知识对象补齐
- 类错误回归集固化

---

## 十、最终实施判断

如果只能先做 3 件事，优先级必须是：

1. Rewrite 一致性修复
2. 参数解释型 answer policy
3. Topic resolution 细粒度优先

因为这 3 件事决定了：

> 系统到底是在围绕正确知识对象工作，还是继续围绕一个大而泛的父主题打转。
