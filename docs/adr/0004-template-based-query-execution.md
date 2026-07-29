# 查询执行采用模板引擎而非 LLM 生成 SQL

用户查询经 LLM 理解为 QueryFrame（含 intent、target_entity、target_attributes），Core 根据 intent 选择预定义查询模板执行，返回结构化结果。LLM 不直接生成 SQL/SPARQL。

**为什么**：LLM 直接生成查询语句（Text-to-SQL 路线）有三个严重风险：
1. 安全性——LLM 可能生成注入或破坏性查询
2. 可靠性——LLM 生成的查询语法错误或逻辑错误不可预测
3. 可审计性——每次查询结果不可复现（LLM 可能生成不同查询）

模板引擎路线下，LLM 只做意图理解和参数提取（这是它擅长的），查询执行是确定性的预定义逻辑（这是必须可控的）。

**查询模板示例**：
```
intent: parameter_lookup
  → SELECT attributes WHERE entity_id = :target AND name IN (:target_attributes)

intent: relation_traversal
  → SELECT relations WHERE source = :source AND type = :relation_type

intent: hierarchy_traversal
  → recursive part_of traversal from :start_entity
```

**代价**：每种查询意图需要预置模板；模板覆盖范围外的查询类型需要扩展。但模板是确定性、可测试、可审计的。
