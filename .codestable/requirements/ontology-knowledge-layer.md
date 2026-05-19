---
doc_type: requirement
slug: ontology-knowledge-layer
pitch: 将 KB1 从证据约束知识工程系统逐步演进为具备本体约束、语义校验和有限推理能力的知识库。
status: current
last_reviewed: 2026-05-12
implemented_by:
  - architecture
  - query-chain-architecture
  - closed-loop-architecture
tags:
  - ontology
  - knowledge-graph
  - semantic-model
  - long-term-goal
---

# 本体论知识层

## 用户故事

- 作为知识库设计者，我希望 KB1 最终不只是保存 evidence、facts 和 graph edges，而是有清晰的概念类型、关系语义和约束规则。
- 作为查询使用者，我希望系统能理解 `OBC`、`CP`、`测试方法`、`参数`、`过程活动` 等对象的语义类型，而不是只靠关键词相似度。
- 作为维护者，我希望新增文档后能自动检查实体类型、关系类型、domain/range、证据形状是否一致，避免错误知识进入 graph 或答案链路。
- 作为评测者，我希望本体约束能进入召回、证据判定和回归测试，证明系统不是靠局部补丁回答问题。

## 为什么需要

KB1 当前已经具备轻量知识工程基础：`entities`、`facts`、`wiki_pages`、`graph_edges`、`source_units`、`evidence shape` 和五个质量闭环。但这些能力仍主要是工程结构，还没有形成正式的本体层。

如果没有本体目标，系统容易出现三类长期问题：

- 实体类型漂移：同一个概念可能被当作 term、parameter、component 或 process 混用。
- 关系语义不清：`related_to`、`has_process`、`defined_in` 等关系如果没有 domain/range，Graph 容易产生看似命中但不可回答的候选。
- 证据形状不稳定：definition、test_method、timing、process_activity 等知识形态如果没有结构 contract，后续召回和答案策略会继续依赖局部规则。

因此，KB1 的最终目标应明确为：在现有证据约束和闭环治理基础上，逐步建设 Pragmatic Ontology Layer，让知识对象、关系、证据形状、召回策略和答案约束共享同一套语义模型。

## 怎么解决

分阶段演进，不一次性引入重型 OWL/RDF 依赖。

### 阶段一：本体词表和类型体系

建立稳定 registry，定义核心类型：

- entity types：`standard`、`document`、`term`、`component`、`signal`、`state`、`parameter`、`test_method`、`process`、`activity`、`requirement`。
- knowledge types：`term_definition`、`parameter_meaning`、`test_method`、`timing`、`process_activity`、`state_transition`、`constraint`。
- evidence shapes：definition、parameter row、test procedure、timing table、process activity、state table。

### 阶段二：关系语义和约束

定义关系类型及 domain/range：

- `defines(term, definition_fact)`
- `has_parameter(component|system|standard, parameter)`
- `has_test_method(component|function|requirement, test_method)`
- `has_activity(process, activity)`
- `belongs_to_standard(entity, standard)`
- `measured_at(signal|parameter, test_point)`
- `has_condition(test_method|state_transition, condition)`
- `has_expected_observation(test_method, observation)`

Graph build、topic resolution、retrieval 和 evidence judge 都应复用这些约束，而不是各自维护临时规则。

### 阶段三：本体驱动的查询和证据判定

查询链路应使用本体层做三件事：

- Query understanding：把用户问题映射到 ontology type 和 expected evidence shape。
- Candidate constraint：召回和 rerank 候选必须满足类型和关系约束。
- Evidence judgement：judge 不只看文本相关性，还要校验证据形状和 ontology relation 是否匹配。

### 阶段四：一致性检查和回归

把 ontology checks 纳入派生状态治理闭环和回归闭环：

- workspace-doctor 能报告 entity type 冲突、关系 domain/range 违规、缺失必要证据形状。
- corpus eval 能按 ontology type 生成覆盖样例。
- failure analysis 能把失败归因为 ontology_missing、ontology_conflict、relation_constraint_violation 或 evidence_shape_gap。

## 成功标准

- 系统存在可版本化的 ontology registry，描述 entity types、relation types、knowledge types、evidence shapes 和约束。
- graph_edges 不再只是自由关系边，而是受 domain/range 约束。
- query rewrite / topic resolution / graph retrieval / evidence judge 共享 ontology 类型信息。
- 短缩写和多义词不靠人工逐个 registry 补丁，而能优先由 ontology type、上下文和关系约束生成澄清选项。
- workspace-doctor 能发现本体一致性问题。
- golden/corpus eval 能覆盖 ontology type 级别的召回和答案质量。

## 边界

- 当前阶段不要求一次性迁移到 OWL/RDF，不引入分布式图数据库。
- 本体层不能绕过 evidence/facts/source_units 的可追溯链路。
- 本体推理只能作为候选约束和解释增强，不能单独生成最终事实。
- 任何 ontology 推断进入答案前，仍必须经过 evidence judge 和候选 ID 约束。

