# Query Repair Master Plan

## 文档目的

这是一份单页总纲，用来把当前 KB1 查询链问题、修复方向、实施顺序、验收标准压缩到一个可决策、可跟进的统一视图中。

它是以下文档的汇总版：

- [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md)
- [query_repair_blueprint_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_blueprint_2026-04-23.md)
- [query_repair_task_breakdown_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_task_breakdown_2026-04-23.md)
- [query_repair_phase0_execution_spec_2026-04-23.md](E:/AI_Project/opencode_workspace/KB1/docs/query_repair_phase0_execution_spec_2026-04-23.md)

---

## 一、当前问题的一句话定义

KB1 当前最核心的问题不是“完全没有召回”，而是：

> 细粒度问题在查询链上游被压粗，后续各层围绕错误主题工作，最后表现成错答、泛答、空答或近似漂移。

典型例子：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `什么是V2V`

---

## 二、根因总括

### 根因 1：查询理解失真

表现：

- `query_type`、`normalized_query`、`target_topic`、`must_terms` 不一致
- 系统知道“这是参数类问题”，但不知道“在问哪个参数”

### 根因 2：主题锚点粗化

表现：

- `CC阻值` 被压成 `CC`
- `CP占空比` 被压成 `CP`
- `V2V` 被拉向 `V2X`

### 根因 3：参数解释类策略缺位

表现：

- 参数解释问题被当作 `general_search`
- 回答结果偏整表、偏大段片段、偏证据堆叠

### 根因 4：知识对象粒度不足

表现：

- 缺少细粒度 term / parameter topic / definition fact / wiki page

---

## 三、总体修复策略

### 战略原则

先修“理解链路”，再修“召回与答案”，最后补“知识对象”。

不要反过来做。

原因：

- 如果主题一开始就错了
- rerank 越优化，错对象排得越漂亮
- synonym 越补，漂移面越大
- answer 模板越丰富，错答越像正确答案

---

## 四、实施总路线

## Phase 0：让系统先知道自己在回答什么

### 目标

修复 query rewrite 一致性，让系统不再出现“类型对了、主题错了”的半修正状态。

### 解决的问题

- 解释型问法误判
- 限定词丢失
- semantic parser 坏输出未被兜底
- rewrite 与 rule override 不一致

### 关键交付

- 两阶段 rewrite
- 限定词保护机制
- 解释型问法规则覆盖
- 最小调试字段输出

### 完成标准

对以下 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `什么是V2V`

要求：

- 不再掉进错误意图
- `target_topic` 不再退化成粗主题
- `must_terms` 保留细粒度锚点

---

## Phase 1：让系统围绕正确对象工作

### 目标

让 topic resolution、retrieval routing、answer policy 围绕细粒度对象工作，而不是围绕父主题/大表工作。

### 解决的问题

- parameter group 过度命中
- routing 通道错配
- 参数解释问题没有专用 answer policy

### 关键交付

- parameter topic 优先
- 参数解释型 routing
- 参数解释型 answer policy

### 完成标准

对参数解释类 query：

- top candidate 不再默认是总表
- facts/wiki 优先于泛 evidence/document
- answer 不再默认输出总表片段

---

## Phase 2：让退化是显式的，而不是偷偷漂移

### 目标

对缺少精确对象的问题，建立可解释 fallback。

### 解决的问题

- `V2V` 静默漂到 `V2X`
- 相关概念替代没有显式提示

### 关键交付

- fallback reason
- parent concept fallback
- 近似解释模板

### 完成标准

对无精确定义对象的问题：

- 系统必须说明“当前是近似解释”

---

## Phase 3：让高频问题不再依赖 fallback

### 目标

补足细粒度知识对象，让系统能直接命中而不是长期依赖退化解释。

### 关键交付

- 细粒度 term
- parameter topic
- definition fact
- wiki page

### 完成标准

高频 query 直接命中目标对象，不再优先走父主题替代。

---

## 五、模块总表

| 模块 | 当前主要问题 | 修复重点 | 优先级 |
|---|---|---|---|
| `query_semantic_parser.py` | 高置信坏输出、解释型问法不稳 | 输出质量约束、解释型模式 | P0 |
| `query_rewrite.py` | 类型与主题不一致、限定词丢失 | 两阶段 rewrite、限定词保护 | P0 |
| `topic_resolution.py` | 大对象优先、parameter group 过强 | 细粒度对象优先、父主题惩罚 | P1 |
| `retrieval_router.py` | 参数解释类 routing 错配 | parameter meaning routing | P1 |
| `query_api.py` | wiki/fact 注入偏粗 | 细粒度对象注入优先 | P1 |
| `answer_policy.py` | parameter_lookup 映射到 general_search | 参数解释专用 policy | P1 |
| `answer_api.py` | fallback 不可解释、答案拼接不对类 | fallback reason、近似解释模板 | P1/P2 |
| `facts.py / entities.py / wiki_compiler.py` | 细粒度对象不足 | term/parameter topic/definition 补齐 | P3 |

---

## 六、必须先修的 3 件事

如果只能先做 3 件事，顺序必须是：

1. `rewrite consistency`
2. `parameter meaning answer policy`
3. `topic resolution` 细粒度优先

原因：

- 第 1 项修“理解错”
- 第 2 项修“回答错类”
- 第 3 项修“对象跑偏”

只做第 2 或第 3，不做第 1，收益会明显打折。

---

## 七、不推荐的修法

### 不推荐 1：只补 synonym

问题：

- 只能扩大召回面，不能稳定 topic 锚点

### 不推荐 2：只调 rerank

问题：

- 主题一旦错了，rerank 只是把错对象排得更高

### 不推荐 3：只修 answer 模板

问题：

- supporting facts 不对时，模板越漂亮，错答越像对答

### 不推荐 4：按单 query 打补丁

问题：

- 会快速积累不可维护的特例逻辑

---

## 八、验收总原则

不要只看“最终有没有答出来”，必须同时看：

1. 意图是否对
2. topic anchor 是否对
3. top candidate 是否细粒度优先
4. answer policy 是否匹配问题类型
5. fallback 是否可解释

---

## 九、验收用 query 包

### Query Pack A：限定词丢失型

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c'是什么意思`

### Query Pack B：参数值型

- `CC阻值是多少`
- `CP占空比是多少`

### Query Pack C：别名漂移型

- `什么是V2V`
- `V2V的定义是什么`
- `车车通信是什么`

### Query Pack D：标准定义型

- `什么是控制导引电路`
- `V2G的定义是什么`

---

## 十、必须暴露的最小调试字段

后续所有修复都应至少暴露：

- `final_query_type`
- `final_normalized_query`
- `final_target_topic`
- `protected_anchor_terms`
- `rewrite_override_applied`
- `semantic_quality_flags`
- `topic_resolution_top_candidates`
- `retrieval_channels`
- `answer_policy`
- `fallback_reason`

没有这组字段，后续维护成本会重新升高。

---

## 十一、建议的推进顺序

### Sprint 1

范围：

- semantic parser 输出约束
- rewrite consistency
- 解释型问法识别
- 限定词保护

目标：

- 不再把 query 在最上游理解错

### Sprint 2

范围：

- topic resolution 调整
- retrieval routing 拆分
- parameter meaning answer policy

目标：

- 参数解释类问题能稳定围绕正确对象作答

### Sprint 3

范围：

- fallback reason
- 近似解释模板

目标：

- 缺知识时仍然可解释，不再静默漂移

### Sprint 4

范围：

- term / parameter topic / wiki / definition 补齐
- 回归集固化

目标：

- 高频 query 直接命中，不依赖 fallback

---

## 十二、最终决策建议

如果现在立刻进入代码实施，建议只做一件事：

> 先按 Phase 0 开始，不要跳到召回优化或知识补齐。

因为当前系统最该先修的不是“查更多”，而是“别把用户问题先理解错”。
