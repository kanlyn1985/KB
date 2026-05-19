# 知识库优化任务清单落地分析

## 来源

外部任务清单：

`E:\chome download\hil_sim\knowledge_base_optimization_tasks.md`

本文档将外部优化项映射到当前项目现状，给出：

- 当前状态
- 差距判断
- 建议落点模块
- 实施优先级

---

## 一、总体判断

当前项目已经具备以下基础：

- 工作区、SQLite、文档构建链路已经完整
- PDF 多级解析与 OCR fallback 已具备
- evidence / facts / entities / wiki / graph 已打通
- retrieval / query_context / answer_query / agent_query 已成型
- demo 工作台与 HTTP API 已工程化
- 黄金测试生成与执行已具备

但相对于优化任务清单，当前系统仍属于：

- 有结构化中间层的单机知识库系统
- 但还未进入“检索策略精细化 + 评测体系完备化 + 诊断体系完备化”的第二阶段

也就是说：

- 第一阶段“能跑通”已经完成
- 第二阶段“能稳定召回、稳定回答、稳定评测”仍需系统性优化

---

## 二、逐项映射分析

## 1. 检索优化任务

### 1.1 建立多路召回

当前状态：

- 已有 `facts / evidence / wiki` 三类召回混合
- `query_api.py` 会展开到结构化上下文
- `graph` 与 `entity` 目前更多用于展示和后处理，不是独立召回通道

差距：

- 缺少显式的 retrieval router
- 缺少 document-level retrieval 独立通道
- 缺少统一的多路候选格式与融合层

建议模块：

- `query_rewrite.py`
- `retrieval_router.py`
- `candidate_fusion.py`

优先级：

- 高

### 1.2 新增 query rewrite 层

当前状态：

- 仅在 `answer_api.py` 中做了轻量规则化识别
- definition / standard 具备基础意图判断
- 没有统一输出的 rewrite schema

差距：

- 没有 `normalized_query / query_type / must_terms / should_terms / negative_terms`
- comparison / scope / constraint / no_answer_candidate 尚未正式建模

建议模块：

- `query_rewrite.py`

优先级：

- 最高

### 1.3 术语与标准号规范化

当前状态：

- 已支持 `GB/T / QC/T / ISO / IEC` 基础标准号归一化
- 已支持部分定义型问法归一化
- 已支持部分缩写类精确约束

差距：

- 中英术语互查不完整
- 缩写、标准号、术语别名没有统一规范化器
- 规则分散在 `answer_api.py / facts.py / retrieval.py`

建议模块：

- `normalizers.py` 或 `query_rewrite.py`

优先级：

- 高

### 1.4 同义词与别名扩展

当前状态：

- `synonyms.py` 已存在
- 已用于充电导引类召回增强

差距：

- 当前主要仍然偏手工
- 没有从 facts/wiki 自动回写别名
- 没有高频术语自动扩展

建议模块：

- 扩展 `synonyms.py`
- 新增 `alias_mining.py`

优先级：

- 高

### 1.5 引入 reranker

当前状态：

- 目前仅有规则加权排序
- 规则散布在 `retrieval.py` 与 `answer_api.py`

差距：

- 缺少独立 reranker
- 缺少排序解释输出
- 缺少 query type alignment / quality bonus / risk penalty 的统一融合

建议模块：

- `reranker.py`

优先级：

- 最高

### 1.6 建立 document-first 检索流程

当前状态：

- 某些问题在 `answer_api.py` 内有 primary doc 限定
- 但不是正式的两阶段检索

差距：

- 缺少明确的 document-first routing
- document retrieval 还不是显式召回通道

建议模块：

- `retrieval_router.py`
- `candidate_fusion.py`

优先级：

- 高

### 1.7 邻域扩展召回

当前状态：

- supporting evidence 选择时能间接带出部分上下文
- 但没有显式邻块扩展

差距：

- 缺少同页标题/前后块自动补全
- 缺少 doc metadata fact 自动邻域补充

建议模块：

- 扩展 `query_api.py`
- 新增 `neighbor_expansion.py`

优先级：

- 中高

### 1.8 保守召回策略

当前状态：

- 已对精确缩写做了一层 no-answer 保护
- 但策略还局部

差距：

- 缺少正式 `no_answer_candidate` 类型
- 缺少 query rewrite 与 retrieval 联动的保守模式

建议模块：

- `query_rewrite.py`
- `retrieval_router.py`
- `answer_policy.py`

优先级：

- 最高

---

## 2. 结构化知识层优化任务

### 2.1 扩展 fact 类型

当前状态：

- 已有 metadata / section / definition / abstract 相关 fact

差距：

- `scope_statement / requirement / prohibition / constraint / threshold / comparison_relation` 尚未建立

建议模块：

- `facts.py`
- `fact_extractors/`

优先级：

- 最高

### 2.2 强化术语定义抽取

当前状态：

- 已支持多种基础定义版式
- 已支持 `3.1 + term + definition` 结构

差距：

- 还缺跨页定义、多块聚合、注释结构、复杂双语结构
- 当前仍是单阶段规则抽取

建议模块：

- `fact_extractors/term_definitions.py`

优先级：

- 最高

### 2.3 标准类文档模板抽取器

当前状态：

- facts 中已有部分 cover / title / lifecycle / section 的模板能力

差距：

- 未拆分成标准化模板抽取器
- 范围、引用、术语、日期类模板还未系统化

建议模块：

- `fact_extractors/standard_cover.py`
- `fact_extractors/scope.py`
- `fact_extractors/references.py`

优先级：

- 高

### 2.4 facts 与 evidence 关联粒度

当前状态：

- 已能追溯到 page / evidence
- fact_evidence_map 已存在

差距：

- 还可继续细化到 block 粒度稳定追踪
- 部分 answer 仍偏 summary，不一定始终回 fact/evidence

建议模块：

- `facts.py`
- `answer_api.py`

优先级：

- 中高

### 2.5 wiki 反哺检索

当前状态：

- wiki 已进入检索
- 但 wiki 不会主动反向写 synonym / alias

差距：

- 缺少 wiki -> synonym / rewrite 的回写逻辑

建议模块：

- `wiki_compiler.py`
- `synonyms.py`
- `query_rewrite.py`

优先级：

- 高

### 2.6 graph 参与查询扩展

当前状态：

- graph 已构建
- answer 中会附带 related edges

差距：

- graph 不参与主召回
- 多跳扩展未建立

建议模块：

- `retrieval_router.py`
- `graph_expansion.py`

优先级：

- 中高

---

## 3. 回答层优化任务

### 3.1 建立回答策略树

当前状态：

- `answer_api.py` 中已有分支化逻辑

差距：

- 逻辑仍集中在一个文件内
- 缺少显式策略树/策略模块

建议模块：

- `answer_policy.py`

优先级：

- 最高

### 3.2 统一答案输出结构

当前状态：

- 已接近统一 schema

差距：

- 缺少 `answer_mode / confidence_score / related_candidates`

建议模块：

- `answer_api.py`

优先级：

- 高

### 3.3 引入置信度机制

当前状态：

- 目前只有事实/证据隐式 confidence

差距：

- 缺少 answer-level `confidence_score`

建议模块：

- `confidence.py`

优先级：

- 高

### 3.4 拒答机制

当前状态：

- 已有“没有找到足够的结构化结果”
- 已有局部 no-answer 防误召回

差距：

- 还没有正式 no-answer policy
- 没有“相关但不等价候选”的统一输出

建议模块：

- `answer_policy.py`

优先级：

- 最高

### 3.5 冲突检测

当前状态：

- 尚未系统实现

差距：

- 多文档冲突识别为空白

建议模块：

- `conflict_detector.py`

优先级：

- 中高

### 3.6 可解释输出

当前状态：

- 已经具备 supporting facts / evidence / warnings

差距：

- 还缺置信度说明与冲突说明

建议模块：

- `answer_api.py`
- `confidence.py`
- `conflict_detector.py`

优先级：

- 中高

---

## 4. 评测与回归优化任务

### 4.1 分类型 benchmark

当前状态：

- 已有 benchmark tests

差距：

- 还没有按 query_type 聚合统计

建议模块：

- `benchmark_dashboard.py`

优先级：

- 高

### 4.2 统一指标体系

当前状态：

- 已有 pass/fail 回归

差距：

- 缺少 recall / no-answer precision / hallucination rate 等体系化指标

建议模块：

- `benchmark_dashboard.py`

优先级：

- 高

### 4.3 扩展黄金测试集

当前状态：

- 已支持网络候选、本地回填、页覆盖、自动执行

差距：

- comparison / scope / constraint / negative sample / confusion set 还不充分

建议模块：

- `generated_tests.py`

优先级：

- 高

### 4.4 错例库

当前状态：

- 还没有独立错例库

差距：

- 失败样本无法累积管理

建议模块：

- `error_analysis.py`
- `knowledge_base/logs/`

优先级：

- 高

### 4.5 自动归因机制

当前状态：

- 尚未实现

差距：

- 缺少 parse_error / retrieval_miss / answer_policy_error 等自动分类

建议模块：

- `error_analysis.py`

优先级：

- 中高

### 4.6 版本对比评测

当前状态：

- 尚未实现

差距：

- 无法系统比较优化前后收益与回归

建议模块：

- `benchmark_dashboard.py`

优先级：

- 中高

---

## 5. 文档构建质量优化任务

### 5.1 文档质量诊断报表

当前状态：

- 已有 quality report 与 detail 接口

差距：

- 还没有系统级诊断报表
- 缺少结构完整度、可问答性指标

建议模块：

- `doc_diagnostics.py`

优先级：

- 高

### 5.2 completeness 检查

当前状态：

- 有零散检查

差距：

- 没有完整性 checklist

建议模块：

- `doc_diagnostics.py`

优先级：

- 高

### 5.3 异常文档识别

当前状态：

- 已有 OCR 异常检测、稀疏页检测

差距：

- 缺少 build warning 汇总层

建议模块：

- `quality.py`
- `doc_diagnostics.py`

优先级：

- 中高

### 5.4 结构层 coverage 指标

当前状态：

- 黄金测试覆盖已开始统计页覆盖

差距：

- facts coverage / definition coverage / scope coverage 还未系统化

建议模块：

- `doc_diagnostics.py`

优先级：

- 高

---

## 三、建议的实施顺序

## Phase 1：直接影响召回与回答

建议优先做：

1. `query_rewrite.py`
2. `retrieval_router.py`
3. `reranker.py`
4. `answer_policy.py`
5. `no_answer_candidate` 正式机制

这是最直接改善“问得对但召回偏”和“库里没有却乱答”的一组任务。

## Phase 2：直接影响知识质量

建议做：

1. 扩展 facts 类型
2. term_definition 两阶段抽取
3. 标准类模板抽取器
4. wiki -> synonym 反哺
5. graph 扩展召回

这是把“可检索”推进到“可稳定回答”的关键。

## Phase 3：评测与诊断闭环

建议做：

1. 错例库
2. 自动归因
3. benchmark dashboard
4. 文档诊断报表
5. 版本对比评测

这是把优化变成可持续工程流程的关键。

---

## 四、当前最值得先开的模块

如果现在立刻开始下一轮优化，建议优先新增：

- `src/enterprise_agent_kb/query_rewrite.py`
- `src/enterprise_agent_kb/retrieval_router.py`
- `src/enterprise_agent_kb/reranker.py`
- `src/enterprise_agent_kb/answer_policy.py`
- `src/enterprise_agent_kb/confidence.py`
- `src/enterprise_agent_kb/doc_diagnostics.py`

---

## 五、结论

外部任务清单里的大方向是对的，而且与当前项目阶段高度匹配。  
当前项目已经完成“系统骨架 + 主链路打通”，下一阶段最关键的不是再继续堆功能，而是把以下三件事系统化：

- 查询改写
- 多路召回与重排
- 回答策略与拒答机制

如果只从投资回报比来看，建议优先级最高的 5 项是：

1. 建立 `query_rewrite.py`
2. 建立 `retrieval_router.py`
3. 建立 `reranker.py`
4. 建立 `answer_policy.py`
5. 建立 `doc_diagnostics.py`

这 5 项完成后，当前系统会从“可运行知识库”明显提升到“可优化、可诊断、可持续迭代的知识库系统”。

